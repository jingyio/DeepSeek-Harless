"""All attempts, paired qualified costs, per-family repeated outcomes and complete repair acquisition costs."""
import argparse,json,sys,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from common import save
FIELDS=('upstream_requests','outputTokens','inputTokens','cacheReadTokens','budget_accounted_usd','elapsed_seconds')
def totals(rows):
    return {'runs':len(rows),'passed':sum(o['acceptance']['passed'] for o in rows),'tool_errors':sum(o['tool_errors'] for o in rows),
            **{f:sum((o['run'] or {}).get(f,0) for o in rows) for f in FIELDS}}
def paired(rows,left,right):
    groups={}
    for o in rows:groups.setdefault(o['pair_id'],{})[o['arm']]=o
    complete=[r for r in groups.values() if left in r and right in r]
    qualified=[r for r in complete if r[left]['acceptance']['passed'] and r[right]['acceptance']['passed']]
    metrics={a:totals([r[a] for r in qualified]) for a in (left,right)}
    base=metrics[left]['budget_accounted_usd'];delta=base-metrics[right]['budget_accounted_usd']
    return {'complete_pairs':len(complete),'both_pass':len(qualified),'only_left_pass':sum(r[left]['acceptance']['passed'] and not r[right]['acceptance']['passed'] for r in complete),
            'only_right_pass':sum(r[right]['acceptance']['passed'] and not r[left]['acceptance']['passed'] for r in complete),
            'both_fail':sum(not r[left]['acceptance']['passed'] and not r[right]['acceptance']['passed'] for r in complete),
            'qualified_metrics':metrics,'qualified_fee_change_percent':(metrics[right]['budget_accounted_usd']/base-1)*100 if base else None,
            'average_qualified_fee_saving_per_task':delta/len(qualified) if qualified else None}
def main():
    p=argparse.ArgumentParser();p.add_argument('--experiment',type=Path,required=True);p.add_argument('--negative-version',type=Path,action='append',default=[]);a=p.parse_args();exp=a.experiment.resolve()
    s=json.loads((exp/'summary.json').read_text());rows=s['outcomes'];quality=[o for o in rows if o['role']=='quality'];benchmark=[o for o in rows if o['role']=='benchmark']
    family={}
    for f in dict.fromkeys(o['family'] for o in benchmark):
        chosen=[o for o in benchmark if o['family']==f];family[f]={'arms':{arm:totals([o for o in chosen if o['arm']==arm]) for arm in ('H','L2')},'pairing':paired(chosen,'H','L2')}
    negative=[]
    for path in a.negative_version:
        old=json.loads((path/'summary.json').read_text());negative.append({'experiment':old['experiment'],'attempts':old['attempts'],'passed':old['passed'],'totals':totals(old['outcomes']),
            'failures':[{'task':o['task_id'],'errors':o['acceptance']['errors'],'estimated_usd':o['run']['budget_accounted_usd']} for o in old['outcomes'] if not o['acceptance']['passed']]})
    acquisition=totals([o for o in rows if o['role'] not in ('quality','benchmark')]);bp=paired(benchmark,'H','L2');cost=acquisition['budget_accounted_usd']+sum(n['totals']['budget_accounted_usd'] for n in negative)
    delta=bp['average_qualified_fee_saving_per_task']
    result={'experiment':exp.name,'all_attempts':totals(rows),'roles':s['roles'],'quality_H_L2':paired(quality,'H','L2'),'quality_L1_L2':paired(quality,'L1','L2'),
        'benchmark_H_L2':bp,'benchmark_by_family':family,'new_library_acquisition_including_failed_tasks':acquisition,'negative_versions':negative,
        'repair_and_library_cost_including_all_negative_versions_usd':cost,
        'conditional_payback_tasks':math.ceil(cost/delta) if delta and delta>0 else None,
        'payback_limitations':'qualified generated-task subset and unchanged future costs/cache/quality only; no labor or actual bill; negative versions fully included',
        'failures':[{'task':o['task_id'],'role':o['role'],'arm':o['arm'],'errors':o['acceptance']['errors'],'requests':o['run']['upstream_requests'],'estimated_usd':o['run']['budget_accounted_usd']} for o in rows if not o['acceptance']['passed']],
        'per_repeated_pair':[{'pair':k,'arms':{o['arm']:{'passed':o['acceptance']['passed'],'requests':o['run']['upstream_requests'],'estimated_usd':o['run']['budget_accounted_usd']} for o in rows if o['pair_id']==k}} for k in sorted({o['pair_id'] for o in benchmark})],
        'series_accounting':s['series_accounting'],'actual_bill_verified':False,'human_blind_review':False}
    save(exp/'paired-analysis.json',result);print(json.dumps({k:v for k,v in result.items() if k not in ('benchmark_by_family','failures','per_repeated_pair','negative_versions')},ensure_ascii=False))
if __name__=='__main__':main()
