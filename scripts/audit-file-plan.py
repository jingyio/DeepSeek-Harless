"""Independent raw-event, capability, preimage, effect and HTTP accounting audit."""
import argparse,json,math,hashlib,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scenarios/file-management'));sys.path.insert(0,str(ROOT))
from common import digest,sha,snapshot,save,PREFIX
from plan_study import scope,expected_actions
from src.motif_core.offline.plan_compiler import effect_snapshot

def main():
 p=argparse.ArgumentParser();p.add_argument('--experiment',type=Path,required=True);args=p.parse_args();exp=args.experiment.resolve();protocol=json.loads((exp/'protocol.json').read_text())
 assert all(sha(exp/'frozen-source'/n)==h for n,h in protocol['source_code'].items())
 schemas=set();pairs={};rows=[];source_proofs=[];verified=0;synthetic=0;restores=0;ordered=[]
 for c in protocol['tasks']:
  td=Path(c['task_dir']);spec=json.loads((td/'input.json').read_text());assert digest(spec)==c['input_sha256']
  if c['role']=='evaluate':pairs.setdefault(c['pair_id'],[]).append((digest(spec),sha(td/'prompt.md')))
  op=next(td.glob('attempts/*/outcome.json'));o=json.loads(op.read_text());a=op.parent;m=o['run'];run=Path(m['output_dir'])
  assert json.loads((a/'execution-source-code.json').read_text())==protocol['source_code'];assert all(protocol['source_code'][n]==h for n,h in json.loads((a/'source-code.json').read_text()).items());schemas.add(digest(json.loads((a/'tool-schemas.json').read_text())))
  if c['role']=='evaluate':ordered.append((json.loads((a/'config.json').read_text())['series_before']['estimated_usd'],c['task_id']))
  assert sha(run/'agent-events.jsonl')==o['events_sha256'];events=[json.loads(l) for l in (run/'agent-events.jsonl').read_text().splitlines()]
  calls={e['data']['callId']:e['data'] for e in events if e['type']=='tool/call'};results={b['toolCallId']:b for e in events if e['type']=='tool/result' for b in e['data']['message'].get('content',[]) if b.get('type')=='tool-result'}
  ledger=[json.loads(l) for l in (run/'cost-ledger.jsonl').read_text().splitlines()];assert len(ledger)==m['upstream_requests'];cost=0
  for r in ledger:
   assert r['response_status']==200;u=r['response_usage'];assert u['prompt_tokens']==u['prompt_cache_hit_tokens']+u['prompt_cache_miss_tokens'];cost+=(u['prompt_cache_hit_tokens']*.006+u['prompt_cache_miss_tokens']*.3+u['completion_tokens']*1.2)/1e6
  assert math.isclose(cost,m['budget_accounted_usd'],abs_tol=1e-12)
  for field,key in [('outputTokens','completion_tokens'),('inputTokens','prompt_cache_miss_tokens'),('cacheReadTokens','prompt_cache_hit_tokens')]:assert m[field]==sum(r['response_usage'][key] for r in ledger)
  journals=[json.loads(p.read_text()) for p in (a/'delivery/journals').glob('*.json')];assert len(journals)==1;j=journals[0]
  wanted=expected_actions(spec);assert sorted(j['actions'],key=lambda v:v['destination'])==sorted(wanted,key=lambda v:v['destination']);assert j['before']==spec['initial_snapshot']
  for n,h in j['before'].items():assert sha(a/'delivery/backups'/j['plan_id']/n)==h
  final=json.loads((a/'final-copy.json').read_text());expected=spec['initial_snapshot'] if spec['expected_restore'] else effect_snapshot(scope(spec),wanted)
  assert snapshot(final['path'])==final['snapshot']==j['after']
  desired_status='restored_verified' if spec['expected_restore'] else 'executed_verified'
  task_effect_matches=final['snapshot']==expected and j['status']==desired_status
  assert task_effect_matches==o['acceptance']['passed'];restores+=(j['status']=='restored_verified')
  state=json.loads((a/'delivery/plan-state.json').read_text());assert state['state_sha256']==digest({k:v for k,v in state.items() if k!='state_sha256'});assert state['expected']==final['snapshot']
  token=state['authorizations'][j['authorization_id']];assert token['authorization_sha256']==digest({k:v for k,v in token.items() if k!='authorization_sha256'});assert token['plan_id']==j['plan_id'] and token['input_sha256']==digest(spec) and token['grant_sha256']==digest(spec['write_grant'])
  source=[cid for cid,call in calls.items() if call['name']==PREFIX+'preview_actions' and cid in results and not results[cid].get('isError')];assert len(source)==1;cid=source[0];preview=json.loads(results[cid]['content'][0]['text'])
  assert not cid.startswith('sss-') and preview['plan_id']==j['plan_id'];assert preview['preview_sha256']==token['preview_sha256'];assert preview['plan_sha256']==token['plan_sha256']
  assert any(e['type']=='assistant/message' and e['data'].get('usage') and e['data']['message'].get('source',{}).get('kind')=='model' and any(b.get('id')==cid for b in e['data']['message'].get('content',[])) for e in events)
  generated={cid:call for cid,call in calls.items() if cid.startswith('sss-plan-')}
  if c['arm']=='H':assert not generated
  else:
   log=[json.loads(l) for l in (run/'.local/online-motif'/(hashlib.sha256(m['session_id'].encode()).hexdigest()+'.jsonl')).read_text().splitlines()]
   assert len(generated)==2;v=[r for r in log if r['kind']=='plan_model_request_bypassed_verified'];assert len(v)==m['plan_model_requests_bypassed_verified']==(1 if spec['fault_after_operations'] else 2)
   assert sum(r['kind']=='plan_execution_verified' for r in log)==(0 if spec['fault_after_operations'] else 1)
   for id,call in generated.items():
    args=json.loads(call['arguments']);assert args['plan_id']==j['plan_id']
    if call['name']==PREFIX+'execute_plan':assert args['authorization_id']==j['authorization_id']
    else:assert call['name']==PREFIX+'authorize_plan'
   assert all(call['name']!=PREFIX+'restore_plan' for call in generated.values());verified+=len(v);synthetic+=len(generated)
   if spec['fault_after_operations']:assert any(r['kind']=='plan_motif_deferred' for r in log)
  if j['status']=='restored_verified':
   actual=[(cid,call) for cid,call in calls.items() if call['name']==PREFIX+'restore_plan' and cid in results and not results[cid].get('isError')];assert actual and all(not cid.startswith('sss-') for cid,_ in actual)
   for id,call in actual:assert json.loads(call['arguments'])=={'plan_id':j['plan_id'],'authorization_id':j['authorization_id']}
  report=json.loads((a/'delivery/report.json').read_text());rr=[json.loads(results[cid]['content'][0]['text']) for cid,call in calls.items() if call['name']==PREFIX+'submit_report' and cid in results and not results[cid].get('isError')];assert rr[-1]['artifact_sha256']==digest(report)
  rows.append({'task':c['task_id'],'role':c['role'],'arm':c['arm'],'passed':o['acceptance']['passed'],'requests':len(ledger),'cost':cost,'tool_errors':o['tool_errors']});source_proofs.append({'task':c['task_id'],'actual_model_preview':source[0]})
 assert len(schemas)==1 and all(len(v)==2 and len(set(v))==1 for v in pairs.values());assert [n for _,n in sorted(ordered)]==[c['task_id'] for c in protocol['tasks'] if c['role']=='evaluate']
 result={'audited':len(rows),'pairs':len(pairs),'preimages_effects_capabilities_source_version_http_verified':True,'restored_tasks':restores,'runtime_effect_tools':synthetic,'verified_continuations':verified,'restore_by_actual_model':True,'actual_bill_verified':False,'human_blind_review':False,'source_proofs':source_proofs,'rows':rows};save(exp/'independent-audit.json',result);print(json.dumps({k:v for k,v in result.items() if k not in ('rows','source_proofs')}))
if __name__=='__main__':main()
