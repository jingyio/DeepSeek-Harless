"""Persistent lifecycle queue and budget admission for the ordinary CLI's Motif learner.

The online interpreter remains TypeScript. This module captures immutable evidence,
admits bounded offline work, and never changes an in-flight task's library or grants.
"""
from __future__ import annotations
import asyncio
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from uuid import uuid4
from src.motif_core.offline.experience_registry import ExperienceRegistry, digest, durable, read, sha

ROOT = Path(__file__).resolve().parents[2]
PRIVATE_HOME = Path(os.environ.get('HARLESS_MANAGEMENT_PRIVATE_ROOT', ROOT / '.local')).absolute()
if not PRIVATE_HOME.is_relative_to((ROOT/'.local').absolute()) or any(p.is_symlink() for p in (PRIVATE_HOME,*PRIVATE_HOME.parents)):
    raise ValueError('management private home must be server-owned and inside the private deployment root')
STATE_HOME = PRIVATE_HOME / 'rsi'
DATA = ROOT / 'testpdf/file-management-experiment'
FORMAT = 'sss-continuous-rsi-v1'
RUNTIME = ['src/adapters/dsh_experience.ts', 'src/motif_core/collection_read_policy.ts',
           'src/motif_core/collection_reentry_policy.ts', 'src/motif_core/collection_read_policy_v2.ts',
           'src/motif_core/collection_reentry_policy_v2.ts', 'src/motif_core/online_skill_runtime.mjs',
           'scenarios/file-management/common.py', 'scenarios/file-management/file_tools.py',
           'scenarios/file-management/collection_tools.py', 'scenarios/file-management/report_tools.py']
LEARNER = [*RUNTIME, 'src/adapters/continuous_rsi.py', 'src/adapters/continuous_motif_learning.py',
           'src/adapters/dsh_continuous_rsi.ts', 'scripts/run-file-scenario.py', 'scripts/rsi-worker.py',
           'src/motif_core/offline/experience_registry.py', 'src/motif_core/offline/collection_compiler.py',
           'src/motif_core/offline/reentry_compiler.py', 'scenarios/file-management/workflow_learning.py',
           'scripts/validate-file-delivery.py','src/adapters/mcp_learning.py',
           'src/motif_core/offline/operation_graph.py','src/motif_core/operation_graph_policy.ts',
           'src/adapters/dsh_operation_motif.ts','scenarios/file-management/operation_tools.py',
           'scenarios/file-management/operation_contract.py','scenarios/file-management/operation_prepare.py',
           'src/adapters/file_cost_gate.py','src/adapters/file_web_task_budget.py',
           'src/adapters/dsh_web_tasks.ts','scripts/harness-web.py','scenarios/file-management/operation_web_binding.py',
           'scenarios/file-management/operation_web_binding.ts']
LEARNER += ['src/motif_core/offline/operation_graph_v1.py','src/motif_core/operation_graph_policy_v1.ts',
    'scenarios/file-management/operation_tools_v2.py','scenarios/file-management/operation_contract_v2.py',
    'scenarios/file-management/operation_prepare_v2.py','src/adapters/operation_job.ts','src/adapters/file_workflow_job.ts',
    'src/adapters/operation_budget.py','src/adapters/operation_runner.py','src/adapters/persistent_file_rsi.py',
    'src/adapters/persistent_web_budget.py','src/adapters/process_state.py','src/adapters/file_acceptance_guard.ts','src/adapters/file_scenario.py']
LEARNER += ['scenarios/file-management/management_tools.py','scenarios/file-management/management_contract.py',
    'scenarios/file-management/management_prepare.py','src/adapters/dsh_web_tasks_legacy.ts','src/adapters/dsh_geneloop_tasks.ts',
    'scripts/harness-web-legacy.py','scripts/harness-geneloop.py']
LEARNER += ['scenarios/file-management/management_web.py','scenarios/file-management/management_native.py',
    'src/adapters/harless_management.ts','src/adapters/file_task_scope.ts','src/adapters/harless_web_client/client.js','scenarios/file-management/management_study.py']
