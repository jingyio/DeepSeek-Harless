"""Replay certified selections/plans through real MCP and existing TS controllers; zero cloud."""
from __future__ import annotations
import argparse,asyncio,importlib.util,json,os,shutil,subprocess,sys
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scenarios/file-management'));sys.path.insert(0,str(ROOT))
from common import DATA,PREFIX,digest,sha,save,snapshot
from workflow_learning import dependencies,candidate_lock,load_case
from src.adapters.file_job_budget import job_command
sp=importlib.util.spec_from_file_location('workflow_replay_mcp',ROOT/'scripts/check-file-workflows.py');helpers=importlib.util.module_from_spec(sp);sp.loader.exec_module(helpers)
from src.motif_core.offline.plan_compiler import native_rows

class Bridge:
    def __init__(self,kind,policy,task,schemas,out):
        env={k:v for k,v in os.environ.items() if not k.startswith(('DEEPSEEK','OPENAI','SSS_'))}
        self.process=subprocess.Popen(['node',str(ROOT/'scripts/replay-file-workflow-motif.mjs'),kind,str(policy),str(task),str(schemas)],cwd=ROOT,env=env,text=True,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=(out/'controller.stderr').open('w'))
    def ask(self,value):
        self.process.stdin.write(json.dumps(value)+'\n');self.process.stdin.flush();line=self.process.stdout.readline()
        if not line:raise RuntimeError('TS controller exited; inspect retained stderr')
        return json.loads(line)
    def close(self):
        self.process.stdin.close();self.process.wait(timeout=10)

def scope(spec,version,pristine):
    rows=[{'file_id':'file:local:'+digest({'path':n,'sha':h})[:24],'path':n,'extension':Path(n).suffix.lower(),'sha256':h,
           'bytes':(Path(pristine)/n).stat().st_size,'source_version':digest({'path':n,'sha':h,'parser':'fm-parser-v1'})}
          for n,h in spec['initial_snapshot'].items() if n!='.experiment-copy']
    return {'schema_version':1,'task_id':spec['task_id'],'session_id':'offline-replay-'+uuid4().hex,'input_version':digest(spec),
            'snapshot_sha256':digest(spec['initial_snapshot']),'initial_snapshot':spec['initial_snapshot'],'inventory':rows,'inventory_sha256':digest(rows),'execution_version_sha256':version,
            **({'grant':spec['write_grant'],'grant_sha256':digest(spec['write_grant'])} if spec.get('write_grant') else {})}

