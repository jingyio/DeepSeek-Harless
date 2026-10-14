"""Actual local observations; fabricated provider metadata is for validation tests only."""
import copy,json
import pytest
from tests.test_collection_compiler import make,TOOLS,CT,common
from src.motif_core.offline.collection_compiler import collection_witness,compile_collection_motif,certify_collection_motif,export_collection_policy
from src.motif_core.offline.reentry_compiler import reentry_witness,compile_reentry,certify_reentry

def parent_policy(make):
 ws=[]
 for label,n in [('old-a',2),('old-b',4),('old-c',3)]:
  _,ev,t=make(label,n);ws.append(collection_witness(ev,t,TOOLS,trace_id=label,task_fingerprint=label))
 a=compile_collection_motif(ws[:2],CT,{t:{'type':'object'} for t in TOOLS});return export_collection_policy(certify_collection_motif(a,ws[2],CT),ws[0]['execution_version_sha256'])
def experience(make,label,n,parent):
 scene,events,scope=make(label,n)
 # Keep the actual model selection; mark inherited execution calls as Runtime, never relabel them as normal.
 replacements={e['data']['callId']:'sss-collection-'+e['data']['callId'] for e in events if e['type']=='tool/call' and e['data']['name']!=TOOLS[0]}
 for e in events:
  if e['type']=='tool/call':e['data']['callId']=replacements.get(e['data']['callId'],e['data']['callId'])
  elif e['type']=='tool/result':
   for b in e['data']['message']['content']:b['toolCallId']=replacements.get(b['toolCallId'],b['toolCallId'])
  elif e['type']=='assistant/message' and e['data']['message']['content'][0]['id'] in replacements:e['data']['message']['source']['kind']='runtime'
 first=json.loads(events[2]['data']['message']['content'][0]['content'][0]['text']);gather=json.loads(events[-1]['data']['message']['content'][0]['content'][0]['text']);boundary=events[-1]['seq']
 audit=[{'kind':'collection_motif_loaded','policy_digest':parent['policy_digest']},{'kind':'collection_motif_selection_verified','call_id':events[1]['data']['callId'],'selection_sha256':common.digest(first)},
  {'kind':'collection_motif_complete','collection_id':gather['collection_id'],'observation_sha256':common.digest(gather)},
  {'kind':'collection_model_request_bypassed_verified','count':len(replacements)}]
 def call(name,args):
  seq=events[-1]['seq']+1;cid=label+'-residual-'+str(seq);out=getattr(scene,name)(**args);raw=json.dumps(args);tool='mcp__file_management__'+name
  events.extend([{'seq':seq,'type':'assistant/message','data':{'usage':{'outputTokens':10},'message':{'source':{'kind':'model'},'content':[{'type':'tool-call','id':cid,'name':tool,'arguments':raw}]}}},
  {'seq':seq+1,'type':'tool/call','data':{'callId':cid,'name':tool,'arguments':raw}}, {'seq':seq+2,'type':'tool/result','data':{'message':{'content':[{'type':'tool-result','toolCallId':cid,'content':[{'type':'text','text':json.dumps(out)}]}]}}}]);return out
 packet=call('select_files',{'file_ids':[r['file_id'] for r in scene.inventory_rows()]});handles=[]
 for row in packet['files']:
  h=call('pin_file',{'file_id':row['file_id']})['source_id'];handles.append(h);call('read_file',{'source_id':h})
 call('collect_reads',{'collection_id':packet['collection_id'],'source_ids':handles});return events,scope,audit,boundary

def test_real_residual_certification_keeps_L1_and_excludes_runtime(make):
 p=parent_policy(make);original=copy.deepcopy(p);episodes=[]
 for label,n in [('fresh-a',2),('fresh-b',5),('fresh-c',3)]:
  ev,t,a,_=experience(make,label,n,p);episodes.append(reentry_witness(ev,t,p,a,label,label))
 c=compile_reentry(episodes[:2],p,CT,{t:{'type':'object'} for t in TOOLS});l2=certify_reentry(c,episodes[2],CT)
 assert l2['parent_policy']==original and l2['next_policy']['artifact']['source_task_fingerprints']==['fresh-a','fresh-b']
 assert all(not r['call_id'].startswith('sss-') for e in episodes for r in e['residual_witness']['references'])
 with pytest.raises(ValueError):certify_reentry(c,episodes[0],CT)
@pytest.mark.parametrize('damage',['parent_digest','boundary_failure','missing_batch','residual_runtime','residual_model_origin','premature_decision'])
def test_bad_handoff_or_native_provenance_rejected(make,damage):
 p=parent_policy(make);ev,t,a,boundary=experience(make,'negative',3,p)
 if damage=='parent_digest':a[0]['policy_digest']='f'*64
 elif damage=='missing_batch':a[-1]['count']=0
 elif damage=='boundary_failure':next(e for e in ev if e['seq']==boundary)['data']['message']['content'][0]['isError']=True
 else:
  selected=next(e for e in ev if e['seq']>boundary and e['type']=='assistant/message')
  if damage=='residual_model_origin':selected['data']['usage']={}
  elif damage=='premature_decision':selected['seq']=boundary-1
  else:next(e for e in ev if e['seq']>boundary and e['type']=='tool/call')['data']['callId']='sss-fake-new-evidence'
 with pytest.raises(ValueError):reentry_witness(ev,t,p,a,'trace','task')
