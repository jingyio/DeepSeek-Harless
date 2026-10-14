"""Evidence preparation entry; reuse the public Harness/budget runner, never add an Agent loop."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from http.server import ThreadingHTTPServer
from uuid import uuid4
from mcp.server.mcpserver.exceptions import ToolError

from pdf_tools import DEFAULT_QUESTION, ROOT, digest, save_private
from pdf_evidence_tools import EvidenceScene, PREFIX, continuation_policy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def module(filename, name):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def prepare_task(directory, question, *, cache_policy='reuse', mode='baseline', script_chain=False,
                 model_call_enabled=False, frozen_plan=None, tool_presentation='native'):
    base = module('run-pdf.py', 'evidence_pdf_entry')
    output, env = base.prepare_task(directory, question, cache_policy=cache_policy)
    scenario = json.loads((HERE / 'pdf-evidence-scenario.json').read_text())
    prompt = output / 'prompt.md'
    prompt_text = ((HERE / 'pdf-evidence-task.md').read_text()
                   + '\n本次研究问题：\n' + question.strip() + '\n')
    prompt.write_text(prompt_text, encoding='utf-8')
    prompt.chmod(0o600)
    scenario['prompt'] = str(prompt)
    save_private(output / 'scenario.json', scenario)
    env.pop('SSS_PDF_SCRIPT_READ', None)
    env['SSS_EVIDENCE_SCRIPT_CHAIN'] = '1' if script_chain else '0'
    task = json.loads((output / 'task.json').read_text())
    scene = EvidenceScene(directory, Path(env['SSS_PDF_CACHE']), task,
                          delivery=Path(env['SSS_PDF_DELIVERY']), cache_policy=cache_policy)
    if frozen_plan is not None:
        scene._assert_current()
        frozen_plan = scene._plan(json.dumps(frozen_plan, ensure_ascii=False))
        if frozen_plan['allow_deterministic_continuation'] is not True:
            raise ValueError('frozen comparison requires an explicitly approved plan')
        prompt_text += ('\n本次是已批准计划的机械执行对照。下面的计划是固定任务输入，'
                        '不得修改窗口、purpose 或重新选择页面。先 list_pdfs 核对任务，'
                        '然后 register_reading_plan 登记原样计划，使用 plan_id 提取；'
                        '若工具尚未完成后续校验与组装，再调用相应工具。'
                        '本次不需要 prepare_pdf 或 search_pdf_text 重新选页。'
                        '以成功的证据包工具收据为交付，最后只简短报告状态，不生成论文结论。\n'
                        + '\n统一效率要求（所有对照组相同）：尽可能减少模型往返。独立工具可批量调用，依赖参数应来自实际成功结果。'
                          '若提供 run_code，请优先在同一程序中完成 list_pdfs → register_reading_plan → extract_evidence_windows → verify_evidence_windows → build_evidence_packet，'
                          '局部解析实际MCP返回值，遇到isError立即停止或显式恢复，仅输出最终收据状态/摘要，完整原文包由入口保存。'
                          '没有run_code时使用允许的MCP；若extract已返回packet_ready，不再重复校验/组装。本任务不提供代码模板，程序由模型自行生成。\n'
                        + json.dumps(frozen_plan, ensure_ascii=False, sort_keys=True) + '\n')
        prompt.write_text(prompt_text, encoding='utf-8')
    snapshot = json.loads((output / 'input-snapshot.json').read_text())
    snapshot.update(scope='evidence_preparation_only', execution_version_sha256=scene.execution_version,
                    execution_options={'mode': mode, 'script_chain': script_chain,
                                       'model_call_enabled': model_call_enabled, 'tool_presentation': tool_presentation})
    if frozen_plan is not None:
        snapshot.update(frozen_plan=frozen_plan, frozen_plan_sha256=digest(frozen_plan))
    shared_files = ['src/motif_core/approved_plan_continuation.ts',
                    'src/motif_core/approved_plan_continuation.generated.mjs',
                    'src/motif_core/online_skill_runtime.mjs', 'src/adapters/dsh_online_motif.mjs',
                    'src/motif_core/offline/continuation_policy.py',
                    'src/motif_core/offline/chain_compiler.py', 'src/motif_core/offline/edge_compiler.py',
                    'src/motif_core/offline/trace_compiler.py', 'src/adapters/dsh_trajectory.py',
                    'src/adapters/tool_contract_loader.py', 'src/adapters/tool_schema_contracts.py',
                    'scripts/export-online-motif-manifest.py', 'scripts/prepare-online-motif.py']
    snapshot['continuation_protocol'] = {'online_manifest_schema_version': 2,
        'policy_sha256': digest(continuation_policy()), 'allowed_steps': continuation_policy()['steps'],
        'code_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in shared_files}}
    save_private(output / 'input-snapshot.json', snapshot)
    return output, env


def collect_packet(run, task_directory):
    from src.adapters.dsh_trajectory import extract_dsh_trace, infer_dsh_provenance
    from src.adapters.tool_contract_loader import parse_tool_contracts
    snapshot = json.loads((task_directory / 'input-snapshot.json').read_text())
    save_private(run / 'evidence-input-snapshot.json', snapshot)
    events_path = run / 'agent-events.jsonl'
    if not events_path.is_file():
        result = {'status': 'missing_packet', 'reason': 'no_original_events'}
    else:
        contracts = parse_tool_contracts(json.loads((HERE / 'pdf-evidence-contracts.json').read_text()))
        events = [json.loads(line) for line in events_path.read_text().splitlines()]
        if snapshot['execution_options'].get('tool_presentation') == 'ptc':
            from src.adapters.dsh_event_projection import project_ptc_dispatches
            events = project_ptc_dispatches(events)
            save_private(run / 'ptc-analysis-projection.json', {'scope': 'derived analysis, not original events or model decisions', 'events': events})
        trace = extract_dsh_trace(events, contracts, trace_id=run.name,
                                 provenance_by_call_id=infer_dsh_provenance(events, contracts))
        ready = []
        for record in trace.records:
            if not record.observation:
                continue
            value = record.observation
            if record.name == PREFIX + 'extract_evidence_windows':
                value = value.get('script_packet', {})
            elif record.name != PREFIX + 'build_evidence_packet':
                continue
            if value.get('status') == 'packet_ready':
                ready.append(value)
        if not ready:
            result = {'status': 'missing_packet', 'reason': 'no_successful_verified_packet_tool'}
        else:
            receipt = ready[-1]
            artifact = Path(receipt['artifact'])
            if artifact.is_symlink() or artifact.resolve().parent != (task_directory / 'delivery').resolve():
                raise ValueError('untrusted evidence packet location')
            packet = json.loads(artifact.read_text())
            if (digest(packet) != receipt['artifact_sha256'] or receipt.get('packet') != packet
                    or receipt['execution_version_sha256'] != snapshot['execution_version_sha256']):
                raise ValueError('packet content or receipt version mismatch')
            scene = EvidenceScene(Path(snapshot['task']['sources']['root']), task_directory / 'collect-cache',
                                  snapshot['task'], delivery=task_directory / 'collection')
            scene.validate_packet(packet)
            if 'frozen_plan' in snapshot and packet['plan'] != snapshot['frozen_plan']:
                raise ValueError('delivered plan differs from frozen comparison input')
            save_private(run / 'evidence-packet.json', packet)
            save_private(run / 'evidence-packet-receipt.json', receipt)
            result = {'status': 'packet_ready', 'window_count': len(packet['windows']),
                      'source_checks': 'exact_current_source_replay', 'research_quality': 'unreviewed',
                      'claim_support_assessed': False, 'packet': str(run / 'evidence-packet.json')}
    save_private(run / 'evidence-delivery.json', result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--papers-dir', type=Path, default=ROOT / 'testpdf')
    parser.add_argument('--question', default=DEFAULT_QUESTION)
    parser.add_argument('--cache-policy', choices=['reuse', 'off'], default='reuse')
    parser.add_argument('--budget-usd', type=float, default=0.25)
    parser.add_argument('--max-output', type=int, default=3000)
    parser.add_argument('--max-steps', type=int, default=24)
    parser.add_argument('--call-model', action='store_true')
    parser.add_argument('--script-chain', action='store_true')
    parser.add_argument('--tool-presentation', choices=['native', 'ptc'], default='native')
    parser.add_argument('--mode', choices=['baseline', 'shadow', 'execute'], default='baseline')
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--frozen-plan', type=Path, help='private approved plan JSON; compare continuation only')
    args = parser.parse_args(argv)
    if (not 0 < args.budget_usd <= 100 or not 1 <= args.max_output <= 8000
            or not 1 <= args.max_steps <= 100):
        parser.error('invalid budget/step/output limits')
    if args.tool_presentation == 'ptc' and (args.mode != 'baseline' or args.script_chain):
        parser.error('Code Mode baseline is separate from script/Motif modes')
    if args.script_chain and args.mode != 'baseline':
        parser.error('ordinary script comparison requires baseline mode')
    if (args.mode != 'baseline') != bool(args.manifest):
        parser.error('manifest is required exactly for shadow/execute mode')
    try:
        frozen_plan = None
        if args.frozen_plan:
            from pdf_dependencies import private_file
            path = private_file(args.frozen_plan)
            if path.stat().st_size > 16000:
                raise ValueError('frozen plan exceeds bounded plan size')
            frozen_plan = json.loads(path.read_text())
        output, env = prepare_task(args.papers_dir, args.question, cache_policy=args.cache_policy,
                                  mode=args.mode, script_chain=args.script_chain,
                                  model_call_enabled=args.call_model, frozen_plan=frozen_plan, tool_presentation=args.tool_presentation)
    except (ValueError, OSError, ToolError) as exc:
        parser.error(str(exc))
    snapshot = json.loads((output / 'input-snapshot.json').read_text())
    snapshot['execution_options'].update(budget_cap_usd=args.budget_usd, max_steps=args.max_steps,
                                         max_output=args.max_output,
                                         manifest_digest=json.loads(args.manifest.read_text())['manifest_digest'] if args.manifest else None)
    save_private(output / 'input-snapshot.json', snapshot)
    child_env = {**os.environ, **env}
    if args.call_model:
        key = module('run-live.py', 'evidence_key')
        try:
            child_env['DEEPSEEK_API_KEY'] = key.load_key(key.KEY_FILE, child_env)
        except ValueError as exc:
            parser.error(str(exc))
    command = [sys.executable, str(ROOT / 'scripts/run-scenario.py'), '--scenario', str(output / 'scenario.json'),
               '--mode', args.mode, '--budget-usd', str(args.budget_usd), '--max-output', str(args.max_output),
               '--max-steps', str(args.max_steps), '--tool-presentation', args.tool_presentation]
    if args.call_model:
        command.append('--call-model')
    server = worker = None
    if args.mode != 'baseline':
        save_private(output / 'motif-task.json', {'schema_version': 1, 'task_id': output.name,
                     'session_id': 'evidence-' + uuid4().hex, 'intent': args.question,
                     'input_version': digest(snapshot['task']), 'bindings': {},
                     'continuation_policy_digests': [digest(continuation_policy())],
                     'source_versions': {PREFIX + name: [snapshot['execution_version_sha256']] for name in
                                         ('extract_evidence_windows', 'verify_evidence_windows', 'build_evidence_packet')}})
        handler = module('compare-pdf.py', 'evidence_closed_reads').ClosedReadOnly
        handler.calls = 0
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        command += ['--manifest', str(args.manifest), '--task', str(output / 'motif-task.json'),
                    '--embedding-endpoint', f'http://127.0.0.1:{server.server_port}/v1/embeddings',
                    '--embedding-model', 'disabled-closed-source-proof-only']
    print(json.dumps({'task_directory': str(output), 'scope': 'evidence_preparation_only',
                      'mode': args.mode, 'script_chain': args.script_chain, 'model_call_enabled': args.call_model,
                      'budget_cap_usd': args.budget_usd, 'research_quality': 'unreviewed'}, ensure_ascii=False), flush=True)
    try:
        result = subprocess.run(command, cwd=ROOT, env=child_env, text=True, capture_output=True)
        print(result.stdout, end='', flush=True)
        if result.stderr:
            print(result.stderr, file=sys.stderr, end='')
        if not args.call_model:
            return result.returncode
        summaries = []
        for line in result.stdout.splitlines():
            try:
                value = json.loads(line)
                if isinstance(value, dict) and 'output_dir' in value:
                    summaries.append(value)
            except ValueError:
                pass
        if not summaries:
            save_private(output / 'run-series.json', {'status': 'missing_runner_summary', 'exit_code': result.returncode,
                                                     'cost_complete': False})
            return result.returncode or 2
        summary = summaries[-1]
        run = Path(summary['output_dir']).resolve()
        if not run.is_relative_to(ROOT / '.local/runs'):
            raise ValueError('unexpected shared runner output directory')
        try:
            delivery = collect_packet(run, output)
        except Exception as exc:
            delivery = {'status': 'packet_collection_failed', 'error_type': type(exc).__name__}
            save_private(run / 'evidence-delivery.json', delivery)
        save_private(output / 'run-series.json', {'attempts': [summary], 'delivery': delivery,
                     'embedding_requests': handler.calls if server else 0, 'retry_count': 0,
                     'scope': 'source preparation, not complete scientific delivery'})
        print(json.dumps({'evidence_delivery': delivery}, ensure_ascii=False), flush=True)
        return result.returncode or (0 if delivery['status'] == 'packet_ready' else 2)
    finally:
        if server:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)


if __name__ == '__main__':
    raise SystemExit(main())
