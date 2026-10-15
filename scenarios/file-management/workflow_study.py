"""Normal Harness exploration on frozen copies; no automatic learning or holdout use."""
from __future__ import annotations
import argparse,asyncio,importlib.util,importlib.metadata,json,os,platform,shutil,subprocess,sys
from pathlib import Path
from uuid import uuid4
from collections import Counter
from common import ROOT,HERE,DATA,PREFIX,digest,sha,save,snapshot
sys.path.insert(0,str(ROOT))
from experiment import accounting,inspect_schema
from workflow_tools import workflow_version
from recovery_tools import recovery_version
from workflow_contract import verify_workflow
from src.adapters.file_job_budget import job_command
from workflow_prepare import fixture,IDS

PROMPT='''你使用普通DeepSeek Harness完成文件管理任务。先read_task确认权限和必读范围，使用实际MCP证据判断；不读取私有答案或账本，不扩大权限。
只有workflow_contract.allowed_reads内的文件可pin/read。allowed_reads为空时只用目录和哈希元数据；选择文件不强制读取其内容。允许读取的集合如被选定，应以实际source_ids完整collect_reads。图片只有元数据，PDF限已交付范围。
操作必须preview_actions；需要authorization_id时使用实际authorize_plan结果。目标是完整相对文件路径，不能覆盖已有目标。
效果后刷新list_files，submit_report的file_ids包含所有当前身份；gaps按实际待审/缺失项逐一写完整路径。允许无操作直接报告。
恢复目标以read_task.recovery_goal为准；已记录部分计划不得重放，read_task.recovery_state中的原plan_id/authorization_id才能用于restore_plan。恢复不会重置原预算、步骤或修复上限。
'''

def prepare(parent,workflow_ids=None):
    parent=parent.resolve();base=json.loads((parent/'protocol.json').read_text());prior=accounting()
    eid='fm-workflow-explore-20261014-'+uuid4().hex[:8];exp=ROOT/'.local/file-management'/eid;exp.mkdir(parents=True,mode=0o700)
    data=DATA/eid;tasks=[]
    for t in base['tasks']:
        if t['role']!='explore' or (workflow_ids and t['workflow_id'] not in workflow_ids):continue
        td=exp/'tasks'/t['task_id'];td.mkdir(parents=True,mode=0o700)
        pristine=data/'pristine'/t['task_id']
        spec=json.loads((Path(t['task_dir'])/'input-template.json').read_text())
        if workflow_ids and t['workflow_id']=='FM38':
            pristine.mkdir(parents=True,exist_ok=False)
            c,oracle,ops,initial=fixture(pristine,'FM38',t['condition'],eid+' '+t['task_id']+' '+uuid4().hex[:12],None,None)
            save(td/'oracle.json',oracle);spec.update(workflow_contract=c,allowed_operations=ops,initial_snapshot=initial,workflow_oracle_sha256=sha(td/'oracle.json'))
            spec['write_grant'].update(source_paths=c['source_paths'],destination_prefixes=c['destination_prefixes'])
        else:
            shutil.copytree(t['pristine'],pristine);shutil.copyfile(spec['workflow_oracle_file'],td/'oracle.json')
        spec.update(workspace=str(pristine),workflow_oracle_file=str(td/'oracle.json'));save(td/'input-template.json',spec)
        (td/'prompt.md').write_text(PROMPT+'\n本次独立任务：'+t['task_id']+'\n'+spec['objective'],encoding='utf-8')
        cfg=json.loads((Path(t['task_dir'])/'scenario.json').read_text());cfg['prompt']=str(td/'prompt.md');save(td/'scenario.json',cfg)
        tasks.append({'task_id':t['task_id'],'role':'explore','family':t['workflow_id'],'workflow_id':t['workflow_id'],'condition':t['condition'],'task_dir':str(td),
                      'pristine':str(pristine),'input_template_sha256':sha(td/'input-template.json'),'oracle_sha256':sha(td/'oracle.json'),'snapshot_sha256':digest(snapshot(pristine))})
    if not tasks:raise ValueError('no selected exploration material')
    paths=[*HERE.glob('*.py'),*HERE.glob('*.md')]+[ROOT/n for n in ('scripts/run-scenario.py','scripts/validate-file-delivery.py','scripts/check-file-workflow-sdk.py','scripts/check-file-workflows.py',
        'src/adapters/file_job_budget.py','src/adapters/file_workflow_job.ts','src/adapters/dsh_acceptance_guard.ts','src/adapters/scenario.py',
        'src/adapters/deepseek_cost_gate.py','src/adapters/harness_runtime.py','src/adapters/dsh_trajectory.py','config/semantic-sdk.patch.yml','package.json','package-lock.json','requirements.txt')]
    for p in paths:
        dest=exp/'frozen-source'/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest);dest.chmod(0o600)
    protected={t['task_id']:{'snapshot_sha256':t['snapshot_sha256'],'template_sha256':t['input_template_sha256']} for t in base['tasks']}
    protocol={'experiment_id':eid,'parent':str(parent),'data_directory':str(data),'type':'real normal Harness exploration only','tasks':tasks,
              'source_code':{str(p.relative_to(ROOT)):sha(p) for p in paths},'versions':{'workflow':workflow_version(),'recovery':recovery_version()},
              'total_cap_usd':1000,'per_task_cap_usd':5,'batch_cap_usd':5*len(tasks),'max_steps':96,'max_output':4000,'max_repairs':2,'max_cold_restarts':1,
              'model':'deepseek-flash','reasoning_effort':'off','compression_enabled':False,'mode':'baseline','series_before':prior,
              'parent_protected':protected,'original_pdfs':base['original_pdfs'],'price_source':'https://api-docs.deepseek.com/quick_start/pricing/',
              'pricing_checked_client_date':'2026-10-14','peak_usd_per_million':{'cache_hit':0.006,'cache_miss':0.30,'output':1.20},
              'runtime':{'node':subprocess.check_output(['node','--version'],text=True).strip(),'python':platform.python_version(),'os':platform.platform(),
                         'packages':{n:importlib.metadata.version(n) for n in ('deepseek-harness-sdk','mcp','Pillow')}},
              'limitations':['generated text/paths; reused Office/image containers and known PDF copies','mechanical acceptance; semantic blind review not performed','no new Motif learned/certified','parent holdout never run']}
    save(exp/'protocol.json',protocol);save(ROOT/'.local/file-management/workflow-explore-current.json',{'experiment':str(exp)})
    print(json.dumps({'experiment':str(exp),'tasks':len(tasks),'batch_cap_usd':5*len(tasks),'series_before':prior,'paid':False}));return exp

