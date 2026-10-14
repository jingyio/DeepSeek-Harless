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
    parser.add_argument('--tool-presentation', choices=['native', 'ptc'], default='native')
    parser.add_argument('--entry-policy', type=Path)
    parser.add_argument('--entry-task', type=Path)
    parser.add_argument('--terminal-policy', type=Path)
    parser.add_argument('--terminal-task', type=Path)
    parser.add_argument('--collection-policy', type=Path)
    parser.add_argument('--collection-task', type=Path)
    parser.add_argument('--collection-script', type=Path)
    parser.add_argument('--collection-script-task', type=Path)
    parser.add_argument('--plan-policy', type=Path)
    parser.add_argument('--plan-task', type=Path)
    parser.add_argument('--reentry-policy', type=Path)
    parser.add_argument('--reentry-task', type=Path)
    parser.add_argument('--mode', choices=['baseline', 'shadow', 'execute'], default='baseline')
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--task', type=Path)
    parser.add_argument('--embedding-endpoint')
    parser.add_argument('--embedding-model')
    parser.add_argument('--model', choices=['deepseek-flash', 'deepseek-pro', 'deepseek-v4-pro'], default='deepseek-flash')
    parser.add_argument('--budget-usd', type=float, default=0.25)
    parser.add_argument('--max-output', type=int, default=3000)
    parser.add_argument('--max-steps', type=int, default=16)
    parser.add_argument('--call-model', action='store_true')
    args = parser.parse_args()
    requested_model = args.model
    # Keep the old CLI alias; runtime and budget accounting use the official ID.
    if args.model == 'deepseek-pro':
        args.model = 'deepseek-v4-pro'
    if not 0 < args.budget_usd <= 100 or not 1 <= args.max_output <= 8000 or not 1 <= args.max_steps <= 100:
        parser.error('invalid budget')
    if args.tool_presentation == 'ptc' and args.mode != 'baseline':
        parser.error('PTC strong baseline is separate from native Motif execution')
    if bool(args.entry_policy) != bool(args.entry_task) or args.entry_policy and (args.mode != 'baseline' or args.tool_presentation != 'native'):
        parser.error('entry policy/task must be paired and separate from legacy Motif/PTC')
    if (bool(args.terminal_policy) != bool(args.terminal_task) or args.terminal_policy and
            (args.entry_policy or args.mode != 'baseline' or args.tool_presentation != 'native')):
        parser.error('terminal policy/task must be paired and separate from entry/legacy Motif/PTC')
    if (bool(args.collection_policy) != bool(args.collection_task) or args.collection_policy and
            (args.entry_policy or args.terminal_policy or args.mode != 'baseline' or args.tool_presentation != 'native')):
        parser.error('collection policy/task must be paired and separate from other modes')
    if (bool(args.collection_script) != bool(args.collection_script_task) or args.collection_script and
            (args.entry_policy or args.terminal_policy or args.collection_policy or args.mode != 'baseline' or args.tool_presentation != 'native')):
        parser.error('collection script/task must be paired and separate from all Motif/PTC modes')
    if (bool(args.plan_policy) != bool(args.plan_task) or args.plan_policy and
            (args.entry_policy or args.terminal_policy or args.collection_policy or args.collection_script or args.mode != 'baseline' or args.tool_presentation != 'native')):
        parser.error('plan policy/task must be paired and separate from all other modes')
    if (bool(args.reentry_policy) != bool(args.reentry_task) or args.reentry_policy and
            (args.entry_policy or args.terminal_policy or args.collection_policy or args.collection_script or args.plan_policy or args.mode != 'baseline' or args.tool_presentation != 'native')):
        parser.error('reentry policy/task must be paired and separate from all other modes')
    prepared = prepare_scenario(args.scenario, case=args.case, tool_presentation=args.tool_presentation, entry_motif=bool(args.entry_policy or args.terminal_policy or args.collection_policy or args.collection_script or args.plan_policy or args.reentry_policy))
    patches = [prepared['patch']]
    session_id = 'sss-' + uuid4().hex
    child_env = {'SSS_SCENARIO_PRESENTATION': args.tool_presentation, 'SSS_SCENARIO_TOOLS': json.dumps(prepared['allowed_tools'])}
    entry_digest = None
    terminal_digest = None
    collection_digest = None
    script_digest = None
    plan_digest = None
    reentry_digest = None
    if args.collection_policy:
        policy_path, task_path = args.collection_policy.resolve(strict=True), args.collection_task.resolve(strict=True)
        if (any(p.is_symlink() for p in (args.collection_policy.absolute(), args.collection_task.absolute()))
                or any(not p.is_file() or not p.is_relative_to((ROOT / '.local').resolve()) for p in (policy_path, task_path))):
            raise ValueError('collection files must be private regular artifacts')
        policy = json.loads(policy_path.read_text()); collection = json.loads(task_path.read_text())
        if any(tool not in prepared['allowed_tools'] for tool in policy['artifact']['tools']):
            raise ValueError('collection policy names an unapproved scene tool')
        collection.update(session_id=session_id, prompt_sha256=prepared['prompt_sha256'])
        bound = ROOT / '.local/online-motif/collection-tasks' / (session_id + '.json')
        bound.parent.mkdir(parents=True, exist_ok=True)
        with bound.open('x', encoding='utf-8') as stream: json.dump(collection, stream, ensure_ascii=False)
        bound.chmod(0o600)
        verifier = "import fs from 'node:fs';import {validateCollectionPolicy,validateCollectionTask} from './src/motif_core/collection_read_policy.ts';const p=validateCollectionPolicy(JSON.parse(fs.readFileSync(process.argv[1])));validateCollectionTask(JSON.parse(fs.readFileSync(process.argv[2])),p);"
        import subprocess
        subprocess.run(['node','--input-type=module','-e',verifier,str(policy_path),str(bound)],cwd=ROOT,check=True,capture_output=True)
        collection_digest = policy['policy_digest']
        child_env.update(SSS_COLLECTION_MOTIF_POLICY=str(policy_path), SSS_COLLECTION_MOTIF_TASK=str(bound))
    if args.reentry_policy:
        policy_path, task_path = args.reentry_policy.resolve(strict=True), args.reentry_task.resolve(strict=True)
        if (any(p.is_symlink() for p in (args.reentry_policy.absolute(), args.reentry_task.absolute()))
                or any(not p.is_file() or not p.is_relative_to((ROOT / '.local').resolve()) for p in (policy_path, task_path))):
            raise ValueError('collection files must be private regular artifacts')
        policy = json.loads(policy_path.read_text()); collection = json.loads(task_path.read_text())
        if any(tool not in prepared['allowed_tools'] for tool in policy['parent_policy']['artifact']['tools']):
            raise ValueError('collection policy names an unapproved scene tool')
        collection.update(session_id=session_id, prompt_sha256=prepared['prompt_sha256'])
        bound = ROOT / '.local/online-motif/collection-tasks' / (session_id + '.json')
        bound.parent.mkdir(parents=True, exist_ok=True)
        with bound.open('x', encoding='utf-8') as stream: json.dump(collection, stream, ensure_ascii=False)
        bound.chmod(0o600)
        verifier = "import fs from 'node:fs';import {validateReentryPolicy,validateReentryTask} from './src/motif_core/collection_reentry_policy.ts';const p=validateReentryPolicy(JSON.parse(fs.readFileSync(process.argv[1])));validateReentryTask(JSON.parse(fs.readFileSync(process.argv[2])),p);"
        import subprocess
        subprocess.run(['node','--input-type=module','-e',verifier,str(policy_path),str(bound)],cwd=ROOT,check=True,capture_output=True)
        reentry_digest = policy['policy_digest']
        child_env.update(SSS_REENTRY_MOTIF_POLICY=str(policy_path), SSS_REENTRY_MOTIF_TASK=str(bound))
    if args.plan_policy:
        policy_path, task_path = args.plan_policy.resolve(strict=True), args.plan_task.resolve(strict=True)
        if (any(p.is_symlink() for p in (args.plan_policy.absolute(), args.plan_task.absolute()))
                or any(not p.is_file() or not p.is_relative_to((ROOT / '.local').resolve()) for p in (policy_path, task_path))):
            raise ValueError('collection files must be private regular artifacts')
        policy = json.loads(policy_path.read_text()); collection = json.loads(task_path.read_text())
        if any(tool not in prepared['allowed_tools'] for tool in policy['artifact']['tools']):
            raise ValueError('collection policy names an unapproved scene tool')
        collection.update(session_id=session_id, prompt_sha256=prepared['prompt_sha256'])
        bound = ROOT / '.local/online-motif/collection-tasks' / (session_id + '.json')
        bound.parent.mkdir(parents=True, exist_ok=True)
        with bound.open('x', encoding='utf-8') as stream: json.dump(collection, stream, ensure_ascii=False)
        bound.chmod(0o600)
        verifier = "import fs from 'node:fs';import {validatePlanPolicy,validatePlanTask} from './src/motif_core/authorized_plan_policy.ts';const p=validatePlanPolicy(JSON.parse(fs.readFileSync(process.argv[1])));validatePlanTask(JSON.parse(fs.readFileSync(process.argv[2])),p);"
        import subprocess
        subprocess.run(['node','--input-type=module','-e',verifier,str(policy_path),str(bound)],cwd=ROOT,check=True,capture_output=True)
        plan_digest = policy['policy_digest']
        child_env.update(SSS_PLAN_MOTIF_POLICY=str(policy_path), SSS_PLAN_MOTIF_TASK=str(bound))
    if args.collection_script:
        policy_path, task_path = args.collection_script.resolve(strict=True), args.collection_script_task.resolve(strict=True)
        if (any(p.is_symlink() for p in (args.collection_script.absolute(), args.collection_script_task.absolute()))
                or any(not p.is_file() or not p.is_relative_to((ROOT / '.local').resolve()) for p in (policy_path, task_path))):
            raise ValueError('collection files must be private regular artifacts')
        policy = json.loads(policy_path.read_text()); collection = json.loads(task_path.read_text())
        if any(tool not in prepared['allowed_tools'] for tool in policy['tools']):
            raise ValueError('collection policy names an unapproved scene tool')
        collection.update(session_id=session_id, prompt_sha256=prepared['prompt_sha256'])
        bound = ROOT / '.local/online-motif/collection-tasks' / (session_id + '.json')
        bound.parent.mkdir(parents=True, exist_ok=True)
        with bound.open('x', encoding='utf-8') as stream: json.dump(collection, stream, ensure_ascii=False)
        bound.chmod(0o600)
        verifier = "import fs from 'node:fs';import {validateCollectionTask} from './src/motif_core/collection_read_policy.ts';import {validateCollectionScript} from './src/motif_core/collection_batch_script.ts';const p=validateCollectionScript(JSON.parse(fs.readFileSync(process.argv[1])));validateCollectionTask(JSON.parse(fs.readFileSync(process.argv[2])),p);"
        import subprocess
        subprocess.run(['node','--input-type=module','-e',verifier,str(policy_path),str(bound)],cwd=ROOT,check=True,capture_output=True)
        script_digest = policy['script_digest']
        child_env.update(SSS_COLLECTION_SCRIPT=str(policy_path), SSS_COLLECTION_SCRIPT_TASK=str(bound))
    if args.entry_policy:
        policy_path, task_path = args.entry_policy.resolve(strict=True), args.entry_task.resolve(strict=True)
        if (any(p.is_symlink() for p in (args.entry_policy.absolute(), args.entry_task.absolute()))
                or any(not p.is_relative_to((ROOT / '.local').resolve()) for p in (policy_path, task_path))):
            raise ValueError('entry files must be private regular artifacts')
        policy = json.loads(policy_path.read_text()); entry = json.loads(task_path.read_text())
        if any(tool not in prepared['allowed_tools'] for tool in policy['artifact']['tools']):
            raise ValueError('entry policy names an unapproved scene tool')
        entry.update(session_id=session_id, prompt_sha256=prepared['prompt_sha256'])
        bound = ROOT / '.local/online-motif/entry-tasks' / (session_id + '.json')
        bound.parent.mkdir(parents=True, exist_ok=True)
        with bound.open('x', encoding='utf-8') as stream: json.dump(entry, stream, ensure_ascii=False)
        bound.chmod(0o600)
        verifier = "import fs from 'node:fs';import {validateEntryPolicy,validateEntryTask} from './src/motif_core/entry_read_policy.ts';const p=validateEntryPolicy(JSON.parse(fs.readFileSync(process.argv[1])));validateEntryTask(JSON.parse(fs.readFileSync(process.argv[2])),p);"
        import subprocess
        subprocess.run(['node','--input-type=module','-e',verifier,str(policy_path),str(bound)],cwd=ROOT,check=True,capture_output=True)
        entry_digest = policy['policy_digest']
        child_env.update(SSS_ENTRY_MOTIF_POLICY=str(policy_path), SSS_ENTRY_MOTIF_TASK=str(bound))
    if args.terminal_policy:
        policy_path, task_path = args.terminal_policy.resolve(strict=True), args.terminal_task.resolve(strict=True)
        if (any(p.is_symlink() for p in (args.terminal_policy.absolute(), args.terminal_task.absolute()))
                or any(not p.is_file() or not p.is_relative_to((ROOT / '.local').resolve()) for p in (policy_path, task_path))):
            raise ValueError('terminal files must be private regular artifacts')
        policy = json.loads(policy_path.read_text()); terminal = json.loads(task_path.read_text())
        if any(tool not in prepared['allowed_tools'] for tool in policy['artifact']['tools']):
            raise ValueError('terminal policy names an unapproved scene tool')
        terminal.update(session_id=session_id, prompt_sha256=prepared['prompt_sha256'])
        bound = ROOT / '.local/online-motif/terminal-tasks' / (session_id + '.json')
        bound.parent.mkdir(parents=True, exist_ok=True)
        with bound.open('x', encoding='utf-8') as stream: json.dump(terminal, stream, ensure_ascii=False)
        bound.chmod(0o600)
        verifier = "import fs from 'node:fs';import {validateTerminalPolicy,validateTerminalTask} from './src/motif_core/terminal_receipt_policy.ts';const p=validateTerminalPolicy(JSON.parse(fs.readFileSync(process.argv[1])));validateTerminalTask(JSON.parse(fs.readFileSync(process.argv[2])),p);"
        import subprocess
        subprocess.run(['node','--input-type=module','-e',verifier,str(policy_path),str(bound)],cwd=ROOT,check=True,capture_output=True)
        terminal_digest = policy['policy_digest']
        child_env.update(SSS_TERMINAL_MOTIF_POLICY=str(policy_path), SSS_TERMINAL_MOTIF_TASK=str(bound))
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
    preview.update(model=args.model, requested_model=requested_model, reasoning_effort='off', mode=args.mode,
                   entry_policy_digest=entry_digest, entry_mode='execute' if entry_digest else 'off',
                   terminal_policy_digest=terminal_digest, terminal_mode='execute' if terminal_digest else 'off',
                   collection_policy_digest=collection_digest, collection_mode='execute' if collection_digest else 'off',
                   collection_script_digest=script_digest, collection_script_mode='execute' if script_digest else 'off',
                   plan_policy_digest=plan_digest, plan_mode='execute' if plan_digest else 'off',
                   reentry_policy_digest=reentry_digest, reentry_mode='execute' if reentry_digest else 'off',
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
    for name in ['SSS_ONLINE_MOTIF_MANIFEST', 'SSS_ONLINE_MOTIF_TASK', 'SSS_ENTRY_MOTIF_POLICY', 'SSS_ENTRY_MOTIF_TASK', 'SSS_TERMINAL_MOTIF_POLICY', 'SSS_TERMINAL_MOTIF_TASK', 'SSS_COLLECTION_MOTIF_POLICY', 'SSS_COLLECTION_MOTIF_TASK', 'SSS_COLLECTION_SCRIPT', 'SSS_COLLECTION_SCRIPT_TASK', 'SSS_PLAN_MOTIF_POLICY', 'SSS_PLAN_MOTIF_TASK', 'SSS_REENTRY_MOTIF_POLICY', 'SSS_REENTRY_MOTIF_TASK']:
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
                   completion_guard_enabled=bool(prepared.get('agent_plugins')),
                   completion_continuations=sum(event.get('type') == 'user/message' and
                       event.get('data', {}).get('source', {}).get('kind') == 'task-completion-guard' for event in guard.events),
                   agent_steps=guard.started_requests, **_usage(guard.events),
                   upstream_requests=state.request_count, budget_accounted_usd=state.reserved_usd,
                   collection_model_requests_bypassed_verified=sum(row.get('kind') == 'collection_model_request_bypassed_verified' for row in decisions),
                   collection_script_batches_verified=sum(row.get('kind') == 'collection_script_batch_verified' for row in decisions),
                   plan_model_requests_bypassed_verified=sum(row.get('kind') == 'plan_model_request_bypassed_verified' for row in decisions),
                   reentry_epoch_batches_verified=sum(row.get('kind') == 'reentry_epoch_batch_verified' for row in decisions),
                   entry_model_requests_bypassed_verified=sum(row.get('kind') == 'entry_model_request_bypassed_verified' for row in decisions),
                   terminal_model_requests_bypassed_verified=sum(row.get('kind') == 'terminal_model_request_bypassed_verified' for row in decisions),
                   model_requests_skipped_verified=sum(row.get('kind') == 'model_request_skipped_verified' for row in decisions))
    if prepared.get('acceptance_guard'):
        trace=ROOT/'.local/task-acceptance'/hashlib.sha256(session_id.encode()).hexdigest()
        checks=[json.loads(p.read_text()) for p in sorted(trace.glob('round-*/result.json'))]
        passed=bool(checks and checks[-1]['passed'])
        metrics.update(acceptance_guard_enabled=True,acceptance_passed=passed,acceptance_checks=len(checks),
            acceptance_repairs=sum(e.get('type')=='user/message' and e.get('data',{}).get('source',{}).get('kind')=='task-acceptance-repair' for e in guard.events),
            acceptance_trace_dir=str(trace),acceptance_max_repairs=prepared['acceptance_guard']['max_repairs'])
        if metrics['status']=='done' and not passed:metrics['status']='acceptance_failed'
    save('metrics.json', json.dumps(metrics, ensure_ascii=False, indent=2))
    print(json.dumps({'output_dir': str(out), **metrics}, ensure_ascii=False))
    return 0 if metrics['status'] == 'done' else 2


if __name__ == '__main__':
    raise SystemExit(main())
