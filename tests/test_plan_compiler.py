"""Compiler receives actual local service observations; synthetic provider metadata is test-only."""
import copy
import pytest
from tests.test_authorized_plan import scene,mod,fm,common
from src.motif_core.offline.plan_compiler import plan_witness,compile_plan,certify_plan
TOOLS=['mcp__file_management__'+n for n in ('preview_actions','authorize_plan','execute_plan')]
def fixture(s,count=1):
 rows=s.list_files()['files'];actions=[fm.Action(op='copy',file_ids=[r['file_id']],destination='processed/'+r['path']).model_dump() for r in rows[:count]]
 p=s.preview_actions(actions);a=s.authorize_plan(p['plan_id']);r=s.execute_plan(p['plan_id'],a['authorization_id'])
 args=[{'actions':actions},{'plan_id':p['plan_id']},{'plan_id':p['plan_id'],'authorization_id':a['authorization_id']}];outs=[p,a,r];events=[]
 import json
 for i,(tool,arg,out) in enumerate(zip(TOOLS,args,outs)):
  cid='normal-'+str(i);base=i*3
  events.extend([{'seq':base,'type':'assistant/message','data':{'usage':{'outputTokens':1},'message':{'source':{'kind':'model'},'content':[{'type':'tool-call','id':cid,'name':tool,'arguments':json.dumps(arg)}]}}},
   {'seq':base+1,'type':'tool/call','data':{'callId':cid,'name':tool,'arguments':json.dumps(arg)}},
   {'seq':base+2,'type':'tool/result','data':{'message':{'content':[{'type':'tool-result','toolCallId':cid,'content':[{'type':'text','text':json.dumps(out)}]}]}}}])
 inventory=[{'file_id':'file:local:'+common.digest({'path':n,'sha':h})[:24],'path':n,'sha256':h} for n,h in s.spec['initial_snapshot'].items() if n!='.experiment-copy']
 scope={'initial_snapshot':s.spec['initial_snapshot'],'inventory':inventory,'grant':s.grant,'input_version':s.input_digest,'execution_version_sha256':mod.execution_version()};return events,scope
@pytest.mark.parametrize('damage',['runtime','origin','grant','receipt','ordering','token'])
def test_plan_evidence_rejects(scene,damage):
 import json
 events,scope=fixture(scene)
 if damage=='runtime':events[1]['data']['callId']='sss-fake'
 elif damage=='origin':events[0]['data']['usage']={}
 elif damage=='ordering':events[3]['seq']=1
 else:
  i=5 if damage in ('grant','token') else 8;b=events[i]['data']['message']['content'][0];out=json.loads(b['content'][0]['text']);out['grant_sha256' if damage=='grant' else 'authorization_id' if damage=='token' else 'operation_count']='changed';b['content'][0]['text']=json.dumps(out)
 with pytest.raises(ValueError):plan_witness(events,scope,TOOLS,'trace','task')
def test_independent_varying_traces_and_heldout(scene):
 events,scope=fixture(scene);w=plan_witness(events,scope,TOOLS,'trace-1','task-1')
 with pytest.raises(ValueError):compile_plan([w,w],{})
 # Negative independence/contract checks are distinct from evidence extraction.
 other={**w,'trace_id':'trace-2','task_fingerprint':'task-2','operation_count':2}
 schemas={t:{'required':r} for t,r in zip(TOOLS,[['actions'],['plan_id'],['plan_id','authorization_id']])};a=compile_plan([w,other],schemas)
 with pytest.raises(ValueError):certify_plan(a,w)
 p=certify_plan(a,{**w,'trace_id':'trace-3','task_fingerprint':'task-3'});assert p['artifact']['status']=='trace_validated_effectful'
