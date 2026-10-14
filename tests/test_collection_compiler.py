"""Actual local tool observations witness array membership, iteration and gather."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import pytest
from tests.test_file_management import fm,common
from src.adapters.tool_contract_loader import parse_tool_contracts
from src.motif_core.offline.collection_compiler import collection_witness,compile_collection_motif,certify_collection_motif,export_collection_policy

prior={k:sys.modules.get(k) for k in ('common','file_tools')}
sys.modules['common']=common;sys.modules['file_tools']=fm
spec=importlib.util.spec_from_file_location('fm_collection_test',common.HERE/'collection_tools.py')
collection=importlib.util.module_from_spec(spec);spec.loader.exec_module(collection)
for key,value in prior.items():
    if value is None:sys.modules.pop(key,None)
    else:sys.modules[key]=value
TOOLS=['mcp__file_management__'+n for n in ('select_files','pin_file','read_file','collect_reads')]
CT=parse_tool_contracts({t:{'required_params':list(p),'read_only':True,'replay_stable':True,
                          'output_fields':['source_id','file_id','source_version'],'description':'Local collection tool'}
                        for t,p in zip(TOOLS,(('file_ids',),('file_id',),('source_id',),('collection_id','source_ids')))})

@pytest.fixture
def make(tmp_path,monkeypatch):
    monkeypatch.setattr(fm,'ROOT',tmp_path);monkeypatch.setattr(fm,'DATA',tmp_path/'data')
    def factory(label,n):
        root=tmp_path/'data'/label;root.mkdir(parents=True)
        (root/'.experiment-copy').write_text(label)
        for i in range(n):(root/f'{i}.txt').write_text(f'{label} graph record {i}')
        spec={'workspace':str(root),'task_id':label,'family':'inventory','objective':'Read chosen files','rules':{},
              'initial_snapshot':common.snapshot(root),'allowed_operations':[]}
        scene=collection.CollectionScene(spec,tmp_path/'.local'/label);scene.read_task()
        rows=scene.inventory_rows();task={'input_version':scene.input_digest,'snapshot_sha256':common.digest(scene.expected),
             'execution_version_sha256':scene.execution_version,'inventory':rows}
        events=[]
        def call(name,args):
            seq=len(events)+1;cid=f'{label}-{seq}';out=getattr(scene,name)(**args);tool='mcp__file_management__'+name;raw=json.dumps(args)
            events.extend([{'seq':seq,'type':'assistant/message','data':{'usage':{'outputTokens':20},'message':{'source':{'kind':'model'},
                           'content':[{'type':'tool-call','id':cid,'name':tool,'arguments':raw}]}}},
                           {'seq':seq+1,'type':'tool/call','data':{'callId':cid,'name':tool,'arguments':raw}},
                           {'seq':seq+2,'type':'tool/result','data':{'message':{'content':[{'type':'tool-result','toolCallId':cid,
                           'content':[{'type':'text','text':json.dumps(out)}]}]}}}]);return out
        chosen=call('select_files',{'file_ids':[r['file_id'] for r in rows]});handles=[]
        for r in rows:
            pin=call('pin_file',{'file_id':r['file_id']});handles.append(pin['source_id']);call('read_file',{'source_id':pin['source_id']})
        call('collect_reads',{'collection_id':chosen['collection_id'],'source_ids':handles})
        return scene,events,task
    return factory

def test_real_local_foreach_gather_certifies_with_new_size_and_task(make):
    witnesses=[]
    for label,n in [('a',2),('b',5),('c',3)]:
        _,events,task=make(label,n);witnesses.append(collection_witness(events,task,TOOLS,trace_id=label,task_fingerprint=label))
    compiled=compile_collection_motif(witnesses[:2],CT,{t:{'type':'object'} for t in TOOLS})
    certified=certify_collection_motif(compiled,witnesses[2],CT);policy=export_collection_policy(certified,witnesses[0]['execution_version_sha256'])
    assert policy['artifact']['graph']['selection']=='actual_model_selected_members'
    assert [e['mapping'] for e in certified['transfer_evidence']]==['foreach_all_selected','same_iteration','gather_complete','same_collection']
    with pytest.raises(ValueError):certify_collection_motif(compiled,witnesses[0],CT)

@pytest.mark.parametrize('damage',['runtime','changed_result','outside_member','missing_read','premature_read','wrong_gather'])
def test_negative_provenance_and_coverage_cannot_train(make,damage):
    _,events,task=make('negative',3);events=copy.deepcopy(events)
    if damage=='runtime':events[1]['data']['callId']='sss-collection-fake'
    elif damage=='changed_result':events[2]['data']['message']['content'][0]['isError']=True
    elif damage=='outside_member':task['inventory']=task['inventory'][1:]
    elif damage=='missing_read':events=[e for e in events if not 7<=e['seq']<=9]
    elif damage=='premature_read':events[6]['seq']=3
    elif damage=='wrong_gather':
        block=events[-1]['data']['message']['content'][0];out=json.loads(block['content'][0]['text']);out['collection_id']='wrong';block['content'][0]['text']=json.dumps(out)
    with pytest.raises(ValueError):collection_witness(events,task,TOOLS,trace_id='n',task_fingerprint='n')

def test_scope_gather_missing_duplicate_outside_and_stale(make):
    scene,_,_=make('scope',3);rows=scene.inventory_rows();packet=scene.select_files([rows[0]['file_id']])
    with pytest.raises(fm.ToolError):scene.collect_reads(packet['collection_id'],[])
    handle=scene.pin_file(rows[0]['file_id'])['source_id'];scene.read_file(handle)
    with pytest.raises(fm.ToolError):scene.collect_reads(packet['collection_id'],[handle,handle])
    outside=scene.pin_file(rows[1]['file_id'])['source_id'];scene.read_file(outside)
    with pytest.raises(fm.ToolError):scene.collect_reads(packet['collection_id'],[outside])
    assert scene.collect_reads(packet['collection_id'],[handle])['semantic_judgment_certified'] is False
    scene.path(rows[0]['path']).write_text('changed')
    with pytest.raises(fm.ToolError):scene.collect_reads(packet['collection_id'],[handle])

def test_empty_selection_is_explicit_and_file_state_is_preserved(make):
    scene,_,_=make('empty',1);before=common.snapshot(scene.root);packet=scene.select_files([])
    assert scene.collect_reads(packet['collection_id'],[])['count']==0
    assert common.snapshot(scene.root)==before
