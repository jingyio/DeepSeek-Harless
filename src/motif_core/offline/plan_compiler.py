"""Bounded preview -> task authorization -> byte preserving execution evidence. Offline only."""
import json
from .entry_compiler import digest

def unsigned(v,k):return {a:b for a,b in v.items() if a!=k}
def native_rows(events):
 calls={};results={};models={}
 for e in events:
  if e.get('ptc_analysis_source'):raise ValueError('native evidence required')
  if e['type']=='tool/call':
   cid=e['data']['callId']
   if cid in calls or cid.startswith('sss-'):raise ValueError('runtime/duplicate cannot train effect graph')
   calls[cid]=e
  elif e['type']=='tool/result':
   for b in e['data']['message'].get('content',[]):
    if b.get('type')=='tool-result':results.setdefault(b['toolCallId'],[]).append((e,b))
  elif e['type']=='assistant/message':
   for b in e['data']['message'].get('content',[]):
    if b.get('type')=='tool-call':
     if not e['data'].get('usage') or e['data']['message'].get('source',{}).get('kind')!='model' or b['id'] in models:raise ValueError('real independent model origin required')
     models[b['id']]=(e,b)
 rows=[]
 for cid,c in sorted(calls.items(),key=lambda v:v[1]['seq']):
  rs=results.get(cid,[])
  if len(rs)!=1 or cid not in models:raise ValueError('unique real decision/result required')
  e,b=rs[0];m,mb=models[cid];args=json.loads(c['data']['arguments'])
  if not m['seq']<c['seq']<e['seq'] or mb['name']!=c['data']['name'] or json.loads(mb['arguments'])!=args:raise ValueError('changed argument/name/ordering')
  out=None if b.get('isError') else json.loads(b['content'][0]['text'])
  rows.append({'name':c['data']['name'],'args':args,'out':out,'call_id':cid,'message_seq':m['seq'],'call_seq':c['seq'],'result_seq':e['seq'],'observation_sha256':digest(out)})
 return rows

def effect_snapshot(scope,actions):
 after=dict(scope['initial_snapshot']);by_id={r['file_id']:r for r in scope['inventory']};touched=set();destinations=[];grant=scope['grant']
 if not 1<=len(actions)<=grant['max_actions']:raise ValueError('count outside grant')
 for a in actions:
  if set(a)!= {'op','file_ids','destination','format'} or a['op'] not in grant['allowed_ops'] or a['format']!='none' or len(a['file_ids'])!=1:raise ValueError('effects outside grant')
  r=by_id.get(a['file_ids'][0]);d=a['destination']
  if not r or r['path'] in touched or r['path'] not in grant['source_paths'] or d.startswith('/') or '\\' in d or any(v in ('','.','..') for v in d.split('/')) or not any(d.startswith(p) for p in grant['destination_prefixes']) or d in after:raise ValueError('source/path outside grant')
  if any(d.startswith(v+'/') or v.startswith(d+'/') for v in destinations):raise ValueError('destination overlap')
  touched.add(r['path']);destinations.append(d);after[d]=r['sha256']
  if a['op']!='copy':del after[r['path']]
 return after

