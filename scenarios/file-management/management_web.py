"""Native GeneLoop task binding, sealing and explicit one-plan approval bridge."""
import json,os,shutil,sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(Path(__file__).parent))
from common import sha,digest,save,snapshot
from management_prepare import prepare,PROMPT
from management_tools import ManagementScene,execution_version
from src.adapters.continuous_rsi import STATE_HOME,load_config,initialize,private,writer_lock,enroll,seal,launch_worker
from src.adapters.operation_runner import initialize_job
from src.adapters.scenario import prepare_scenario
from src.motif_core.offline.experience_registry import durable,read

def default_config(real):
    name='daily-management-real-v3' if real else 'daily-management-mock-v3';file=STATE_HOME/(name+'.json')
    with writer_lock(STATE_HOME,'management-profile'):
        if not file.exists():
            workspace=ROOT/'.local/management-copies'/name;workspace.mkdir(parents=True,exist_ok=True,mode=0o700)
            durable(file,{'schema_version':1,'format':'sss-continuous-rsi-v1','adapter':'management_v3','state_root':str(STATE_HOME/name),
              'workspace_roots':[str(workspace)],'mode':'learn' if real else 'observe','provider_mode':'real' if real else 'mock',
              'series_cap_usd':1000,'learning_cap_usd':25,'auto_worker':real,'allow_material_copy':real,
              'limits':{'budget_usd':5,'max_steps':96,'max_output':4000,'max_repairs':2}},exclusive=True)
    initialize(load_config(file));return file