LEARNER += ['src/adapters/management_backup.py','scenarios/file-management/experiment.py','scenarios/file-management/management_goals.py']
LEARNER += ['src/adapters/experience_library.py','src/adapters/management_recertification.py']
LEARNER += ['src/adapters/management_legacy.py','src/adapters/management_program.ts']
LEARNER += ['scenarios/file-management/management_provenance.py']
LEARNER += ['scenarios/file-management/management_reading.py']
LEARNER += ['src/adapters/general_tools.py','scenarios/file-management/general-tools.json','scenarios/general/runtime.py','scenarios/general/runtime_code.ts']
LEARNER += ['scenarios/general/server.py','src/adapters/file_settings.ts','src/adapters/file_scenarios.py']
LEARNER += ['src/adapters/harless_reasoning.ts','src/adapters/harless_legacy_reasoning.ts']
LEARNER += ['src/adapters/harless_status_cache.ts']
LEARNER += ['src/motif_core/offline/control_flow.py','src/motif_core/control_flow_policy.ts','src/adapters/general_tool_replay.py']
LEARNER += ['scenarios/file-management/management_temporal.py','src/adapters/management_temporal.ts','src/adapters/management_model_gate.py','src/adapters/management_model_gate.ts','src/adapters/management_platform_budget.py','src/adapters/management_seed.py','src/adapters/management_seed.ts']

LEARNER += ['src/adapters/file_event_projection.ts','scenarios/file-management/semantic-sdk.patch.yml','src/adapters/harless_file_scene.ts','src/adapters/file_approval_bridge.ts','scenarios/file-management/file_scene_worker.py','scenarios/file-management/general-tools.json','src/adapters/file_scenario.py','src/adapters/file_cost_gate.py','src/adapters/file_acceptance_guard.ts','src/adapters/file_entry_motif.ts']

LEARNER += ['src/adapters/geneloop_task_trace.ts','src/adapters/model_transport.py','config/geneloop-transport.json']

def private(path):
    p = Path(path).absolute()
    if not p.is_relative_to((ROOT / '.local').absolute()):
        raise ValueError('RSI artifacts must stay in the project private directory')
    for q in (p, *p.parents):
        if q.is_symlink(): raise ValueError('RSI symlink refused')
        if q == ROOT: break
    return p.resolve()


def snapshot(path):
    result = {}
    for p in sorted(Path(path).rglob('*')):
        if p.is_symlink(): raise ValueError('experiment symlink refused')
        if p.is_file(): result[p.relative_to(path).as_posix()] = sha(p)
    return result


def source_map(names=LEARNER):
    return {n: sha(ROOT / n) for n in names}


def ledger_accounting(ledger, metrics):
    rows=[json.loads(l) for l in Path(ledger).read_text().splitlines()] if Path(ledger).exists() else []
    # Files API operations are free provider transport, retained in the same
    # ledger but not completions or missing completion-usage observations.
    paid=[r for r in rows if r.get('kind') not in ('budget_denied','files_api')]
    known=all(r.get('observed_peak_usd') is not None or r.get('reserved_upper_usd') is not None for r in paid)
    cost=sum(r.get('observed_peak_usd') if r.get('observed_peak_usd') is not None else r.get('reserved_upper_usd',0) for r in paid)
    return {'accounting_complete':known and len(paid)==metrics['upstream_requests'] and abs(cost-metrics['budget_accounted_usd'])<1e-6,
            'observed_usage_complete':all(r.get('observed_peak_usd') is not None and not r.get('recovered_usage_unknown') for r in paid),
            'missing_observed_usage_requests':sum(r.get('observed_peak_usd') is None for r in paid),
            'cost_upper_usd':cost,'formula':'observed_peak_else_original_reserved_upper','requests':len(paid),
            'free_files_api_requests':sum(r.get('kind')=='files_api' for r in rows)}


