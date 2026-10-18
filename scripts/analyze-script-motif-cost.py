#!/usr/bin/env python3
"""离线按完整请求归因；类别是可见动作，不推断隐藏推理或反事实节省。"""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import re

FIELDS=('prompt_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens','completion_tokens')

def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line] if path.exists() else []

def actions(message):
    for block in message.get('content',[]):
        if block.get('type')=='tool-call':
            args=block.get('arguments',{})
            try:args=json.loads(args) if isinstance(args,str) else args
            except ValueError:args={}
            yield block['name'],args

def category(message):
    calls=list(actions(message));labels=set()
    for name,args in calls:
        if name=='bash':
            command=args.get('command','')
            if re.search(r'(?:^|&&\s*)geneloop-cache\s',command):label='cached_script_dispatch'
            elif re.search(r"python3?\s+(?:-\s*<<|-c\s)|cat\s*>\s*\S+\.py\s*<<",command):
                label='script_authoring_network' if re.search(r'\burlopen\b|requests\.(?:get|post|request|Session)|httpx\.|curl\s|wget\s',command) else 'script_authoring_local'
            elif re.search(r'python3?\s+[^\s]+\.py\b',command):label='saved_script_dispatch'
            elif re.search(r'\b(curl|wget)\b',command):label='shell_network_dispatch'
            elif re.search(r'\b(cat|ls|grep|rg|sed|head|tail|find|wc|unzip)\b',command):label='shell_read_dispatch'
            else:label='shell_other_dispatch'
        elif any(k in name for k in ('stage_current_audit','finalize_current_audit','export_','read_current_audit')):label='report_protocol'
        elif name in ('web_search','web_fetch'):label=name+'_dispatch'
        else:label='other_tool_dispatch'
        labels.add(label)
    return next(iter(labels)) if len(labels)==1 else 'mixed_tool_request' if labels else 'final_or_intermediate_text'

def report_start(message):
    return any('stage_current_audit' in name or 'export_review_report' in name or
               name=='bash' and re.search(r'canvas\.Canvas|SimpleDocTemplate|BaseDocTemplate|reportlab[\s\S]*\.build\(',args.get('command',''))
               for name,args in actions(message))

def analyze(task):
    task=Path(task);events=read_rows(task/'events.jsonl');ledger=read_rows(task/'ledger.jsonl')
    messages=[e for e in events if e.get('type')=='assistant/message' and e['data'].get('usage')]
    intervals=[];calls={};errors=[];repeats=Counter()
    for e in events:
        d=e.get('data',{})
        if e.get('type')=='tool/call':
            calls[d['callId']]=e
            repeats[hashlib.sha256(json.dumps([d['name'],d.get('arguments')],sort_keys=True).encode()).hexdigest()]+=1
        elif e.get('type')=='tool/result':
            for b in d.get('message',{}).get('content',[]):
                start=calls.get(b.get('toolCallId'))
                if not start:continue
                if b.get('isError'):errors.append(e['time'])
                if start['data']['name']=='web_search':intervals.append((start['time'],e['time']))
    totals=defaultdict(lambda:{'requests':0,'estimated_usd':0,**{k:0 for k in FIELDS}});assigned=set();records=[]
    for row in ledger:
        if row.get('response_usage') is None:continue
        stamp=row['request_utc_epoch']*1000
        possible=[(abs(e['time']-stamp),i,e) for i,e in enumerate(messages) if i not in assigned]
        match=min(possible,key=lambda p:p[0]) if possible else None
        if match and match[0]<=500:
            _,i,event=match;assigned.add(i);kind=category(event['data']['message']);step=event['data'].get('step')
        else:
            kind='web_search_internal_model' if any(a-500<=stamp<=b+500 for a,b in intervals) else 'unassigned_provider_request';step=None
        total=totals[kind];total['requests']+=1;total['estimated_usd']+=row.get('observed_peak_usd',0) or 0
        for field in FIELDS:total[field]+=row['response_usage'].get(field,0) or 0
        prior=next((e for e in reversed(messages) if e['time']<stamp-500),None)
        recovery=any((prior['time'] if prior else 0)<t<stamp for t in errors)
        records.append({'request_id':row.get('request_id'),'category':kind,'step':step,'estimated_usd':row.get('observed_peak_usd'),'after_tool_error':recovery,'elapsed_seconds':row.get('elapsed_seconds')})
    report_boundary=next((e['time'] for e in messages if report_start(e['data']['message'])),None)
    report_rows=[row for row in ledger if report_boundary is not None and row.get('response_usage') is not None and row['request_utc_epoch']*1000>=report_boundary-500]
    report_phase={'scope':'报告首次写作或暂存开始后的全部请求；可能含补检，不等于纯排版费用',
                  'requests':len(report_rows),'estimated_usd':sum((r.get('observed_peak_usd') or 0) for r in report_rows),
                  'output_tokens':sum(r['response_usage'].get('completion_tokens',0) for r in report_rows)}
    audit=read_rows(task/'script-motif-audit.jsonl');counts=Counter(r['kind'] for r in audit)
    return {'task_id':task.name,'scope':'完整请求的可见动作归因；含该请求的语义判断；不等于纯代码生成费用或反事实可节省费用',
      'alignment':'provider completion timestamp within 500 ms of assistant message; remaining web_search tool intervals',
      'categories':dict(totals),'report_phase':report_phase,'requests_with_known_usage':len(records),'requests_after_tool_errors':sum(r['after_tool_error'] for r in records),
      'unassigned_assistant_messages':len(messages)-len(assigned),'exact_repeated_tool_arguments':sum(n-1 for n in repeats.values() if n>1),
      'script_events':dict(counts),'embedding_elapsed_ms':sum(r.get('elapsed_ms',0) for r in audit if r['kind']=='script_embedding'),'requests':records}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--task',type=Path,required=True);p.add_argument('--output',type=Path)
    args=p.parse_args();value=json.dumps(analyze(args.task),ensure_ascii=False,indent=2)+'\n'
    if args.output:
        with args.output.open('x') as f:f.write(value)
    else:print(value,end='')
