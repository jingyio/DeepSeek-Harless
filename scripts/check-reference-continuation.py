"""Coverage/provenance diagnostics; never substitutes for reference-quality review."""
from collections import Counter
import argparse
import json
from pathlib import Path


def check(run):
    catalog = json.loads((run / 'work/catalog.json').read_text())
    path = run / 'work/triage.json'
    metrics = json.loads((run / 'metrics.json').read_text())
    if not path.exists(): return {'metrics': metrics, 'artifact_present': False, 'quality': 'failed_missing_artifact'}
    result = json.loads(path.read_text())
    expected = {(i['item_id'].rsplit(':',1)[0], i['id']) for i in catalog['query_items']}
    pairs = [(r.get('key'), r.get('arxiv_id')) for r in result.get('references', [])]
    actual = set(pairs)
    audits = [json.loads(line) for line in (run / 'parameter-motif/audit.jsonl').read_text().splitlines()] if (run / 'parameter-motif/audit.jsonl').exists() else []
    selections = [row for row in audits if row['kind']=='selection_accepted']
    joins = [row for row in audits if row['kind']=='model_request_skipped_verified']
    # Semantic checks are flags for review, not automatic relabeling of historical answers.
    unjustified_p0 = []
    for row in result.get('references', []):
        reason = ' '.join(row.get('differences', []))
        if row.get('priority')=='P0' and row.get('status') in {'已确认','已确认但需修正'} and not any(word in reason for word in ['另一篇','不存在','错位','虚构','指向错误','不匹配']):
            unjustified_p0.append(row['key'])
    ledgers = [json.loads(line) for line in (run/'cost-ledger.jsonl').read_text().splitlines()]
    usage = [row for row in ledgers if row.get('response_status') == 200 and isinstance(row.get('response_usage'), dict)]
    events = [json.loads(line)['event'] for line in (run/'session-events.jsonl').read_text().splitlines()]
    calls = []
    for event in events:
        if event['type'] == 'tool/call':
            data = event['data']; args = data['arguments']
            calls.append((data['name'], json.loads(args) if isinstance(args, str) else args))
    urls = [args['url'] for name,args in calls if name=='web_fetch']
    native_plans = sum(name=='write' and str(args.get('file_path','')).endswith('selection.json') for name,args in calls)
    token_fields = ['prompt_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens','completion_tokens']
    return {'metrics':metrics, 'artifact_present':True, 'expected_references':len(expected),
            'output_references':len(pairs), 'covered':len(expected&actual),
            'missing': sorted(expected-actual), 'extra': sorted(actual-expected),
            'duplicates': [pair for pair,n in Counter(pairs).items() if n>1],
            'citation_issue_count':len(result.get('citation_issues',[])),
            'p0_requires_review':unjustified_p0,
            'selected_batches':len(selections), 'verified_joins':len(joins),
            'verified_collections':sum(row.get('tool_count',0) for row in joins),
            'guard_deferred':dict(Counter(row.get('reason') for row in audits if row['kind'] in {'selection_deferred','parameter_deferred'})),
            'reference_set_passed':actual==expected and len(pairs)==len(expected),
            'semantic_quality':'not_blind_reviewed',
            'ledger_completed_rows':len(usage),
            'tokens':{field:sum(row['response_usage'].get(field,0) for row in usage) for field in token_fields},
            'native_plan_writes':native_plans, 'web_calls':len(urls), 'web_unique_urls':len(set(urls)),
            'duplicate_web_calls':len(urls)-len(set(urls)),
            'status_counts':dict(Counter(r.get('status') for r in result.get('references',[])))}


def main():
    p=argparse.ArgumentParser();p.add_argument('experiment',type=Path);args=p.parse_args()
    rows={run.name:check(run) for run in sorted((args.experiment/'runs').iterdir()) if (run/'metrics.json').exists()}
    out=args.experiment/'verification-summary.json';out.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n');out.chmod(0o600)
    print(json.dumps({name:{k:v for k,v in row.items() if k not in {'missing','extra','duplicates','p0_requires_review','guard_deferred'}} for name,row in rows.items()},ensure_ascii=False))

if __name__=='__main__': main()