async def replay(exp,kind,mode):
    p=json.loads((exp/'protocol.json').read_text());candidate_lock(exp);lock=json.loads((exp/'library-lock.json').read_text())
    group='workflow14' if kind=='collection' else 'recovery15'
    if dependencies(group)!=lock['groups'][group]['dependencies']:raise ValueError('outer service dependencies changed; cannot reuse component-only proof')
    record=next(a for a in lock['artifacts'] if a['kind']==kind);policy_path=exp/'libraries'/record['path']
    if sha(policy_path)!=record['sha256']:raise ValueError('certified policy changed')
    policy=json.loads(policy_path.read_text());w=policy['artifact']['validation_witness']
    case=next(c for c in p['tasks'] if c['role']=='certify' and c['task_id']==next(r['task_id'] for r in json.loads((exp/'libraries/result.json').read_text())['certification_reviews'] if r['trace_id']==w['trace_id']))
    if mode=='crash':case=next(c for c in p['tasks'] if c['task_id']=='certify-FM38-E')
    original=next(Path(case['task_dir']).glob('attempts/*/outcome.json'));item,error=load_case(case,original,exp,p)
    if error:raise ValueError('successful independent business acceptance required')
    out=exp/'free-replays'/(kind+'-'+mode+'-'+uuid4().hex[:12]);out.mkdir(parents=True,mode=0o700)
    spec=json.loads((Path(item['outcome']['attempt'])/'input.json').read_text());work=DATA/exp.name/'free-replays'/out.name;shutil.copytree(case['pristine'],work);spec['workspace']=str(work);save(out/'input.json',spec)
    if kind=='plan':job_command(out/'job.json','init',{'task_file':str(out/'input.json'),'delivery_root':str(out/'delivery'),'execution_version_sha256':p['versions']['recovery'],
                    'limits':{'budget_usd':5,'max_requests':96,'max_steps':96,'max_output':4000,'max_repairs':2}})
    task=scope(spec,policy['execution_version_sha256'],case['pristine'])
    if mode=='version':task['input_version']='0'*64
    save(out/'controller-task.json',task);save(out/'tool-schemas.json',item['schemas'])
    bridge=Bridge(kind,policy_path,out/'controller-task.json',out/'tool-schemas.json',out);rows=item['rows'];last=None;executed=[];auth=None
    try:
        async with helpers.Connection(out,spec) as connection:
            await connection.call('read_task');ids=await helpers.listing(connection)
            if kind=='collection':
                # Reproduce only already-approved context prerequisites; the set
                # itself is the actual independent model's certified selection.
                for n in spec['workflow_contract']['context_paths']:
                    handle=await connection.call('pin_file',{'file_id':ids[n]});await connection.call('read_file',{'source_id':handle['source_id']})
                source=next(r for r in rows if r['call_id']==w['references'][0]['call_id']);args=source['args'];result=await connection.call('select_files',args)
                initial={'callId':'certified-model-selection','name':PREFIX+'select_files','arguments':args}
            else:
                source=next(r for r in rows if r['name']==PREFIX+'preview_actions' and r['out']);args=source['args'];result=await connection.call('preview_actions',args)
                initial={'callId':'certified-model-preview','name':PREFIX+'preview_actions','arguments':args}
            last=bridge.ask({'operation':'observe','exec':initial,'result':{'value':{'structuredContent':result}},'changedSchema':mode=='schema'})
            if mode=='revoked':job_command(out/'job.json','revoke')
            for _ in range(96):
                if not last['proposals']:break
                calls=last['proposals']
                for proposal in calls:
                    call=proposal['proposal'];name=call['tool'].removeprefix(PREFIX);args=call['arguments'];executed.append(name)
                    try:
                        if mode=='revoked':body=await connection.call(name,args,reject=True);value={'isError':True}
                        else:
                            body=await connection.call(name,args);value={'value':{'structuredContent':body}}
                            if name=='authorize_plan':auth=body
                    except Exception:
                        if mode!='crash':raise
                        value={'isError':True}
                    last=bridge.ask({'operation':'observe','exec':{'callId':proposal['callId'],'name':call['tool'],'arguments':args},'result':value})
                    # Proposals are batches; consume each issued result before
                    # requesting the next batch so controller pending stays exact.
                if not last['proposals'] and not last['done'] and not last['halted']:last=bridge.ask({'operation':'propose'})
            if mode=='normal':assert last['done'] and not last['halted']
            else:assert last['halted'] and not last['done'] and not last['proposals']
            if mode=='crash':
                assert executed==['authorize_plan','execute_plan']
            elif mode!='normal':assert snapshot(work)==spec['initial_snapshot']
            elif kind=='plan':assert snapshot(work)==json.loads(Path(spec['workflow_oracle_file']).read_text())['expected_snapshot']
            else:
                assert snapshot(work)==spec['initial_snapshot'];assert len(list((out/'delivery/collections').glob('*/summary.json')))==1
            if kind=='plan':
                job=job_command(out/'job.json','state')['state'];assert job['requests']==0 and job['spent_units']==0
        if mode=='crash':
            # The bare stdio MCP client does not reconnect like Harness's native
            # client. Close the dead transport before creating a new connection.
            before=job_command(out/'job.json','state')['state']
            async with helpers.Connection(out,spec) as restarted:
                recovered=await restarted.call('read_task');recorded=next(r for r in recovered['recovery_state'] if r['plan_id']==auth['plan_id'])
                assert recorded['status']=='partial_failure'
                after=job_command(out/'job.json','state')['state']
                assert all(before[k]==after[k] for k in ('requests','steps','spent_units','repairs','pending','status','limits'))
                await restarted.call('restore_plan',{'plan_id':recorded['plan_id'],'authorization_id':recorded['authorization_id']})
                assert snapshot(work)==spec['initial_snapshot']
        save(out/'controller-result.json',last)
        result={'status':'passed','kind':kind,'mode':mode,'real_mcp_and_ts_controller':True,'real_api_requests':0,'estimated_model_cost_usd':0,
                'original_independent_trace_id':item['trace_id'],'actual_automated_calls':executed,'controller_done':last['done'],'controller_halted':last['halted'],
                'handoff_after_crash_without_automatic_retry_or_restore':mode=='crash','fixed_restore_by_replay_program_not_learned':mode=='crash','output':str(out),'not_training':True}
        save(out/'outcome.json',result);return result
    except Exception as e:
        save(out/'outcome.json',{'status':'failed','kind':kind,'mode':mode,'error':type(e).__name__+': '+str(e),'real_api_requests':0,'output':str(out),'controller':last});raise
    finally:bridge.close()

async def main(exp):
    results=[]
    for kind,modes in [('collection',['normal','version','schema']),('plan',['normal','version','schema','revoked','crash'])]:
        for mode in modes:
            r=await replay(exp,kind,mode);results.append(r);print(json.dumps(r),flush=True)
    save(exp/'free-replay-summary.json',{'checks':len(results),'passed':len(results),'results':results,'real_api_requests':0,'estimated_model_cost_usd':0,'not_training':True})

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--experiment',type=Path,required=True);a.add_argument('--crash-only',action='store_true');args=a.parse_args()
    if args.crash_only:print(json.dumps(asyncio.run(replay(args.experiment.resolve(),'plan','crash'))))
    else:asyncio.run(main(args.experiment.resolve()))
