"""Compare pre-request predictions with unmodified real messages/results."""
import importlib.util
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('rsi_tool_score',ROOT/'scripts/paper-rsi-tool-learning.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
run=Path(sys.argv[1]);es=m.events(run)
messages=[e for e in es if e['type']=='assistant/message']
predictions=[json.loads(l) for l in (run/'work/shadow.jsonl').read_text().splitlines()]
predictions=[p for p in predictions if p['kind'] in ['prediction','deferred']]
if len(messages)!=len(predictions) or [p['request_ordinal'] for p in predictions]!=list(range(1,len(messages)+1)):
    raise ValueError('missing live request boundaries')
results={}
for e in es:
    if e['type']!='tool/result':continue
    for block in e['data']['message']['content']:
        if block.get('type')!='tool-result' or block.get('isError'):continue
        try:results[block['toolCallId']]=json.loads(''.join(c.get('text','') for c in block.get('content',[]) if c.get('type')=='text'))
        except ValueError:continue
rows=[]
for message,pred in zip(messages,predictions):
    outcome='no_prediction';check=None;content=message['data']['message']['content']
    if pred['prediction']:
        calls=[c for c in content if c['type']=='tool-call'];actual=[]
        for c in calls:
            args=c['arguments'];args=json.loads(args) if isinstance(args,str) else args
            actual.append({'tool':c['name'],'arguments':args})
        if actual!=pred['prediction']['expected_tools']:outcome='different_next_operation'
        else:
            check=results.get(calls[0]['id']);p=pred['prediction']
            if not check or check.get('report_sha256')!=p['report_sha256'] or check.get('source_version')!=p['source_version']:
                outcome='result_or_version_changed'
            elif any(c['type']!='tool-call' and not (c['type']=='text' and not c.get('text','').strip()) for c in content):
                outcome='local_match_text_requires_review'
            else:outcome='strict_whole_request'
    rows.append({'request_ordinal':pred['request_ordinal'],'outcome':outcome,'prediction':pred['prediction'],
      'actual_check_output':check.get('output') if check else None})
strict=sum(r['outcome']=='strict_whole_request' for r in rows)
local=sum(r['outcome'] in ['strict_whole_request','local_match_text_requires_review'] for r in rows)
summary={'requests':len(rows),'strict_whole_request':strict,'matching_local_operation':local,
 'strict_ratio':strict/len(rows),'actual_model_skips':0,'semantic_quality':'not_reviewed','requests_detail':rows}
m.save(run/'shadow-score.json',summary);print(json.dumps(summary,ensure_ascii=False))
