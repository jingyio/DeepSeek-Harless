"""Bounded online composition on fresh development copies. Never opens a holdout task."""
from __future__ import annotations
import argparse,asyncio,hashlib,importlib.util,json,os,shutil,subprocess,sys,threading
from pathlib import Path
from uuid import uuid4
from common import ROOT,HERE,DATA,PREFIX,digest,sha,save,snapshot
sys.path.insert(0,str(ROOT))
from workflow_prepare import fixture
from workflow_study import PROMPT,check_frozen,receipt_from
from workflow_learning import dependencies
from recovery_tools import recovery_version
from plan_tools import execution_version as plan_version
from workflow_contract import verify_workflow
from experiment import accounting,inspect_schema
from src.adapters.file_job_budget import job_command,FileJobBudget
from src.adapters.file_scenario import prepare_scenario
from src.adapters.harness_runtime import create_harness
from src.adapters.native_budget import NativeBudgetGuard
from src.adapters.file_cost_gate import create_server

RUNTIME=['src/adapters/file_entry_motif.ts','src/adapters/dsh_job_plan_gate.ts','src/motif_core/authorized_plan_policy.ts','src/motif_core/online_skill_runtime.mjs']
CASES=[('normal-count2','N',2),('normal-count4','N',4),('stale-runtime','N',3),('permission-denial','N',3),
       ('request-limit','N',3),('acceptance-repair','N',3),('crash-recovery','E',3),('revoke-before-execute','N',3)]

