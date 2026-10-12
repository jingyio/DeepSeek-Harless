"""Read-only cost/quality audit of all predefined local RSI comparison runs."""
import importlib.util
import argparse
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('patch_summary_base',ROOT/'scripts/paper-rsi-patch-task.py')
task=importlib.util.module_from_spec(spec);spec.loader.exec_module(task)
EXP=task.EXP
def load(p):return json.loads(p.read_text())
def summarize(run):
    metrics=load(run/'metrics.json');by_id={}
    for line in (run/'cost-ledger.jsonl').read_text().splitlines():
        row=json.loads(line);by_id[row['request_id']]=row
    usage=[r.get('response_usage') for r in by_id.values()]
    keys=['prompt_cache_hit_tokens','prompt_cache_miss_tokens','completion_tokens']
    tokens={k:sum(u[k] for u in usage) if all(isinstance(u,dict) and isinstance(u.get(k),int) for u in usage) else None for k in keys}
    observed=sum(r['observed_peak_usd'] for r in by_id.values()) if all(r.get('observed_peak_usd') is not None for r in by_id.values()) else None
    result={'label':run.name,'case_id':load(run/'config.json').get('case_id'),'status':metrics['status'],
      'actual_requests':metrics['actual_requests'],'verified_skips':metrics.get('verified_skips',0),
      'unverified_skips':metrics.get('unverified_skips',0),'observed_proxy_usd':observed,
      'reserved_or_observed_increment_usd':metrics['new_estimated_usd'],'elapsed_seconds':metrics['elapsed_seconds'],**tokens}
    if (run/'verification.json').exists():result['quality']=load(run/'verification.json')
    if (run/'shadow-score.json').exists():result['strict_shadow_requests']=load(run/'shadow-score.json')['strict_whole_request']
    return result
def main():
    global EXP
    parser=argparse.ArgumentParser();parser.add_argument('--experiment',default=str(EXP.relative_to(ROOT)))
    args=parser.parse_args();EXP=ROOT/args.experiment
    if EXP.is_symlink() or not EXP.resolve().is_relative_to((ROOT/'.local/paper-reference').resolve()):
        raise ValueError('private_experiment_required')
    rows=[summarize(p) for p in sorted((EXP/'runs').iterdir()) if (p/'metrics.json').exists()]
    learning=[summarize(p) for p in sorted((ROOT/'.local/paper-reference/paper-rsi-patch-20261012-v1/runs').iterdir()) if (p/'metrics.json').exists()]
    groups={}
    for prefix in ['full','shadow','execute','baseline']:
        subset=[r for r in rows if r['label'].startswith(prefix+'-')]
        groups[prefix]={'runs':len(subset),'actual_requests':sum(r['actual_requests'] for r in subset),
          'verified_skips':sum(r['verified_skips'] for r in subset),
          'structurally_complete':sum(r['quality']['stage_output_passed'] for r in subset),
          'observed_proxy_usd':sum(r['observed_proxy_usd'] for r in subset) if all(r['observed_proxy_usd'] is not None for r in subset) else None,
          'completion_tokens':sum(r['completion_tokens'] for r in subset) if all(r['completion_tokens'] is not None for r in subset) else None,
          'strict_shadow_requests':sum(r.get('strict_shadow_requests',0) for r in subset)}
    _,prior,ledgers=task.paid.rsi.reference.budget.account(EXP)
    pairs=[]
    suffixes=sorted({r['label'][len('shadow-'):] for r in rows if r['label'].startswith('shadow-')})
    for suffix in suffixes:
        by={p:next((r for r in rows if r['label']==p+'-'+suffix),None) for p in ['full','shadow','execute']}
        if by['shadow'] and by['execute']:
            a,b,c=(by[p] for p in ['full','shadow','execute'])
            pair={'case':suffix,'same_tools_structural_quality_pass':all(r['quality']['stage_output_passed'] for r in [b,c]),
              'same_tools_requests_reduction':1-c['actual_requests']/b['actual_requests'],
              'same_tools_cost_reduction':1-c['observed_proxy_usd']/b['observed_proxy_usd'] if b['observed_proxy_usd'] and c['observed_proxy_usd'] is not None else None}
            if a:
                pair.update(full_quality=a['quality']['stage_output_passed'],
                  full_to_plan_output_reduction=1-b['completion_tokens']/a['completion_tokens'] if a['completion_tokens'] and b['completion_tokens'] is not None else None,
                  full_to_execute_cost_reduction=1-c['observed_proxy_usd']/a['observed_proxy_usd'] if a['observed_proxy_usd'] and c['observed_proxy_usd'] is not None else None,
                  all_three_structural_quality_pass=all(r['quality']['stage_output_passed'] for r in by.values()))
            pairs.append(pair)
    result={'schema_version':1,'rows':rows,'learning':learning,'groups':groups,'pairs':pairs,
      'cumulative_estimated_usd':prior,'new_local_estimated_usd':prior-7.71064363,'cap_usd':10,
      'prior_ledger_sha256':ledgers,'bill_verified':False,'cross_paper':False,'semantic_quality':'not_reviewed'}
    task.save(EXP/'comparison-summary.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='prior_ledger_sha256'},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