def reconcile_cost(root,session):
    """Append a conservative review of old failed HTTP usage; raw record stays immutable."""
    root=private(root);file=root/'records'/(session+'.json');record=read(file)
    ledger=Path(record['run_dir'])/'cost-ledger.jsonl';review=ledger_accounting(ledger,record['metrics'])
    if not review['accounting_complete']:raise ValueError('HTTP fees still cannot be bounded from the original ledger')
    review.update(record_sha256=sha(file),ledger_sha256=sha(ledger),raw_record_unchanged=True,requests_not_reset=True)
    target=root/'cost-reconciliations'/(session+'.json')
    if not target.exists():durable(target,review,exclusive=True)
    with writer_lock(STATE_HOME,'series'):
        pool=read(root/'pool.json');pool['runs'][session].update(status='settled',cost_usd=record['cost_usd'],cost_review_sha256=sha(target))
        durable(root/'pool.json',pool)
    return review


def load_config(path):
    path = private(path); cfg = read(path)
    allowed = {'schema_version','format','state_root','workspace_roots','mode','provider_mode',
               'series_cap_usd','learning_cap_usd','limits','auto_worker','allow_material_copy',
               'role','registry_file','candidate_job','adapter'}
    if set(cfg) - allowed or cfg.get('schema_version') != 1 or cfg.get('format') != FORMAT:
        raise ValueError('invalid continuous RSI configuration')
    cfg = {'mode':'learn','provider_mode':'real','auto_worker':True,'allow_material_copy':False,
           'role':'ordinary', **cfg}
    state = private(cfg['state_root'])
    if state.parent != STATE_HOME.resolve(): raise ValueError('state_root must be a direct .local/rsi child')
    if cfg['mode'] not in ('observe','learn') or cfg['provider_mode'] not in ('real','mock'):
        raise ValueError('unknown RSI mode/provider')
    if cfg['role'] not in ('ordinary','native_certification','candidate_certification'):
        raise ValueError('invalid RSI evidence role')
    if any(type(cfg[k]) is not bool for k in ('auto_worker','allow_material_copy')):
        raise ValueError('RSI switches must be booleans')
    if cfg['provider_mode']=='mock' and cfg['mode']=='learn': raise ValueError('mock evidence cannot learn')
    def number(value, minimum=0):
        return value is None or type(value) in (int,float) and math.isfinite(value) and value >= minimum
    if (not number(cfg['series_cap_usd']) or not number(cfg['learning_cap_usd']) or
            cfg['series_cap_usd'] is not None and not 0 < cfg['series_cap_usd'] <= 1000 or
            cfg['series_cap_usd'] is not None and (cfg['learning_cap_usd'] is None or cfg['learning_cap_usd'] > cfg['series_cap_usd'])):
        raise ValueError('RSI caps exceed existing authorization')
    limits=cfg['limits']
    if (set(limits) != {'budget_usd','max_steps','max_output','max_repairs'} or not number(limits['budget_usd']) or
            limits['budget_usd'] is not None and not 0 < limits['budget_usd'] <= 5):
        raise ValueError('invalid original per-task RSI limits')
    if any(limits[k] is not None and (type(limits[k]) is not int or not minimum <= limits[k] <= maximum)
           for k,minimum,maximum in [('max_steps',1,96),('max_output',1,393216),('max_repairs',0,2)]):
        raise ValueError('RSI limits cannot expand original bounds')
    roots=[]
    for value in cfg['workspace_roots']:
        p=Path(value).absolute()
        management_root=PRIVATE_HOME/'management-copies'
        in_management=cfg.get('adapter')=='management_v3' and p.is_relative_to(management_root.absolute()) and p!=management_root.absolute()
        if (not in_management and (not p.is_relative_to(DATA.absolute()) or p==DATA.absolute())) or any(q.is_symlink() for q in (p,*p.parents)):
            raise ValueError('RSI workspace roots require specific authorized experiment copies')
        roots.append(str(p.resolve()))
    if not roots: raise ValueError('no authorized RSI workspace')
    if cfg['role']=='ordinary' and ('registry_file' in cfg or 'candidate_job' in cfg):
        raise ValueError('ordinary tasks cannot select a candidate or library')
    if cfg['role']!='ordinary' and cfg.get('auto_worker'):
        raise ValueError('certification cannot recursively schedule learning')
    cfg.update(state_root=str(state),workspace_roots=roots,config_file=str(path),config_sha256=sha(path))
    if cfg.get('adapter'):
        from .mcp_learning import adapter
        adapter(cfg['adapter'])
    return cfg


