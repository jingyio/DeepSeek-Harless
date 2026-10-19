"""Free real MCP structural delivery and recovery guards, on newly created copies."""
import asyncio,copy,importlib.util,json,sys
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scenarios/file-management'));sys.path.insert(0,str(ROOT))
import auto_rsi as rsi
from workflow_prepare import fixture,IDS
from common import DATA,save,sha,snapshot
from src.adapters.file_job_budget import job_command
sp=importlib.util.spec_from_file_location('report_free_mcp',ROOT/'scripts/check-file-workflows.py')
m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)

class ReportConnection(m.Connection):
    async def call(self,name,args=None,reject=False):
        if name=='submit_report':args={**args,'file_ids':[]}
        result=await super().call(name,args,reject)
        if name=='submit_report' and not reject:
            body=rsi.read(self.out/'delivery/report.json');actual=snapshot(self.spec['workspace'])
            ids=sorted('file:local:'+rsi.digest({'path':n,'sha':h})[:24] for n,h in actual.items() if n!='.experiment-copy')
            assert body['file_ids']==ids and body['final_snapshot']==actual
            assert body['structural_provenance']['legacy_hint']['count']==0 and result['artifact_sha256']==rsi.digest(body)
        return result

m.Connection=ReportConnection


async def report_guard(out,spec,kind):
    async with m.Connection(out,spec) as c:
        facts=await c.call('read_task');assert facts['task_result_serialization']['file_ids_owner']=='current_mcp_state'
        if kind=='cancel':job_command(out/'job.json','cancel')
        elif kind=='revoke':job_command(out/'job.json','revoke')
        await c.call('submit_report',{'summary':'unauthorized report probe','file_ids':[], 'gaps':[], 'report_kind':'task_result'},reject=True)
    assert not (out/'delivery/report.json').exists() and snapshot(spec['workspace'])==spec['initial_snapshot']
    return {'status':'passed','guard':'report-'+kind,'real_api_requests':0,'output':str(out)}


def main():
    archive=Path(rsi.read(ROOT/'.local/report-delivery-development-current.json')['directory'])
    exp=archive/('free-workflows-'+uuid4().hex[:8]);exp.mkdir(mode=0o700)
    original=Path(rsi.read(ROOT/'.local/file-management/workflow-current.json')['experiment']);base=rsi.read(original/'protocol.json')
    tasks=[];assets=ROOT/'.local/file-management-author/assets/a';pdfs=sorted((ROOT/'testpdf').glob('*.pdf'))
    for wid,condition in [(w,'N') for w in IDS]+[('FM38','E')]:
        tid='probe-'+wid+'-'+condition;td=exp/'tasks'/tid;pristine=DATA/('fm-report-free-'+uuid4().hex[:8])/tid
        pristine.mkdir(parents=True)
        c,oracle,ops,initial=fixture(pristine,wid,condition,tid+' '+uuid4().hex,assets,pdfs[IDS.index(wid)%3]);save(td/'oracle.json',oracle)
        origin=next(t for t in base['tasks'] if t['workflow_id']==wid and t['condition']==condition and t['role']=='probe')
        spec=copy.deepcopy(rsi.read(Path(origin['task_dir'])/'input-template.json'))
        spec.update(task_id=tid,workspace=str(pristine),initial_snapshot=initial,workflow_contract=c,allowed_operations=ops,
                    workflow_oracle_file=str(td/'oracle.json'),workflow_oracle_sha256=sha(td/'oracle.json'))
        if wid=='FM38':spec['write_grant'].update(source_paths=c['source_paths'],destination_prefixes=c['destination_prefixes'],max_actions=len(c['source_paths']))
        save(td/'input-template.json',spec)
        tasks.append({'task_id':tid,'workflow_id':wid,'condition':condition,'task_dir':str(td),'pristine':str(pristine)})
    save(exp/'protocol.json',{'tasks':tasks,'limits':base['limits'],'real_api_requests':0,'training_permitted':False})
    results=[]
    for t in tasks:
        result=asyncio.run(m.probe(exp,t));results.append(result);print(json.dumps({k:result.get(k) for k in ('workflow_id','condition','status','error')}),flush=True)
    recovery=next(t for t in tasks if t['task_id']=='probe-FM38-N')
    for kind in ('budget','cancel','revoke','input','repair','requests','version'):
        result=asyncio.run(m.guard_probe(exp,recovery,kind));results.append(result)
        print(json.dumps({'guard':kind,'status':result['status'],'error':result.get('error')}),flush=True)
    for kind in ('budget','cancel','revoke'):
        limits={**base['limits'],**({'budget_usd':0} if kind=='budget' else {})}
        out,spec=m.instantiate(exp,recovery,'report-'+kind,limits)
        results.append(asyncio.run(report_guard(out,spec,kind)))
    value={'checks':len(results),'passed':sum(r['status']=='passed' for r in results),'real_api_requests':0,'results':results}
    save(exp/'summary.json',value);print(json.dumps({'checks':value['checks'],'passed':value['passed'],'real_api_requests':0}),flush=True)
    if value['checks']!=value['passed']:raise SystemExit(2)


if __name__=='__main__':main()
