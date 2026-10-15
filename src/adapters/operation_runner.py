"""Restart the public Harness around one original durable task; never reset admission."""
import hashlib,json,os,threading,time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from .continuous_rsi import ROOT,private,load_config,enroll,seal,launch_worker,read,sha,source_map,writer_lock
from .operation_budget import OperationBudget,command
from .scenario import prepare_scenario
from .harness_runtime import create_harness
from .deepseek_cost_gate import create_server
from .native_budget import NativeBudgetGuard
from .dsh_client import _usage
from src.motif_core.offline.experience_registry import durable,digest

def initialize_job(file,task,delivery,limits):
    import sys
    sys.path.insert(0,str(ROOT/'scenarios/file-management'))
    if json.loads(Path(task).read_text()).get('management_contract'):
        from management_tools import execution_version as operation_version
    else:
        from operation_tools_v2 import operation_version
    if not Path(file).exists():command(file,'init',{'task_file':str(task),'delivery_root':str(delivery),'execution_version_sha256':operation_version(),
        'limits':{**limits,'max_requests':limits.get('max_requests',limits['max_steps'])}})
    s=command(file,'state')['state']
    if s['task_sha256']!=sha(task) or s['execution_version_sha256']!=operation_version():raise ValueError('frozen durable task/version changed')
    return s

