"""Independent fifth-stage audit: original events, split/library hashes, HTTP, coverage and final bytes."""
import argparse,json,hashlib,math,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scenarios/file-management'));sys.path.insert(0,str(ROOT))
from common import digest,sha,save,snapshot,PREFIX
from src.motif_core.offline.reentry_compiler import reentry_witness

def main():
 p=argparse.ArgumentParser();p.add_argument('--experiment',type=Path,required=True);a=p.parse_args();exp=a.experiment.resolve();protocol=json.loads((exp/'protocol.json').read_text());parent=json.loads((exp/'L1/policy.json').read_text());child=json.loads((exp/'L2/policy.json').read_text());learning=json.loads((exp/'L2/learning-result.json').read_text())
 assert sha(exp/'L1/policy.json')==protocol['L1_sha256'];assert digest(parent)==digest(child['parent_policy']);assert all(sha(exp/'frozen-source'/n)==h for n,h in protocol['source_code'].items())
 lock=json.loads((exp/'holdout-library-lock.json').read_text());assert sha(exp/'L2/policy.json')==lock['L2_sha256'] and sha(exp/'L1/policy.json')==lock['L1_sha256']
 assert child['policy_digest']==digest({k:v for k,v in child.items() if k!='policy_digest'});assert learning['L1_digest']==parent['policy_digest'] and learning['L2_digest']==child['policy_digest']
 trained={e['trace_id'] for e in child['artifact']['training_episodes']}|{child['artifact']['validation_episode']['trace_id']};rows=[];schemas=set();triples={};order=[];source_proofs=[];runtime_reads={'L1':0,'L2':0};stage2_reads=0;boundary_count=0
 for c in protocol['tasks']:
  td=Path(c['task_dir']);spec=json.loads((td/'input.json').read_text());assert digest(spec)==c['input_sha256']
  if c['role']=='evaluate':triples.setdefault(c['pair_id'],[]).append((digest(spec),sha(td/'prompt.md')))
  outcomes=list(td.glob('attempts/*/outcome.json'))
  for op in outcomes:
   o=json.loads(op.read_text());attempt=op.parent;m=o['run'];run=Path(m['output_dir']);cfg=json.loads((attempt/'config.json').read_text())
   assert json.loads((attempt/'execution-source-code.json').read_text())==protocol['source_code'];assert all(protocol['source_code'][n]==h for n,h in json.loads((attempt/'source-code.json').read_text()).items());schemas.add(digest(json.loads((attempt/'tool-schemas.json').read_text())))
   if c['arm']=='L1':assert cfg['collection_policy_sha256']==lock['L1_sha256']
   if c['arm']=='L2':assert cfg['reentry_policy_sha256']==lock['L2_sha256']
   if c['role']=='evaluate':assert run.name not in trained;order.append((cfg['series_before']['estimated_usd'],c['task_id']))
   assert sha(run/'agent-events.jsonl')==o['events_sha256'];events=[json.loads(l) for l in (run/'agent-events.jsonl').read_text().splitlines()];calls={e['data']['callId']:e for e in events if e['type']=='tool/call'};results={b['toolCallId']:(e,b) for e in events if e['type']=='tool/result' for b in e['data']['message'].get('content',[]) if b.get('type')=='tool-result'}
   final=json.loads((attempt/'final-copy.json').read_text());assert snapshot(final['path'])==final['snapshot']==spec['initial_snapshot']
   ledger=[json.loads(l) for l in (run/'cost-ledger.jsonl').read_text().splitlines()];assert len(ledger)==m['upstream_requests'];cost=0
   for r in ledger:
    assert r['response_status']==200;u=r['response_usage'];assert u['prompt_tokens']==u['prompt_cache_hit_tokens']+u['prompt_cache_miss_tokens'];cost+=(u['prompt_cache_hit_tokens']*.006+u['prompt_cache_miss_tokens']*.3+u['completion_tokens']*1.2)/1e6
   assert math.isclose(cost,m['budget_accounted_usd'],abs_tol=1e-12)
   for field,key in [('outputTokens','completion_tokens'),('inputTokens','prompt_cache_miss_tokens'),('cacheReadTokens','prompt_cache_hit_tokens')]:assert m[field]==sum(r['response_usage'][key] for r in ledger)
   source_ids=[cid for cid,e in calls.items() if e['data']['name']==PREFIX+'select_files' and cid in results and not results[cid][1].get('isError')]
   source_ids.sort(key=lambda cid:calls[cid]['seq'])
   for cid in source_ids:
    assert not cid.startswith('sss-');assert any(e['type']=='assistant/message' and e['data'].get('usage') and e['data']['message'].get('source',{}).get('kind')=='model' and any(b.get('id')==cid for b in e['data']['message'].get('content',[])) for e in events)
   ap=run/'.local/online-motif'/(hashlib.sha256(m['session_id'].encode()).hexdigest()+'.jsonl');log=[json.loads(l) for l in ap.read_text().splitlines()] if ap.exists() else [];generated={cid:e for cid,e in calls.items() if cid.startswith('sss-')}
   if c['arm']=='H':assert not generated
   else:
    loaded=[r for r in log if r['kind'] in ('collection_motif_loaded','reentry_motif_loaded')];assert len(loaded)==1;assert loaded[0]['policy_digest']==(parent['policy_digest'] if c['arm']=='L1' else child['policy_digest'])
    batches=[r for r in log if r['kind']=='collection_model_request_bypassed_verified'];assert len(batches)==m['collection_model_requests_bypassed_verified'];assert sum(r['count'] for r in batches)<=len(generated);attempted=[r for r in log if r['kind']=='collection_motif_bypass_attempt'];assert {cid for r in attempted for cid in r['call_ids']}==set(generated)
    reads=[r for r in log if r['kind']=='collection_motif_read_verified'];runtime_reads[c['arm']]+=len(reads)
    for r in reads:
     e,b=results[r['call_id']];out=json.loads(b['content'][0]['text']);call=calls[r['call_id']]['data'];assert not b.get('isError') and digest(out)==r['observation_sha256'];assert json.loads(call['arguments'])=={'source_id':out['source_id']};assert out['file_id']==r['file_id'] and out['source_version']==r['source_version']
     if c['arm']=='L1' and o['acceptance']['passed']:assert out['path'].startswith('stage_a/')
     if c['arm']=='L2' and r.get('library_epoch')==2:
      if o['acceptance']['passed']:assert out['path'].startswith('stage_b/')
      stage2_reads+=1
    if c['arm']=='L2':
     second=[r for r in log if r['kind']=='reentry_epoch_batch_verified'];assert len(second)==m['reentry_epoch_batches_verified'];assert len(second)==sum(r.get('library_epoch')==2 for r in batches)
     frontiers=[r for r in log if r['kind']=='reentry_model_frontier_observed'];assert len(frontiers)<=1
     if frontiers:
      fid=frontiers[0]['call_id'];assert fid in calls and not fid.startswith('sss-') and calls[fid]['data']['name']==PREFIX+'select_files'
      if fid in source_ids:assert fid==source_ids[1]
      else:assert results[fid][1].get('isError') and any(r['kind']=='reentry_deferred' or r['kind']=='collection_motif_deferred' for r in log)
      boundary_count+=1
    if run.name in trained:
     scope=json.loads((td/'scope.json').read_text());fingerprint=next(e['task_fingerprint'] for e in [*child['artifact']['training_episodes'],child['artifact']['validation_episode']] if e['trace_id']==run.name)
     recomputed=reentry_witness(events,scope,parent,log,run.name,fingerprint)
     recorded=next(e for e in [*child['artifact']['training_episodes'],child['artifact']['validation_episode']] if e['trace_id']==run.name)
     assert digest(recomputed['residual_witness'])==digest(recorded['residual_witness']);assert recomputed['parent_boundary']==recorded['parent_boundary']
   for packet_path in (attempt/'delivery/collections').glob('*/summary.json'):
    packet=json.loads(packet_path.read_text());assert packet['coverage_sha256']==digest(packet['files'])
    for r in packet['files']:
     actual=json.loads((attempt/'delivery/reads'/f"{r['source_id']}.json").read_text());assert digest(actual)==r['read_sha256']
   report=json.loads((attempt/'delivery/report.json').read_text());published=[json.loads(b['content'][0]['text']) for cid,(e,b) in results.items() if calls[cid]['data']['name']==PREFIX+'submit_report' and not b.get('isError')];assert published[-1]['artifact_sha256']==digest(report)
   rows.append({'task':c['task_id'],'role':c['role'],'arm':c['arm'],'accepted':o['acceptance']['passed'],'requests':len(ledger),'cost':cost,'tool_errors':o['tool_errors']});source_proofs.append({'task':c['task_id'],'model_selections':source_ids})
 assert len(schemas)==1;assert all(len(v)==3 and len(set(v))==1 for v in triples.values());assert [n for _,n in sorted(order)]==[c['task_id'] for c in protocol['tasks'] if c['role']=='evaluate' and list(Path(c['task_dir']).glob('attempts/*/outcome.json'))]
 assert trained=={r['trace_id'] for r in child['artifact']['training_episodes']}|{child['artifact']['validation_episode']['trace_id']};assert not learning['runtime_parameter_nodes_used_for_learning'] and not learning['holdout_used_for_learning']
 result={'audited':len(rows),'heldout_triples':len(triples),'L1_unchanged':True,'new_native_training_recomputed':len(trained),'holdout_training_overlap':False,'runtime_parameter_training':False,'runtime_reads':runtime_reads,'L2_second_stage_reads':stage2_reads,'actual_model_reentry_boundaries':boundary_count,'input_prompt_schema_source_final_http_verified':True,'actual_bill_verified':False,'human_blind_review':False,'rows':rows,'source_proofs':source_proofs};save(exp/'independent-audit.json',result);print(json.dumps({k:v for k,v in result.items() if k not in ('rows','source_proofs')}))
if __name__=='__main__':main()