def check_frozen(exp,p):
    for n,h in p['source_code'].items():
        if sha(ROOT/n)!=h:raise ValueError('frozen source changed: '+n)
    for c in p['tasks']:
        td=Path(c['task_dir'])
        if sha(td/'input-template.json')!=c['input_template_sha256'] or sha(td/'oracle.json')!=c['oracle_sha256'] or digest(snapshot(c['pristine']))!=c['snapshot_sha256']:
            raise ValueError('frozen material changed: '+c['task_id'])

def instantiate(exp,c,p):
    td=Path(c['task_dir']);attempt=td/'attempts'/uuid4().hex[:12];attempt.mkdir(parents=True,mode=0o700)
    spec=json.loads((td/'input-template.json').read_text());work=DATA/exp.name/'actual'/c['task_id']/attempt.name
    shutil.copytree(c['pristine'],work);spec['workspace']=str(work);save(attempt/'input.json',spec)
    if c['workflow_id']=='FM38':
        job_command(attempt/'job.json','init',{'task_file':str(attempt/'input.json'),'delivery_root':str(attempt/'delivery'),'execution_version_sha256':recovery_version(),
                   'limits':{'budget_usd':p['per_task_cap_usd'],'max_requests':p['max_steps'],'max_steps':p['max_steps'],'max_output':p['max_output'],'max_repairs':p['max_repairs']}})
    return attempt,spec

def receipt_from(events):
    calls={e['data']['callId']:e['data']['name'] for e in events if e.get('type')=='tool/call'};receipt=None
    for e in events:
        if e.get('type')!='tool/result':continue
        for b in e['data'].get('message',{}).get('content',[]):
            if b.get('type')=='tool-result' and not b.get('isError') and calls.get(b.get('toolCallId'))==PREFIX+'submit_report':
                receipt=json.loads(b['content'][0]['text'])
    return receipt

