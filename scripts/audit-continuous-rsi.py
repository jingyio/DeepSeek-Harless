"""Read-only audit of sealed tasks, independent graph certificates and all fees."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from src.adapters.continuous_rsi import records,source_map,snapshot,ledger_accounting
from src.motif_core.offline.experience_registry import read,sha,digest,check_motif_certificate
from src.adapters.continuous_motif_learning import frame
from report_study import verify_report

def need(value,reason):
    if not value:raise ValueError(reason)

def audit(exp,allow_incomplete=False):
    exp=Path(exp).resolve();p=read(exp/'protocol.json');root=Path(p['state_root'])
    need(sha(exp/'protocol.json')==read(exp/'protocol-lock.json')['sha256'],'protocol mutation')
    if (exp/'frozen-driver.py').exists():need(sha(exp/'frozen-driver.py')==p['driver_sha256'],'frozen driver mutation')
    need(p['source_code']==source_map(),'current execution/learner source changed')
    need(all(sha(ROOT/'testpdf'/n)==h for n,h in p['original_pdfs'].items()),'original PDF mutation')
    rr=records(root);pool=read(root/'pool.json');details=[];tokens={'cache_hit':0,'cache_miss':0,'output':0};statuses={}
    for r in rr:
        file=root/'records'/(r['session_id']+'.json');origin=Path(r['origin']);run=Path(r['run_dir'])
        q=read(root/'queue'/(r['session_id']+'.json'))
        need(q['record_sha256']==sha(file) and q['sealed_after_cost_and_acceptance'],'unsealed/modified record')
        need(r['provider_mode']=='real' and r['lifecycle_verified'],'invalid actual lifecycle')
        spec=read(origin/'task.json');need(spec['role'] not in ('holdout','evaluate','benchmark'),'final material used')
        need(snapshot(spec['workspace'])==spec['initial_snapshot']==snapshot(origin/'pristine'),'source bytes changed')
        sources=read(origin/'source-code.json')
        need(sources==p['source_code'] and all(sha(origin/'frozen-source'/n)==h for n,h in sources.items()),'source archive changed')
        need(sha(run/'agent-events.jsonl')==r['events_sha256'],'native events changed')
        need(sha(origin/'tool-schemas.json')==r['schemas_sha256'],'schema mutation')
        need(sha(r['registry_file'])==r['registry_sha256'],'in-flight library mutation')
        cost=ledger_accounting(run/'cost-ledger.jsonl',r['metrics']);need(cost['accounting_complete'],'unbounded cost')
        need(pool['runs'][r['session_id']]['status']=='settled','budget reservation unresolved')
        need(r['cost_usd']<=5 and r['upstream_requests']<=96 and r['metrics']['agent_steps']<=96,'original bounds exceeded')
        need(r['metrics'].get('acceptance_repairs',0)<=2,'repair allowance exceeded')
        rows=[json.loads(l) for l in (run/'cost-ledger.jsonl').read_text().splitlines()]
        for row in rows:
            if row.get('kind')=='budget_denied':continue
            status=str(row['response_status']);statuses[status]=statuses.get(status,0)+1
            usages=row.get('response_usage') or []
            if isinstance(usages,dict):usages=[usages]
            for usage in usages:
                tokens['cache_hit']+=usage.get('prompt_cache_hit_tokens',0)
                tokens['cache_miss']+=usage.get('prompt_cache_miss_tokens',0)
                tokens['output']+=usage.get('completion_tokens',0)
        if r['accepted']:
            f=frame(r);delivery=Path(r['delivery']);report=read(delivery/'report.json')
            review=verify_report(spec,report,delivery,f['events'])
            need(review['passed'],'independent delivery rejection: '+str(review['errors']))
            submits=[v for v in f['rows'] if v['name']=='mcp__file_management__submit_report' and v['out'].get('artifact_sha256')==digest(report)]
            need(submits,'report lacks actual submit receipt')
        details.append({'session_id':r['session_id'],'role':r['role'],'accepted':r['accepted'],'requests':r['upstream_requests'],
                        'cost_usd':r['cost_usd'],'observed_usage_complete':cost['observed_usage_complete'],
                        'verified_batches':r['verified_motif_batches'],'policy_digest':r['policy_digest']})
    events=sorted((root/'events').glob('*.json'));previous=None
    for i,file in enumerate(events,1):
        row=read(file);need(row['sequence']==i and row['previous_sha256']==previous,'broken state history');previous=sha(file)
    activations=[]
    for file in (root/'learning').glob('*/activation.json'):
        job=file.parent;a=read(file);policy=read(job/'policy.json');cert=job/'certificate.json'
        check_motif_certificate(policy,cert,sha(job/'policy.json'))
        lock=read(job/'candidate-lock.json');need(lock['candidate_sha256']==sha(job/'compiled.json'),'compiled candidate mutation')
        need(lock['source_code']==p['source_code'] and not lock['holdout_used'] and not lock['certification_used'],'invalid training lock')
        training={t['task_fingerprint'] for t in lock['training']};c=read(cert)
        need(all(sha(t['record_file'])==t['record_sha256'] and read(t['record_file'])['role']=='ordinary' for t in lock['training']),'non-ordinary training')
        need(not training & {v['task_fingerprint'] for v in [c['native_review'],*c['reviews']]},'training/certification overlap')
        need(a['certificate_sha256']==sha(cert) and a['registry_sha256']==sha(a['registry_file']),'activation mutation')
        activations.append({'kind':a['kind'],'policy_digest':a['policy_digest'],'job':job.name})
    ordinary=[r for r in rr if r['role']=='ordinary']
    need(len(ordinary)<=p['expected_ordinary_tasks'],'unexpected ordinary tasks')
    if not allow_incomplete:need(len(ordinary)==p['expected_ordinary_tasks'],'incomplete ordinary stream')
    learning_cost=sum(r['cost_usd'] for r in rr if r['role']!='ordinary')
    need(learning_cost<=read(exp/'rsi.json')['learning_cap_usd'],'learning budget exceeded')
    result={'status':'passed','integrity_audit_only':True,'stream_complete':len(ordinary)==p['expected_ordinary_tasks'],
            'planned_ordinary_tasks':p['expected_ordinary_tasks'],'attempts':len(rr),'ordinary_passed':sum(r['accepted'] for r in ordinary),'ordinary_tasks':len(ordinary),
            'requests':sum(r['upstream_requests'] for r in rr),'cost_usd':sum(r['cost_usd'] for r in rr),'learning_cost_usd':learning_cost,
            'elapsed_run_seconds':sum(r['metrics']['elapsed_seconds'] for r in rr),'http_statuses':statuses,'tokens':tokens,
            'activations':activations,'details':details,'final_used_for_learning':False,'actual_bill_verified':False,'human_blind_review':False}
    target=exp/'independent-audit.json';need(not target.exists(),'retain old audit; use a new output for revisions')
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');target.chmod(0o600)
    return {k:v for k,v in result.items() if k!='details'}

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--experiment',type=Path,required=True);a.add_argument('--allow-incomplete',action='store_true');args=a.parse_args()
    print(json.dumps(audit(args.experiment,args.allow_incomplete),ensure_ascii=False))
