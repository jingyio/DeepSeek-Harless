#!/usr/bin/env python3
"""Preview a custom MCP task; explicit --call-model enables a bounded paid run."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.scenario import prepare_scenario
from src.adapters.harness_runtime import create_harness
from src.adapters.dsh_client import _usage
from src.adapters.native_budget import NativeBudgetGuard
from src.adapters.deepseek_cost_gate import State, create_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', type=Path, default=ROOT / 'scenarios/example/scenario.json')
    parser.add_argument('--case', default='')
    parser.add_argument('--mode', choices=['baseline', 'shadow', 'execute'], default='baseline')
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--task', type=Path)
    parser.add_argument('--embedding-endpoint')
    parser.add_argument('--embedding-model')
    parser.add_argument('--model', choices=['deepseek-flash', 'deepseek-pro'], default='deepseek-flash')
    parser.add_argument('--budget-usd', type=float, default=0.25)
    parser.add_argument('--max-output', type=int, default=3000)
    parser.add_argument('--max-steps', type=int, default=16)
    parser.add_argument('--call-model', action='store_true')
    args = parser.parse_args()
    if not 0 < args.budget_usd <= 100 or not 1 <= args.max_output <= 8000 or not 1 <= args.max_steps <= 100:
        parser.error('invalid budget')
    prepared = prepare_scenario(args.scenario, case=args.case)
    patches = [prepared['patch']]
    session_id = 'sss-' + uuid4().hex
    child_env = {'SSS_SCENARIO_TOOLS': json.dumps(prepared['allowed_tools'])}
    motif_digest = None
    if args.mode != 'baseline':
        if not all([args.manifest, args.task, args.embedding_endpoint, args.embedding_model]):
            parser.error('Motif modes require manifest, structured task and local embedding configuration')
        endpoint = urlparse(args.embedding_endpoint)
        if endpoint.scheme != 'http' or endpoint.hostname not in {'127.0.0.1', 'localhost', '::1'} or not endpoint.path.endswith('/v1/embeddings'):
            parser.error('embedding endpoint must be local /v1/embeddings')
        spec = importlib.util.spec_from_file_location('prepare_online', ROOT / 'scripts/prepare-online-motif.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        online = module.prepare(args.manifest, args.task)
        session_id = online['session_id']; patches.append(online['patch'])
        motif_digest = json.loads(args.manifest.read_text(encoding='utf-8'))['manifest_digest']
        child_env.update(SSS_ONLINE_MOTIF_MANIFEST=online['manifest'], SSS_ONLINE_MOTIF_TASK=online['task'],
                         SSS_ONLINE_MOTIF_MODE=args.mode, SSS_MOTIF_EMBEDDING_ENDPOINT=args.embedding_endpoint,
                         SSS_MOTIF_EMBEDDING_MODEL=args.embedding_model,
                         SSS_ONLINE_MOTIF_PROMPT_SHA256=prepared['prompt_sha256'])
    elif any([args.manifest, args.task, args.embedding_endpoint, args.embedding_model]):
        parser.error('Motif options require shadow or execute mode')
    preview = {key: value for key, value in prepared.items() if key != 'prompt'}
    preview.update(model=args.model, reasoning_effort='off', mode=args.mode,
                   budget_cap_usd=args.budget_usd, max_output_tokens=args.max_output,
                   max_agent_steps=args.max_steps, manifest_digest=motif_digest,
                   model_call_enabled=args.call_model)
    print(json.dumps(preview, ensure_ascii=False, indent=2), flush=True)
    if not args.call_model:
        return 0
    missing = [name for name in prepared['required_env'] if not os.environ.get(name)]
    if missing:
        raise ValueError('required environment variables are missing: ' + ', '.join(missing))
    if args.mode != 'baseline':
        locks = ROOT / '.local/online-motif/session-locks'; locks.mkdir(parents=True, exist_ok=True)
        lock = locks / (hashlib.sha256(session_id.encode()).hexdigest() + '.json')
        with lock.open('x', encoding='utf-8') as stream:
            json.dump({'prompt_sha256': prepared['prompt_sha256'], 'mode': args.mode}, stream)
        lock.chmod(0o600)
    out = ROOT / '.local/runs' / uuid4().hex
    out.mkdir(parents=True, mode=0o700)
    ledger = out / 'cost-ledger.jsonl'
    state = State(cap_usd=args.budget_usd, output_cap=args.max_output, record=ledger)
    # Bind port 0 directly to avoid racing another process for a free port.
    gate = create_server('127.0.0.1', 0, 'https://api.deepseek.com', state)
    worker = threading.Thread(target=gate.serve_forever, daemon=True); worker.start()
    child_env.update(DEEPSEEK_BASE_URL=f'http://127.0.0.1:{gate.server_port}/v1',
                     SSS_BUDGET_GATE_ACTIVE='1', SSS_BUDGET_CAP_USD=str(args.budget_usd),
                     SSS_BUDGET_LEDGER=str(ledger))
    # Baseline runs must not inherit opt-in plugins from the caller's shell.
    for name in ['SSS_ONLINE_MOTIF_MANIFEST', 'SSS_ONLINE_MOTIF_TASK']:
        child_env.setdefault(name, '')
    guard = NativeBudgetGuard(max_model_requests=args.max_steps, max_observed_input_tokens=None)

    def save(name, value):
        path = out / name; path.write_text(value, encoding='utf-8'); path.chmod(0o600)

    save('preview.json', json.dumps(preview, ensure_ascii=False, indent=2))
    save('manifest.json', json.dumps({
        'task_id': session_id, 'question': prepared['prompt'], **preview,
    }, ensure_ascii=False, indent=2))
    def observe(notification):
        if notification.method == 'session.event':
            event = notification.payload.get('event')
            if isinstance(event, dict):
                path = out / 'agent-events.jsonl'
                with path.open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(event, ensure_ascii=False) + '\n')
                path.chmod(0o600)
        guard.on_notification(notification)

    started = time.monotonic()
    try:
        with create_harness(root=ROOT, patches=tuple(patches), env=child_env,
                            provider='deepseek-official', model=args.model, max_tokens=args.max_output,
                            cwd=str(out), runtime_cwd=str(out), request_timeout_seconds=900) as harness:
            result = harness.run(prepared['prompt'], session_id=session_id, on_notification=observe)
        save('answer.md', result.final_response)
        status = 'done' if result.finish_reason == 'completed' and result.final_response.strip() else 'incomplete'
        metrics = {'status': status, 'finish_reason': result.finish_reason}
    except Exception as exc:
        metrics = {'status': 'error', 'error_type': type(exc).__name__}
    finally:
        gate.shutdown(); gate.server_close(); worker.join(timeout=5)
    audit_path = out / '.local/online-motif' / (hashlib.sha256(session_id.encode()).hexdigest() + '.jsonl')
    decisions = [json.loads(line) for line in audit_path.read_text(encoding='utf-8').splitlines()] if audit_path.exists() else []
    metrics.update(reasoning_effort='off', session_id=session_id, elapsed_seconds=round(time.monotonic()-started, 3),
                   agent_steps=guard.started_requests, **_usage(guard.events),
                   upstream_requests=state.request_count, budget_accounted_usd=state.reserved_usd,
                   model_requests_skipped_verified=sum(row.get('kind') == 'model_request_skipped_verified' for row in decisions))
    save('metrics.json', json.dumps(metrics, ensure_ascii=False, indent=2))
    print(json.dumps({'output_dir': str(out), **metrics}, ensure_ascii=False))
    return 0 if metrics['status'] == 'done' else 2


if __name__ == '__main__':
    raise SystemExit(main())