@contextmanager
def writer_lock(root, name):
    """One writer; dead owners are archived, never reset their paid reservations."""
    root=Path(root);root.mkdir(parents=True,exist_ok=True,mode=0o700);path=root/(name+'.lock')
    # These locks cover short metadata publication, never a model/tool run.
    # Independent chats can contend during startup without rejecting a task.
    # Background learning keeps its existing fail-fast single-worker gate.
    wait_for_metadata=name in {'series','state','management-profile'}
    deadline=time.monotonic()+30
    while True:
        try:
            with path.open('x') as f:json.dump({'pid':os.getpid(),'created':time.time()},f)
            break
        except PermissionError:
            # Windows can briefly report a delete-pending lock as access
            # denied rather than FileExistsError. Retain real permission
            # errors after the same bounded metadata wait.
            if os.name!='nt' or not wait_for_metadata or time.monotonic()>=deadline:raise
            time.sleep(.05)
        except FileExistsError:
            try:previous=read(path)
            except PermissionError:
                # Its owner can unlink between exclusive-open failure and
                # this read; Windows then exposes a delete-pending handle as
                # access denied. Unknown ownership still cannot be stolen.
                if os.name!='nt' or not wait_for_metadata or time.monotonic()>=deadline:raise
                time.sleep(.05);continue
            except (FileNotFoundError,json.JSONDecodeError):
                if not wait_for_metadata or time.monotonic()>=deadline:raise RuntimeError(name+' writer is active')
                time.sleep(.05);continue
            from .process_state import process_exists
            if not process_exists(previous['pid']):
                archive=root/'stale-locks';archive.mkdir(exist_ok=True)
                try:path.rename(archive/(name+'-'+uuid4().hex+'.json'))
                except FileNotFoundError:pass
                continue
            if not wait_for_metadata or time.monotonic()>=deadline:raise RuntimeError(name+' writer is active')
            time.sleep(.05)
    path.chmod(0o600)
    try: yield
    finally:
        # A contender may still be reading this owner's PID when it exits.
        # Windows' ordinary read handles do not share deletion; a failed
        # unlink would strand a live-PID lock and make every later waiter time
        # out. Retry only that transient sharing conflict, never steal a lock
        # or suppress a real permission/cleanup failure.
        release_deadline=time.monotonic()+30
        while True:
            try:path.unlink();break
            except PermissionError as error:
                if (os.name!='nt' or getattr(error,'winerror',None) not in (32,33)
                        or time.monotonic()>=release_deadline):raise
                time.sleep(.05)


def state_event(root, kind, detail):
    directory=Path(root)/'events';directory.mkdir(parents=True,exist_ok=True)
    files=sorted(directory.glob('*.json'))
    row={'sequence':len(files)+1,'previous_sha256':sha(files[-1]) if files else None,'kind':kind,'detail':detail}
    durable(directory/f'{len(files)+1:08d}.json',row,exclusive=True)


def records(root):
    result=[]
    for p in sorted((Path(root)/'records').glob('*.json')):
        q=Path(root)/'queue'/p.name
        if not q.exists():continue  # Cost settlement and queue seal are not finished yet.
        item=read(q)
        if item.get('record_sha256')!=sha(p) or item.get('sealed_after_cost_and_acceptance') is not True:
            raise ValueError('sealed record mutated')
        result.append(read(p))
    return result


def initialize(cfg):
    root=Path(cfg['state_root']);root.mkdir(parents=True,exist_ok=True,mode=0o700)
    from .experience_library import enabled, synchronize
    managed=enabled(cfg)
    with writer_lock(root,'state'):
        if not (root/'registry/current.json').exists():
            ExperienceRegistry(root/'registry').publish(reason='empty continuous library; learn only from new ordinary task events')
            durable(root/'pool.json',{'runs':{}},exclusive=True)
            state_event(root,'initialized',{'net_benefit_required':False,'config_sha256':cfg['config_sha256']})
        if managed:
            from .management_seed import install
            install(cfg)
    if managed:
        synchronize(cfg)
    return root


def series_accounting():
    sys.path.insert(0,str(ROOT/'scenarios/file-management'))
    from experiment import accounting
    return accounting()


