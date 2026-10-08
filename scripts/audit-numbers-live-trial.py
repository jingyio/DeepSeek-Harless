#!/usr/bin/env python3
"""Grade frozen Numbers answers against source usage and reconcile model costs."""
from __future__ import annotations
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / '.local/benchmarks/numbers-live-v1'


def main():
    rows = []
    for case in ['test_calendar_a','test_calendar_b','test_calendar_c']:
        expected = json.loads((BASE/case/'reference.json').read_text())
        for arm in ['baseline','motif']:
            run = BASE/case/(arm+'-first')
            metrics = json.loads((run/'metrics.json').read_text())
            text = (run/'answer.txt').read_text().strip()
            full_block = re.fullmatch(r'```(?:json)?\s*(.*?)\s*```', text, re.S)
            candidate = full_block.group(1) if full_block else text
            try:
                answer = json.loads(candidate)
                json_only = True
            except ValueError:
                json_only = False
                blocks = re.findall(r'```json\s*(\{.*?\})\s*```', text, re.S)
                try:
                    answer = json.loads(blocks[0]) if len(blocks)==1 else {}
                except ValueError:
                    answer = {}
            checks = {k:(isinstance(answer.get(k),(int,float)) and
                         not isinstance(answer.get(k),bool) and
                         abs(answer[k]-expected[k]) <= 1e-8 if k=='total_usd'
                        else type(answer.get(k)) is type(expected[k]) and answer.get(k)==expected[k])
                      for k in ['request_count','total_usd','most_expensive_request','total_matches','total_is_formula']}
            ledger = [json.loads(x) for x in (run/'budget-ledger.jsonl').read_text().splitlines()]
            usage_rows = [x for x in ledger if x.get('response_status') == 200]
            if len(usage_rows) != metrics['model_requests']:
                raise ValueError('SDK and budget request counts do not reconcile')
            events = [json.loads(x) for x in (run/'agent-events.jsonl').read_text().splitlines()]
            calls = [x['data'] for x in events if x.get('type') == 'tool/call']
            rows.append({'case':case,'arm':arm, 'data_pass':all(checks.values()),
                         'json_only':json_only, 'quality_pass':all(checks.values()) and json_only,'checks':checks,
                         **{k:metrics[k] for k in ['model_requests','verified_skips','inputTokens','cacheReadTokens','outputTokens','elapsed_seconds']},
                         'mcp_calls':len(calls),'tool_sequence':[x['name'] for x in calls],
                         'cost_usd':sum(x.get('observed_peak_usd',0) for x in ledger)})
    totals = {}
    for arm in ['baseline','motif']:
        selected = [r for r in rows if r['arm']==arm]
        totals[arm] = {k:sum(r[k] for r in selected) for k in ['model_requests','verified_skips','inputTokens','cacheReadTokens','outputTokens','elapsed_seconds','mcp_calls','cost_usd']}
        totals[arm]['quality_pass'] = sum(r['quality_pass'] for r in selected)
        totals[arm]['data_pass'] = sum(r['data_pass'] for r in selected)
    all_costs = {}
    for path in BASE.glob('*/*/budget-ledger.jsonl'):
        all_costs[str(path.relative_to(BASE))] = sum(json.loads(x).get('observed_peak_usd',0) for x in path.read_text().splitlines() if x.strip())
    result = {'runs':rows,'totals':totals,
              'execution_cost_reduction':1-totals['motif']['cost_usd']/totals['baseline']['cost_usd'],
              'all_attempts_api_cost_usd':sum(all_costs.values()),'all_attempts_costs':all_costs,
              'cost_kind':'API usage-priced estimate, not supplier-reconciled bill; training/diagnostics separated'}
    path=BASE/'evaluation.json'; path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');path.chmod(0o600)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