def run_task(exp,c,p,call_model=False):
    td=Path(c['task_dir']);prior=accounting()
    if list((td/'attempts').glob('*/outcome.json')):raise ValueError('prior outcome retained; prepare a new version for another attempt')
    if prior['estimated_usd']+p['per_task_cap_usd']>p['total_cap_usd']:raise ValueError('series budget insufficient for frozen task cap')
    attempt,spec=instantiate(exp,c,p);env={**os.environ,'FM_TASK_FILE':str(attempt/'input.json'),'FM_OUTPUT':str(attempt/'delivery')}
    if c['workflow_id']=='FM38':env['FM_JOB_FILE']=str(attempt/'job.json')
    entry=HERE/('recovery_tools.py' if c['workflow_id']=='FM38' else 'workflow_tools.py')
    schemas=asyncio.run(inspect_schema(env,entry));save(attempt/'tool-schemas.json',schemas)
    save(attempt/'source-code.json',p['source_code']);save(attempt/'config.json',{'protocol_sha256':sha(exp/'protocol.json'),'input_sha256':digest(spec),
        'schemas_sha256':digest(schemas),'series_before':prior,'max_steps':p['max_steps'],'max_output':p['max_output'],'max_repairs':p['max_repairs'],'budget_usd':p['per_task_cap_usd'],
        'model':p['model'],'reasoning_effort':'off','mode':'baseline','compression_enabled':False,'motif_enabled':False})
    if not call_model:
        save(attempt/'preview.json',{'tools':len(schemas),'task':c['task_id'],'paid':False});print(json.dumps({'preview':c['task_id'],'tools':len(schemas),'paid':False}));return
    loader_spec=importlib.util.spec_from_file_location('workflow_key_loader',ROOT/'scenarios/literature-notes/run-live.py');loader=importlib.util.module_from_spec(loader_spec);loader_spec.loader.exec_module(loader)
    env['DEEPSEEK_API_KEY']=loader.load_key(loader.KEY_FILE,env)
    cmd=[sys.executable,str(ROOT/'scripts/run-scenario.py'),'--scenario',str(td/'scenario.json'),'--model',p['model'],'--mode','baseline',
         '--budget-usd',str(p['per_task_cap_usd']),'--max-steps',str(p['max_steps']),'--max-output',str(p['max_output']),'--call-model']
    if c['workflow_id']=='FM38':cmd.extend(['--file-job',str(attempt/'job.json')])
    print(json.dumps({'starting':c['task_id'],'cap_usd':p['per_task_cap_usd'],'tools':len(schemas)}),flush=True)
    runs=[];all_events=[]
    for segment in range(p['max_cold_restarts']+1):
        save(exp/'progress.json',{'task_id':c['task_id'],'attempt':str(attempt),'segment':segment,'state':'running'})
        result=subprocess.run(cmd,cwd=ROOT,env=env,text=True,capture_output=True)
        save(attempt/f'segment-{segment}.process.json',{'returncode':result.returncode})
        for name,value in [('stdout',result.stdout),('stderr',result.stderr)]:
            f=attempt/f'segment-{segment}.{name}.txt';f.write_text(value,encoding='utf-8');f.chmod(0o600)
        summary=None
        for line in result.stdout.splitlines():
            try:
                value=json.loads(line)
                if isinstance(value,dict) and 'output_dir' in value:summary=value
            except ValueError:pass
        if not summary:raise RuntimeError('runner has no cost summary; retain process logs and reconcile before further calls')
        run=Path(summary['output_dir']);eventfile=run/'agent-events.jsonl';events=[json.loads(l) for l in eventfile.read_text().splitlines()] if eventfile.exists() else []
        runs.append(summary);all_events.extend(events)
        save(attempt/f'segment-{segment}.run.json',summary)
        if segment>=p['max_cold_restarts'] or c['workflow_id']!='FM38' or not spec.get('recovery_crash_after_publish'):break
        checks=[json.loads(f.read_text()) for f in sorted(Path(summary['acceptance_trace_dir']).glob('round-*/result.json'))]
        state=job_command(attempt/'job.json','state')['state']
        if not checks or not checks[-1].get('restart_required') or state['status']!='running':break
        if state['repairs']>p['max_repairs'] or state['spent_units']>=int(p['per_task_cap_usd']*1e9):break
        save(attempt/'cold-restart.json',{'reason':'fixed verifier recorded MCP crash boundary','prior_run':summary['output_dir'],'original_job_sha256':state['task_sha256'],
                                        'requests_before':state['requests'],'repairs_before':state['repairs'],'spent_units_before':state['spent_units'],'task_not_reset':True})
        # A cold MCP preflight validates the recorded footprint and exposes actual prior capability IDs.
        asyncio.run(inspect_schema(env,entry))
        print(json.dumps({'cold_restart':c['task_id'],'original_requests':state['requests'],'original_repairs':state['repairs']}),flush=True)
    report_path=attempt/'delivery/report.json';report=json.loads(report_path.read_text()) if report_path.exists() else None
    final_events=[json.loads(l) for l in (Path(runs[-1]['output_dir'])/'agent-events.jsonl').read_text().splitlines()]
    receipt=receipt_from(final_events);receipt_ok=bool(receipt and report and receipt['artifact_sha256']==digest(report) and receipt['input_sha256']==digest(spec))
    try:review=verify_workflow(spec,report if receipt_ok else None,attempt/'delivery',final_events)
    except Exception as e:review={'passed':False,'errors':[type(e).__name__+': '+str(e)],'human_blind_review':False}
    last=runs[-1];combined={**last,'upstream_requests':sum(r['upstream_requests'] for r in runs),'budget_accounted_usd':sum(r['budget_accounted_usd'] for r in runs),
                         'inputTokens':sum(r.get('inputTokens',0) for r in runs),'cacheReadTokens':sum(r.get('cacheReadTokens',0) for r in runs),'outputTokens':sum(r.get('outputTokens',0) for r in runs),
                         'elapsed_seconds':sum(r['elapsed_seconds'] for r in runs),'segments':len(runs)}
    errors=sum(b.get('isError',False) for e in all_events if e.get('type')=='tool/result' for b in e['data']['message'].get('content',[]))
    out={'task_id':c['task_id'],'role':c['role'],'family':c['family'],'workflow_id':c['workflow_id'],'arm':'H','attempt':str(attempt),'input_sha256':digest(spec),
         'run':combined,'runs':runs,'receipt_verified':receipt_ok,'acceptance':review,'accounting_complete':True,'tool_errors':errors,
         'events_sha256':sha(Path(last['output_dir'])/'agent-events.jsonl'),'source_sha256':digest(p['source_code']),'normal_harness_only':True,'learning_performed':False}
    save(attempt/'outcome.json',out);print(json.dumps({'finished':c['task_id'],'passed':review['passed'],'errors':review['errors'],'requests':combined['upstream_requests'],
        'estimated_usd':combined['budget_accounted_usd'],'segments':len(runs),'tool_errors':errors},ensure_ascii=False),flush=True)
    return out

