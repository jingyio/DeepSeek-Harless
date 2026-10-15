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
    parser.add_argument('--file-job',type=Path,help='existing private durable file task; never initializes or resets it')
    parser.add_argument('--file-plan-binding',type=Path,help='explicit certified plan/library/runtime binding for the original durable job')
    parser.add_argument('--rsi-config',type=Path,help='private continuous learning state/config; task events can learn certified Motifs')
    parser.add_argument('--rsi-resume',type=Path,help='resume one original v2 RSI enrollment without resetting task grants or fees')
    args = parser.parse_args()
    requested_model = args.model
    # Keep the old CLI alias; runtime and budget accounting use the official ID.
    if args.model == 'deepseek-pro':
        args.model = 'deepseek-v4-pro'
    if not 0 < args.budget_usd <= 100 or not 1 <= args.max_output <= 8000 or not 1 <= args.max_steps <= 100:
        parser.error('invalid budget')
    if not args.rsi_config and not args.rsi_resume and args.scenario:
        candidate=json.loads(args.scenario.read_text())
        if candidate.get('acceptance_guard',{}).get('durable_job') and any('operation_tools_v2.py' in str(v.get('args',[])) for v in candidate.get('servers',[])):
            from src.adapters.persistent_file_rsi import default_config
            args.rsi_config=default_config(True)
    if args.rsi_resume or args.rsi_config:
        from src.adapters.continuous_rsi import load_config
        v2=args.rsi_resume or load_config(args.rsi_config).get('adapter') in ('file_operations_v2','management_v3')
        if v2:
            if args.mode!='baseline' or args.tool_presentation!='native' or any((args.entry_policy,args.terminal_policy,args.collection_policy,args.collection_script,args.plan_policy,args.reentry_policy,args.file_job)):
                parser.error('durable RSI owns its original native task and experience selection')
            from src.adapters.operation_runner import execute
            prepared=None if args.rsi_resume else prepare_scenario(args.scenario)
            value=execute(args,prepared);print(json.dumps(value,ensure_ascii=False),flush=True)
            return 0 if value.get('paid') is False or value.get('status')=='done' else 2
    if args.tool_presentation == 'ptc' and args.mode != 'baseline':
        parser.error('PTC strong baseline is separate from native Motif execution')
    if args.rsi_config and (args.mode!='baseline' or args.tool_presentation!='native' or any((
            args.entry_policy,args.terminal_policy,args.collection_policy,args.collection_script,args.plan_policy,args.reentry_policy,args.file_job))):
        parser.error('continuous RSI requires native ordinary mode and owns certified experience selection')
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
    durable=None
    if (prepared.get('acceptance_guard') or {}).get('durable_job'):
        if (not args.file_job or args.mode!='baseline' or any((args.entry_policy,args.terminal_policy,args.collection_policy,args.collection_script,args.reentry_policy))
                or bool(args.plan_policy)!=bool(args.file_plan_binding)):
            parser.error('durable recovery allows ordinary baseline or a plan policy with explicit --file-plan-binding only')
        from src.adapters.file_job_budget import job_command,FileJobBudget
        sys.path.insert(0,str(ROOT/'scenarios/file-management'))
        from recovery_tools import recovery_version
        durable=job_command(args.file_job,'state')['state']
        if durable['execution_version_sha256']!=recovery_version() or hashlib.sha256(Path(durable['task_file']).read_bytes()).hexdigest()!=durable['task_sha256']:
            raise ValueError('durable task/permission/execution version changed')
        limits=durable['limits']
        if (args.budget_usd,args.max_output,args.max_steps)!=(limits['budget_usd'],limits['max_output'],limits['max_steps']):
            parser.error('use exactly the frozen durable budget/output/step limits; they cannot reset on restart')
        # The pinned SDK can create, but cannot reopen, a persisted transport Session.
        # Original task/permissions/counters and round archive stay bound to the same durable job.
        session_id='sss-job-'+hashlib.sha256(str(args.file_job.resolve()).encode()).hexdigest()[:24]+'-'+uuid4().hex[:12]
        child_env.update(FM_JOB_FILE=str(args.file_job.resolve()),FM_TASK_FILE=durable['task_file'],FM_OUTPUT=durable['delivery_root'])
    elif args.file_job:
        parser.error('--file-job requires explicit durable_job acceptance configuration')
    if args.file_plan_binding and not durable:
        parser.error('--file-plan-binding requires the original durable job')
    entry_digest = None
    terminal_digest = None
    collection_digest = None
    script_digest = None
    plan_digest = None
    plan_composition_preview = None
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
        if durable:
            binding_path=args.file_plan_binding.resolve(strict=True)
            binding=json.loads(binding_path.read_text())
            if binding.get('job_file')!=str(args.file_job.resolve()):raise ValueError('composition belongs to another job')
            child_env['SSS_DURABLE_PLAN_BINDING']=str(binding_path)
            check = "import fs from 'node:fs';import {createJobPlanGuard} from './src/adapters/dsh_job_plan_gate.ts';const g=createJobPlanGuard(process.cwd(),process.argv[1],process.argv[2],JSON.parse(fs.readFileSync(process.argv[3])),()=>{});try{g.validate();console.log(JSON.stringify({eligible:true,activated:false}));}catch(e){console.log(JSON.stringify({eligible:false,activated:false,reason:e.message}));}"
            checked=subprocess.run(['node','--input-type=module','-e',check,str(binding_path),str(policy_path),str(bound)],cwd=ROOT,check=True,capture_output=True,text=True)
            plan_composition_preview=json.loads(checked.stdout)
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
    if args.rsi_config:
        from src.adapters.continuous_rsi import load_config
        rsi_config=load_config(args.rsi_config)
        preview['continuous_rsi']={'mode':rsi_config['mode'],'state_root':rsi_config['state_root'],
          'learning_cap_usd':rsi_config['learning_cap_usd'],'series_cap_usd':rsi_config['series_cap_usd'],
          'net_benefit_required':False,'quality_certification_required':True}
    if durable:preview.update(durable_job_status=durable['status'],durable_requests=durable['requests'],
                              durable_spent_usd=durable['spent_units']/1e9,durable_repairs=durable['repairs'])
    if plan_composition_preview is not None:preview['durable_plan_composition']=plan_composition_preview
    print(json.dumps(preview, ensure_ascii=False, indent=2), flush=True)
    if not args.call_model:
        return 0
    missing = [name for name in prepared['required_env'] if not child_env.get(name) and not os.environ.get(name)]
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
    rsi_context=None
    if args.rsi_config:
        from src.adapters.continuous_rsi import enroll
        rsi_context,rsi_patch=enroll(args.rsi_config,prepared,session_id,out,args,child_env)
        patches.append(rsi_patch)
    else:
        child_env['SSS_CONTINUOUS_RSI_BINDING']=''
    ledger = out / 'cost-ledger.jsonl'
    state = FileJobBudget(args.file_job,ledger) if durable else State(cap_usd=args.budget_usd, output_cap=args.max_output, record=ledger)
    start_requests,start_cost=state.request_count,state.reserved_usd
    # Bind port 0 directly to avoid racing another process for a free port.
    gate = create_server('127.0.0.1', 0, 'https://api.deepseek.com', state)
    worker = threading.Thread(target=gate.serve_forever, daemon=True); worker.start()
    child_env.update(DEEPSEEK_BASE_URL=f'http://127.0.0.1:{gate.server_port}/v1',
                     SSS_BUDGET_GATE_ACTIVE='1', SSS_BUDGET_CAP_USD=str(args.budget_usd),
                     SSS_BUDGET_LEDGER=str(ledger))
    # Baseline runs must not inherit opt-in plugins from the caller's shell.
    for name in ['SSS_ONLINE_MOTIF_MANIFEST', 'SSS_ONLINE_MOTIF_TASK', 'SSS_ENTRY_MOTIF_POLICY', 'SSS_ENTRY_MOTIF_TASK', 'SSS_TERMINAL_MOTIF_POLICY', 'SSS_TERMINAL_MOTIF_TASK', 'SSS_COLLECTION_MOTIF_POLICY', 'SSS_COLLECTION_MOTIF_TASK', 'SSS_COLLECTION_SCRIPT', 'SSS_COLLECTION_SCRIPT_TASK', 'SSS_PLAN_MOTIF_POLICY', 'SSS_PLAN_MOTIF_TASK', 'SSS_REENTRY_MOTIF_POLICY', 'SSS_REENTRY_MOTIF_TASK', 'SSS_DURABLE_PLAN_BINDING']:
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
        metrics = {'status': 'error', 'error_type': type(exc).__name__, 'error_message':str(exc)[:2000]}
    finally:
        gate.shutdown(); gate.server_close(); worker.join(timeout=5)
    audit_path = out / '.local/online-motif' / (hashlib.sha256(session_id.encode()).hexdigest() + '.jsonl')
    decisions = [json.loads(line) for line in audit_path.read_text(encoding='utf-8').splitlines()] if audit_path.exists() else []
    metrics.update(reasoning_effort='off', session_id=session_id, elapsed_seconds=round(time.monotonic()-started, 3),
                   completion_guard_enabled=bool(prepared.get('agent_plugins')),
                   completion_continuations=sum(event.get('type') == 'user/message' and
                       event.get('data', {}).get('source', {}).get('kind') == 'task-completion-guard' for event in guard.events),
                   agent_steps=guard.started_requests, **_usage(guard.events),
                   upstream_requests=state.request_count-start_requests, budget_accounted_usd=state.reserved_usd-start_cost,
                   collection_model_requests_bypassed_verified=sum(row.get('kind') == 'collection_model_request_bypassed_verified' for row in decisions),
                   collection_script_batches_verified=sum(row.get('kind') == 'collection_script_batch_verified' for row in decisions),
                   plan_model_requests_bypassed_verified=sum(row.get('kind') == 'plan_model_request_bypassed_verified' for row in decisions),
                   reentry_epoch_batches_verified=sum(row.get('kind') == 'reentry_epoch_batch_verified' for row in decisions),
                   entry_model_requests_bypassed_verified=sum(row.get('kind') == 'entry_model_request_bypassed_verified' for row in decisions),
                   terminal_model_requests_bypassed_verified=sum(row.get('kind') == 'terminal_model_request_bypassed_verified' for row in decisions),
                   model_requests_skipped_verified=sum(row.get('kind') == 'model_request_skipped_verified' for row in decisions))
    if durable:
        final_job=job_command(args.file_job,'state')['state']
        metrics.update(durable_job_status=final_job['status'],durable_requests_total=final_job['requests'],
                       durable_spent_usd_total=final_job['spent_units']/1e9,durable_repairs_total=final_job['repairs'])
    if prepared.get('acceptance_guard'):
        trace=ROOT/'.local/task-acceptance'/hashlib.sha256((str(args.file_job.resolve()) if durable else session_id).encode()).hexdigest()
        checks=[json.loads(p.read_text()) for p in sorted(trace.glob('round-*/result.json'))]
        passed=bool(checks and checks[-1]['passed'])
        metrics.update(acceptance_guard_enabled=True,acceptance_passed=passed,acceptance_checks=len(checks),
            acceptance_repairs=sum(e.get('type')=='user/message' and e.get('data',{}).get('source',{}).get('kind')=='task-acceptance-repair' for e in guard.events),
            acceptance_trace_dir=str(trace),acceptance_max_repairs=prepared['acceptance_guard']['max_repairs'])
        if metrics['status']=='done' and not passed:metrics['status']='acceptance_failed'
    save('metrics.json', json.dumps(metrics, ensure_ascii=False, indent=2))
    if rsi_context is not None:
        from src.adapters.continuous_rsi import seal,launch_worker
        sealed=seal(rsi_context,metrics)
        metrics['continuous_rsi']=sealed
        if sealed['auto_worker']:
            metrics['continuous_rsi']['worker']=launch_worker(args.rsi_config,sealed['state_root'])
        save('metrics.json',json.dumps(metrics,ensure_ascii=False,indent=2))
    print(json.dumps({'output_dir': str(out), **metrics}, ensure_ascii=False))
    return 0 if metrics['status'] == 'done' else 2


if __name__ == '__main__':
    raise SystemExit(main())