def reserve(cfg, session, cap):
    root=Path(cfg['state_root'])
    with writer_lock(STATE_HOME,'series'):
        pool=read(root/'pool.json')
        if session in pool['runs']: raise ValueError('task reservation already exists; no cold budget reset')
        pending_runs=[r for p in STATE_HOME.glob('*/pool.json') for r in read(p)['runs'].values() if r['status']=='reserved']
        if cfg['series_cap_usd'] is not None:
            current=series_accounting()
            if cap is None or any(r['cap_usd'] is None for r in pending_runs) or current['estimated_usd']+sum(r['cap_usd'] for r in pending_runs)+cap>cfg['series_cap_usd']:
                raise ValueError('original series budget exhausted')
        # A new adapter/version cannot receive a fresh independent learning cap.
        all_runs=[r for p in STATE_HOME.glob('*/pool.json') for r in read(p)['runs'].values()]
        if cfg['role']!='ordinary' and cfg['learning_cap_usd'] is not None:
            from .management_backup import imported_budget
            carry=imported_budget(ROOT)
            learned=sum(r['cost_usd'] for r in all_runs if r['status']=='settled' and r['role']!='ordinary')+carry.get('learning_spent_usd',0)
            pending=[r['cap_usd'] for r in all_runs if r['status']=='reserved' and r['role']!='ordinary']+[carry.get('learning_reserved_usd',0)]
            if cap is None or None in pending or learned+sum(pending)+cap>cfg['learning_cap_usd']:
                raise ValueError('continuous learning budget exhausted')
        pool['runs'][session]={'status':'reserved','cap_usd':cap,'role':cfg['role'],'pid':os.getpid(),'reserved_at':time.time()}
        durable(root/'pool.json',pool)


async def actual_schemas(prepared, task_file, output, adapter_id=None,probe_environment=None):
    """Inspect the same registered local service without passing provider credentials."""
    from mcp import Client,StdioServerParameters
    rows=prepared['mcp_rows']
    if adapter_id:
        result=[]
        def bound(value):
            if value not in prepared['environment_references']:return value
            expression=json.loads(prepared['environment_references'][value][5:])
            import re
            match=re.fullmatch(r'process\.env\["([A-Za-z_][A-Za-z0-9_]*)"\]',expression)
            if match and match[1]=='FM_TASK_FILE':return str(task_file)
            if match and match[1]=='FM_OUTPUT':return str(output)
            if match and match[1]=='FM_JOB_FILE' and probe_environment:return probe_environment[match[1]]
            if not match or match[1] not in os.environ:raise ValueError('unresolved registered MCP environment reference')
            return os.environ[match[1]]
        for row in rows:
            c=row['config']
            async def collect(connection):
                async with Client(connection) as client:
                    tools=await client.list_tools()
                    result.extend({**t.model_dump(mode='json'),'server_name':c['serverName']} for t in tools.tools)
            if c['transport']=='stdio':
                env={k:v for k,v in os.environ.items() if not k.startswith(('DEEPSEEK','OPENAI','SSS_'))}
                env.update({k:bound(v) for k,v in c.get('env',{}).items()})
                env.update(FM_TASK_FILE=str(task_file),FM_OUTPUT=str(output))
                await collect(StdioServerParameters(command=bound(c['command']),args=[bound(v) for v in c['args']],cwd=bound(c['cwd']),env=env))
            else:
                from mcp.client.streamable_http import streamable_http_client
                from httpx2 import AsyncClient
                async with AsyncClient(headers={k:bound(v) for k,v in c.get('headers',{}).items()}) as http:
                    await collect(streamable_http_client(bound(c['url']),http_client=http))
        return result
    if len(rows)!=1 or rows[0]['config']['serverName']!='file_management':
        raise ValueError('first continuous adapter requires the registered file MCP')
    config=rows[0]['config']
    if config['transport']!='stdio': raise ValueError('continuous file material adapter requires local stdio')
    env={k:v for k,v in os.environ.items() if not k.startswith(('DEEPSEEK','OPENAI','SSS_'))}
    env.update(FM_TASK_FILE=str(task_file),FM_OUTPUT=str(output))
    args=config['args']
    if args != [str(ROOT/'scenarios/file-management/report_tools.py')]:
        raise ValueError('first continuous adapter supports read-only ReportScene; other services are recorded but not enrolled')
    async with Client(StdioServerParameters(command=config['command'],args=args,cwd=ROOT,env=env)) as client:
        tools=await client.list_tools()
        return [t.model_dump(mode='json') for t in tools.tools]


