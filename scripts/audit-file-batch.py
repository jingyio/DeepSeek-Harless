"""Raw HTTP, parameter, coverage and byte audit for matched three-arm comparisons."""
import argparse,json,math,hashlib,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from common import digest,sha,snapshot,save

def main():
 p=argparse.ArgumentParser();p.add_argument('--experiment',type=Path,required=True);args=p.parse_args();exp=args.experiment.resolve();protocol=json.loads((exp/'protocol.json').read_text())
 assert all(sha(exp/'frozen-source'/n)==h for n,h in protocol['source_code'].items())
 triples={};schemas=set();rows=[];order=[];reads={'S':0,'M':0};batches={'S':0,'M':0}
 for c in protocol['tasks']:
  td=Path(c['task_dir']);spec=json.loads((td/'input.json').read_text());assert digest(spec)==c['input_sha256'];triples.setdefault(c['pair_id'],[]).append((digest(spec),sha(td/'prompt.md')))
  op=next(td.glob('attempts/*/outcome.json'));o=json.loads(op.read_text());a=op.parent;run=Path(o['run']['output_dir']);m=o['run']
  cfg=json.loads((a/'config.json').read_text());order.append((cfg['series_before']['estimated_usd'],c['task_id']))
  assert json.loads((a/'execution-source-code.json').read_text())==protocol['source_code']
  assert all(protocol['source_code'][n]==h for n,h in json.loads((a/'source-code.json').read_text()).items())
  schemas.add(digest(json.loads((a/'tool-schemas.json').read_text())))
  final=json.loads((a/'final-copy.json').read_text());assert snapshot(final['path'])==final['snapshot']==spec['initial_snapshot']
  assert sha(run/'agent-events.jsonl')==o['events_sha256'];events=[json.loads(l) for l in (run/'agent-events.jsonl').read_text().splitlines()]
  calls={e['data']['callId']:e['data'] for e in events if e['type']=='tool/call'};results={b['toolCallId']:b for e in events if e['type']=='tool/result' for b in e['data']['message'].get('content',[]) if b.get('type')=='tool-result'}
  ledger=[json.loads(l) for l in (run/'cost-ledger.jsonl').read_text().splitlines()];assert len(ledger)==m['upstream_requests'];cost=0
  for r in ledger:
   assert r['response_status']==200;u=r['response_usage'];assert u['prompt_tokens']==u['prompt_cache_hit_tokens']+u['prompt_cache_miss_tokens'];cost+=(u['prompt_cache_hit_tokens']*.006+u['prompt_cache_miss_tokens']*.3+u['completion_tokens']*1.2)/1e6
  assert math.isclose(cost,m['budget_accounted_usd'],abs_tol=1e-12)
  for field,key in [('outputTokens','completion_tokens'),('inputTokens','prompt_cache_miss_tokens'),('cacheReadTokens','prompt_cache_hit_tokens')]:assert m[field]==sum(r['response_usage'][key] for r in ledger)
  generated={cid:call for cid,call in calls.items() if cid.startswith('sss-collection-')}
  if c['arm']=='H':assert not generated
  else:
   log=[json.loads(l) for l in (run/'.local/online-motif'/(hashlib.sha256(m['session_id'].encode()).hexdigest()+'.jsonl')).read_text().splitlines()]
   script=c['arm']=='S';base='collection_script_' if script else 'collection_motif_';kind='collection_script_batch_verified' if script else 'collection_model_request_bypassed_verified'
   bs=[r for r in log if r['kind']==kind];assert len(bs)==m['collection_script_batches_verified' if script else 'collection_model_requests_bypassed_verified'];assert sum(r['count'] for r in bs)==len(generated)
   chosen=[r for r in log if r['kind']==base+'selection_verified'];assert len(chosen)==1;cid=chosen[0]['call_id'];assert not cid.startswith('sss-');raw=json.loads(results[cid]['content'][0]['text']);assert digest(raw)==chosen[0]['selection_sha256']
   assert any(e['type']=='assistant/message' and e['data'].get('usage') and e['data']['message'].get('source',{}).get('kind')=='model' and any(b.get('id')==cid for b in e['data']['message'].get('content',[])) for e in events)
   rs=[r for r in log if r['kind']==base+'read_verified'];assert len(rs)==raw['count'];assert {r['file_id'] for r in rs}=={r['file_id'] for r in raw['files']}
   for r in rs:
    v=json.loads(results[r['call_id']]['content'][0]['text']);assert not results[r['call_id']].get('isError') and digest(v)==r['observation_sha256'];assert json.loads(calls[r['call_id']]['arguments'])=={'source_id':v['source_id']};assert v['source_version']==r['source_version']
   assert sum(r['kind']==base+'complete' for r in log)==1;reads[c['arm']]+=len(rs);batches[c['arm']]+=len(bs)
   assert all(not r.get('policy_digest') and not r.get('certified_digest') for r in log if script and r['kind']!='collection_script_loaded')
  report=json.loads((a/'delivery/report.json').read_text());actual=[json.loads(results[cid]['content'][0]['text']) for cid,v in calls.items() if v['name']=='mcp__file_management__submit_report' and cid in results and not results[cid].get('isError')];assert actual[-1]['artifact_sha256']==digest(report)
  rows.append({'task':c['task_id'],'arm':c['arm'],'passed':o['acceptance']['passed'],'requests':len(ledger),'cost':cost,'tool_errors':o['tool_errors']})
 assert len(schemas)==1 and all(len(v)==3 and len(set(v))==1 for v in triples.values());assert [name for _,name in sorted(order)]==[c['task_id'] for c in protocol['tasks']]
 result={'audited':len(rows),'matched_triples':len(triples),'byte_prompt_schema_usage_order_verified':True,'runtime_reads':reads,'verified_batches':batches,'human_blind_review':False,'actual_bill_verified':False,'rows':rows};save(exp/'independent-audit.json',result);print(json.dumps({k:v for k,v in result.items() if k!='rows'}))
if __name__=='__main__':main()
