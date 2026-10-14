import copy
import json
import pytest
from src.adapters.tool_contract_loader import parse_tool_contracts
from src.motif_core.offline.entry_compiler import entry_witness, compile_entry_motif, certify_entry_motif
from src.motif_core.offline.library_builder import library_from_certified

TOOL='mcp__test__read_packet'
CONTRACTS=parse_tool_contracts({TOOL:{'required_params':['id'],'read_only':True,'replay_stable':True}})

def sample(count,tag):
    task={'target_ids':[tag+str(i) for i in range(count)],'input_version':'a'*64,
          'target_versions':{tag+str(i):'b'*64 for i in range(count)}}
    blocks=[{'type':'tool-call','id':f'call{i}','name':TOOL,'arguments':json.dumps({'id':t})} for i,t in enumerate(task['target_ids'])]
    events=[{'type':'assistant/message','seq':0,'data':{'usage':{'outputTokens':20},'message':{'source':{'kind':'model'},'content':blocks}}}]
    for i,(target,block) in enumerate(zip(task['target_ids'],blocks)):
        events.extend([{'type':'tool/call','seq':i*2+1,'data':{'callId':block['id'],'name':TOOL,'arguments':block['arguments']}},
            {'type':'tool/result','seq':i*2+2,'data':{'message':{'content':[{'type':'tool-result','toolCallId':block['id'],'isError':False,
                'content':[{'type':'text','text':json.dumps({'id':target,'input_sha256':'a'*64,'document_version_sha256':'b'*64})}]}]}}}])
    return task,events

def witness(count,tag):
    task,events=sample(count,tag)
    return entry_witness(events,task,TOOL,'id',trace_id=tag,task_fingerprint=tag)

def test_varying_lists_certify_a_new_task_and_existing_library_accepts_artifact():
    compiled=compile_entry_motif([witness(3,'a'),witness(2,'b')],CONTRACTS,tool=TOOL,param='id',schema_sha256='c'*64)
    artifact=certify_entry_motif(compiled,witness(1,'heldout'),CONTRACTS)
    assert artifact['entry']['selection']=='all_targets'
    assert library_from_certified([artifact])['heldout_trace_ids']==['heldout']
    with pytest.raises(ValueError,match='new task'):
        certify_entry_motif(compiled,witness(3,'a'),CONTRACTS)

@pytest.mark.parametrize('mutation',['missing','duplicate','wrong_input','failed','runtime','no_usage','changed_argument'])
def test_entry_witness_rejects_unproved_or_non_original_prefixes(mutation):
    task,events=sample(2,'t')
    if mutation=='missing': task['target_ids'].append('missing');task['target_versions']['missing']='b'*64
    if mutation=='duplicate': task['target_ids'][1]=task['target_ids'][0]
    if mutation=='wrong_input': task['input_version']='d'*64
    if mutation=='failed': events[2]['data']['message']['content'][0]['isError']=True
    if mutation=='runtime': events[0]['data']['message']['content'][0]['id']='sss-entry-fake'
    if mutation=='no_usage': events[0]['data']['usage']=None
    if mutation=='changed_argument': events[1]['data']['arguments']='{"id":"different"}'
    with pytest.raises(ValueError):entry_witness(events,task,TOOL,'id',trace_id='t',task_fingerprint='t')

def test_same_cardinality_or_task_is_not_repeated_frontier_evidence():
    with pytest.raises(ValueError,match='varying'):
        compile_entry_motif([witness(2,'a'),witness(2,'b')],CONTRACTS,tool=TOOL,param='id',schema_sha256='c'*64)