def execute(args,prepared=None):
    import sys
    if not args.call_model and not args.rsi_resume:return {'paid':False,'original_limits':load_config(args.rsi_config)['limits']}
    if args.rsi_resume:
        origin=private(args.rsi_resume);context=read(origin/'enrollment.json');out=private(context['out']);cfg=context['config'];job=private(context['job_file'])
        if read(origin/'source-code.json')!=source_map() or digest(read(context['task_file']))!=digest(read(origin/'task.json')):raise ValueError('original code/task changed; recovery refused')
        original=context['arguments'];args=SimpleNamespace(**{**vars(args),**original,'rsi_config':Path(cfg['config_file']),'scenario':Path(context['scenario_file'])})
        prepared=prepare_scenario(args.scenario)
        if sha(args.scenario)!=context['scenario_sha256'] or digest(prepared['prompt'])!=context['prompt_sha256']:raise ValueError('original scenario/prompt changed; recovery refused')
        env={'FM_TASK_FILE':context['task_file'],'FM_OUTPUT':context['delivery'],'FM_JOB_FILE':str(job)}
        s=command(job,'state')['state'];session=context['session_id']
        if (out/'metrics.json').exists() and (Path(cfg['state_root'])/'queue'/(session+'.json')).exists():return read(out/'metrics.json')
    else:
        cfg=load_config(args.rsi_config);out=ROOT/'.local/runs'/uuid4().hex;out.mkdir(parents=True,mode=0o700)
        env={'FM_TASK_FILE':os.environ['FM_TASK_FILE'],'FM_OUTPUT':os.environ['FM_OUTPUT'],'FM_JOB_FILE':str(out/'operation-job.json')};job=Path(env['FM_JOB_FILE'])
        limits={'budget_usd':args.budget_usd,'max_steps':args.max_steps,'max_output':args.max_output,'max_repairs':cfg['limits']['max_repairs']}
        s=initialize_job(job,Path(env['FM_TASK_FILE']),Path(env['FM_OUTPUT']),limits);session='sss-'+uuid4().hex
        context,_=enroll(args.rsi_config,prepared,session,out,args,env);origin=Path(context['origin'])
    if not args.call_model:return {'paid':False,'original_job':str(job),'requests_used':s['requests'],'spent_usd':s['spent_units']/1e9,'limits':s['limits']}
    with writer_lock(out,'execution'):
        if s['accepted']:
            record=Path(cfg['state_root'])/'records'/(session+'.json')
            if record.exists():metrics=read(record)['metrics']
            elif (out/'metrics.json').exists():metrics=read(out/'metrics.json')
            else:
                ev=[json.loads(l) for l in (out/'agent-events.jsonl').read_text().splitlines()]
                metrics={'status':'done','session_id':session,'acceptance_passed':True,'acceptance_repairs':s['repairs'],'agent_steps':s['steps'],
                  'upstream_requests':s['requests'],'budget_accounted_usd':s['spent_units']/1e9,'original_job':str(job),'elapsed_seconds':None,
                  'attempt_files':[{'file':str(p),'sha256':sha(p),'attempt':p.parent.name} for p in (out/'attempts').glob('*/native-events.jsonl')],
                  'recovered_from_accepted_original_job':True,**_usage(ev)}
            value=seal(context,metrics);saved={**metrics,'continuous_rsi':value,'output_dir':str(out),'no_new_model_requests':True}
            if value['auto_worker']:saved['continuous_rsi']['worker']=launch_worker(args.rsi_config,cfg['state_root'])
            durable(out/'metrics.json',saved);return saved
        state=OperationBudget(job,out/'cost-ledger.jsonl');state.recover(s['execution_version_sha256'],os.getpid())
        attempt=out/'attempts'/uuid4().hex;attempt.mkdir(parents=True,mode=0o700)
        durable(attempt/'started.json',{'original_job':str(job),'source_sha256':context['source_sha256'],'pid':os.getpid()},exclusive=True)
        patches=[prepared['patch'],str(out/'rsi.patch.yml')]
        env.update(SSS_OPERATION_BINDING=str(out/'operation-binding.json'),SSS_EXPERIENCE_BINDING=str(out/'experience-binding.json'),
            SSS_CONTINUOUS_RSI_BINDING=str(out/'rsi-binding.json'),DSH_HOME=str(attempt/'dsh'),SSS_SCENARIO_PRESENTATION='native',SSS_SCENARIO_TOOLS=json.dumps(prepared['allowed_tools']))
        endpoint='https://api.deepseek.com'
        if cfg['provider_mode']=='mock':
            import re
            endpoint=os.environ.get('SSS_MOCK_ENDPOINT','')
            if not re.fullmatch(r'http://127\.0\.0\.1:\d+',endpoint):raise ValueError('mock task requires an explicit local mock endpoint; no cloud fallback')
        gate=create_server('127.0.0.1',0,endpoint,state);thread=threading.Thread(target=gate.serve_forever,daemon=True);thread.start()
        env.update(DEEPSEEK_BASE_URL=f'http://127.0.0.1:{gate.server_port}/v1',SSS_BUDGET_GATE_ACTIVE='1',SSS_BUDGET_CAP_USD=str(args.budget_usd),SSS_BUDGET_LEDGER=str(state.record))
        prior=[json.loads(l) for l in (out/'agent-events.jsonl').read_text().splitlines()] if (out/'agent-events.jsonl').exists() else []
        count=len(prior);guard=NativeBudgetGuard(max_model_requests=max(1,s['limits']['max_steps']-s['steps']),max_observed_input_tokens=None)
        def observe(n):
            nonlocal count
            if n.method=='session.event' and isinstance(n.payload.get('event'),dict):
                e=n.payload['event']
                with (attempt/'native-events.jsonl').open('a') as f:f.write(json.dumps(e,ensure_ascii=False)+'\n')
                count+=1;combined={**e,'seq':count,'original_seq':e['seq'],'durable_attempt':attempt.name}
                with (out/'agent-events.jsonl').open('a') as f:f.write(json.dumps(combined,ensure_ascii=False)+'\n')
                import re
                if e['type']=='tool/result' and re.search(r'connection.*closed|broken pipe|end of stream|server.*terminated|session.*closed',json.dumps(e),re.I):raise RuntimeError('MCP transport interrupted; retain the original job for recovery')
            guard.on_notification(n)
        start=time.monotonic();error=None
        try:
            with create_harness(root=ROOT,patches=tuple(patches),env=env,provider='deepseek-official',model=args.model,max_tokens=args.max_output,
                                cwd=str(out),runtime_cwd=str(out),request_timeout_seconds=900) as h:
                result=h.run(context['prompt'],session_id=session,on_notification=observe)
            (out/'answer.md').write_text(result.final_response)
        except Exception as e:error={'type':type(e).__name__,'message':str(e)[:2000]}
        finally:gate.shutdown();gate.server_close();thread.join(timeout=5)
        s=command(job,'state')['state'];events=[json.loads(l) for l in (out/'agent-events.jsonl').read_text().splitlines()] if (out/'agent-events.jsonl').exists() else []
        attempts=[]
        for a in (out/'attempts').glob('*/native-events.jsonl'):attempts.append({'file':str(a),'sha256':sha(a),'attempt':a.parent.name})
        trace=ROOT/'.local/task-acceptance'/hashlib.sha256(str(job.resolve()).encode()).hexdigest()
        checks=[read(p) for p in sorted(trace.glob('round-*/result.json'))]
        metrics={'status':'done' if s['accepted'] else 'interrupted' if s['status'] in ('running','paused') else s['status'],'output_dir':str(out),
          'session_id':session,'acceptance_passed':s['accepted'],'acceptance_repairs':s['repairs'],'agent_steps':s['steps'],
          'upstream_requests':state.request_count,'budget_accounted_usd':state.reserved_usd,'elapsed_seconds':round(time.monotonic()-start,3),
          'original_job':str(job),'attempt_files':attempts,'acceptance_checks':len(checks),'error':error,**_usage(events)}
        durable(attempt/'outcome.json',metrics,exclusive=True)
        if metrics['status']=='interrupted':
            if s['status']=='running':command(job,'pause')
            metrics['resume_origin']=str(origin);durable(out/'interrupted.json',metrics)
            return metrics
        durable(out/'metrics.json',metrics)
        metrics['continuous_rsi']=seal(context,metrics)
        if metrics['continuous_rsi']['auto_worker']:metrics['continuous_rsi']['worker']=launch_worker(args.rsi_config,cfg['state_root'])
        durable(out/'metrics.json',metrics);return metrics