def fingerprint(spec):
    return digest({'objective':spec['objective'],'snapshot':{n:h for n,h in spec['initial_snapshot'].items() if n!='.experiment-copy'},
                   'report_contract':spec['report_contract'],'operations':spec['allowed_operations']})


def enroll(config_file, prepared, session, out, args, env):
    cfg=load_config(config_file);root=initialize(cfg);out=private(out)
    limits=cfg['limits']
    if any(limits[k] is not None and (value is None or value>limits[k]) for k,value in
           [('budget_usd',args.budget_usd),('max_steps',args.max_steps),('max_output',args.max_output)]):
        raise ValueError('ordinary run exceeds original RSI task bounds')
    if not prepared.get('acceptance_guard') or prepared['acceptance_guard'].get('durable_job') and cfg.get('adapter') not in ('file_operations_v2','management_v3'):
        raise ValueError('continuous read tasks require the original independent file acceptance guard')
    if limits['max_repairs'] is not None and (prepared['acceptance_guard']['max_repairs'] is None or prepared['acceptance_guard']['max_repairs']>limits['max_repairs']): raise ValueError('repair grant exceeds original RSI limits')
    task_file=private(env.get('FM_TASK_FILE') or os.environ.get('FM_TASK_FILE',''))
    delivery=private(env.get('FM_OUTPUT') or os.environ.get('FM_OUTPUT',''));spec=read(task_file)
    work=Path(spec['workspace']).resolve()
    if not any(work.is_relative_to(Path(p)) for p in cfg['workspace_roots']) or not (work/'.experiment-copy').is_file():
        raise ValueError('task outside original RSI workspace grant')
    if spec.get('role') in ('holdout','evaluate','benchmark'):
        raise ValueError('sealed evaluation tasks cannot enter continuous learning')
    scene=None
    if cfg.get('adapter'):
        from .mcp_learning import adapter
        scene=adapter(cfg['adapter']);scene.validate(spec,prepared)
    elif spec.get('allowed_operations')!=[] or spec.get('workflow_contract') or spec.get('task_contract'):
        raise ValueError('effectful task material adapter is not yet enrolled')
    if snapshot(work)!=spec['initial_snapshot']: raise ValueError('initial task bytes changed')
    origin=root/'runs'/session;origin.mkdir(parents=True,mode=0o700,exist_ok=False)
    shutil.copytree(work,origin/'pristine');durable(origin/'task.json',spec,exclusive=True)
    schemas=asyncio.run(actual_schemas(prepared,task_file,out/'rsi-schema-probe',cfg.get('adapter'),env))
    durable(origin/'tool-schemas.json',schemas,exclusive=True)
    durable(origin/'source-code.json',source_map(),exclusive=True)
    for name in source_map():
        target=origin/'frozen-source'/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,target);target.chmod(0o600)
    reserve(cfg,session,args.budget_usd)
    pointer=read(root/'registry/current.json')
    registry_file=Path(cfg['registry_file']) if cfg.get('registry_file') else root/'registry'/pointer['file']
    registry_file=private(registry_file)
    if not registry_file.is_relative_to(root): raise ValueError('candidate registry outside this state')
    experience={'role':'ordinary' if cfg['role']=='ordinary' else 'certify','registry_root':str(root/'registry'),
                'registry_file':str(registry_file),'registry_sha256':sha(registry_file),'task_file':str(task_file),
                'task_sha256':sha(task_file),'prompt_sha256':prepared['prompt_sha256'],
                'runtime_sha256':sha(ROOT/'src/adapters/dsh_experience.ts'),'audit_file':str(out/'experience-audit.jsonl')}
    durable(out/'experience-binding.json',experience,exclusive=True)
    actual_session=env.get('SSS_RSI_ACTUAL_SESSION',session)
    binding={'session_id':actual_session,'task_file':str(task_file),'task_sha256':sha(task_file),'observer_sha256':sha(ROOT/'src/adapters/dsh_continuous_rsi.ts'),
             'allowed_tools':prepared['allowed_tools'],'event_file':str(out/'rsi-lifecycle.jsonl'),'schema_file':str(out/'rsi-runtime-schemas.json')}
    durable(out/'rsi-binding.json',binding,exclusive=True)
    if scene:
        from src.motif_core.offline.operation_graph import catalog
        operation={**experience,'scope':scene.scope(spec),'catalog':catalog(schemas),'runtime_source':source_map(scene.runtime_sources()),
                   'adapter':cfg.get('adapter'),
                   'session_id':actual_session,'allowed_tools':prepared['allowed_tools'],
                   **({'job_file':env['FM_JOB_FILE']} if cfg.get('adapter') in ('file_operations_v2','management_v3') else {})}
        durable(out/'operation-binding.json',operation,exclusive=True)
        env['SSS_OPERATION_BINDING']=str(out/'operation-binding.json')
    gate='dsh_operation_motif.ts' if scene else 'dsh_experience.ts'
    patch=[{'insert':[{'id':'sss-operation-motif' if scene else 'sss-experience','name':(ROOT/'src/adapters'/gate).as_uri()},
                       {'id':'sss-continuous-rsi-events','name':(ROOT/'src/adapters/dsh_continuous_rsi.ts').as_uri()}]}]
    durable(out/'rsi.patch.yml',patch,exclusive=True)
    env.update(SSS_EXPERIENCE_BINDING=str(out/'experience-binding.json'),SSS_CONTINUOUS_RSI_BINDING=str(out/'rsi-binding.json'))
    context={'config':cfg,'origin':str(origin),'out':str(out),'spec':spec,'delivery':str(delivery),'task_file':str(task_file),
             'registry_file':str(registry_file),'registry_sha256':sha(registry_file),'session_id':session,'actual_session_id':actual_session,'scenario_file':str(args.scenario.resolve()),
             'scenario_sha256':sha(args.scenario),'prompt_sha256':digest(prepared['prompt']),
             'prompt':prepared['prompt'],'source_sha256':digest(source_map()),'arguments':{'model':args.model,'budget_usd':args.budget_usd,
               'max_steps':args.max_steps,'max_output':args.max_output},'candidate_job':cfg.get('candidate_job'),
             **({'job_file':env['FM_JOB_FILE']} if cfg.get('adapter') in ('file_operations_v2','management_v3') else {})}
    durable(origin/'enrollment.json',context,exclusive=True)
    return context,str(out/'rsi.patch.yml')