def summarize(exp):
    outcomes=[json.loads(f.read_text()) for f in exp.glob('tasks/*/attempts/*/outcome.json')]
    summary={'experiment_id':exp.name,'attempts':len(outcomes),'passed':sum(o['acceptance']['passed'] for o in outcomes),
             'failed':sum(not o['acceptance']['passed'] for o in outcomes),'upstream_requests':sum(o['run']['upstream_requests'] for o in outcomes),
             'estimated_usd':sum(o['run']['budget_accounted_usd'] for o in outcomes),'accounting':accounting(),'outcomes':outcomes,
             'learning_performed':False,'new_certification':False,'holdout_runs':0}
    save(exp/'summary.json',summary);return summary

def main():
    a=argparse.ArgumentParser();a.add_argument('--parent',type=Path);a.add_argument('--experiment',type=Path);a.add_argument('--call-model',action='store_true');a.add_argument('--case');a.add_argument('--summary',action='store_true');a.add_argument('--workflows',nargs='+',choices=IDS);args=a.parse_args()
    if not args.experiment:
        parent=args.parent or Path(json.loads((ROOT/'.local/file-management/workflow-current.json').read_text())['experiment']);prepare(parent,args.workflows);return
    exp=args.experiment.resolve();p=json.loads((exp/'protocol.json').read_text())
    if args.summary:print(json.dumps({k:v for k,v in summarize(exp).items() if k!='outcomes'}));return
    check_frozen(exp,p);selected=[c for c in p['tasks'] if (not args.case or c['task_id']==args.case) and not list((Path(c['task_dir'])/'attempts').glob('*/outcome.json'))]
    if not selected:raise ValueError('no unrun exploration task')
    lock=ROOT/'.local/file-management/active.lock'
    with lock.open('x') as f:f.write(exp.name)
    try:
        for c in selected:
            check_frozen(exp,p);run_task(exp,c,p,args.call_model)
            if args.call_model:summarize(exp)
    finally:lock.unlink()

if __name__=='__main__':main()
