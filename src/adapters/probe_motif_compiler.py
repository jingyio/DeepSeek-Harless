"""Learn subset-probe axes from real native trials, not error-name rules."""
import json
from collections import defaultdict
from jsonschema import Draft202012Validator
from pathlib import Path
from .script_motif_compiler import digest, sha


def arrays(value, path=()):
    if isinstance(value, list):
        if value: yield path, value
        for child in value: yield from arrays(child, path+('*',))
    elif isinstance(value, dict):
        for key, child in value.items(): yield from arrays(child, path+(key,))


def failure_signature(value):
    if not isinstance(value, dict) or not any(v is False for v in value.values()): return None
    fields={k:v for k,v in value.items() if v is False or isinstance(v,list) and v and all(isinstance(x,str) for x in v)}
    return fields if any(isinstance(v,list) for v in fields.values()) else None


def proper_subsequence(full, subset):
    """Only deletion is learned: preserve JSON types, order and multiplicity."""
    if not 0 < len(subset) < len(full): return False
    remaining = iter(map(digest, full))
    return all(any(candidate == digest(item) for candidate in remaining) for item in subset)


def collect(task):
    task=Path(task);cfg=json.loads((task/'effective-config.json').read_text());state=json.loads((task/'task-state.json').read_text())
    if cfg.get('provider_mode')!='real' or state.get('status')!='completed':raise ValueError('completed_real_task_required')
    schemas={t['name']:t['parameters'] for t in cfg['tools'] if t['name'].startswith('mcp__')}
    raw=(task/'events.jsonl').read_bytes();calls={};rows=[]
    for event in map(json.loads,raw.splitlines()):
        d=event.get('data',{})
        if event.get('type')=='tool/call':
            try:
                args=json.loads(d['arguments']) if isinstance(d['arguments'],str) else d['arguments']
                if d['name'] in schemas and not d['callId'].startswith(('sss-reuse-','sss-script-')):calls[d['callId']]=(d['name'],args)
            except (KeyError,ValueError):pass
        if event.get('type')!='tool/result':continue
        for b in d.get('message',{}).get('content',[]):
            cid=b.get('toolCallId');call=calls.pop(cid,None)
            if not call or b.get('isError'):continue
            try:r=json.loads(next(c['text'] for c in b['content'] if c['type']=='text'))
            except (KeyError,ValueError,StopIteration):continue
            if not isinstance(r,dict) or list(Draft202012Validator(schemas[call[0]]).iter_errors(call[1])):continue
            rows.append({'tool':call[0],'arguments':call[1],'result':r,'call_id':cid,'task_id':task.name,'schema_sha256':digest(schemas[call[0]]),'events_sha256':sha(raw)})
    return rows


def compile_probes(rows):
    groups=defaultdict(list)
    for row in rows:groups[(row['tool'],row['schema_sha256'])].append(row)
    contracts=[]
    for (tool,schema),trials in groups.items():
        failures={digest(s):s for r in trials if (s:=failure_signature(r['result']))}
        for signature in failures.values():
            boolean_keys=[k for k,v in signature.items() if v is False]
            valid=[r for r in trials if isinstance(r['result'],dict) and (all(digest(r['result'].get(k))==digest(v) for k,v in signature.items()) or all(r['result'].get(k) is True for k in boolean_keys))]
            witnesses=defaultdict(list)
            for i,base in enumerate(valid):
                if not all(digest(base['result'].get(k))==digest(v) for k,v in signature.items()):continue
                for small in valid[i+1:]:
                    if base['task_id']!=small['task_id']:continue
                    for path,full in arrays(base['arguments']):
                        for other,subset in arrays(small['arguments']):
                            if path==other and proper_subsequence(full,subset):
                                witnesses[path].append({k:base[k] for k in ('task_id','call_id','events_sha256')}|{'probe_call_id':small['call_id'],'base_arguments_sha256':digest(base['arguments']),'probe_arguments_sha256':digest(small['arguments']), 'probe_succeeded':all(small['result'].get(k) is True for k in boolean_keys)})
            axes=[{'path':list(path),'witnesses':list({w['task_id']:w for w in seen if w['probe_succeeded']}.values())+list({w['task_id']:w for w in seen}.values())} for path,seen in witnesses.items() if len({w['task_id'] for w in seen})>=2 and any(w['probe_succeeded'] for w in seen)]
            if not axes:continue
            body={'tool':tool,'schema_sha256':schema,'failure':signature,'success_fields':boolean_keys,'axes':sorted(axes,key=lambda x:len(x['path'])),
                  'scope':'observed_subset_trials_not_monotonicity_or_cause_proof','max_probes':24}
            contracts.append({'id':'probe_'+digest(body)[:20],**body})
    return contracts