def prepare():
    library=Path(json.loads((ROOT/'.local/file-management/workflow-learning-current.json').read_text())['experiment'])
    lock=json.loads((library/'library-lock.json').read_text());group=lock['groups']['recovery15']
    if group['dependencies']!=dependencies('recovery15') or group['execution_version_sha256']!=recovery_version() or group['plan_component_version_sha256']!=plan_version():raise ValueError('certified outer/component service is stale; do not silently rebind')
    base=Path(json.loads((ROOT/'.local/file-management/workflow-current.json').read_text())['experiment']);bp=json.loads((base/'protocol.json').read_text())
    eid='fm-workflow-online-20261014-'+uuid4().hex[:8];exp=ROOT/'.local/file-management'/eid;exp.mkdir(mode=0o700);tasks=[]
    for tid,condition,count in CASES:
        td=exp/'tasks'/tid;pristine=DATA/eid/'pristine'/tid;pristine.mkdir(parents=True,exist_ok=False)
        c,oracle,ops,initial=fixture(pristine,'FM38',condition,eid+' '+tid+' '+uuid4().hex,None,None)
        for n in c['source_paths'][count:]:(pristine/n).unlink()
        if count>3:
            p=pristine/'inbox/delta.txt';p.write_text(eid+' extra independent bytes');c['source_paths'].append('inbox/delta.txt')
        c['source_paths']=sorted(n for n in c['source_paths'] if (pristine/n).exists());initial=snapshot(pristine)
        mapping={n:f'normalized/txt/item_{i:02d}.txt' for i,n in enumerate(c['source_paths'],1)};expected=dict(initial)
        if condition!='E':
            for n,d in mapping.items():expected[d]=expected.pop(n)
        oracle.update(mapping=mapping,expected_snapshot=expected);save(td/'oracle.json',oracle)
        origin=next(t for t in bp['tasks'] if t['workflow_id']=='FM38' and t['condition']==condition and t['role']=='probe')
        spec=json.loads((Path(origin['task_dir'])/'input-template.json').read_text())
        spec.update(task_id=tid,role='online_development',workspace=str(pristine),initial_snapshot=initial,workflow_contract=c,allowed_operations=ops,
                    workflow_oracle_file=str(td/'oracle.json'),workflow_oracle_sha256=sha(td/'oracle.json'))
        spec['write_grant'].update(source_paths=c['source_paths'],max_actions=count)
        save(td/'input-template.json',spec)
        extra=''
        if tid=='permission-denial':extra='受控拒绝检查：先仅对outside-scope/sentinel.txt尝试preview_actions移动到normalized/txt/forbidden.txt，确认原授权拒绝，不要读取其内容；然后按原任务完成合法重命名。这个尝试不会扩展权限。'
        if tid=='request-limit':extra='逐步调用：先仅read_task，再仅list_files，再仅preview_actions。原请求上限为3；额度耗尽后不得执行或重启任务。此例预期未完成且无文件效果。'
        if tid=='acceptance-repair':extra='受控提前停止测试：当实际execute_plan返回executed_verified后，先结束本轮，只回复“已执行，等待程序验收”，本轮暂不submit_report。收到程序验收修复指令后，再按原任务提交真实报告。这是为了验证一次缺报告的验收失败会触发原Harness修复。'
        (td/'prompt.md').write_text(PROMPT+'\n'+spec['objective']+'\n'+extra,encoding='utf-8')
        cfg=json.loads((Path(origin['task_dir'])/'scenario.json').read_text());cfg['prompt']=str(td/'prompt.md');save(td/'scenario.json',cfg)
        tasks.append({'task_id':tid,'role':'online_development','workflow_id':'FM38','family':'rename','condition':condition,'task_dir':str(td),'pristine':str(pristine),
                      'input_template_sha256':sha(td/'input-template.json'),'oracle_sha256':sha(td/'oracle.json'),'snapshot_sha256':digest(initial),
                      'max_requests':3 if tid=='request-limit' else 96,'budget_usd':5,'expected_delivery':tid not in ('request-limit','revoke-before-execute')})
    # Only this negative case adds a fixed trusted test hook. The public launcher is unchanged.
    plugin=exp/'revoke-test.ts'
    plugin.write_text("import {FileJob} from "+json.dumps((ROOT/'src/adapters/file_workflow_job.ts').as_uri())+";\nimport {observation} from "+json.dumps((ROOT/'src/motif_core/online_skill_runtime.mjs').as_uri())+";\nexport const name='test-revoke-before-execute';export const inject=['agents'];export function apply(ctx:any){let fired=false;ctx.on('agent/created',({agent}:any)=>{agent.ctx.on('tools/result',(exec:any,result:any)=>{if(!fired&&exec.name==='mcp__file_management__authorize_plan'&&observation(result,exec.name)?.status==='task_grant_authorized'){fired=true;new FileJob("+json.dumps(str(ROOT))+",process.env.FM_JOB_FILE!).apply('revoke',{reason:'frozen online negative drill after actual authorization'});}});});}\n")
    patch=exp/'revoke-test.patch.yml';patch.write_text(json.dumps([{'insert':[{'id':'test-revoke-before-execute','name':plugin.as_uri()}]}]))
    launcher=exp/'revoke-launcher.py';launcher.write_text("import importlib.util\ns=importlib.util.spec_from_file_location('public_runner',"+repr(str(ROOT/'scripts/run-file-scenario.py'))+");m=importlib.util.module_from_spec(s);s.loader.exec_module(m)\noriginal=m.create_harness\ndef wrapped(**kwargs):\n kwargs['patches']=tuple(kwargs['patches'])+("+repr(str(patch))+",)\n return original(**kwargs)\nm.create_harness=wrapped\nraise SystemExit(m.main())\n")
    code=[*HERE.glob('*.py'),*HERE.glob('*.md'),*HERE.glob('*.json')]+[ROOT/n for n in RUNTIME+[
        'scripts/run-file-scenario.py','scripts/validate-file-delivery.py','scripts/check-file-workflow-sdk.py','src/adapters/file_workflow_job.ts',
        'src/adapters/file_job_budget.py','src/adapters/file_acceptance_guard.ts','src/adapters/file_scenario.py','src/adapters/file_cost_gate.py',
        'src/adapters/harness_runtime.py','src/adapters/native_budget.py','config/semantic-sdk.patch.yml','package.json','package-lock.json','requirements.txt']]
    for p in code:
        q=exp/'frozen-source'/p.relative_to(ROOT);q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q)
    protocol={'experiment_id':eid,'type':'controlled online development; real model on generated copies, not prospective user quality','tasks':tasks,
              'source_code':{str(p.relative_to(ROOT)):sha(p) for p in code},'versions':{'recovery':recovery_version(),'plan_component':plan_version()},
              'library':str(library),'library_lock_sha256':sha(library/'library-lock.json'),'test_sources':{p.name:sha(p) for p in (plugin,patch,launcher)},
              'total_cap_usd':1000,'per_task_cap_usd':5,'batch_cap_usd':40,'max_steps':96,'max_output':4000,'max_repairs':2,'max_cold_restarts':1,
              'model':'deepseek-flash','reasoning_effort':'off','compression_enabled':False,'series_before':accounting(),
              'original_pdfs':bp['original_pdfs'],'parent':str(base),'parent_protected':{t['task_id']:{'template_sha256':t['input_template_sha256'],'oracle_sha256':t['oracle_sha256'],'snapshot_sha256':t['snapshot_sha256']} for t in bp['tasks']},
              'holdout_runs':0,'learning_performed':False,'runtime':json.loads((library/'protocol.json').read_text())['runtime'],
              'actual_bill_verified':False,'human_blind_review':False}
    save(exp/'protocol.json',protocol);save(ROOT/'.local/file-management/workflow-online-current.json',{'experiment':str(exp)})
    print(json.dumps({'experiment':str(exp),'tasks':len(tasks),'batch_cap_usd':40,'series_before':protocol['series_before'],'paid':False}));return exp

