import copy,json
import pytest
from src.adapters.tool_contract_loader import parse_tool_contracts
from src.motif_core.offline.terminal_compiler import terminal_witness,compile_terminal,certify_terminal
TOOL='mcp__literature_pdf_repair__submit_claim_repair'
CONTRACTS=parse_tool_contracts({TOOL:{'required_params':['decisions','synthesis_hypothesis'],'read_only':True,'replay_stable':False}})

def sample(n,tag):
 args={'decisions':[{'claim_id':tag+str(i)} for i in range(n)],'synthesis_hypothesis':'fixture'}
 receipt={'artifact':'private-artifact','input_sha256':'a'*64,'status':'preview'}
 block={'type':'tool-call','id':tag,'name':TOOL,'arguments':json.dumps(args)}
 events=[{'type':'assistant/message','seq':1,'data':{'usage':{'outputTokens':10},'message':{'source':{'kind':'model'},'content':[block]}}},
  {'type':'tool/call','seq':2,'data':{'callId':tag,'name':TOOL,'arguments':json.dumps(args)}},
  {'type':'tool/result','seq':3,'data':{'message':{'content':[{'type':'tool-result','toolCallId':tag,'content':[{'type':'text','text':json.dumps(receipt)}]}]}}},
  {'type':'assistant/message','seq':4,'data':{'usage':{'outputTokens':5},'message':{'source':{'kind':'model'},'content':[{'type':'text','text':'preview'}]},
   'stream':[{'type':'chunk','chunk':{'type':'finish','reason':{'kind':'stop'}}}]}},
  {'type':'turn/end','seq':5,'data':{}}]
 return events

def witness(n,tag):
 return terminal_witness(sample(n,tag),TOOL,trace_id=tag,task_fingerprint=tag,input_version='a'*64,request_version='b'*64,target_ids=[tag+str(i) for i in range(n)])

def test_certifies_stop_only_after_independent_original_receipts():
 c=compile_terminal([witness(1,'a'),witness(2,'b')],CONTRACTS,tool=TOOL,schema={})
 a=certify_terminal(c,witness(1,'new'),CONTRACTS)
 assert a['terminal']['provider_requests']==0 and a['terminal']['statuses']==['preview']
 with pytest.raises(ValueError):certify_terminal(c,witness(1,'a'),CONTRACTS)
 w=witness(1,'fresh');w['status']='needs_review'
 with pytest.raises(ValueError):certify_terminal(c,w,CONTRACTS)

@pytest.mark.parametrize('change',['runtime','no_usage','pending','failure','mixed','future_tool','steer','not_stop','different_call'])
def test_rejects_unproved_or_nonterminal_decisions(change):
 es=sample(1,'x')
 if change=='runtime':es[0]['data']['message']['content'][0]['id']='sss-raw'
 if change=='no_usage':es[3]['data']['usage']=None
 if change=='pending':es[2]['data']['message']['content'][0]['content'][0]['text']='{"status":"pending_claim_decisions"}'
 if change=='failure':es[2]['data']['message']['content'][0]['isError']=True
 if change=='mixed':es[0]['data']['message']['content'].append(copy.deepcopy(es[0]['data']['message']['content'][0]))
 if change=='future_tool':es.append({'type':'tool/call','seq':6,'data':{'callId':'other','name':'other'}})
 if change=='steer':es.append({'type':'user/message','seq':6,'data':{}})
 if change=='not_stop':es[3]['data']['stream'][0]['chunk']['reason']={'kind':'length'}
 if change=='different_call':es[1]['data']['arguments']='{}'
 with pytest.raises(ValueError):terminal_witness(es,TOOL,trace_id='x',task_fingerprint='x',input_version='a'*64,request_version='b'*64,target_ids=['x'])
