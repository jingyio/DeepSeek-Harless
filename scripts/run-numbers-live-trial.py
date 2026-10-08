#!/usr/bin/env python3
"""Budget-gated ordinary DSH / online Motif trial on live Numbers documents."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.dsh_client import _usage, require_budget_gate
from src.adapters.native_budget import NativeBudgetGuard

BASE = ROOT / '.local/benchmarks/numbers-live-v1'


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    path.chmod(0o600)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', required=True)
    parser.add_argument('--arm', choices=['baseline', 'motif'], default='baseline')
    parser.add_argument('--attempt', default='first')
    parser.add_argument('--call-model', action='store_true')
    args = parser.parse_args()
    if args.case not in json.loads((BASE / 'cases.json').read_text()):
        parser.error('unknown frozen case')
    scope_path = BASE / args.case / 'scope.json'
    scope = json.loads(scope_path.read_text())
    prompt = (BASE / args.case / 'prompt.txt').read_text()
    out = BASE / args.case / (args.arm + '-' + args.attempt)
    out.mkdir(parents=True, exist_ok=True)
    prefix = (ROOT / 'config/gmail-alert-read.patch.yml').read_text().split('- insert:')[0]
    patch = BASE / 'numbers-read.patch.yml'
    patch.write_text(prefix + '''- insert:
    - id: numbers-live-read
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: numbers_live
        transport: stdio
        command: !!js process.env.SSS_MCP_PYTHON
        args: ['scripts/numbers-live-read-mcp.py']
        cwd: !!js process.env.SSS_PROJECT_ROOT
        env:
          SSS_NUMBERS_SCOPE: !!js process.env.SSS_NUMBERS_SCOPE
        failOnStartupError: true
''')
    preview = {'case': args.case, 'arm': args.arm, 'model': 'deepseek-flash',
               'reasoning_effort': 'off', 'max_requests': 12, 'budget_usd': 0.5,
               'tool_compaction': os.environ.get('SSS_TOOL_COMPACTION_MODE', 'off'),
               'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
               'scope': scope, 'output': str(out), 'external_data': 'anonymous historical usage costs only',
               'authorization_basis': 'User requested continuing local real-app experiments; prior approval: 全部批准，花费没有上限'}
    preview['code_sha256'] = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
        for name in ['scripts/numbers-live-read-mcp.py','scripts/run-numbers-live-trial.py',
                     'src/motif_core/online_skill_runtime.mjs','src/adapters/dsh_online_motif.mjs',
                     '.local/numbers-digits-upstream/server/digits_server.py',
                     'src/adapters/motif_output_projection.py', 'scripts/run-distil-dsh.py']}
    print(json.dumps(preview, ensure_ascii=False), flush=True)
    save(out / 'PREVIEW.json', preview)
    if not args.call_model:
        return 0
    require_budget_gate()
    if float(os.environ['SSS_BUDGET_CAP_USD']) > .5:
        raise ValueError('budget exceeds this run cap')
    marker = out / 'paid-attempt.marker'
    with marker.open('x') as stream:
        stream.write('one paid attempt\n')
    session_id = 'sss-numbers-' + uuid4().hex
    os.environ.update(SSS_MCP_PYTHON=str(ROOT / '.venv312/bin/python'),
                      SSS_PROJECT_ROOT=str(ROOT), SSS_NUMBERS_SCOPE=str(scope_path),
                      DSH_PERMISSION_MODE='read-only')
    patches = [str(patch)]
    if args.arm == 'motif':
        manifest_path = BASE / 'online-manifest.json'
        manifest = json.loads(manifest_path.read_text())
        task = {'schema_version': 1, 'task_id': args.case, 'session_id': session_id,
                'intent': 'Read the selected Numbers spreadsheet table and its formulas to audit the expense totals.',
                'input_version': scope['sha256'], 'bindings': {},
                'source_versions': {name: scope['sha256'] for name in manifest['contracts']}}
        task_path = out / 'online-task.json'; save(task_path, task)
        spec = importlib.util.spec_from_file_location('prepare', ROOT / 'scripts/prepare-online-motif.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        prepared = module.prepare(manifest_path, task_path)
        os.environ.update(SSS_ONLINE_MOTIF_MANIFEST=str(manifest_path),
                          SSS_ONLINE_MOTIF_TASK=str(task_path), SSS_ONLINE_MOTIF_MODE='execute',
                          SSS_ONLINE_MOTIF_PROMPT_SHA256=preview['prompt_sha256'],
                          SSS_MOTIF_EMBEDDING_ENDPOINT='http://127.0.0.1:8776/v1/embeddings',
                          SSS_MOTIF_EMBEDDING_MODEL='Qwen/Qwen3-Embedding-0.6B')
        patches.append(prepared['patch'])
    guard = NativeBudgetGuard(max_model_requests=12, max_observed_input_tokens=200000)
    def observe(notification):
        if getattr(notification, 'method', None) != 'session.event':
            return
        event = notification.payload.get('event')
        if isinstance(event, dict):
            p = out / 'agent-events.jsonl'
            with p.open('a') as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + '\n')
            p.chmod(0o600)
        guard.on_notification(notification)
    from deepseek_harness import DeepSeekHarness
    started = time.monotonic()
    try:
        with DeepSeekHarness(provider='deepseek-official', model='deepseek-flash',
                reasoning_effort='off', max_tokens=1500, cwd=str(out), runtime_cwd=str(out),
                dsh_bin=str(ROOT / 'node_modules/.bin/dsh'), profile='sdk', patches=tuple(patches),
                dsh_home=str(ROOT / '.local/dsh'), request_timeout_seconds=300) as harness:
            result = harness.run(prompt, session_id=session_id, on_notification=observe)
        (out / 'answer.txt').write_text(result.final_response)
        report = {'status': result.finish_reason, 'session_id': session_id}
    except Exception as exc:
        report = {'status': 'error', 'error': str(exc)[:300], 'error_type': type(exc).__name__}
    report.update(elapsed_seconds=round(time.monotonic()-started,3), **_usage(guard.events))
    report['budget_ledger'] = os.environ['SSS_BUDGET_LEDGER']
    audits = list((out / '.local/online-motif').glob('*.jsonl'))
    decisions = [json.loads(line) for p in audits for line in p.read_text().splitlines()]
    report['verified_skips'] = sum(x.get('kind') == 'model_request_skipped_verified' for x in decisions)
    report['tool_compaction'] = preview['tool_compaction']
    if os.environ.get('SSS_PROJECTION_HOME'):
        audits = [json.loads(p.read_text()) for p in (Path(os.environ['SSS_PROJECTION_HOME']) / 'audit').glob('*.json')]
        report['compacted_results'] = len(audits)
        report['tool_bytes_removed'] = sum(x['original_bytes'] - x['view_bytes'] for x in audits)
    save(out / 'metrics.json', report)
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0 if report['status'] == 'completed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