def instantiate(exp,c,p,free=False):
    td=Path(c['task_dir']);out=(exp/'free-checks'/c['task_id'] if free else td/'attempts')/uuid4().hex[:12];out.mkdir(parents=True,mode=0o700)
    spec=json.loads((td/'input-template.json').read_text());work=DATA/exp.name/('free' if free else 'actual')/c['task_id']/out.name
    shutil.copytree(c['pristine'],work);spec['workspace']=str(work);save(out/'input.json',spec)
    job=out/'job.json';state=job_command(job,'init',{'task_file':str(out/'input.json'),'delivery_root':str(out/'delivery'),'execution_version_sha256':recovery_version(),
           'limits':{'budget_usd':c['budget_usd'],'max_requests':c['max_requests'],'max_steps':p['max_steps'],'max_output':p['max_output'],'max_repairs':p['max_repairs']}})['state']
    library=Path(p['library']);lock=json.loads((library/'library-lock.json').read_text());record=next(a for a in lock['artifacts'] if a['kind']=='plan');policy=library/'libraries'/record['path']
    binding={'format':'sss-durable-plan-binding-v1','schema_version':1,'job_file':str(job),'task_sha256':state['task_sha256'],'delivery_root':state['delivery_root'],
             'service_execution_version_sha256':state['execution_version_sha256'],'limits_sha256':digest(state['limits']),
             'library_lock_file':str(library/'library-lock.json'),'library_lock_sha256':p['library_lock_sha256'],'policy_sha256':record['sha256'],
             'runtime_source':{n:sha(ROOT/n) for n in RUNTIME}}
    if c['task_id']=='stale-runtime':binding['runtime_source'][RUNTIME[0]]='0'*64
    save(out/'binding.json',binding)
    sp=importlib.util.spec_from_file_location('plan_scope_helper',ROOT/'scripts/replay-file-workflow-motif.py');helper=importlib.util.module_from_spec(sp);sp.loader.exec_module(helper)
    task=helper.scope(spec,plan_version(),c['pristine']);save(out/'plan-task.json',task)
    env={**os.environ,'FM_TASK_FILE':str(out/'input.json'),'FM_OUTPUT':str(out/'delivery'),'FM_JOB_FILE':str(job)}
    schemas=asyncio.run(inspect_schema(env,HERE/'recovery_tools.py'));save(out/'tool-schemas.json',schemas);save(out/'source-code.json',p['source_code'])
    save(out/'config.json',{'input_sha256':digest(spec),'schemas_sha256':digest(schemas),'protocol_sha256':sha(exp/'protocol.json'),'binding_sha256':sha(out/'binding.json'),
                          'library_lock_sha256':p['library_lock_sha256'],'model':p['model'],'reasoning_effort':'off','compression_enabled':False,'limits':state['limits'],'motif_enabled':True,'learning_performed':False})
    return out,spec,policy,task,env

