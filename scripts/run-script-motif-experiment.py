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
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--prompt', type=Path, default=ROOT / 'scenarios/paper-submission/reference-audit.prompt.md')
    parser.add_argument('--mode', choices=['baseline', 'shadow', 'execute'], required=True)
    parser.add_argument('--script-config', type=Path)
    parser.add_argument('--learning-store', type=Path)
    parser.add_argument('--user-id', default='script-motif-experiment')
    parser.add_argument('--port', type=int, default=3230)
    parser.add_argument('--budget-usd', type=float, default=1.0, help='单任务/本次启动共用额度；0 仅用于已有无限额授权')
    parser.add_argument('--max-output-tokens', type=int, default=8000)
    args = parser.parse_args()
    if args.budget_usd < 0 or args.max_output_tokens < 1:
        parser.error('预算非负，输出上限必须为正数')
    if (args.mode == 'baseline') != (args.script_config is None):
        parser.error('baseline 不加载 Script Motif；shadow/execute 必须提供 --script-config')
    env = dict(os.environ)
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
               '--max-output-tokens', str(args.max_output_tokens)]
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
            draft = web.api(opener, base, {'action': 'preview', 'session_id': session,
                'request': {'instruction': prompt, 'scene_options': {'allow_output': True}}})
            draft = web.api(opener, base, {'action': 'upload', 'task_id': draft['task_id'],
                'name': source.name, 'data': base64.b64encode(source.read_bytes()).decode()})
            (record / 'task-id.txt').write_text(draft['task_id'])
            web.submit(opener, base, draft)
            while True:
                result = web.api(opener, base, task_id=draft['task_id'])
                (record / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
                if result['status'] in ('completed', 'failed', 'cancelled', 'budget_exhausted') and not result.get('stats', {}).get('active'):
                    break
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
