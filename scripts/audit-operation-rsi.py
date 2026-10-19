"""Independent read-only audit of real file operation graphs, effects and costs."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from src.adapters.continuous_rsi import records,source_map,snapshot,ledger_accounting
from src.adapters.continuous_motif_learning import operation_observations,frame
from src.motif_core.offline.operation_graph import catalog,witnesses
from src.motif_core.offline.experience_registry import read,sha,digest,check_motif_certificate
from operation_contract import verify_operations

def need(value,reason):
    if not value:raise ValueError(reason)

def audit(root,experiment=None,output=None):
    root=Path(root).resolve();rr=records(root);pool=read(root/'pool.json');details=[];activations=[];http={};tokens={'cache_hit':0,'cache_miss':0,'output':0};clean={}
    if experiment:
        exp=Path(experiment);p=read(exp/'protocol.json')
        need(sha(exp/'protocol.json')==read(exp/'protocol-lock.json')['sha256'],'protocol changed')
        need(sha(exp/'frozen-driver.py')==p['driver_sha256'],'frozen driver changed')
        need(all(sha(ROOT/'testpdf'/n)==h for n,h in p['original_pdfs'].items()),'original PDF changed')
    for r in rr:
        origin=Path(r['origin']);run=Path(r['run_dir']);file=root/'records'/(r['session_id']+'.json');q=read(root/'queue'/(r['session_id']+'.json'))
        need(q['record_sha256']==sha(file) and q['sealed_after_cost_and_acceptance'],'record/queue mutation')
        need(r['provider_mode']=='real','mock evidence in real experiment')
        spec=read(origin/'task.json');need(spec.get('role') not in ('holdout','evaluate','benchmark'),'final used')
        need(snapshot(origin/'pristine')==spec['initial_snapshot'],'initial material changed')
        need(snapshot(origin/'final-workspace')==snapshot(spec['workspace']),'sealed final material changed')
        sources=read(origin/'source-code.json');need(digest(sources)==r['source_sha256'],'source digest changed')
        need(all(sha(origin/'frozen-source'/n)==h for n,h in sources.items()),'source archive changed')
        if experiment:need(sources==p['source_code'],'experiment source version mismatch')
        need(sha(run/'agent-events.jsonl')==r['events_sha256'],'actual events changed')
        need(sha(origin/'tool-schemas.json')==r['schemas_sha256'],'actual schema changed')
        need(sha(r['registry_file'])==r['registry_sha256'],'in-flight registry changed')
        cost=ledger_accounting(run/'cost-ledger.jsonl',r['metrics']);need(cost['accounting_complete'],'cost unresolved')
        need(pool['runs'][r['session_id']]['status']=='settled','reservation unresolved')
        need(r['upstream_requests']<=96 and r['cost_usd']<=5 and r['metrics']['agent_steps']<=96 and r['metrics'].get('acceptance_repairs',0)<=2,'original limit exceeded')
        ledger=[json.loads(l) for l in (run/'cost-ledger.jsonl').read_text().splitlines()]
        for row in ledger:
            if row.get('kind')=='budget_denied':continue
            status=str(row['response_status']);http[status]=http.get(status,0)+1
            usages=row.get('response_usage') or [];usages=[usages] if isinstance(usages,dict) else usages
            for u in usages:
                tokens['cache_hit']+=u.get('prompt_cache_hit_tokens',0);tokens['cache_miss']+=u.get('prompt_cache_miss_tokens',0);tokens['output']+=u.get('completion_tokens',0)
        events=[json.loads(l) for l in (run/'agent-events.jsonl').read_text().splitlines()];rows=operation_observations(events)
        for row in rows:row['generated']=row['call_id'].startswith('sss-')
        audit_rows=[json.loads(l) for l in (run/'experience-audit.jsonl').read_text().splitlines()] if (run/'experience-audit.jsonl').exists() else []
        generated={v['call_id'] for v in rows if v['generated']};verified={v['call_id'] for v in audit_rows if v['kind']=='operation_model_request_bypassed_verified'}
        need(generated==verified,'unverified or invented graph execution')
        if r['accepted']:
            need(r['lifecycle_verified'],'accepted task lacks original lifecycle')
            delivery=Path(r['delivery']);report=read(delivery/'report.json');review=verify_operations(spec,report,delivery,events)
            need(review['passed'],'independent delivery rejected: '+str(review['errors']))
            need(any(v['name'].endswith('__submit_report') and (v['out'] or {}).get('artifact_sha256')==digest(report) for v in rows),'report lacks original actual receipt')
            if not r['metrics'].get('acceptance_repairs') and r['observed_usage_complete']:
                if sources==source_map():clean[r['session_id']]=frame(r)
                else:
                    task=next(v['out'] for v in rows if v['name'].endswith('__read_task'));scope=task['learning_scope']
                    need(scope['input_sha256']==digest(spec),'original intent scope differs')
                    parents=[]
                    for e in read(r['registry_file'])['entries']:
                        if e['kind']=='operation_graph' and e['entry_id'] in {v['entry_id'] for v in r['selected']}:
                            payload=root/'registry'/e['payload'];need(sha(payload)==e['sha256'],'inherited payload changed');parents.append(read(payload))
                    clean[r['session_id']]={'rows':rows,'tools':catalog(read(origin/'tool-schemas.json')),'scope':scope,'parents':parents,
                                            'fingerprint':r['task_fingerprint'],'record':r}
        details.append({'session_id':r['session_id'],'role':r['role'],'accepted':r['accepted'],'requests':r['upstream_requests'],
                        'cost_usd':r['cost_usd'],'verified_skips':len(verified),'repairs':r['metrics'].get('acceptance_repairs',0),'failure_class':r.get('failure_class')})
    previous=None
    for i,file in enumerate(sorted((root/'events').glob('*.json')),1):
        e=read(file);need(e['sequence']==i and e['previous_sha256']==previous,'broken RSI history');previous=sha(file)
    for file in (root/'learning').glob('*/activation.json'):
        job=file.parent;a=read(file);policy=read(job/'policy.json');cert=job/'certificate.json';check_motif_certificate(policy,cert,sha(job/'policy.json'))
        lock=read(job/'candidate-lock.json');need(sha(job/'compiled.json')==lock['candidate_sha256'] and not lock['holdout_used'] and not lock['certification_used'],'training lock changed')
        training={v['task_fingerprint'] for v in lock['training']};c=read(cert)
        need(not training & {v['task_fingerprint'] for v in [c['native_review'],*c['reviews']]},'certification overlap')
        witnesses_out=[]
        for t in lock['training']:
            need(sha(t['record_file'])==t['record_sha256'],'training record changed');r=read(t['record_file']);need(r['role']=='ordinary','not ordinary evidence')
            f=clean[r['session_id']];matched=[w for w in witnesses(f['rows'],f['tools'],f['scope'],f['parents']) if w['nodes']==policy['artifact']['nodes']]
            need(matched,'graph not derived from original native parameter flow');witnesses_out+=matched
        need(a['certificate_sha256']==sha(cert) and a['registry_sha256']==sha(a['registry_file']),'activation mutated')
        activations.append({'policy_digest':policy['policy_digest'],'nodes':len(policy['artifact']['nodes']),
          'route':[n['tool'].split('__')[-1] for n in policy['artifact']['nodes']],
          'inherited_policies':sorted({w['inherited_policy'] for w in witnesses_out if w['inherited_policy']}),
          'native_new_nodes':[w['native_new_nodes'] for w in witnesses_out]})
    ordinary=[r for r in rr if r['role']=='ordinary'];learning=sum(r['cost_usd'] for r in rr if r['role']!='ordinary')
    value={'status':'passed','integrity_and_mechanical_delivery_only':True,'attempts':len(rr),'ordinary_tasks':len(ordinary),
      'ordinary_passed':sum(r['accepted'] for r in ordinary),'requests':sum(r['upstream_requests'] for r in rr),'cost_usd':sum(r['cost_usd'] for r in rr),
      'learning_cost_usd':learning,'elapsed_run_seconds':sum(r['metrics']['elapsed_seconds'] for r in rr),'http_statuses':http,'tokens':tokens,
      'activations':activations,'details':details,'failed_worker_logs':[str(f) for f in (root/'worker-logs').glob('*.log') if 'Traceback (most recent call last)' in f.read_text()],
      'final_used_for_learning':False,'human_blind_review':False,'actual_bill_verified':False,'current_source':all(read(Path(r['origin'])/'source-code.json')==source_map() for r in rr)}
    output=Path(output) if output else root/'independent-operation-audit.json';need(not output.exists(),'old audit retained; choose a new output')
    output.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');output.chmod(0o600)
    return {k:v for k,v in value.items() if k!='details'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--state-root',type=Path,required=True);p.add_argument('--experiment',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
    print(json.dumps(audit(a.state_root,a.experiment,a.output),ensure_ascii=False))
