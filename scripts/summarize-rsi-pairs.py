"""Full and qualified fifth-stage costs, repeat-level results, conservative acquisition payback."""
import argparse,json,math,sys,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from common import save

def main():
 p=argparse.ArgumentParser();p.add_argument('--experiment',type=Path,required=True);a=p.parse_args();exp=a.experiment.resolve();s=json.loads((exp/'summary.json').read_text());pairs={};fields=['upstream_requests','outputTokens','inputTokens','cacheReadTokens','budget_accounted_usd','elapsed_seconds']
 for o in s['outcomes']:
  if o['role']=='evaluate':pairs.setdefault(o['pair_id'],{})[o['arm']]=o
 def compare(left,right,excluded=None):
  eligible=[v for v in pairs.values() if left in v and right in v and v[left]['acceptance']['passed'] and v[right]['acceptance']['passed'] and v[left]['task_id'] not in (excluded or set())]
  totals={arm:{f:sum(v[arm]['run'].get(f,0) for v in eligible) for f in fields} for arm in (left,right)}
  fee_delta=totals[left]['budget_accounted_usd']-totals[right]['budget_accounted_usd'];rate=(totals[right]['budget_accounted_usd']/totals[left]['budget_accounted_usd']-1)*100 if totals[left]['budget_accounted_usd'] else None
  return {'joint_pass_pairs':len(eligible),'metrics':totals,'fee_change_percent':rate,'average_observed_fee_saving_per_qualified_task':fee_delta/len(eligible) if eligible else None}
 result={'experiment':exp.name,'all_arms':s['arms'],'H_L1_qualified':compare('H','L1'),'H_L2_qualified':compare('H','L2'),'L1_L2_qualified':compare('L1','L2'),
  'learning_certification_requests':sum(o['run']['upstream_requests'] for o in s['outcomes'] if o['role']!='evaluate'),
  'learning_certification_estimated_usd':sum(o['run']['budget_accounted_usd'] for o in s['outcomes'] if o['role']!='evaluate'),
  'stage_estimated_usd':sum(o['run']['budget_accounted_usd'] for o in s['outcomes']),'stage_requests':sum(o['run']['upstream_requests'] for o in s['outcomes']),
  'failures':[{'task':o['task_id'],'role':o['role'],'arm':o['arm'],'errors':o['acceptance']['errors']} for o in s['outcomes'] if not o['acceptance']['passed']],
  'per_repeated_triple':[{ 'pair':k,'arms':{arm:{'passed':o['acceptance']['passed'],'requests':o['run']['upstream_requests'],'estimated_usd':o['run']['budget_accounted_usd']} for arm,o in v.items()}} for k,v in sorted(pairs.items())]}
 deferred=set()
 for o in s['outcomes']:
  if o['role']=='evaluate' and o['arm']=='L1':
   run=Path(o['run']['output_dir']);audit=run/'.local/online-motif'/(hashlib.sha256(o['run']['session_id'].encode()).hexdigest()+'.jsonl')
   if any(json.loads(l)['kind']=='collection_motif_deferred' for l in audit.read_text().splitlines()):deferred.add(o['task_id'])
 result['qualified_sensitivity_excluding_L1_deferred']=compare('L1','L2',deferred)
 result['L1_deferred_tasks']=sorted(deferred)
 delta=result['L1_L2_qualified']['average_observed_fee_saving_per_qualified_task']
 result['conditional_payback_tasks']=math.ceil(result['learning_certification_estimated_usd']/delta) if delta is not None and delta>0 else None
 result['payback_scope']='conditional on qualified subset and unchanged future costs/quality; all nine acquisition runs counted; labor/real bills excluded; not a promise'
 save(exp/'paired-analysis.json',result);print(json.dumps({k:v for k,v in result.items() if k not in ('failures','per_repeated_triple')},ensure_ascii=False))
if __name__=='__main__':main()