def plan_witness(events,scope,tools,trace_id,fingerprint):
 rows=native_rows(events);sources=[r for r in rows if r['name']==tools[0] and r['out']]
 if len(sources)!=1:raise ValueError('single successful preview required')
 p=sources[0];preview=p['out'];a=next((r for r in rows if r['name']==tools[1] and r['call_seq']>p['result_seq']),None)
 x=next((r for r in rows if r['name']==tools[2] and a and r['call_seq']>a['result_seq']),None)
 if not a or not x or not a['out'] or not x['out']:raise ValueError('successful actual authorization and execution required')
 token=a['out'];receipt=x['out'];plan_id=preview['plan_id'];after=effect_snapshot(scope,preview['actions'])
 if set(p['args'])!={'actions'} or [{**{'format':'none'},**a} for a in p['args']['actions']]!=preview['actions'] or preview.get('preview_sha256')!=digest(unsigned(preview,'preview_sha256')) or preview.get('status')!='validated_copy_plan' or preview.get('permission_status')!='within_task_grant' or preview.get('copy_only') is not True:raise ValueError('invalid current model preview')
 for out in (preview,token,receipt):
  if out.get('input_sha256')!=scope['input_version'] or out.get('execution_version_sha256')!=scope['execution_version_sha256'] or out.get('grant_sha256')!=digest(scope['grant']) or out.get('copy_only') is not True:raise ValueError('input/grant/version differs')
 if a['message_seq']<=p['result_seq'] or x['message_seq']<=a['result_seq'] or a['args']!={'plan_id':plan_id} or token.get('plan_id')!=plan_id or token.get('preview_sha256')!=preview['preview_sha256'] or token.get('plan_sha256')!=preview['plan_sha256'] or token.get('snapshot_sha256')!=digest(scope['initial_snapshot']) or preview.get('snapshot_sha256')!=digest(scope['initial_snapshot']) or token.get('authorization_sha256')!=digest(unsigned(token,'authorization_sha256')) or token.get('status')!='task_grant_authorized' or token.get('single_plan') is not True:raise ValueError('actual capability not bound to preview/current grant')
 if x['args']!={'plan_id':plan_id,'authorization_id':token['authorization_id']} or receipt.get('plan_id')!=plan_id or receipt.get('authorization_id')!=token['authorization_id'] or receipt.get('authorization_sha256')!=token['authorization_sha256'] or receipt.get('plan_sha256')!=preview['plan_sha256'] or receipt.get('snapshot_sha256')!=digest(after) or receipt.get('status')!='executed_verified' or receipt.get('operation_count')!=len(preview['actions']):raise ValueError('execution receipt differs from granted effect footprint')
 if any(r['name'] not in tools for r in rows if p['result_seq']<r['call_seq']<x['result_seq']):raise ValueError('interleaving invalidates local plan graph')
 return {'trace_id':trace_id,'task_fingerprint':fingerprint,'tools':tools,'execution_version_sha256':scope['execution_version_sha256'],
  'operation_count':len(preview['actions']),'operations':sorted({r['op'] for r in preview['actions']}),'references':[{k:v for k,v in r.items() if k not in ('args','out')} for r in (p,a,x)],'effects_sha256':digest(after),'grant_sha256':digest(scope['grant'])}

def compile_plan(training,schemas):
 if len(training)<2 or len({r['trace_id'] for r in training})!=len(training) or len({r['task_fingerprint'] for r in training})!=len(training) or len({r['operation_count'] for r in training})<2 or len({r['execution_version_sha256'] for r in training})!=1 or len({digest(r['tools']) for r in training})!=1:raise ValueError('independent varied ordinary plan witnesses required')
 tools=training[0]['tools'];required=[['actions'],['plan_id'],['plan_id','authorization_id']]
 for t,r in zip(tools,required):
  if set(schemas[t].get('required',[]))!=set(r):raise ValueError('contract params differ')
 artifact={'kind':'authorized_copy_plan_chain','status':'compiled_candidate','tools':tools,'training_witnesses':training,
  'source_task_fingerprints':[r['task_fingerprint'] for r in training],'source_trace_ids':[r['trace_id'] for r in training],
  'tool_schema_sha256':{t:digest(schemas[t]) for t in tools},'graph':{'preview_tool':tools[0],'authorize_tool':tools[1],'execute_tool':tools[2],
  'max_actions':6,'allowed_ops':['copy','move','quarantine'],'stop':'after_verified_execution_or_semantic_recovery'},
  'transfer_evidence':[{'from':tools[0]+'.plan_id','to':tools[1]+'.plan_id'}, {'from':tools[0]+'.plan_id','to':tools[2]+'.plan_id'}, {'from':tools[1]+'.authorization_id','to':tools[2]+'.authorization_id'}]}
 return artifact

def certify_plan(artifact,heldout):
 if heldout['trace_id'] in artifact['source_trace_ids'] or heldout['task_fingerprint'] in artifact['source_task_fingerprints'] or heldout['tools']!=artifact['tools'] or heldout['execution_version_sha256']!=artifact['training_witnesses'][0]['execution_version_sha256']:raise ValueError('independent unchanged-version heldout required')
 a={**artifact,'status':'trace_validated_effectful','validation_task_fingerprint':heldout['task_fingerprint'],'validation_witness':heldout};a['certified_digest']=digest(a)
 p={'schema_version':1,'format':'sss-authorized-plan-v1','artifact':a,'execution_version_sha256':heldout['execution_version_sha256']};p['policy_digest']=digest(p);return p
