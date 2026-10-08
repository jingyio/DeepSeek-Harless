#!/usr/bin/env python3
"""Reconcile three local-app live trials from private answers and API ledgers."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
SPECS={
 'numbers':('numbers-live-v1',['debug_d','debug_e','debug_f'],'v2',
            ['request_count','total_usd','most_expensive_request','total_matches','total_is_formula']),
 'keynote':('keynote-live-v1',['test_d','test_e','test_f'],'v2',
            ['slide_title','claim_usd','note_usd','consistent','source_code']),
 'finder':('finder-live-v1',['test_a','test_b','test_c'],'first',
            ['project','report_name','size_bytes','nonempty','has_manifest']),
}

def parse_answer(raw):
    text=raw.strip()
    block=re.fullmatch(r'```(?:json)?\s*(.*?)\s*```',text,re.S)
    candidate=block.group(1) if block else text
    try:return json.loads(candidate),True
    except json.JSONDecodeError:
        blocks=re.findall(r'```(?:json)?\s*(\{.*?\})\s*```',text,re.S)
        if len(blocks)!=1:return {},False
        try:return json.loads(blocks[0]),False
        except json.JSONDecodeError:return {},False

def source_is_frozen(app,scope):
    if app=='finder':
        folder=Path(scope['path'])
        actual={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                for p in folder.iterdir() if p.is_file()}
        return actual==scope['files']
    p=Path(scope['path'])
    return hashlib.sha256(p.read_bytes()).hexdigest()==scope['sha256']

def main():
    summary={}
    for app,(folder,cases,attempt,fields) in SPECS.items():
        base=ROOT/'.local/benchmarks'/folder
        lock=json.loads((base/('EVALUATION-LOCK-v2.json' if attempt=='v2' else 'EVALUATION-LOCK.json')).read_text())
        if hashlib.sha256((base/'online-manifest.json').read_bytes()).hexdigest()!=lock['manifest_sha256']:
            raise ValueError(app+' manifest changed after lock')
        rows=[]
        for case in cases:
            scope=json.loads((base/case/'scope.json').read_text())
            if not source_is_frozen(app,scope):raise ValueError(app+'/'+case+' source changed')
            expected=json.loads((base/case/'reference.json').read_text())
            for arm in ('baseline','motif'):
                run=base/case/(arm+'-'+attempt)
                metrics=json.loads((run/'metrics.json').read_text())
                answer,json_only=parse_answer((run/'answer.txt').read_text())
                checks={field: (type(answer.get(field)) is type(expected[field]) and
                   (abs(answer[field]-expected[field])<=1e-8 if field=='total_usd'
                    else answer[field]==expected[field])) for field in fields}
                ledger=[json.loads(x) for x in (run/'budget-ledger.jsonl').read_text().splitlines()]
                if sum(x.get('response_status')==200 for x in ledger)!=metrics['model_requests']:
                    raise ValueError('Request count does not reconcile: '+str(run))
                api_cost=sum(x.get('observed_peak_usd') or 0 for x in ledger)
                rows.append({'case':case,'arm':arm,'data_pass':all(checks.values()),
                   'json_only':json_only,'quality_pass':all(checks.values()) and json_only,
                   'checks':checks,'model_requests':metrics['model_requests'],
                   'verified_skips':metrics['verified_skips'],
                   'inputTokens':metrics['inputTokens'],
                   'cacheReadTokens':metrics['cacheReadTokens'],
                   'outputTokens':metrics['outputTokens'],
                   'elapsed_seconds':metrics['elapsed_seconds'],
                   'cost_usd':api_cost})
        totals={}
        for arm in ('baseline','motif'):
            group=[r for r in rows if r['arm']==arm]
            totals[arm]={key:sum(r[key] for r in group) for key in
               ['model_requests','verified_skips','inputTokens','cacheReadTokens',
                'outputTokens','elapsed_seconds','cost_usd','data_pass','quality_pass']}
        result={'app':app,'runs':rows,'totals':totals,
                'cost_reduction':1-totals['motif']['cost_usd']/totals['baseline']['cost_usd'],
                'cost_kind':'API usage-priced estimate, not provider invoice'}
        out=base/('evaluation-v2.json' if attempt=='v2' else 'evaluation.json')
        out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');out.chmod(0o600)
        summary[app]={'cost_reduction':result['cost_reduction'],'totals':totals,
                      'all_data_pass':all(r['data_pass'] for r in rows)}
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
