"""Server-owned Web material/acceptance/RSI bridge; no second model loop."""
import json,os,shutil,sys
from pathlib import Path,PurePosixPath
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(Path(__file__).parent))
from common import DATA,PREFIX,save,snapshot,digest,sha
from operation_tools import TOOLS as V1_TOOLS
from operation_prepare import PROMPT
from operation_contract import VERSION,verify_operations
from src.adapters.scenario import prepare_scenario
from src.adapters.continuous_rsi import load_config,enroll,seal,launch_worker,private

def invoke(v):
    action=v['action'];cfg=load_config(v['rsi_config'])
    if cfg.get('adapter') not in ('file_operations_v1','file_operations_v2'):raise ValueError('Web requires registered file operation learning adapter')
    v2=cfg['adapter']=='file_operations_v2'
    if v2:
        from operation_tools_v2 import TOOLS,OperationSceneV2
    else:TOOLS=V1_TOOLS
    if action=='status':
        from src.adapters.persistent_file_rsi import status
        return status(v['rsi_config'])
    if action=='prepare':
        req=v['request'];output=private(v['output']);source=Path(v['files_dir']).resolve()
        if not source.is_relative_to(DATA.resolve()) or not (source/'.experiment-copy').is_file():raise ValueError('Web source requires authorized experimental copy')
        before=snapshot(source)
        texts=[p['text'] for p in req['content'] if p['type']=='text']
        if len(texts)!=1 or len(req['content'])!=1 or req['resources']:raise ValueError('file tasks require one registered file goal; attachments use a new authorized source copy')
        goal=json.loads(texts[0]);actions=goal['actions']
        if set(goal)-{'actions','require_result_read','objective'} or type(goal.get('require_result_read',True)) is not bool or not isinstance(actions,list) or not 1<=len(actions)<=40:raise ValueError('invalid original file goal')
        for a in actions:
            if set(a)!={'op','source','destination','format'} or a['op'] not in ('copy','move','convert','archive','quarantine'):raise ValueError('invalid original operation grant')
            if a['format'] not in ('none','text','csv') or (a['op']=='convert')!=(a['format']!='none'):raise ValueError('unsupported operation conversion format')
            for key in ('source','destination'):
                if not isinstance(a[key],str) or not a[key] or any(ord(c)<32 for c in a[key]):raise ValueError('invalid relative file path')
                p=PurePosixPath(a[key])
                if p.is_absolute() or '..' in p.parts or '.' in p.parts or '\\' in a[key]:raise ValueError('file path outside registered relative scope')
            if a['source'] not in before or a['source']=='.experiment-copy':raise ValueError('source not registered')
        if len({a['source'] for a in actions})!=len(actions) or len({a['destination'] for a in actions})!=len(actions):raise ValueError('ambiguous repeated source or destination')
        workspace=Path(cfg['workspace_roots'][0])/'web-materials'/req['task_id']
        if workspace.exists():raise ValueError('Web task material already exists')
        shutil.copytree(source,workspace)
        spec={'schema_version':1,'task_id':req['task_id'],'role':'bootstrap','family':'inventory',
          'objective':goal.get('objective') or '完成用户明确授权的文件操作及结果检查。','workspace':str(workspace),'initial_snapshot':snapshot(workspace),
          'rules':{'experimental_copy_only':True},'allowed_operations':sorted({a['op'] for a in actions}),
          'report_contract':{'version':'sss-file-report-v3','kind':'task_result'},
          'operation_contract':{'version':VERSION,'actions':actions,'require_result_read':goal.get('require_result_read',True)}}
        if v2:spec['operation_contract']['validation_version']='sss-file-operation-quality-v2'
        directory=output/'scene';save(directory/'input.json',spec);prompt=PROMPT+'\n用户原始要求：\n'+texts[0]
        (directory/'prompt.md').write_text(prompt)
        job=output/'operation-job.json'
        if v2:
            from src.adapters.operation_runner import initialize_job
            initialize_job(job,directory/'input.json',directory/'delivery',{'budget_usd':req['budget_usd'],'max_steps':v['request_limit'],
              'max_output':v['max_output'],'max_repairs':cfg['limits']['max_repairs']})
        scenario={'schema_version':1,'name':'file_management','prompt':str(directory/'prompt.md'),
          'servers':[{'server_name':'file_management','transport':'stdio','command':sys.executable,'args':[str(ROOT/'scenarios/file-management'/('operation_tools_v2.py' if v2 else 'operation_tools.py'))],
             'cwd':str(ROOT),'env':{'FM_TASK_FILE':str(directory/'input.json'),'FM_OUTPUT':str(directory/'delivery'),**({'FM_JOB_FILE':str(job)} if v2 else {})}}],
          'allowed_tools':[PREFIX+n for n in TOOLS],'acceptance_guard':{'kind':'file_management','max_repairs':cfg['limits']['max_repairs'],
              **({'durable_job':True,'interruptible':True} if v2 else {})}}
        save(directory/'scenario.json',scenario);prepared=prepare_scenario(directory/'scenario.json')
        rows=[*prepared['mcp_rows'],*prepared['agent_plugins']]
        def replace(value):
            if isinstance(value,list):return [replace(x) for x in value]
            if isinstance(value,dict):return {k:replace(x) for k,x in value.items()}
            if value in prepared['environment_references']:
                expr=json.loads(prepared['environment_references'][value][5:]);key=json.loads(expr[len('process.env['):-1])
                return {'FM_TASK_FILE':str(directory/'input.json'),'FM_OUTPUT':str(directory/'delivery'),'FM_JOB_FILE':str(job)}[key]
            return value
        rows=replace(rows);save(directory/'binding.json',{'task_sha256':sha(directory/'input.json'),'files_dir':str(source),'source_snapshot':before})
        return {'directory':str(directory),'prompt':prompt,'rows':rows,'allowed_tools':prepared['allowed_tools'],'task_sha256':sha(directory/'input.json'),
                'sources':[{'resource_id':'file:registered-copy','version':digest(before),'sha256':digest(before)}],**({'job_file':str(job)} if v2 else {})}
    directory=private(v['directory']);spec=json.loads((directory/'input.json').read_text());binding=json.loads((directory/'binding.json').read_text())
    if sha(directory/'input.json')!=binding['task_sha256']:raise ValueError('frozen Web file task changed')
    if action=='check':
        if snapshot(binding['files_dir'])!=binding['source_snapshot'] or snapshot(spec['workspace'])!=spec['initial_snapshot']:raise ValueError('registered source/task version changed before execution')
        return {'task_sha256':binding['task_sha256']}
    if action=='recover':
        if not v2:raise ValueError('this task has no durable recovery binding')
        from src.adapters.operation_budget import command
        from src.adapters.continuous_rsi import source_map
        context=json.loads((directory/'enrollment.json').read_text())
        if json.loads((Path(context['origin'])/'source-code.json').read_text())!=source_map():raise ValueError('original execution source changed; recovery refused')
        s=command(context['job_file'],'state')['state']
        if s['status'] not in ('running','paused') and not s['accepted']:raise ValueError('original task is not recoverable')
        OperationSceneV2(spec,directory/'delivery')
        return {'already_accepted':s['accepted'],'original_limits':s['limits'],'requests_used':s['requests'],'spent_usd':s['spent_units']/1e9}
    if action=='enroll':
        prepared=prepare_scenario(directory/'scenario.json');output=private(v['output'])
        limits=cfg['limits'];args=SimpleNamespace(model='deepseek-flash',budget_usd=v['budget_usd'],max_steps=min(v['request_limit'],limits['max_steps']),
                       max_output=v['max_output'],scenario=directory/'scenario.json')
        env={'FM_TASK_FILE':str(directory/'input.json'),'FM_OUTPUT':str(directory/'delivery'),**({'FM_JOB_FILE':str(output/'operation-job.json')} if v2 else {})}
        context,_=enroll(v['rsi_config'],prepared,v['session_id'],output,args,env);save(directory/'enrollment.json',context)
        return {'operation_binding':json.loads((output/'operation-binding.json').read_text()),'observer_binding':json.loads((output/'rsi-binding.json').read_text()),
                'observer_binding_sha256':sha(output/'rsi-binding.json'),'library_generation':json.loads(Path(context['registry_file']).read_text())['generation'],
                'learning_enabled':cfg['mode']=='learn' and cfg['auto_worker'] and cfg['provider_mode']=='real','learning_cap_usd':cfg['learning_cap_usd']}
    if action=='collect':
        events=[json.loads(l) for l in Path(v['events']).read_text().splitlines()];delivery=directory/'delivery'
        report=json.loads((delivery/'report.json').read_text()) if (delivery/'report.json').exists() else None
        if v2:
            from operation_contract_v2 import verify_operations_v2
            review=verify_operations_v2(spec,report,delivery,events)
        else:review=verify_operations(spec,report,delivery,events)
        if not review['passed']:raise ValueError('file delivery rejected: '+str(review['errors']))
        save(directory/'independent-review.json',review)
        return {'status':'delivered','task_sha256':binding['task_sha256'],'artifact':str(delivery/'report.json'),
                'artifact_sha256':digest(report),'markdown':report['summary'],'gaps':report['gaps'],'gap_count':len(report['gaps']),'claim_count':len(report['file_ids']),
                'outputs':[{'source':a['source'],'path':a['destination'],'operation':a['op'],'sha256':report['final_snapshot'][a['destination']]} for a in spec['operation_contract']['actions']],
                'mechanical_acceptance_passed':True}
    if action=='seal':
        context=json.loads((directory/'enrollment.json').read_text());result=seal(context,v['metrics'])
        if result['auto_worker']:result['worker']=launch_worker(v['rsi_config'],result['state_root'])
        return result
    raise ValueError('unknown file Web binding operation')

if __name__=='__main__':print(json.dumps(invoke(json.load(sys.stdin)),ensure_ascii=False))
