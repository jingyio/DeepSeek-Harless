#!/usr/bin/env python3
"""Isolated official Harness Web, mock-only. SDK entry is unchanged."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
import os
import platform
import re
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.scenario import prepare_scenario
from src.adapters.deepseek_cost_gate import State, create_server


def save(path, value):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.chmod(0o600)
    temporary.replace(path)


def fixture_module():
    spec = importlib.util.spec_from_file_location('sss_public_fixture', ROOT / 'scripts/motif-example.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def demo_action(values, _event):
    for object_id in ('note:alpha', 'note:beta'):
        rows = [row for row in values if row.get('object_id') == object_id]
        pins = [row for row in rows if 'source_id' in row]
        reads = [row for row in rows if 'text' in row]
        if not pins:
            return 'mcp__demo__pin_note', {'object_id': object_id}
        if not reads:
            return 'mcp__demo__read_pinned_note', {'source_id': pins[-1]['source_id']}
    return None, {'answer': '两次试验的种子数与评测协议不同；还缺同协议下的独立复现实验。',
                  'sources': [{key: row[key] for key in ('object_id', 'source_id', 'version_sha256')}
                              for row in values if 'text' in row]}


def prepare(args, output, endpoint):
    public = json.loads((ROOT / 'config/harness-web.json').read_text())
    scenario = ROOT / f'scenarios/{args.scenario}/scenario.json'
    prepared = prepare_scenario(scenario, case='l_retrieval_persistence' if args.scenario == 'portfolio-v1' else '')
    preset = output / 'presets/sss-task'
    preset.mkdir(parents=True, mode=0o700)
    rows = [{'id': 'sss-persona', 'name': '@deepseek-ai/dsh-persona', 'config': {
        'prefix': 'Complete the bounded task using only the permitted MCP evidence.',
        'suffix': 'Cite source IDs and versions. Do not invent evidence or perform writes.'}}, *prepared['mcp_rows']]
    rendered = json.dumps(rows, ensure_ascii=False, indent=2)
    for token, expression in prepared['environment_references'].items():
        rendered = rendered.replace(json.dumps(token), expression)
    (preset / 'agent.cordis.yml').write_text(rendered)
    (preset / 'agent.cordis.yml').chmod(0o600)
    save(preset / 'preset.yml', {'name': f'SSS {prepared["name"]} / {args.mode}（免费模拟）'})
    canonical_prompt_sha = hashlib.sha256(prepared['prompt'].strip().encode()).hexdigest()
    policy = {'output': str(output), 'prompt_sha256': canonical_prompt_sha,
              'allowed_tools': prepared['allowed_tools'], 'endpoint': endpoint,
              'max_output_tokens': public['max_output_tokens'], 'mode': args.mode,
              'embedding_endpoint': args.embedding_endpoint,
              'fixture': args.fixture}
    if args.mode != 'baseline':
        bundle = ROOT / 'examples/motif-library/research-portfolio-v1'
        task = json.loads((bundle / 'task.json').read_text())
        if args.fixture == 'stale':
            task['source_versions'] = {key: '0' * 64 for key in task['source_versions']}
        save(output / 'task.json', task)
        policy.update(manifest=str(bundle / 'online-manifest.json'), task=str(output / 'task.json'))
    save(output / 'policy.json', policy)
    disabled = ['llm-deepseek', 'llm-pi-ai', 'session-title-llm', 'llm-retry',
                'compaction-basic', 'command-compact', 'session-log-deepseek']
    patch = [{'id': name, 'disabled': True} for name in disabled]
    patch += [{'id': 'agent-presets', 'config': {'default': 'sss-task',
        'includeShippedRoot': False, 'includeUserRoot': False,
        'roots': [{'path': str(output / 'presets'), 'trust': 'system'}]}},
        {'insert': [{'id': 'sss-web-policy', 'name': (ROOT / 'src/adapters/dsh_web_policy.ts').as_uri()}]}]
    save(output / 'host.patch.yml', patch)
    (output / 'prompt.md').write_text(prepared['prompt']); (output / 'prompt.md').chmod(0o600)
    snapshot = {**public, 'mode': args.mode, 'scenario': args.scenario,
                'budget_usd': args.budget_usd, 'request_limit': args.request_limit,
                'prompt_sha256': canonical_prompt_sha, 'raw_prompt_sha256': prepared['prompt_sha256'],
                'prompt_normalization': 'outer whitespace only (official composer trim)',
                'scenario_sha256': prepared['config_sha256'],
                'allowed_tools': prepared['allowed_tools'], 'tools_order': sorted(prepared['allowed_tools']),
                'fixture': args.fixture,
                'case': prepared['case'], 'embedding_model': 'fixture-vectors-not-a-semantic-model',
                'dsh_version': '0.1.5-rc.3', 'python_version': sys.version.split()[0],
                'node_version': subprocess.check_output(['node', '--version'], text=True).strip(),
                'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'dirty_files': subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).splitlines(),
                'output': str(output), 'paid_calls': 0}
    snapshot.update(task_id=output.name, platform=platform.platform(),
        motif_min_similarity=0.8, motif_min_margin=0.1, disabled_host_plugins=disabled,
        git_diff_sha256=hashlib.sha256(subprocess.check_output(['git', 'diff', '--binary'], cwd=ROOT)).hexdigest())
    snapshot['host_patch_sha256'] = hashlib.sha256((output / 'host.patch.yml').read_bytes()).hexdigest()
    snapshot['files_sha256'] = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in [scenario, ROOT / 'config/harness-web.json', ROOT / 'src/adapters/dsh_web_policy.ts',
                     ROOT / 'src/adapters/deepseek_cost_gate.py', ROOT / 'scripts/harness-web.py']}
    if args.mode != 'baseline':
        snapshot['manifest_sha256'] = hashlib.sha256(Path(policy['manifest']).read_bytes()).hexdigest()
        snapshot['task_sha256'] = hashlib.sha256(Path(policy['task']).read_bytes()).hexdigest()
    save(output / 'effective-config.json', snapshot)
    return public


def main():
    defaults = json.loads((ROOT / 'config/harness-web.json').read_text())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', choices=['example', 'portfolio-v1'], default='example')
    parser.add_argument('--mode', choices=['baseline', 'shadow', 'execute'], default='baseline')
    parser.add_argument('--port', type=int, default=defaults['port'])
    parser.add_argument('--run-id', help='optional unique 32-character hexadecimal output identity')
    parser.add_argument('--budget-usd', type=float, default=defaults['budget_usd'])
    parser.add_argument('--request-limit', type=int, default=defaults['request_limit'])
    parser.add_argument('--fixture', choices=['normal', 'stale', 'tool-failure', 'provider-failure', 'outside-tool', 'delay'],
                        default='normal', help='mock-only failure injection for diagnostics')
    args = parser.parse_args()
    if args.mode != 'baseline' and args.scenario != 'portfolio-v1':
        parser.error('Motif modes require the portfolio-v1 historical library scenario')
    if args.fixture in ('stale', 'tool-failure') and (args.mode != 'execute' or args.scenario != 'portfolio-v1'):
        parser.error('stale/tool-failure fixtures require portfolio-v1 execute')
    if not 1024 <= args.port <= 65535 or args.request_limit < 1 or not math.isfinite(args.budget_usd) or args.budget_usd < 0:
        parser.error('invalid port, request limit or budget')
    if args.run_id is not None and not re.fullmatch('[0-9a-f]{32}', args.run_id):
        parser.error('run-id must be 32 lowercase hexadecimal characters')
    os.umask(0o077)
    output = ROOT / '.local/web/runs' / (args.run_id or uuid4().hex)
    output.mkdir(parents=True, mode=0o700)
    (output / 'work').mkdir(mode=0o700)
    (output / 'dsh').mkdir(mode=0o700)
    for name in ('events.jsonl', 'motif-audit.jsonl', 'ledger.jsonl'):
        (output / name).touch(mode=0o600)
    module = fixture_module()
    if args.scenario == 'example':
        module.next_fixture_action = demo_action
    handler = module.provider_handler('event:l_retrieval_persistence:01', with_usage=True)
    if args.fixture == 'outside-tool':
        original_action = module.next_fixture_action
        def outside_action(values, event):
            if len(handler.calls) == 1: return 'bash', {'command': 'echo forbidden'}
            return original_action(values, event)
        module.next_fixture_action = outside_action
    if args.fixture in ('delay', 'provider-failure'):
        original_respond = handler.respond
        def respond(self):
            if args.fixture == 'delay': time.sleep(1)
            else: raise RuntimeError('injected mock provider failure')
            return original_respond(self)
        handler.respond = respond
    provider = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    upstream = f'http://127.0.0.1:{provider.server_port}'
    args.embedding_endpoint = upstream + '/v1/embeddings'
    state = State(cap_usd=args.budget_usd, output_cap=defaults['max_output_tokens'],
                  record=output / 'ledger.jsonl', request_limit=args.request_limit)
    gate = create_server('127.0.0.1', 0, upstream, state)
    for server in (provider, gate):
        threading.Thread(target=server.serve_forever, daemon=True).start()
    prepare(args, output, f'http://127.0.0.1:{gate.server_port}/v1')
    env = {**os.environ, 'DSH_HOME': str(output / 'dsh'), 'SSS_WEB_POLICY': str(output / 'policy.json'),
           'DEEPSEEK_API_KEY': 'sss-mock-only', 'DEEPSEEK_BASE_URL': f'http://127.0.0.1:{gate.server_port}/v1',
           'SSS_ONLINE_MOTIF_MANIFEST': '', 'SSS_ONLINE_MOTIF_TASK': ''}
    log = (output / 'startup.log').open('w')
    process = subprocess.Popen(['node', str(ROOT / 'node_modules/@deepseek-ai/dsh/lib/bin.js'),
        '--profile', 'web', '--patch', str(output / 'host.patch.yml'),
        '--host', '127.0.0.1', '--port', str(args.port), '--no-open'],
        cwd=output / 'work', env=env, stdout=log, stderr=subprocess.STDOUT)
    proc = Path(f'/proc/{os.getpid()}/stat')
    ticks = proc.read_text().rsplit(')', 1)[1].split()[19] if proc.exists() else None
    save(output / 'process.json', {'launcher_pid': os.getpid(), 'harness_pid': process.pid,
                                  'launcher_start_ticks': ticks, 'port': args.port})
    def stop(_signum, _frame):
        if process.poll() is None: process.terminate()
    for number in (signal.SIGTERM, signal.SIGINT): signal.signal(number, stop)
    def metrics():
        audit = [json.loads(line) for line in (output / 'motif-audit.jsonl').read_text().splitlines()]
        save(output / 'metrics.json', {'mock_requests': len(handler.calls),
            'embedding_calls': handler.embedding_calls, 'reserved_upper_usd': state.reserved_usd,
            'paid_calls': 0, 'provider_failures': handler.failures, 'harness_exit_code': process.poll(),
            'gate_requests': state.request_count,
            'shadow_candidates': sum(row.get('kind') == 'shadow_candidate' for row in audit),
            'motif_attempts': sum(row.get('kind') == 'motif_bypass_attempt' for row in audit),
            'verified_skips': sum(row.get('kind') == 'model_request_skipped_verified' for row in audit)})
        if handler.calls:
            snapshot = json.loads((output / 'effective-config.json').read_text())
            first = handler.calls[0]
            snapshot['observed_model_request'] = {key: first.get(key) for key in ('model', 'thinking', 'max_tokens')}
            snapshot['observed_tools_order'] = [row['function']['name'] for row in first['tools']]
            snapshot['observed_tools_sha256'] = hashlib.sha256(json.dumps(first['tools'], sort_keys=True).encode()).hexdigest()
            save(output / 'effective-config.json', snapshot)
    print('SSS 新 Web 入口：模拟模型，实际费用为 0。', flush=True)
    print('私有输出目录：' + str(output), flush=True)
    try:
        for _ in range(300):
            if process.poll() is not None: break
            text = (output / 'startup.log').read_text()
            match = re.search(r'http://127\.0\.0\.1:' + str(args.port) + r'/\?token=[^\s]+', text)
            if match:
                (output / 'access-url.txt').write_text(match.group(0)); (output / 'access-url.txt').chmod(0o600)
                print('官方 Web 已启动；认证地址仅保存在 access-url.txt。题面见 prompt.md。', flush=True)
                break
            time.sleep(0.1)
        if not (output / 'access-url.txt').exists(): raise RuntimeError('Web startup failed; inspect private startup.log')
        while process.poll() is None:
            metrics()
            time.sleep(0.25)
    finally:
        stop(None, None)
        try: process.wait(timeout=10)
        except subprocess.TimeoutExpired: process.kill(); process.wait()
        for server in (gate, provider): server.shutdown(); server.server_close()
        log.close()
        state_path = output / 'task-state.json'
        if state_path.exists():
            final_state = json.loads(state_path.read_text())
            if final_state['status'] in ('ready', 'running'):
                final_state.update(status='cancelled', failure='server_stopped')
                save(state_path, final_state)
        events = [json.loads(line) for line in (output / 'events.jsonl').read_text().splitlines()]
        metrics()
        save(output / 'mock-requests.json', handler.calls)
        answers = [event for event in events if event.get('type') == 'assistant/message']
        save(output / 'answer.json', answers[-1] if answers else None)
        text = '\n'.join(part['text'] for part in answers[-1]['data']['message']['content'] if part['type'] == 'text') if answers else ''
        (output / 'answer.md').write_text(text); (output / 'answer.md').chmod(0o600)
    if process.returncode not in (0, -signal.SIGTERM): sys.exit(1)


if __name__ == '__main__': main()
