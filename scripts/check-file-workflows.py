"""Actual stdio MCP and fixed acceptance, no provider or paid API. All attempts retained."""
from __future__ import annotations
import argparse,asyncio,copy,json,os,shutil,sys,traceback
from pathlib import Path
from uuid import uuid4
from mcp import Client,StdioServerParameters
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scenarios/file-management'));sys.path.insert(0,str(ROOT))
from common import DATA,digest,save,sha,snapshot
from recovery_tools import recovery_version
from src.adapters.file_job_budget import job_command,FileJobBudget
from src.adapters.scenario import prepare_scenario
import importlib.util
sp=importlib.util.spec_from_file_location('workflow_fixed_acceptance',ROOT/'scripts/validate-file-delivery.py');validator=importlib.util.module_from_spec(sp);sp.loader.exec_module(validator)

def instantiate(exp,t,label='probe',limits=None,version=None):
    uid=label+'-'+uuid4().hex[:12];out=exp/'free-checks'/uid;out.mkdir(parents=True,mode=0o700)
    spec=json.loads((Path(t['task_dir'])/'input-template.json').read_text());work=DATA/exp.name/'checks'/uid
    shutil.copytree(t['pristine'],work);spec['workspace']=str(work);save(out/'input.json',spec)
    if t['workflow_id']=='FM38':
        job_command(out/'job.json','init',{'task_file':str(out/'input.json'),'delivery_root':str(out/'delivery'),
                    'execution_version_sha256':version or recovery_version(),'limits':limits or json.loads((exp/'protocol.json').read_text())['limits']})
    return out,spec

class Connection:
    def __init__(self,out,spec,entry=None):self.out=out;self.spec=spec;self.entry=entry;self.client=None;self.log=out/'mcp-calls.jsonl'
    async def __aenter__(self):
        # Never pass model credentials or remote endpoints to a free MCP child.
        env={k:v for k,v in os.environ.items() if not k.startswith(('DEEPSEEK','OPENAI','SSS_'))}
        env.update(FM_TASK_FILE=str(self.out/'input.json'),FM_OUTPUT=str(self.out/'delivery'),FM_JOB_FILE=str(self.out/'job.json'))
        entry=self.entry or ('recovery_tools.py' if self.spec['workflow_contract']['workflow_id']=='FM38' else 'workflow_tools.py')
        self.context=Client(StdioServerParameters(command=sys.executable,args=[str(ROOT/'scenarios/file-management'/entry)],cwd=ROOT,env=env))
        self.client=await self.context.__aenter__();schemas=await self.client.list_tools()
        save(self.out/'schemas.json',[t.model_dump(mode='json') for t in schemas.tools]);return self
    async def __aexit__(self,*args):return await self.context.__aexit__(*args)
    async def call(self,name,args=None,reject=False):
        args=args or {};row={'name':name,'arguments':args}
        try:
            result=await self.client.call_tool(name,args);row.update(result=result.model_dump(mode='json'),is_error=result.is_error)
            if result.is_error:
                if not reject:raise RuntimeError('unexpected MCP refusal: '+name+' '+str(result.content))
                return {'rejected':True}
            if reject:raise AssertionError('expected tool refusal: '+name)
            return json.loads(result.content[0].text)
        except BaseException as e:row['exception']=type(e).__name__+': '+str(e);raise
        finally:
            with self.log.open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
            self.log.chmod(0o600)

async def listing(c):return {r['path']:r['file_id'] for r in (await c.call('list_files'))['files']}
async def reads(c,paths):
    if not paths:return
    ids=await listing(c);selected=await c.call('select_files',{'file_ids':[ids[n] for n in paths]});rows=[]
    for name in paths:
        pin=await c.call('pin_file',{'file_id':ids[name]});rows.append(await c.call('read_file',{'source_id':pin['source_id']}))
    await c.call('collect_reads',{'collection_id':selected['collection_id'],'source_ids':[r['source_id'] for r in rows]})

def actions(spec,oracle,ids):
    wid=spec['workflow_contract']['workflow_id'];op={'FM01':'move','FM05':'copy','FM13':'copy','FM17':'copy','FM38':'move'}.get(wid)
    if wid=='FM21':return [{'op':'archive','file_ids':[ids[n] for n in oracle['zip_members']],'destination':oracle['zip_path']}]
    used=set();out=[]
    for n,d in oracle['mapping'].items():
        if d in used:continue
        used.add(d);out.append({'op':op,'file_ids':[ids[n]],'destination':d})
    return out

def accept(out,spec,receipt,round_no=0):
    log=[json.loads(l) for l in (out/'mcp-calls.jsonl').read_text().splitlines()]
    return validator.check(out/'input.json',sha(out/'input.json'),out/'delivery',out/'acceptance',round_no,{'receipt':receipt,'events':log})