def dispatch(v):
    real=v.get('provider_mode')=='real';config=Path(v['rsi_config']) if v.get('rsi_config') else default_config(real);cfg=load_config(config)
    if cfg['adapter']!='management_v3' or cfg['provider_mode']!=('real' if real else 'mock'):raise ValueError('native management adapter/provider changed')
    action=v['action']
    if action=='status':
        from src.adapters.persistent_file_rsi import status
        return status(config)
    if action=='prepare':
        out=private(v['output']);native=private(v['native_workspace']);owner=v['owner'];wid=v['workspace_id'];task_id=v['task_id']
        work=Path(cfg['workspace_roots'][0])/'workspaces'/digest({'owner':owner,'workspace_id':wid})
        work.mkdir(parents=True,exist_ok=True,mode=0o700);inputs=[]
        for f in v.get('source_files',[]):
            source=private(f['path'])
            if not source.is_relative_to(native/'inputs') or sha(source)!=f['version_sha256']:raise ValueError('native upload approval/version differs')
            name=source.name;target=work/name
            if target.exists() and sha(target)!=f['version_sha256']:target=work/(source.stem+'-'+f['version_sha256'][:10]+source.suffix)
            if target.exists() and sha(target)!=f['version_sha256']:raise ValueError('uploaded copy version collides with an existing file')
            if not target.exists():
                temp=out/'upload-staging'/uuid4().hex;temp.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,temp)
                if sha(temp)!=f['version_sha256']:raise ValueError('upload copy bytes changed')
                os.link(temp,target)
            inputs.append({'name':f['name'],'path':target.name,'sha256':f['version_sha256']})
        directory=out/'management';spec=prepare(directory,work,task_id=task_id,objective=v['objective'],owner=owner,workspace_id=wid,external_roots=v.get('external_roots'),quality=v.get('quality'))
        spec['approved_inputs']=inputs;spec['learning_eligible']=v.get('rsi',True);durable(directory/'input.json',spec)
        spec['rules']['read_only']=v.get('allow_output',True) is False;durable(directory/'input.json',spec)
        durable(native/'file-task.json',spec)
        limits={**cfg['limits'],'budget_usd':v['budget_usd'],'max_output':min(v.get('output_cap',4000),cfg['limits']['max_output']),'max_requests':min(v.get('request_limit',96),cfg['limits']['max_steps'])}
        if v['budget_usd']>cfg['limits']['budget_usd']:raise ValueError('native task budget exceeds original cap')
        job=out/'operation-job.json';initialize_job(job,directory/'input.json',directory/'delivery',limits)
        # Main's native Session preset references this immutable current task.
        durable(native/'management-binding.json',{'directory':str(directory),'task_file':str(directory/'input.json'),'delivery':str(directory/'delivery'),'job_file':str(job)})
        return {'directory':str(directory),'task_file':str(directory/'input.json'),'delivery':str(directory/'delivery'),'job_file':str(job),'rsi_config':str(config),'task_sha256':sha(directory/'input.json'),'prompt':(directory/'prompt.md').read_text()}
    directory=private(v['directory']);spec=read(directory/'input.json');delivery=directory/'delivery'
    if action=='collect':
        if not (delivery/'report.json').exists():return []
        scene=ManagementScene(spec,delivery);scene.guard();native=private(v['native_workspace'])
        export=native/'outputs'/'management'/spec['task_id'];export.mkdir(parents=True,exist_ok=True)
        report=read(delivery/'report.json');rows=[]
        from management_contract import verify_management
        acceptance=verify_management(spec,report,delivery)
        if not acceptance['passed']:raise ValueError('delivery changed before collection')
        summary={'summary':report['summary'],'gaps':report['gaps'],'files':dict(scene.expected_tree['workspace']['files']),'directories':scene.expected_tree['workspace']['directories'],
          'goal_status':acceptance['goal_status'],'goal_checks':acceptance['goal_checks'],'goal_review_reason':acceptance['goal_review_reason'],
          'effect_integrity_verified':acceptance['effect_integrity_verified'],
          'operations':[{'plan_id':k,'actions':scene.plans[k]['actions'],'status':j['status'],'restore_available':not j['irreversible']} for k,j in scene.journals.items()]}
        summary['files'].pop('.experiment-copy',None)
        operation_count=sum(len(scene.plans[k]['actions']) for k,j in scene.journals.items() if j['status']=='executed_verified')
        # Exports are copies; the original effect/recovery journals remain private.
        durable(export/'management-report.json',summary)
        sources=[('management-report.json',export/'management-report.json')]
        for name,h in scene.expected_tree['workspace']['files'].items():
            if name=='.experiment-copy':continue
            target=export/'files'/name;target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists() and sha(target)!=h:raise ValueError('immutable management export changed')
            if not target.exists():shutil.copyfile(scene.root/name,target)
            if sha(target)!=h:raise ValueError('management export source bytes changed')
            sources.append(('files/'+name,target))
        for name in scene.expected_tree['workspace']['directories']:(export/'files'/name).mkdir(parents=True,exist_ok=True)
        for name,f in sources:rows.append({'id':digest({'task':spec['task_id'],'file':name}),'name':name,'path':str(f),'sha256':sha(f),'bytes':f.stat().st_size,**({'operation_count':operation_count,'goal_status':acceptance['goal_status']} if name=='management-report.json' else {})})
        return rows
    if action=='recover':
        from src.adapters.continuous_rsi import source_map
        from src.adapters.operation_budget import command
        context=read(directory/'enrollment.json');origin=Path(context['origin'])
        if read(origin/'source-code.json')!=source_map() or sha(directory/'input.json')!=sha(origin/'task.json'):raise ValueError('original source/task/permission changed; resume refused')
        out=Path(context['out']);s=initialize_job(out/'operation-job.json',directory/'input.json',delivery,cfg['limits'])
        ManagementScene(spec,delivery)
        native=private(v['native_workspace']);durable(native/'file-task.json',spec)
        durable(native/'management-binding.json',{'directory':str(directory),'task_file':str(directory/'input.json'),'delivery':str(delivery),'job_file':str(out/'operation-job.json')})
        return {'already_accepted':s['accepted'],'steps_used':s['steps'],'requests_used':s['requests'],'limits':s['limits']}
    if action=='plan':
        state=read(delivery/'management-state.json');plan=state['plans'].get(v['plan_id'])
        if not plan:raise ValueError('unknown actual management plan')
        restore=v.get('direction')=='restore';key=ManagementScene(spec,delivery).restore_sha(v['plan_id']) if restore else plan['plan_sha256']
        approval=delivery/('restore-approvals' if restore else 'approvals')/f"{v['plan_id']}.json"
        return {'plan_id':plan['plan_id'],'plan_sha256':key,'direction':'restore' if restore else 'execute','actions':plan['actions'],'risks':plan['risks'],'external_paths':{k:r['path'] for k,r in spec.get('external_roots',{}).items()},
          'approved':approval.exists() and read(approval)['plan_sha256']==key,'task_sha256':digest(spec),
          'denied':(delivery/'denials'/(digest({'before':plan['before'],'actions':plan['actions'],'direction':v.get('direction','execute')})+'.json')).exists()}
    if action=='deny':
        plan=read(delivery/'management-state.json')['plans'][v['plan_id']]
        durable(delivery/'denials'/(digest({'before':plan['before'],'actions':plan['actions'],'direction':v.get('direction','execute')})+'.json'),{'plan_sha256':plan['plan_sha256'],'outcome':v['outcome']})
        return {'denial_preserved':True}
    if action=='approve':
        context=read(directory/'enrollment.json');out=Path(context['out']);proof=v['proof']
        events=[json.loads(line) for f in (out/'native-sessions').glob('*.jsonl') for line in f.read_text().splitlines()]
        asked=next((e for e in events if e['type']=='approval/asked' and e['data']['id']==proof['approval_event_id'] and e['data']['callId']==proof['call_id']),None)
        decided=next((e for e in events if e['type']=='approval/decided' and e['data']['id']==proof['approval_event_id'] and e['data']['outcome']=='allowed-once'),None)
        if not asked or not decided or proof['session_id']!=context['actual_session_id']:raise ValueError('actual native user decision not found')
        proof.update(native_asked=asked,native_decided=decided)
        s=ManagementScene(spec,delivery)
        (s.approve_restore if v.get('direction')=='restore' else s.approve)(v['plan_id'],v['plan_sha256'],v['proof']);return {'recorded':True}
    if action=='enroll':
        prepared=prepare_scenario(directory/'scenario.json');out=private(v['output'])
        limits=read(out/'operation-job.json')['limits'];args=SimpleNamespace(scenario=directory/'scenario.json',model='deepseek-flash',budget_usd=v['budget_usd'],max_steps=limits['max_steps'],max_output=limits['max_output'])
        env={'FM_TASK_FILE':str(directory/'input.json'),'FM_OUTPUT':str(delivery),'FM_JOB_FILE':str(out/'operation-job.json'),'SSS_RSI_ACTUAL_SESSION':v['session_id']}
        evidence_id=v['session_id']+'-'+spec['task_id']
        context,_=enroll(config,prepared,evidence_id,out,args,env);durable(directory/'enrollment.json',context)
        return {'context':context,'operation_binding':read(out/'operation-binding.json'),'observer_binding':read(out/'rsi-binding.json'),'observer_binding_sha256':sha(out/'rsi-binding.json')}
    if action=='seal':
        context=read(directory/'enrollment.json');out=Path(context['out'])
        shutil.copyfile(out/'events.jsonl',out/'agent-events.jsonl');shutil.copyfile(out/'ledger.jsonl',out/'cost-ledger.jsonl')
        value=seal(context,v['metrics'])
        if value['auto_worker'] and spec.get('learning_eligible',True):value['worker']=launch_worker(config,cfg['state_root'])
        return value
    if action=='check':
        s=ManagementScene(spec,delivery)
        report=delivery/'report.json'
        if report.exists():
            from management_contract import verify_management
            return verify_management(spec,read(report),delivery)
        return {'passed':False,'errors':['no actual submit_report receipt'],'discussion_only':not s.journals}
    raise ValueError('unknown native management bridge action')

if __name__=='__main__':print(json.dumps(dispatch(json.loads(sys.stdin.read())),ensure_ascii=False))