def real(exp,c,p):
    if c['role']!='online_development':raise ValueError('holdout/other roles forbidden')
    if list(Path(c['task_dir']).glob('attempts/*/outcome.json')):raise ValueError('retained attempt; use new protocol for retry')
    if accounting()['estimated_usd']+c['budget_usd']>1000:raise ValueError('original series budget exhausted')
    out,spec,policy,task,env=instantiate(exp,c,p)
    sp=importlib.util.spec_from_file_location('private_key_loader',ROOT/'scenarios/literature-notes/run-live.py');loader=importlib.util.module_from_spec(sp);sp.loader.exec_module(loader)
    env['DEEPSEEK_API_KEY']=loader.load_key(loader.KEY_FILE,env)
    launcher=exp/'revoke-launcher.py' if c['task_id']=='revoke-before-execute' else ROOT/'scripts/run-file-scenario.py'
    cmd=[sys.executable,str(launcher),'--scenario',str(Path(c['task_dir'])/'scenario.json'),'--model',p['model'],'--mode','baseline','--budget-usd',str(c['budget_usd']),
         '--max-steps',str(p['max_steps']),'--max-output',str(p['max_output']),'--file-job',str(out/'job.json'),'--plan-policy',str(policy),'--plan-task',str(out/'plan-task.json'),'--file-plan-binding',str(out/'binding.json'),'--call-model']
    runs=[];events=[];print(json.dumps({'starting':c['task_id'],'cap_usd':c['budget_usd'],'max_requests':c['max_requests']}),flush=True)
    for segment in range(p['max_cold_restarts']+1):
        save(exp/'progress.json',{'task_id':c['task_id'],'segment':segment,'attempt':str(out),'state':'running'})
        r=subprocess.run(cmd,cwd=ROOT,env=env,text=True,capture_output=True)
        save(out/f'segment-{segment}.process.json',{'returncode':r.returncode})
        for n,v in [('stdout',r.stdout),('stderr',r.stderr)]:f=out/f'segment-{segment}.{n}.txt';f.write_text(v);f.chmod(0o600)
        summary=None
        for line in r.stdout.splitlines():
            try:
                v=json.loads(line)
                if isinstance(v,dict) and 'output_dir' in v:summary=v
            except ValueError:pass
        if not summary:raise RuntimeError('no cost summary; reconcile retained process before further paid calls')
        runs.append(summary);save(out/f'segment-{segment}.run.json',summary)
        file=Path(summary['output_dir'])/'agent-events.jsonl';part=[json.loads(l) for l in file.read_text().splitlines()] if file.exists() else [];events.extend(part)
        checks=[json.loads(f.read_text()) for f in sorted(Path(summary['acceptance_trace_dir']).glob('round-*/result.json'))]
        state=job_command(out/'job.json','state')['state']
        if segment>=p['max_cold_restarts'] or not spec.get('recovery_crash_after_publish') or not checks or not checks[-1].get('restart_required') or state['status']!='running':break
        save(out/'cold-restart.json',{'reason':'actual recorded MCP boundary','before':state,'same_job':True,'motif_must_remain_disabled':True})
        asyncio.run(inspect_schema(env,HERE/'recovery_tools.py'))
    final=runs[-1];file=Path(final['output_dir'])/'agent-events.jsonl';last_events=[json.loads(l) for l in file.read_text().splitlines()] if file.exists() else []
    report_file=out/'delivery/report.json';report=json.loads(report_file.read_text()) if report_file.exists() else None;receipt=receipt_from(last_events)
    receipt_ok=bool(receipt and report and receipt['artifact_sha256']==digest(report) and receipt['input_sha256']==digest(spec))
    review=verify_workflow(spec,report if receipt_ok else None,out/'delivery',last_events)
    combined={**final,'segments':len(runs),**{k:sum(r.get(k,0) for r in runs) for k in ['upstream_requests','budget_accounted_usd','inputTokens','cacheReadTokens','outputTokens','elapsed_seconds','plan_model_requests_bypassed_verified']}}
    state=job_command(out/'job.json','state')['state'];audit=[]
    for run in runs:
        for f in (Path(run['output_dir'])/'.local/online-motif').glob('*.jsonl'):audit.extend(json.loads(l) for l in f.read_text().splitlines())
    unchanged=snapshot(spec['workspace'])==spec['initial_snapshot'];automatic=[e['data'] for e in events if e.get('type')=='tool/call' and e['data']['callId'].startswith('sss-plan-')]
    condition=bool(review['passed'] and state['status']=='completed') if c['expected_delivery'] else bool(not review['passed'] and unchanged and state['status']!='completed')
    if c['task_id'].startswith('normal'):condition &= combined['plan_model_requests_bypassed_verified']==2
    if c['task_id']=='stale-runtime':condition &= not automatic and any(r['kind']=='durable_plan_deferred' for r in audit)
    if c['task_id']=='acceptance-repair':condition &= state['repairs']>=1 and state['motif_disabled']
    if c['task_id']=='crash-recovery':condition &= any(e.get('type')=='tool/call' and e['data']['name']==PREFIX+'restore_plan' and not e['data']['callId'].startswith('sss-') for e in events) and state['motif_disabled']
    if c['task_id']=='revoke-before-execute':condition &= state['status']=='revoked' and len(automatic)==1
    if c['task_id']=='permission-denial':
        forbidden_id='file:local:'+digest({'path':'outside-scope/sentinel.txt','sha':spec['initial_snapshot']['outside-scope/sentinel.txt']})[:24]
        rejected=set(b['toolCallId'] for e in events if e.get('type')=='tool/result' for b in e['data'].get('message',{}).get('content',[]) if b.get('isError'))
        condition &= any(e.get('type')=='tool/call' and e['data']['name']==PREFIX+'preview_actions' and e['data']['callId'] in rejected
            and forbidden_id in json.dumps(e['data'].get('arguments',{})) for e in events)
    tool_errors=sum(b.get('isError',False) for e in events if e.get('type')=='tool/result' for b in e['data'].get('message',{}).get('content',[]))
    result={'task_id':c['task_id'],'role':c['role'],'workflow_id':'FM38','arm':'M-plan-job','attempt':str(out),'input_sha256':digest(spec),'run':combined,'runs':runs,
            'receipt_verified':receipt_ok,'acceptance':review,'condition_passed':condition,'expected_delivery':c['expected_delivery'],'job_final':state,'workspace_unchanged':unchanged,
            'automated_calls':automatic,'audit':audit,'tool_errors':tool_errors,'accounting_complete':True,'normal_harness_only':False,'learning_performed':False,
            'source_sha256':digest(p['source_code']),'events_sha256':sha(file) if file.exists() else None}
    save(out/'outcome.json',result);save(exp/'progress.json',{'task_id':c['task_id'],'state':'finished'})
    print(json.dumps({'finished':c['task_id'],'condition_passed':condition,'delivery_passed':review['passed'],'job_status':state['status'],'requests':combined['upstream_requests'],'estimated_usd':combined['budget_accounted_usd'],'verified_skips':combined['plan_model_requests_bypassed_verified'],'repairs':state['repairs'],'tool_errors':tool_errors}),flush=True)
    return result