async def probe(exp,t):
    out,spec=instantiate(exp,t);wid=t['workflow_id'];oracle=json.loads(Path(spec['workflow_oracle_file']).read_text());condition=t['condition']
    try:
        async with Connection(out,spec) as c:
            await c.call('read_task');ids=await listing(c)
            if wid=='FM38':
                for name in spec['workflow_contract']['source_paths']:
                    await c.call('pin_file',{'file_id':ids[name]},reject=True)
            if wid=='FM13':
                await c.call('select_files',{'file_ids':[ids[n] for n in spec['workflow_contract']['source_paths']]},reject=True)
                await reads(c,spec['workflow_contract']['context_paths'])
                await reads(c,spec['workflow_contract']['source_paths'])
            else:await reads(c,spec['workflow_contract']['required_reads'])
            ids=await listing(c);aa=actions(spec,oracle,ids)
            # Permissions and unsupported destinations must reject before any effects.
            if aa:
                wrong=copy.deepcopy(aa[:1]);wrong[0]['destination']='outside-scope/new.txt'
                await c.call('preview_actions',{'actions':wrong},reject=True)
            plan=await c.call('preview_actions',{'actions':aa}) if aa else None
            auth=await c.call('authorize_plan',{'plan_id':plan['plan_id']}) if wid=='FM38' and plan else None
            if wid=='FM38' and condition=='E':
                # Conservative unresolved reservation is synthetic, not an upstream model call.
                budget=FileJobBudget(out/'job.json',out/'synthetic-ledger.jsonl')
                booked=budget.book(json.dumps({'model':'deepseek-flash','max_tokens':4000,'messages':[]}).encode());assert booked
                save(out/'synthetic-reservation.json',{'real_api_requests':0,'purpose':'nonzero pending/counter preservation across actual MCP crash','booking_id':booked[0]})
            if condition=='V':
                source=spec['workflow_contract']['source_paths'][0];(Path(spec['workspace'])/source).write_bytes(b'FROZEN FREE EXTERNAL CHANGE')
                save(out/'fault-injection.json',{'type':'external source bytes change','path':source,'before_sha':spec['initial_snapshot'][source]})
                args={'plan_id':plan['plan_id'],**({'authorization_id':auth['authorization_id']} if auth else {})}
                await c.call('execute_plan',args,reject=True)
                review=accept(out,spec,None);assert not review['passed']
                result={'guard_probe_passed':True,'task_acceptance_passed':False,'business_outcome':'stopped_on_external_change'}
            elif wid=='FM38' and condition=='E':
                try:await c.call('execute_plan',{'plan_id':plan['plan_id'],'authorization_id':auth['authorization_id']})
                except Exception:pass
                else:raise AssertionError('actual MCP process did not terminate at frozen crash boundary')
                save(out/'crash-boundary.json',{'actual_process_exit_expected':75,'before_restart_job':job_command(out/'job.json','state')['state']})
                result={'needs_restart':True}
            else:
                if plan:
                    kw={'plan_id':plan['plan_id'],**({'authorization_id':auth['authorization_id']} if auth else {})}
                    receipt=await c.call('execute_plan',kw);assert await c.call('execute_plan',kw)==receipt
                if wid=='FM17':
                    ids=await listing(c);aa=[{'op':'copy','file_ids':[ids[n]],'destination':'recovery-drill/'+n[len('backup-set/'):]} for n in oracle['backup_sources']]
                    p=await c.call('preview_actions',{'actions':aa});await c.call('execute_plan',{'plan_id':p['plan_id']})
                if wid=='FM38':result={'needs_restart':True,'executed_receipt':receipt}
                else:
                    ids=await listing(c);receipt=await c.call('submit_report',{'summary':'Free scripted effect check; semantic quality not assessed','file_ids':list(ids.values()),'gaps':oracle['required_gap_markers'],'report_kind':'task_result'})
                    review=accept(out,spec,receipt);assert review['passed'],review['errors']
                    result={'task_acceptance_passed':True,'business_outcome':'scripted_fixture_postconditions'}
        if result.get('needs_restart'):
            if condition=='E':
                round_no=job_command(out/'job.json','begin-check')['round']
                failed=accept(out,spec,None,round_no);assert not failed['passed']
                job_command(out/'job.json','repair',{'reason':'actual interrupted file state failed acceptance'})
            before=job_command(out/'job.json','state')['state']
            async with Connection(out,spec) as c:
                await c.call('read_task')
                current=job_command(out/'job.json','state')['state']
                assert all(before[k]==current[k] for k in ('requests','steps','repairs','spent_units','pending'))
                kw={'plan_id':plan['plan_id'],'authorization_id':auth['authorization_id']}
                if condition=='E':
                    await c.call('execute_plan',kw,reject=True);await c.call('restore_plan',kw)
                else:assert await c.call('execute_plan',kw)==result['executed_receipt']
                ids=await listing(c);receipt=await c.call('submit_report',{'summary':'Restart preserved exact task authority; actual bytes verified','file_ids':list(ids.values()),'gaps':[],'report_kind':'task_result'})
                round_no=job_command(out/'job.json','begin-check')['round']
                review=accept(out,spec,receipt,round_no);assert review['passed'],review['errors']
                job_command(out/'job.json','accept',{'round':round_no})
            after=job_command(out/'job.json','state')['state']
            assert all(before[k]==after[k] for k in ('requests','steps','repairs','spent_units'))
            result={'task_acceptance_passed':True,'actual_mcp_restart':True,'actual_crash_boundary':condition=='E',
                    'nonzero_counters_and_pending_preserved':condition=='E','job_before_restart':before,'job_after_acceptance':after,
                    'synthetic_reservations_not_model_cost':True,'business_outcome':'rolled_back' if condition=='E' else 'completed_idempotently'}
        result.update(status='passed',workflow_id=wid,condition=condition,real_api_requests=0,estimated_model_cost_usd=0,
                      scripted_selection_not_training=True,output=str(out));save(out/'outcome.json',result);return result
    except BaseException as e:
        result={'status':'failed','workflow_id':wid,'condition':condition,'error':type(e).__name__+': '+str(e),'traceback':traceback.format_exc(),'real_api_requests':0,'output':str(out)}
        save(out/'outcome.json',result);return result

