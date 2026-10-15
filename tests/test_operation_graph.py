"""New topology/name discovery, provenance, ambiguity and semantic boundaries."""
import copy
from src.motif_core.offline.operation_graph import discover_graphs,certify_graph,witnesses,catalog,CONTRACT
from src.motif_core.offline.experience_registry import digest

def frames(branch=False):
    values=[]
    for k in ('one','two','cert'):
        names=['mcp__different__prepare','mcp__different__perform','mcp__different__inspect']
        contracts=[]
        for i,n in enumerate(names):
            c={'format':CONTRACT,'effect':'stage' if i==0 else 'authorized_write' if i==1 else 'read',
               'auto_continue':i>0,'exports':['first','branch'] if i==0 else ['second'] if i==1 else []}
            contracts.append({'name':n,'input_schema':{'type':'object','required':['intent' if i==0 else 'handle']},'_meta':{'sss_learning':c}})
        scope={'execution_version':'a'*64,'input_sha256':digest(k)}
        rows=[{'name':names[0],'args':{'intent':k},'out':{'first':k+'-a','branch':k+'-branch','_sss_scope':scope},'call_id':k+'-0','message_seq':1},
              {'name':names[1],'args':{'handle':k+'-a'},'out':{'second':k+'-b','_sss_scope':scope,'_sss_authorized':True},'call_id':k+'-1','message_seq':4},
              {'name':names[2],'args':{'handle':k+'-branch' if branch else k+'-b'},'out':{'_sss_scope':scope},'call_id':k+'-2','message_seq':7}]
        values.append({'tools':catalog(contracts),'scope':scope,'rows':rows,'fingerprint':digest(k),'trace_id':k,'record':{'events_sha256':digest(rows)}})
    return values

def test_names_and_route_come_from_actual_variable_dependencies():
    ff=frames();c,excluded=discover_graphs(ff[:2]);assert not excluded and len(c)==2
    # Both the full route and a later native semantic root are valid entries.
    assert [n['tool'] for n in c[0]['compiled']['nodes']]==[r['name'] for r in ff[0]['rows']]
    p=certify_graph(c[0]['compiled'],ff[2]);assert p['artifact']['status']=='trace_validated_effectful'
    assert p['artifact']['nodes'][2]['bindings']['handle']=={'node':1,'path':'second'}

def test_fanout_is_inferred_without_a_written_sequence():
    ff=frames(True);c,_=discover_graphs(ff[:2]);p=certify_graph(c[0]['compiled'],ff[2])
    assert p['artifact']['nodes'][2]['bindings']['handle']['node']==0

def test_new_generated_nodes_cannot_discover_parameters_but_certified_prefix_can():
    ff=frames();parent={'policy_digest':'p'*64,'artifact':{'nodes':[
        {'tool':ff[0]['rows'][0]['name'],'bindings':{}},
        {'tool':ff[0]['rows'][1]['name'],'bindings':{'handle':{'node':0,'path':'first'}}}]}}
    for f in ff[:2]:
        f['rows'][1].update(generated=True,message_seq=None);f['parents']=[parent]
    c,_=discover_graphs(ff[:2]);assert len(c)==1
    assert all(w['native_new_nodes']==[2] for w in c[0]['compiled']['witnesses'])
    for f in ff[:2]:f['parents']=[]
    assert not discover_graphs(ff[:2])[0]

def test_semantic_required_arguments_scope_failure_and_constant_values_stop_learning():
    for damage in ('semantic','unbound','scope','authority','constant'):
        ff=frames()
        for f in ff[:2]:
            if damage=='semantic':f['tools'][f['rows'][1]['name']]['contract']['auto_continue']=False
            if damage=='unbound':f['rows'][1]['args']['unapproved']='semantic text'
            if damage=='scope':f['rows'][1]['out']['_sss_scope']={}
            if damage=='authority':f['rows'][1]['out']['_sss_authorized']=False
            if damage=='constant':
                f['rows'][0]['out']['first']='constant';f['rows'][1]['args']['handle']='constant'
        c,_=discover_graphs(ff[:2]);assert not any(v['compiled']['nodes'][0]['tool']==ff[0]['rows'][0]['name'] for v in c),damage

def test_reused_native_certification_rejected():
    import pytest
    ff=frames();c,_=discover_graphs(ff[:2])
    with pytest.raises(ValueError,match='overlaps'):certify_graph(c[0]['compiled'],ff[0])

def test_declared_read_interleaving_preserves_parameter_route_but_unknown_calls_are_barriers():
    ff=frames();name='mcp__different__inventory'
    for f in ff:
        tool={'name':name,'input_schema':{'type':'object','required':[]},'_meta':{'sss_learning':{
          'format':CONTRACT,'effect':'read','auto_continue':False,'exports':[],'safe_interleaving':True}}}
        f['tools'].update(catalog([tool]));f['rows'].insert(2,{'name':name,'args':{},'out':{'_sss_scope':f['scope']},'call_id':'read-'+f['trace_id'],'message_seq':6})
    c,_=discover_graphs(ff[:2]);p=certify_graph(c[0]['compiled'],ff[2]);assert len(p['artifact']['nodes'])==3
    for f in ff:f['tools'][name]['contract']['safe_interleaving']=False
    c,_=discover_graphs(ff[:2]);assert not any(len(v['compiled']['nodes'])==3 for v in c)

def test_actual_failed_tool_events_are_not_erased_between_graph_nodes():
    import json
    from src.adapters.continuous_motif_learning import operation_observations
    f=frames()[0];rows=copy.deepcopy(f['rows']);failed={'name':'mcp__different__inventory','call_id':'failed','args':{},'out':{'error':'failed actual read'}}
    rows.insert(1,failed)
    events=[{'seq':0,'type':'assistant/message','data':{'usage':{'inputTokens':1},'message':{'source':{'kind':'model'},
             'content':[{'type':'tool-call','id':r['call_id']} for r in rows]}}}]
    for i,r in enumerate(rows):
        events.extend([{'seq':2*i+1,'type':'tool/call','data':{'name':r['name'],'callId':r['call_id'],'arguments':json.dumps(r['args'])}},
          {'seq':2*i+2,'type':'tool/result','data':{'message':{'content':[{'type':'tool-result','toolCallId':r['call_id'],
            'isError':r is failed,'content':[{'type':'text','text':json.dumps(r['out'])}]}]}}}])
    observed=operation_observations(events)
    assert len(observed)==4 and observed[1]['out'] is None
    assert not any(len(w['nodes'])==3 for w in witnesses(observed,f['tools'],f['scope']))