def free(exp,c,p):
    # Original SDK/MCP, synthetic SSE only. Uses fresh development inputs; never trains.
    sp=importlib.util.spec_from_file_location('free_sdk_provider',ROOT/'scripts/check-file-workflow-sdk.py');helpers=importlib.util.module_from_spec(sp);sp.loader.exec_module(helpers)
    from http.server import ThreadingHTTPServer
    out,spec,policy,task,env=instantiate(exp,c,p,True);prepared=prepare_scenario(Path(c['task_dir'])/'scenario.json',entry_motif=True)
    task.update(session_id='durable-free-'+uuid4().hex,prompt_sha256=prepared['prompt_sha256']);save(out/'plan-task.json',task)
    server=ThreadingHTTPServer(('127.0.0.1',0),helpers.Provider);server.requests=[];server.other=0;server.stopped_once=False;server.crash=False;server.cold=False
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start();budget=FileJobBudget(out/'job.json',out/'cost-ledger.jsonl')
    gate=create_server('127.0.0.1',0,f'http://127.0.0.1:{server.server_port}',budget);gw=threading.Thread(target=gate.serve_forever,daemon=True);gw.start()
    env.update(DEEPSEEK_API_KEY='mock-no-key',DEEPSEEK_BASE_URL=f'http://127.0.0.1:{gate.server_port}/v1',DSH_HOME=str(out/'dsh'),SSS_BUDGET_GATE_ACTIVE='1',SSS_BUDGET_LEDGER=str(out/'cost-ledger.jsonl'),
               SSS_SCENARIO_PRESENTATION='native',SSS_SCENARIO_TOOLS=json.dumps(prepared['allowed_tools']),SSS_PLAN_MOTIF_POLICY=str(policy),SSS_PLAN_MOTIF_TASK=str(out/'plan-task.json'),SSS_DURABLE_PLAN_BINDING=str(out/'binding.json'))
    for n in ['SSS_ONLINE_MOTIF_MANIFEST','SSS_ONLINE_MOTIF_TASK','SSS_ENTRY_MOTIF_POLICY','SSS_ENTRY_MOTIF_TASK','SSS_TERMINAL_MOTIF_POLICY','SSS_TERMINAL_MOTIF_TASK','SSS_COLLECTION_MOTIF_POLICY','SSS_COLLECTION_MOTIF_TASK','SSS_COLLECTION_SCRIPT','SSS_COLLECTION_SCRIPT_TASK','SSS_REENTRY_MOTIF_POLICY','SSS_REENTRY_MOTIF_TASK']:env[n]=''
    guard=NativeBudgetGuard(max_model_requests=96,max_observed_input_tokens=None);patches=(prepared['patch'],)+( (str(exp/'revoke-test.patch.yml'),) if c['task_id']=='revoke-before-execute' else ())
    error=None;result=None
    try:
        try:
            with create_harness(root=ROOT,patches=patches,env=env,cwd=str(out),runtime_cwd=str(out),provider='deepseek-official',model='deepseek-flash',max_tokens=4000,request_timeout_seconds=120) as client:
                result=client.run(prepared['prompt'],session_id=task['session_id'],on_notification=guard.on_notification)
        except Exception as e:error=type(e).__name__+': '+str(e)
        save(out/'events.json',guard.events);save(out/'mock-requests.json',server.requests);state=job_command(out/'job.json','state')['state']
        logs=list((out/'.local/online-motif').glob('*.jsonl'));audit=[json.loads(l) for f in logs for l in f.read_text().splitlines()];skips=sum(r['kind']=='plan_model_request_bypassed_verified' for r in audit)
        negative=c['task_id'] in ('request-limit','revoke-before-execute')
        passed=bool(state['status']=='completed' and state['repairs']==1 and state['checks']==2 and skips==(0 if c['task_id']=='stale-runtime' else 2)) if not negative else bool(state['status']!='completed' and snapshot(spec['workspace'])==spec['initial_snapshot'] and skips==(1 if c['task_id']=='revoke-before-execute' else 0))
        r={'status':'passed' if passed else 'failed','case':c['task_id'],'real_api_requests':0,'estimated_real_model_cost_usd':0,'actual_sdk_mcp':True,'mock_http_requests':len(server.requests),'job':state,'verified_skips':skips,'error':error,'not_training':True,'output':str(out)}
        save(out/'outcome.json',r);print(json.dumps(r),flush=True)
        if not passed:raise RuntimeError('free SDK condition failed; preserve original output')
        return r
    finally:gate.shutdown();gate.server_close();gw.join(timeout=5);server.shutdown();server.server_close();worker.join(timeout=5)