async def guard_probe(exp,t,kind):
    limits=dict(json.loads((exp/'protocol.json').read_text())['limits'])
    if kind=='budget':limits['budget_usd']=0
    if kind=='requests':limits['max_requests']=2
    out,spec=instantiate(exp,t,'guard-'+kind,limits=limits);job=out/'job.json'
    try:
        async with Connection(out,spec) as c:
            await c.call('read_task');ids=await listing(c);oracle=json.loads(Path(spec['workflow_oracle_file']).read_text());aa=actions(spec,oracle,ids)
            if kind=='cancel':job_command(job,'cancel')
            elif kind=='revoke':job_command(job,'revoke')
            elif kind=='input':
                changed=copy.deepcopy(spec);changed['rules']['unauthorized_change']=True;save(out/'input.json',changed)
            elif kind=='repair':
                job_command(job,'begin-check');job_command(job,'repair');job_command(job,'begin-check');job_command(job,'repair');job_command(job,'begin-check')
                try:job_command(job,'repair')
                except ValueError:assert job_command(job,'state')['state']['status']=='failed'
                else:raise AssertionError('third repair admitted')
            elif kind=='requests':
                state=FileJobBudget(job,out/'synthetic-ledger.jsonl')
                for _ in range(limits['max_requests']):
                    booking=state.book(json.dumps({'model':'deepseek-flash','max_tokens':1,'messages':[]}).encode());assert booking
                    state.settle(booking[0],booking[1],503,{})
                assert state.book(json.dumps({'model':'deepseek-flash','max_tokens':1,'messages':[]}).encode()) is None
            elif kind=='version':
                job_command(job,'pause')
                try:job_command(job,'resume',{'execution_version_sha256':'0'*64})
                except ValueError:pass
                else:raise AssertionError('changed execution version resumed')
            await c.call('preview_actions',{'actions':aa},reject=True)
        assert snapshot(spec['workspace'])==spec['initial_snapshot']
        result={'status':'passed','guard':kind,'real_api_requests':0,'synthetic_reservations_not_model_cost':True,'output':str(out)}
    except BaseException as e:result={'status':'failed','guard':kind,'error':str(e),'traceback':traceback.format_exc(),'real_api_requests':0,'output':str(out)}
    save(out/'outcome.json',result);return result

