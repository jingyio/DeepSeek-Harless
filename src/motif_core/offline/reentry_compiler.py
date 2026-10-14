"""L1 handoff -> genuinely model-produced residual graph -> independently certified L2."""
from __future__ import annotations
import json
from .entry_compiler import digest
from .collection_compiler import collection_witness,compile_collection_motif,certify_collection_motif,export_collection_policy

def unsigned(v,k):return {a:b for a,b in v.items() if a!=k}
def reentry_witness(events,scope,parent,audit,trace_id,fingerprint):
 if parent['policy_digest']!=digest(unsigned(parent,'policy_digest')):raise ValueError('parent digest changed')
 if sum(r.get('kind')=='collection_motif_loaded' and r.get('policy_digest')==parent['policy_digest'] for r in audit)!=1:raise ValueError('frozen L1 must actually be loaded')
 calls={e['data']['callId']:e for e in events if e.get('type')=='tool/call'};results={};models={}
 if len(calls)!=sum(e.get('type')=='tool/call' for e in events):raise ValueError('duplicate call identity')
 for e in events:
  if e.get('ptc_analysis_source'):raise ValueError('native events required')
  if e.get('type')=='tool/result':
   for b in e['data']['message'].get('content',[]):
    if b.get('type')=='tool-result':results.setdefault(b['toolCallId'],[]).append((e,b))
  if e.get('type')=='assistant/message':
   for b in e['data']['message'].get('content',[]):
    if b.get('type')=='tool-call':models.setdefault(b['id'],[]).append((e,b))
 def actual(cid,model=False):
  if cid not in calls or len(results.get(cid,[]))!=1:raise ValueError('unique actual call/result required')
  c=calls[cid];r,b=results[cid][0];content=b.get('content',[])
  if b.get('isError') or len(content)!=1 or content[0].get('type')!='text' or c['seq']>=r['seq']:raise ValueError('failed/changed parent observation')
  args=json.loads(c['data']['arguments']);out=json.loads(content[0]['text'])
  if model:
   ms=models.get(cid,[])
   if cid.startswith('sss-') or len(ms)!=1:raise ValueError('actual model decision required')
   m,block=ms[0]
   if not m['data'].get('usage') or m['data']['message'].get('source',{}).get('kind')!='model' or m['seq']>=c['seq'] or block['name']!=c['data']['name'] or json.loads(block['arguments'])!=args:raise ValueError('original provider usage and arguments required')
  return c,r,args,out
 selected=[r for r in audit if r.get('kind')=='collection_motif_selection_verified'];complete=[r for r in audit if r.get('kind')=='collection_motif_complete']
 if len(selected)!=1 or len(complete)!=1:raise ValueError('one successful parent episode required')
 sc,sr,args,packet=actual(selected[0]['call_id'],True);g=parent['artifact']['graph'];tools=parent['artifact']['tools']
 if sc['data']['name']!=g['source_tool'] or args!={'file_ids':[r['file_id'] for r in packet['files']]} or packet['input_sha256']!=scope['input_version'] or packet['execution_version_sha256']!=scope['execution_version_sha256'] or packet['snapshot_sha256']!=scope['snapshot_sha256'] or packet['collection_sha256']!=digest(unsigned(packet,'collection_sha256')) or digest(packet)!=selected[0]['selection_sha256']:raise ValueError('parent selection/version changed')
 if any(r not in scope['inventory'] for r in packet['files']):raise ValueError('parent selection outside current inventory')
 gs=[]
 for cid,c in calls.items():
  if c['data']['name']==g['gather_tool'] and cid.startswith('sss-'):
   row=actual(cid)
   if row[3].get('collection_id')==complete[0]['collection_id']:gs.append(row)
 if len(gs)!=1:raise ValueError('unique actual parent completion boundary required')
 gc,gr,ga,gather=gs[0];boundary=gr['seq']
 generated=[cid for cid,c in calls.items() if cid.startswith('sss-') and c['seq']<=boundary]
 batches=[r for r in audit if r.get('kind')=='collection_model_request_bypassed_verified']
 if sum(r['count'] for r in batches)!=len(generated) or gather['collection_id']!=packet['collection_id'] or gather['status']!='collection_complete' or gather['coverage_sha256']!=digest(gather['files']) or digest(gather)!=complete[0]['observation_sha256']:raise ValueError('parent boundary not fully verified')
 for row in gather['files']:
  matches=[]
  for cid in generated:
   c,r,a,out=actual(cid)
   if c['data']['name']==g['read_tool'] and out.get('file_id')==row['file_id']:
    if a!={'source_id':row['source_id']} or digest(out)!=row['read_sha256'] or out['source_version']!=row['source_version']:raise ValueError('parent read not backed by actual runtime result')
    matches.append(cid)
  if len(matches)!=1:raise ValueError('parent member coverage differs')
 if {r['file_id'] for r in gather['files']}!={r['file_id'] for r in packet['files']}:raise ValueError('parent coverage incomplete')
 # This view retains original sequence IDs and provider usage; it never relabels Runtime calls.
 suffix=[e for e in events if e['seq']>boundary]
 w=collection_witness(suffix,scope,tools,trace_id=trace_id,task_fingerprint=fingerprint)
 if w['references'][0]['message_seq']<=boundary:raise ValueError('next set was not a fresh model decision after handoff')
 return {'kind':'parent_handoff_then_native_collection','trace_id':trace_id,'task_fingerprint':fingerprint,
  'parent_policy_digest':parent['policy_digest'],'parent_boundary':{'call_id':gc['data']['callId'],'result_seq':boundary,
  'observation_sha256':digest(gather),'selection_call_id':sc['data']['callId'],'count':gather['count']},
  'residual_witness':w,'runtime_nodes_used_for_new_parameter_discovery':False}

def compile_reentry(training,parent,contracts,schemas):
 if len(training)<2 or any(t['parent_policy_digest']!=parent['policy_digest'] for t in training):raise ValueError('new L1 execution experience required')
 child=compile_collection_motif([t['residual_witness'] for t in training],contracts,schemas)
 return {'kind':'collection_reentry_candidate','status':'compiled_candidate','parent_policy':parent,'child_candidate':child,
  'episodes':training,'max_episodes':2,'trigger':'fresh_model_selection_after_verified_gather','auto_select':False}

def certify_reentry(candidate,heldout,contracts):
 if candidate['status']!='compiled_candidate' or heldout['parent_policy_digest']!=candidate['parent_policy']['policy_digest']:raise ValueError('unchanged L1 certification required')
 a=certify_collection_motif(candidate['child_candidate'],heldout['residual_witness'],contracts)
 child=export_collection_policy(a,heldout['residual_witness']['execution_version_sha256'])
 artifact={'kind':'certified_collection_reentry','status':'trace_validated_read_only','training_episodes':candidate['episodes'],'validation_episode':heldout,
  'source_task_fingerprints':[t['task_fingerprint'] for t in candidate['episodes']],'validation_task_fingerprint':heldout['task_fingerprint'],
  'max_episodes':2,'trigger':candidate['trigger'],'auto_select':False,'parent_boundary_is_execution_evidence_only':True,
  'runtime_nodes_used_for_new_parameter_discovery':False}
 artifact['certified_digest']=digest(artifact)
 p={'schema_version':1,'format':'sss-collection-reentry-v1','parent_policy':candidate['parent_policy'],'next_policy':child,'artifact':artifact,
  'execution_version_sha256':child['execution_version_sha256']};p['policy_digest']=digest(p);return p