def seal(context, metrics):
    cfg=context['config'];root=Path(cfg['state_root']);out=Path(context['out']);session=context['session_id'];origin=Path(context['origin'])
    existing=root/'records'/(session+'.json')
    if existing.exists():
        prior=read(existing)
        if prior['source_sha256']!=context['source_sha256'] or prior['task_sha256']!=sha(origin/'task.json'):raise ValueError('original seal binding changed')
        metrics=prior['metrics']
    lifecycle=[json.loads(l) for l in (out/'rsi-lifecycle.jsonl').read_text().splitlines()] if (out/'rsi-lifecycle.jsonl').exists() else []
    signals=[r for r in lifecycle if r.get('kind')=='task_lifecycle_end' and r.get('session_id')==context.get('actual_session_id',session)]
    ledger=out/'cost-ledger.jsonl'
    cost_review=ledger_accounting(ledger,metrics);accounted=cost_review['accounting_complete']
    http_rows=[json.loads(l) for l in ledger.read_text().splitlines()] if ledger.exists() else []
    unavailable=any(r.get('response_status') in (502,503) for r in http_rows)
    failure_class='cancelled' if metrics['status']=='cancelled' else 'provider_unavailable' if unavailable else 'budget_exhausted' if metrics['status'] in ('limit_exhausted','budget_exhausted') or any(r.get('kind')=='budget_denied' for r in http_rows) else 'delivery_or_execution'
    audit=[json.loads(l) for l in (out/'experience-audit.jsonl').read_text().splitlines()] if (out/'experience-audit.jsonl').exists() else []
    selected=[r for r in audit if r['kind']=='experience_selected']
    policy_digest=selected[0]['entry_id'] if selected else None
    steps=[r for r in audit if r['kind'] in ('collection_model_request_bypassed_verified','operation_model_request_bypassed_verified')]
    actual_schemas_ok=False
    signal_ok=len(signals)==1 or cfg.get('adapter') in ('file_operations_v2','management_v3') and len(signals)>=1
    if (out/'rsi-runtime-schemas.json').exists() and signal_ok:
        actual=read(out/'rsi-runtime-schemas.json');expected=read(origin/'tool-schemas.json')
        actual_schemas_ok=all(digest(actual)==s['runtime_schema_sha256'] and s['binding_sha256']==sha(out/'rsi-binding.json') for s in signals) and all(
            next((v['parameters'] for v in actual if v['name']=='mcp__'+r.get('server_name','file_management')+'__'+r['name']),None)==r.get('inputSchema',r.get('input_schema')) for r in expected)
    delivery_copy=origin/'delivery'
    if Path(context['delivery']).exists() and not delivery_copy.exists():
        snapshot(Path(context['delivery']));shutil.copytree(context['delivery'],delivery_copy)
    if not (origin/'final-workspace').exists():shutil.copytree(context['spec']['workspace'],origin/'final-workspace')
    record={'schema_version':1,'format':'sss-continuous-run-v1','session_id':session,'role':cfg['role'],'provider_mode':cfg['provider_mode'],
            'origin':str(origin),'run_dir':str(out),'delivery':str(delivery_copy),'task_fingerprint':fingerprint(context['spec']),
            'task_sha256':sha(origin/'task.json'),'input_sha256':digest(context['spec']),'metrics':metrics,
            'accounting_complete':accounted,'cost_usd':metrics['budget_accounted_usd'],'upstream_requests':metrics['upstream_requests'],
            'observed_usage_complete':cost_review['observed_usage_complete'],'cost_accounting':cost_review,
            'accepted':bool(metrics.get('acceptance_passed') and metrics['status']=='done'),'failure_class':failure_class,
            'lifecycle_verified':signal_ok and actual_schemas_ok,
            'events_sha256':sha(out/'agent-events.jsonl') if (out/'agent-events.jsonl').exists() else None,
            'source_sha256':context['source_sha256'],'schemas_sha256':sha(origin/'tool-schemas.json'),
            'selected':selected,'deferred':[r for r in audit if r['kind']=='experience_deferred'],
            'policy_digest':policy_digest,'verified_motif_batches':len(steps),'candidate_job':context['candidate_job'],
            'registry_file':context['registry_file'],'registry_sha256':context['registry_sha256'],'adapter':cfg.get('adapter')}
    file=root/'records'/(session+'.json')
    if file.exists():
        if read(file)!=record:raise ValueError('existing task seal differs; preserve original record')
    else:durable(file,record,exclusive=True)
    with writer_lock(STATE_HOME,'series'):
        pool=read(root/'pool.json');row=pool['runs'][session]
        if accounted:row.update(status='settled',cost_usd=record['cost_usd'],record_sha256=sha(file))
        else:row.update(accounting_incomplete=True)  # Keep the entire conservative reservation.
        durable(root/'pool.json',pool)
    q=root/'queue'/(session+'.json');value={'record_file':str(file),'record_sha256':sha(file),'sealed_after_cost_and_acceptance':True}
    if q.exists():
        if read(q)!=value:raise ValueError('sealed queue entry changed')
    else:durable(q,value,exclusive=True)
    return {'record_file':str(file),'record_sha256':sha(file),'state_root':str(root),'auto_worker':cfg['auto_worker'] and cfg['mode']=='learn' and cfg['role']=='ordinary'}


def launch_worker(config_file, root, environment=None):
    directory=Path(root)/'worker-logs';directory.mkdir(exist_ok=True)
    log=directory/(uuid4().hex+'.log')
    with log.open('xb') as stream:
        process=subprocess.Popen([sys.executable,str(ROOT/'scripts/rsi-worker.py'),'--config',str(config_file),'--drain'],
                                 cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True,env=environment)
    log.chmod(0o600)
    return {'pid':process.pid,'log':str(log)}