async def capacity_probe(exp,kind):
    uid='capacity-'+kind+'-'+uuid4().hex[:10];out=exp/'free-checks'/uid;out.mkdir(parents=True,mode=0o700)
    work=DATA/exp.name/'checks'/uid;work.mkdir(parents=True);(work/'.experiment-copy').write_text(uid)
    for i in range(40):(work/f'f{i:02d}.txt').write_text(f'capacity {i}')
    paths=[f'f{i:02d}.txt' for i in range(40)]
    spec={'schema_version':1,'task_id':uid,'family':'capacity_probe','objective':'free tool capacity only, no business success claim','rules':{},'workspace':str(work),
          'initial_snapshot':snapshot(work),'allowed_operations':['copy','archive']}
    entry='file_tools.py'
    if kind.startswith('selection'):
        entry='workflow_tools.py';spec.update(report_contract={'version':'sss-file-report-v3','kind':'task_result'},workflow_contract={'version':'sss-file-workflow-v1',
            'workflow_id':'FM05','source_paths':paths[:32],'allowed_reads':paths[:32],'required_reads':[],'context_paths':[],'destination_prefixes':['processed/']})
    if kind=='plan6_7':
        entry='plan_tools.py';spec['write_grant']={'schema_version':1,'allowed_ops':['copy'],'source_paths':paths,'destination_prefixes':['processed/'],'max_actions':6,'allow_restore':True}
    save(out/'input.json',spec)
    try:
        async with Connection(out,spec,entry) as c:
            await c.call('read_task');ids=await listing(c)
            if kind.startswith('selection'):
                count=32 if kind=='selection32_33' else int(kind[len('selection'):])
                selected=await c.call('select_files',{'file_ids':[ids[n] for n in paths[:count]]})
                if count<=9:
                    handles=[]
                    for n in paths[:count]:
                        pin=await c.call('pin_file',{'file_id':ids[n]});await c.call('read_file',{'source_id':pin['source_id']});handles.append(pin['source_id'])
                    await c.call('collect_reads',{'collection_id':selected['collection_id'],'source_ids':handles})
                if kind=='selection32_33':await c.call('select_files',{'file_ids':[ids[n] for n in paths[:33]]},reject=True)
            elif kind=='archive30_31':
                await c.call('preview_actions',{'actions':[{'op':'archive','file_ids':[ids[n] for n in paths[:30]],'destination':'processed/valid.zip'}]})
                await c.call('preview_actions',{'actions':[{'op':'archive','file_ids':[ids[n] for n in paths[:31]],'destination':'processed/invalid.zip'}]},reject=True)
            else:
                count=6 if kind=='plan6_7' else 40
                aa=[{'op':'copy','file_ids':[ids[n]],'destination':'processed/'+n} for n in paths[:count]]
                await c.call('preview_actions',{'actions':aa})
                extra=aa+[{'op':'copy','file_ids':[ids[paths[-1]]],'destination':'processed/extra.txt'}]
                await c.call('preview_actions',{'actions':extra},reject=True)
        assert snapshot(work)==spec['initial_snapshot']
        result={'status':'passed','capacity':kind,'entry':entry,'real_api_requests':0,'no_effects':True,'motif_batch_size_not_certified_here':True,'output':str(out)}
    except Exception as e:result={'status':'failed','capacity':kind,'error':str(e),'traceback':traceback.format_exc(),'real_api_requests':0,'output':str(out)}
    save(out/'outcome.json',result);return result

async def main_async(exp):
    protocol=json.loads((exp/'protocol.json').read_text());attempt=exp/'check-runs'/uuid4().hex;attempt.mkdir(parents=True,mode=0o700)
    results=[]
    for t in protocol['tasks']:
        if t['role']=='probe':
            result=await probe(exp,t);results.append(result);print(json.dumps({k:result[k] for k in ('status','workflow_id','condition')}),flush=True)
    base=next(t for t in protocol['tasks'] if t['task_id']=='probe-FM38-N')
    for kind in ('budget','cancel','revoke','input','repair','requests','version'):
        result=await guard_probe(exp,base,kind);results.append(result);print(json.dumps({'guard':kind,'status':result['status']}),flush=True)
    for kind in ('selection0','selection1','selection8','selection9','selection32_33','actions40_41','archive30_31','plan6_7'):
        result=await capacity_probe(exp,kind);results.append(result);print(json.dumps({'capacity':kind,'status':result['status']}),flush=True)
    for t in protocol['tasks']:
        assert sha(Path(t['task_dir'])/'input-template.json')==t['input_template_sha256']
        assert digest(snapshot(t['pristine']))==t['snapshot_sha256']
    summary={'experiment_id':exp.name,'checks':len(results),'passed':sum(r['status']=='passed' for r in results),'failed':sum(r['status']=='failed' for r in results),
             'results':results,'real_api_requests':0,'estimated_model_cost_usd':0,'holdout_pristine_unchanged':True,'motif_learning_runs':0,'human_semantic_review':False}
    save(attempt/'summary.json',summary);save(exp/'latest-free-check.json',{'summary':str(attempt/'summary.json')});print(json.dumps({'summary':str(attempt/'summary.json'),'passed':summary['passed'],'failed':summary['failed'],'real_api_requests':0}))
    return 0 if not summary['failed'] else 2

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--experiment',type=Path);a=p.parse_args();exp=a.experiment or Path(json.loads((ROOT/'.local/file-management/workflow-current.json').read_text())['experiment'])
    raise SystemExit(asyncio.run(main_async(exp.resolve())))
