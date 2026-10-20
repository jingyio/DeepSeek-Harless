#!/usr/bin/env python3
"""按批次审计实际检索和先前读取；不将相似词或重复URL认定为无效查询。输出含私有证据。"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from importlib.util import spec_from_file_location,module_from_spec
spec=spec_from_file_location('cost',Path(__file__).with_name('analyze-script-motif-cost.py'))
cost=module_from_spec(spec);spec.loader.exec_module(cost)

def charge(row):
    return row['observed_peak_usd'] if row.get('observed_peak_usd') is not None else row.get('reserved_upper_usd',0)

def audit(task):
    events=cost.read_rows(task/'events.jsonl');ledger=cost.read_rows(task/'ledger.jsonl')
    results={e['data']['message']['source']['callId']:e for e in events if e['type']=='tool/result'}
    wire={}
    for e in events:
        if e['type']!='web/deepseek-search-llm-request':continue
        body=e['data']['body'];parts=body['messages'][0]['content']
        text=parts if isinstance(parts,str) else ''.join(p.get('text','')for p in parts)
        prefix='Perform a web search for the query: '
        if not text.startswith(prefix):continue
        normalized={**body,'model':'deepseek-v4-flash' if body['model']=='deepseek-flash' else body['model']}
        fingerprint=hashlib.sha256(json.dumps(normalized,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        wire.setdefault(text[len(prefix):],[]).append(fingerprint)
    batches=[];known=set();seen_queries=set();reads=[];query_count=0
    for e in events:
        d=e.get('data',{})
        if e['type']!='tool/call':continue
        try:args=json.loads(d['arguments']) if isinstance(d['arguments'],str) else d['arguments']
        except (ValueError,KeyError):continue
        end=results.get(d['callId']);text='';failed=None
        if end:
            block=end['data']['message']['content'][0];text='\n'.join(p.get('text','') for p in block.get('content',[]));failed=block.get('isError',False)
        if d['name']!='web_search':
            reads.append({'step':d['step'],'call_id':d['callId'],'tool':d['name'],
                'description':args.get('description',args.get('url','')),'error':failed,
                'result_sha256':hashlib.sha256(text.encode()).hexdigest(),'excerpt':text[:1800]})
            continue
        urls=[s['url'] for s in (end or {}).get('data',{}).get('meta',{}).get('sources',[])]
        sources=(end or {}).get('data',{}).get('meta',{}).get('sources',[])
        # request_utc_epoch is written at settlement, not dispatch. Concurrent
        # sibling queries cannot be assigned individual charges without a trace ID.
        rows=[r for r in ledger if r.get('streamed') is False and r.get('kind','web_search')=='web_search' and end and e['time']<=r.get('request_utc_epoch',0)*1000<=end['time']+50]
        queries=[]
        for q in args['queries']:
            matched=[r for r in rows if r.get('search_trace',{}).get('request_sha256') in wire.get(q,[])]
            query_count+=1;queries.append({'id':query_count,'query':q,'exact_prior_query':q in seen_queries,
                'request_ids':[r['request_id']for r in matched],'estimated_usd':sum(charge(r)for r in matched) if matched else None});seen_queries.add(q)
        batches.append({'step':d['step'],'call_id':d['callId'],'queries':queries,'prior_reads':reads[:],
            'source_count':len(urls),'snippet_count':sum(bool(s.get('snippet')) for s in sources),
            'repeated_prior_urls':[u for u in urls if u in known],'sources':sources,
            'truncated':(end or {}).get('data',{}).get('meta',{}).get('truncated'),
            'search_requests':len(rows),'tokens':{k:sum(r.get('response_usage',{}).get(k,0) for r in rows) for k in cost.FIELDS},
            'unknown_usage_requests':sum(r.get('observed_peak_usd') is None for r in rows),
            'estimated_usd':sum(charge(r)for r in rows)})
        known.update(urls)
    return {'task_id':task.name,'query_count':query_count,'exact_repeated_queries':sum(q['exact_prior_query'] for b in batches for q in b['queries']),
        'individual_query_cost_known':all(q['request_ids']for b in batches for q in b['queries']),
        'classification':'requires_semantic_review_of_prior_evidence_not_url_overlap','batches':batches}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--task',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=audit(a.task);a.output.parent.mkdir(parents=True,exist_ok=True,mode=0o700);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');a.output.chmod(0o600)
    print(json.dumps({k:v for k,v in result.items() if k!='batches'}))
