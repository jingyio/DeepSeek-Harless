#!/usr/bin/env python3
"""用原生 Web API 跑一项真实 Paper 任务；所有原始记录只写入 .local。"""
import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    started = time.monotonic()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--real-model', action='store_true', required=True)
    parser.add_argument('--report-evidence',action='store_true',help='显式隔离导出变体，两组必须采用相同设置')
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--prompt', type=Path, default=ROOT / 'scenarios/paper-submission/reference-audit.prompt.md')
    parser.add_argument('--mode', choices=['baseline', 'cache', 'shadow', 'execute'], required=True)
    parser.add_argument('--script-config', type=Path)
    parser.add_argument('--learning-store', type=Path)
    parser.add_argument('--user-id', default='script-motif-experiment')
    parser.add_argument('--port', type=int, default=3230)
    parser.add_argument('--budget-usd', type=float, default=1.0, help='单任务/本次启动共用额度；0 仅用于已有无限额授权')
    parser.add_argument('--max-output-tokens', type=int, default=8000)
    parser.add_argument('--recovery-checkpoint', type=Path,
                        help='显式局部恢复诊断：只复制私有历史草稿，不算完整论文评测')
    parser.add_argument('--preserve-recovery-structure',action='store_true',help='将当前恢复目标的完整结构写入受保护任务状态，允许叶子修订，拒绝子集交付')
    parser.add_argument('--resume-current-operation',action='store_true',help='显式选择以当前完整参数恢复一次原生操作；Runtime核验当前任务授权后先执行，失败即交回模型')
    parser.add_argument('--recovery-goal-scope',type=Path,help='真实失败回执绑定的原完整目标；与失败候选参数分离，必须匹配旧回执的scope SHA')
    parser.add_argument('--reuse-checkpoint', type=Path,
                        help='真实历史原生调用与失败回执；复制为当前同来源任务的数据，单独统计局部恢复')
    parser.add_argument('--max-seconds', type=float, help='诊断超时取消；保留全部费用，不算正常完成')
    args = parser.parse_args()
    if args.preserve_recovery_structure and not args.reuse_checkpoint:
        parser.error('结构保留需要显式当前恢复目标 --reuse-checkpoint')
    if args.resume_current_operation and (not args.preserve_recovery_structure or args.mode!='execute'):
        parser.error('恢复当前操作需要execute及显式受保护的完整恢复目标')
    if args.recovery_goal_scope and not args.preserve_recovery_structure:parser.error('独立完整目标需要preserve-recovery-structure')
    if args.budget_usd < 0 or args.max_output_tokens < 1:
        parser.error('预算非负，输出上限必须为正数')
    if args.max_seconds is not None and args.max_seconds <= 0:
        parser.error('诊断超时必须为正数')
    if (args.mode == 'baseline') != (args.script_config is None):
        parser.error('baseline 不加载 Script Motif；cache/shadow/execute 必须提供 --script-config')
    env = dict(os.environ)
    env['SSS_REUSE_TRACE'] = '1'
    env.pop('SSS_SCRIPT_MOTIF_CONFIG', None)
    env.pop('SSS_SCRIPT_MOTIF_LEARNING_STORE', None)
    if args.script_config:
        config = json.loads(args.script_config.read_text())
        if config['mode'] != args.mode:
            parser.error('sidecar mode 与实验模式不一致')
        env['SSS_SCRIPT_MOTIF_CONFIG'] = str(args.script_config.resolve())
    if args.learning_store:
        env['SSS_SCRIPT_MOTIF_LEARNING_STORE'] = str(args.learning_store.resolve())
    source = args.source.resolve(strict=True)
    checkpoint = None
    reuse_checkpoint = None
    if args.reuse_checkpoint:
        if args.recovery_checkpoint:
            parser.error('两种恢复入口不能合用')
        path = args.reuse_checkpoint.resolve(strict=True)
        if not path.is_relative_to(ROOT / '.local'):
            parser.error('复用恢复仅接受本 worktree 私有轨迹')
        reuse_checkpoint = path.read_bytes()
    recovery_goal=None
    if args.recovery_goal_scope:
        path=args.recovery_goal_scope.resolve(strict=True)
        if not path.is_relative_to(ROOT/'.local'):raise ValueError('private_recovery_goal_required')
        raw=path.read_bytes();previous=json.loads(reuse_checkpoint)
        if previous.get('failure',{}).get('execution_evidence',{}).get('recovery_scope_sha256')!=hashlib.sha256(raw).hexdigest():raise ValueError('recovery_goal_not_bound_to_real_failure')
        recovery_goal=json.loads(raw)
    if args.recovery_checkpoint:
        checkpoint_path = args.recovery_checkpoint.resolve(strict=True)
        if not checkpoint_path.is_relative_to(ROOT / '.local'):
            parser.error('恢复诊断只接纳本 worktree 的私有历史草稿')
        checkpoint = checkpoint_path.read_bytes()
    prompt = args.prompt.read_text()
    run_id = uuid4().hex
    record = ROOT / '.local/script-motif-experiments' / run_id
    record.mkdir(parents=True, exist_ok=False, mode=0o700)
    output = ROOT / '.local/web/runs' / run_id
    manifest = {
        'run_id': run_id, 'mode': args.mode,
        'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
        'cap_usd': args.budget_usd or None, 'reset_history': False,
        'budget_policy': 'uncapped_user_authorized' if args.budget_usd == 0 else 'bounded',
        'request_limit': None, 'max_output_tokens': args.max_output_tokens,
        'reasoning_effort': 'off', 'platform': sys.platform,
        'evaluation_scope': 'historical_artifact_recovery' if reuse_checkpoint else 'historical_local_recovery' if checkpoint else 'full_task',
        'checkpoint_sha256': hashlib.sha256(reuse_checkpoint or checkpoint).hexdigest() if reuse_checkpoint or checkpoint else None,
        'max_seconds': args.max_seconds,
        'reuse_boundary_evidence': True,
        'report_evidence_variant': args.report_evidence,
        'preserve_recovery_structure': args.preserve_recovery_structure,
        'resume_current_operation': args.resume_current_operation,
        'recovery_goal_scope_sha256':hashlib.sha256(args.recovery_goal_scope.read_bytes()).hexdigest() if args.recovery_goal_scope else None,
        'local_script_sandbox_requested': env.get('SSS_LOCAL_SCRIPT_EXPERIMENT') == '1',
        'report_font_sha256': hashlib.sha256(Path(env['HARLESS_REPORT_FONT']).read_bytes()).hexdigest() if env.get('HARLESS_REPORT_FONT') and Path(env['HARLESS_REPORT_FONT']).is_file() else None,
    }
    (record / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    files = subprocess.check_output(['git', 'ls-files', '-co', '--exclude-standard'], cwd=ROOT, text=True).splitlines()
    snapshot = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                for name in sorted(set(files)) if (ROOT / name).is_file()}
    (record / 'source-snapshot.json').write_text(json.dumps(snapshot, indent=2))
    scenes = load('script_experiment_scenes', 'check-harless-scenes.py')
    web = scenes.web
    command = [sys.executable, str(ROOT / 'scripts/script-motif-web.py'), '--real-model',
               '--port', str(args.port), '--run-id', run_id, '--user-id', args.user_id,
               '--budget-usd', str(args.budget_usd), '--run-budget-usd', str(args.budget_usd),
               '--request-limit', '0', '--run-request-limit', '0',
               '--script-max-output-tokens', str(args.max_output_tokens)]
    if args.report_evidence:command.append('--report-evidence')
    print(json.dumps({'record': str(record), **manifest}, ensure_ascii=False), flush=True)
    with (record / 'web.log').open('w') as log:
        child = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            for _ in range(1200):
                if (output / 'access-url.txt').exists():
                    break
                if child.poll() is not None:
                    raise RuntimeError('启动失败；检查本轮私有 web.log')
                time.sleep(.1)
            else:
                raise TimeoutError('Web 启动超时')
            opener = web.client()
            base = 'http://127.0.0.1:' + str(args.port)
            opener.open((output / 'access-url.txt').read_text().strip()).close()
            session = scenes.settings(opener, base, {'action': 'new_session', 'selection': {
                'scene': 'paper-proofreading', 'mode': 'baseline', 'rsi': False}})['session_id']
            if source.stat().st_size > 256 * 1024:
                # Reuse Harness authenticated streamed intake rather than the
                # legacy diagnostic JSON upload's 256 KiB envelope. Preserve
                # the original file bytes and normal session receipt binding.
                upload_url = base + '/api/session/uploadFileBinary?' + urllib.parse.urlencode({
                    'sessionId': session, 'name': source.name})
                request = urllib.request.Request(upload_url, data=source.read_bytes(),
                    headers={'Origin': base, 'Content-Type': 'application/octet-stream'})
                with opener.open(request, timeout=120) as response:
                    uploaded = json.load(response)
                if not uploaded.get('ok'):
                    raise RuntimeError({'native_upload_failed': uploaded.get('error')})
                (record / 'upload-receipt.json').write_text(json.dumps(uploaded, ensure_ascii=False, indent=2))
                draft = web.api(opener, base, {'action': 'preview', 'session_id': session,
                    'request': {'content': [{'type': 'text', 'text': prompt},
                        {'type': 'file', 'receiptId': uploaded['value']['receiptId']}],
                        'scene_options': {'allow_output': True}}})
            else:
                draft = web.api(opener, base, {'action': 'preview', 'session_id': session,
                    'request': {'instruction': prompt, 'scene_options': {'allow_output': True}}})
                draft = web.api(opener, base, {'action': 'upload', 'task_id': draft['task_id'],
                    'name': source.name, 'data': base64.b64encode(source.read_bytes()).decode()})
            (record / 'task-id.txt').write_text(draft['task_id'])
            if reuse_checkpoint:
                effective = json.loads((output / 'tasks' / draft['task_id'] / 'effective-config.json').read_text())
                workspace = Path(effective['workspace']).resolve(strict=True)
                value = json.loads(reuse_checkpoint)
                current_sources = json.loads((workspace / 'approved-inputs.json').read_text())['files']
                if not workspace.is_relative_to(output.resolve()) or value.get('arguments', {}).get('source_versions') != current_sources:
                    raise ValueError('reuse_recovery_source_version_mismatch')
                (workspace / 'code').mkdir(exist_ok=True, mode=0o700)
                recovered = workspace / 'code' / 'recovery-state.json'
                recovered.write_bytes(reuse_checkpoint); recovered.chmod(0o600)
                if args.preserve_recovery_structure:
                    goal_arguments=recovery_goal['arguments'] if recovery_goal else value['arguments']
                    if goal_arguments.get('source_versions')!=current_sources:raise ValueError('recovery_goal_sources_changed')
                    scope = {'version':1,'kind':'current_review_recovery_scope','task_id':draft['task_id'],
                             'source_versions':current_sources,'arguments':goal_arguments,
                             'policy':'preserve_structure_allow_semantic_leaf_revisions',
                             'origin':'explicit_current_recovery_requirement_not_inferred_from_history'}
                    if args.resume_current_operation:
                        from src.adapters.script_motif_compiler import digest
                        scope['execution_obligation']={'kind':'resume_current_operation','tool':value['tool'],
                            'arguments_sha256':digest(value['arguments']),'max_attempts':1}
                        if recovery_goal:
                            scope['resume_arguments']=value['arguments'];scope['execution_obligation']['arguments_pointer']='/resume_arguments'
                    target=workspace/'review-recovery-scope.json'
                    target.write_text(json.dumps(scope,ensure_ascii=False,sort_keys=True));target.chmod(0o400)
            if checkpoint:
                effective = json.loads((output / 'tasks' / draft['task_id'] / 'effective-config.json').read_text())
                workspace = Path(effective['workspace']).resolve(strict=True)
                if not workspace.is_relative_to(output.resolve()):
                    raise ValueError('recovery_workspace_outside_owned_run')
                restored = json.loads(checkpoint)
                current_sources = json.loads((workspace / 'approved-inputs.json').read_text())['files']
                if restored['source_versions'] != current_sources:
                    raise ValueError('recovery_source_version_mismatch')
                restored['task_id'] = draft['task_id']
                target = workspace / 'outputs' / 'paper-audits' / draft['task_id']
                target.mkdir(parents=True, exist_ok=False, mode=0o700)
                restored_raw = (json.dumps(restored, ensure_ascii=False, indent=2) + '\n').encode()
                (target / 'draft.json').write_bytes(restored_raw)
                (target / 'draft.json').chmod(0o600)
                hint = {'evaluation_scope': 'historical_local_recovery_not_full_task',
                        'draft_sha256': hashlib.sha256(restored_raw).hexdigest(),
                        'reference_count': len(restored['report']['references']),
                        'source_count': len(restored['report']['sources']),
                        'original_checkpoint_sha256': hashlib.sha256(checkpoint).hexdigest(),
                        'source_versions': current_sources}
                (workspace / 'code').mkdir(exist_ok=True, mode=0o700)
                (workspace / 'code' / 'recovery-state.json').write_text(json.dumps(hint, ensure_ascii=False))
                (workspace / 'code' / 'recovery-state.json').chmod(0o600)
            web.submit(opener, base, draft)
            submitted = time.monotonic()
            cancelled = False
            while True:
                result = web.api(opener, base, task_id=draft['task_id'])
                (record / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
                if result['status'] in ('completed', 'failed', 'cancelled', 'budget_exhausted') and not result.get('stats', {}).get('active'):
                    break
                if args.max_seconds and not cancelled and time.monotonic() - submitted > args.max_seconds:
                    web.api(opener, base, {'action': 'cancel', 'task_id': draft['task_id']})
                    cancelled = True
                time.sleep(3)
            task = output / 'tasks' / draft['task_id']
            if args.learning_store and result['status'] == 'completed':
                for _ in range(300):
                    if (task / 'script-learning-status.json').exists():
                        break
                    time.sleep(.2)
            summary = load('script_experiment_accounting', 'summarize-script-motif-run.py').summarize(task)
            summary['experiment_wall_ms_until_summary'] = round((time.monotonic() - started) * 1000)
            summary['wall_scope'] = 'includes_startup_upload_and_learning_wait; excludes_installation_and_shutdown'
            (record / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
            print(json.dumps(summary, ensure_ascii=False), flush=True)
        finally:
            if child.poll() is None:
                child.send_signal(signal.SIGTERM)
            try:
                child.wait(timeout=20)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == '__main__':
    main()
