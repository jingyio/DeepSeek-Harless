import copy
import json
import pytest
from src.adapters.tool_contract_loader import parse_tool_contracts
from src.motif_core.offline.entry_compiler import inventory_witness,compile_inventory_motif,certify_entry_motif,digest
from src.motif_core.offline.library_builder import library_from_certified
S='mcp__test__list';P='mcp__test__prepare'
C=parse_tool_contracts({S:{'read_only':True,'replay_stable':False,'required_params':[]},P:{'read_only':True,'replay_stable':False,'required_params':['paper_id']}})
def sample(n,tag):
    papers=[{'paper_id':tag+str(i),'pdf_sha256':'a'*64} for i in range(n)]
    task={'inventory_papers':papers,'input_version':'b'*64,'question':tag,'target_versions':{p['paper_id']:'c'*64 for p in papers},'parser_profile_sha256':'d'*64}
    events=[]
    def request(rows):
        blocks=[{'type':'tool-call','id':'c'+str(len(events))+'-'+str(i),'name':tool,'arguments':json.dumps(args)} for i,(tool,args,out) in enumerate(rows)]
        events.append({'type':'assistant/message','seq':len(events),'data':{'usage':{'outputTokens':10},'message':{'source':{'kind':'model'},'content':blocks}}})
        for b,(_,_,out) in zip(blocks,rows):
            events.append({'type':'tool/call','seq':len(events),'data':{'callId':b['id'],'name':b['name'],'arguments':b['arguments']}})
            events.append({'type':'tool/result','seq':len(events),'data':{'message':{'content':[{'type':'tool-result','toolCallId':b['id'],'content':[{'type':'text','text':json.dumps(out)}]}]}}})
    request([(S,{}, {'papers':papers,'task_sha256':task['input_version'],'question':tag})])
    request([(P,{'paper_id':p['paper_id']},{**p,'document_version_sha256':'c'*64,'parser_profile_sha256':'d'*64,'cache_stats':{}}) for p in reversed(papers)])
    return task,events

def witness(n,tag):
    t,e=sample(n,tag);return inventory_witness(e,t,S,P,trace_id=tag,task_fingerprint=tag)

def test_learns_array_membership_with_permuted_execution_and_nonstable_contracts():
    compiled=compile_inventory_motif([witness(3,'a'),witness(2,'b')],C,source_tool=S,prepare_tool=P,schemas={S:{},P:{}})
    a=certify_entry_motif(compiled,witness(1,'new'),C)
    assert library_from_certified([a])['heldout_trace_ids']==['new']
    assert a['projection_excluded_fields']==['cache_stats']
    assert not C[P].replay_stable
    with pytest.raises(ValueError):certify_entry_motif(compiled,witness(3,'a'),C)

@pytest.mark.parametrize('change',['wrong_inventory','changed_pdf','duplicate','missing','runtime','no_usage','prepare_before_source','semantic_interruption','tool_error','altered_call'])
def test_rejects_unproved_array_binding(change):
    task,events=sample(2,'x')
    if change=='wrong_inventory':task['question']='different'
    if change=='changed_pdf':task['inventory_papers'][0]['pdf_sha256']='f'*64
    if change=='duplicate':task['inventory_papers'][1]=task['inventory_papers'][0]
    if change=='missing':task['inventory_papers'].append({'paper_id':'extra','pdf_sha256':'a'*64})
    if change=='runtime':events[0]['data']['message']['content'][0]['id']='sss-entry-x'
    if change=='no_usage':events[0]['data']['usage']=None
    if change=='prepare_before_source':events[3]['seq']=1
    if change=='semantic_interruption':events[3]['data']['message']['content'][0]['name']='mcp__test__search'
    if change=='tool_error':events[2]['data']['message']['content'][0]['isError']=True
    if change=='altered_call':events[4]['data']['arguments']='{}'
    with pytest.raises(ValueError):inventory_witness(events,task,S,P,trace_id='x',task_fingerprint='x')


def incremental_sample(n, tag):
    task, events = sample(n, tag)
    source = events[2]['data']['message']['content'][0]['content'][0]
    plan = {'work': [{'paper_id': p['paper_id'], 'fields_to_review': ['method']} for p in task['inventory_papers']],
            'retained_claim_ids': ['claim:untouched:method'], 'synthesis_requires_review': True,
            'task_sha256': task['input_version'], 'question': tag, 'plan_sha256': 'e' * 64}
    source['text'] = json.dumps(plan)
    task.update(plan_sha256=plan['plan_sha256'], source_result_sha256=digest(plan))
    return task, events


def incremental_witness(n, tag):
    t, e = incremental_sample(n, tag)
    return inventory_witness(e, t, S, P, trace_id=tag, task_fingerprint=tag, frontier='incremental')


def test_incremental_learns_only_actual_work_array_and_certifies_a_new_task():
    compiled = compile_inventory_motif([incremental_witness(2, 'a'), incremental_witness(1, 'b')], C,
        source_tool=S, prepare_tool=P, schemas={S: {}, P: {}}, frontier='incremental')
    a = certify_entry_motif(compiled, incremental_witness(1, 'new'), C)
    assert a['entry']['selection'] == 'all_invalidated_work'
    assert a['entry']['array_field'] == 'work'
    assert a['transfer_evidence'][0]['from_field'] == 'work[].paper_id'
    with pytest.raises(ValueError): certify_entry_motif(compiled, witness(1, 'wrong-kind'), C)


@pytest.mark.parametrize('change', ['retained', 'plan', 'work', 'untouched_prepare'])
def test_incremental_rejects_changed_plan_or_processing_retained_paper(change):
    t, e = incremental_sample(1, 'x')
    block = e[2]['data']['message']['content'][0]['content'][0]
    plan = json.loads(block['text'])
    if change == 'retained': plan['retained_claim_ids'] = []
    if change == 'plan': plan['plan_sha256'] = 'f' * 64
    if change == 'work': plan['work'][0]['fields_to_review'] = ['findings']
    if change == 'untouched_prepare':
        e[3]['data']['message']['content'][0]['arguments'] = '{"paper_id":"untouched"}'
        e[4]['data']['arguments'] = '{"paper_id":"untouched"}'
    block['text'] = json.dumps(plan)
    with pytest.raises(ValueError):
        inventory_witness(e, t, S, P, trace_id='x', task_fingerprint='x', frontier='incremental')