def summary(exp):
    rows=[json.loads(f.read_text()) for f in exp.glob('tasks/*/attempts/*/outcome.json')];free_rows=[json.loads(f.read_text()) for f in exp.glob('free-checks/*/*/outcome.json')]
    r={'experiment_id':exp.name,'attempts':len(rows),'condition_passed':sum(r['condition_passed'] for r in rows),'delivery_passed':sum(r['acceptance']['passed'] for r in rows),
       'failed_delivery_retained':sum(not r['acceptance']['passed'] for r in rows),'upstream_requests':sum(r['run']['upstream_requests'] for r in rows),'estimated_usd':sum(r['run']['budget_accounted_usd'] for r in rows),
       'verified_skips':sum(r['run']['plan_model_requests_bypassed_verified'] for r in rows),'series':accounting(),'free_passed':sum(r['status']=='passed' for r in free_rows),'free_failures_retained':sum(r['status']!='passed' for r in free_rows),
       'holdout_runs':0,'learning_performed':False,'actual_bill_verified':False,'human_blind_review':False,'outcomes':rows}
    save(exp/'summary.json',r);return r

def main():
    a=argparse.ArgumentParser();a.add_argument('--experiment',type=Path);a.add_argument('--case');a.add_argument('--free-sdk',action='store_true');a.add_argument('--call-model',action='store_true');a.add_argument('--summary',action='store_true');args=a.parse_args()
    if not args.experiment:prepare();return
    exp=args.experiment.resolve();p=json.loads((exp/'protocol.json').read_text())
    if args.summary:print(json.dumps({k:v for k,v in summary(exp).items() if k!='outcomes'}));return
    check_frozen(exp,p)
    for n,h in p['test_sources'].items():
        if sha(exp/n)!=h:raise ValueError('controlled test hook changed')
    selected=[c for c in p['tasks'] if not args.case or c['task_id']==args.case]
    if not selected:raise ValueError('unknown or holdout case')
    lock=ROOT/'.local/file-management/active.lock'
    with lock.open('x') as f:f.write(exp.name)
    try:
        for c in selected:
            check_frozen(exp,p)
            if args.free_sdk:free(exp,c,p)
            elif args.call_model:real(exp,c,p)
            else:
                out,spec,policy,task,env=instantiate(exp,c,p,True);print(json.dumps({'preview':c['task_id'],'tools':15,'binding':str(out/'binding.json'),'paid':False}))
            summary(exp)
    finally:lock.unlink()

if __name__=='__main__':main()
