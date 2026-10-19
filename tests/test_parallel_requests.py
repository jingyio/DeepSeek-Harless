"""Parallel prepared routes retain request ownership and independent evidence."""
import copy
from src.motif_core.offline.operation_graph import catalog,discover_graphs,certify_graph,witnesses
from src.motif_core.offline.experience_registry import digest
from src.adapters.general_tool_replay import operator_contract

NAMES=['mcp__file_management__'+n for n in ['prepare_tool_call','execute_tool_call','inspect_tool_result']]
def frames():
    tools=catalog([{'name':n,'input_schema':{'type':'object','properties':{p:{'type':'string'}},'required':[p]},'_meta':{'sss_learning':operator_contract(n.split('__')[-1])}}
        for n,p in zip(NAMES,['intent','request_id','receipt_id'])]);ff=[]
    for k in range(3):
        scope={'execution_version':'a'*64,'input_sha256':digest(k)};rows=[]
        def row(i,j):
            q='tool-request-'+('%032x'%(k*10+j+1));r=q.replace('tool-request-','tool-result-');lane={'format':'sss-prepared-request-v1','request_id':q,'request_sha256':digest([k,j]),'isolated_outputs':True}
            out={'_sss_scope':scope,'_sss_request_lane':lane,'request_id':q,'status':'prepared_certifiable' if i==0 else 'completed'}
            if i==0:out['request_sha256']=lane['request_sha256']
            else:out['receipt_id']=r
            if i==1:out['_sss_authorized']=True
            return {'name':NAMES[i],'args':{['intent','request_id','receipt_id'][i]:['native intent '+str(j),q,r][i]},'out':out,'call_id':f'{k}-{i}-{j}','message_seq':1+i*5,'call_seq':len(rows)*2+2,'result_seq':len(rows)*2+3}
        for i,j in [(0,0),(0,1),(1,1),(1,0),(2,0),(2,1)]:rows.append(row(i,j))
        ff.append({'tools':tools,'scope':scope,'rows':rows,'fingerprint':digest(k),'trace_id':str(k),'record':{'events_sha256':digest(rows)}})
    return ff

def test_parallel_native_routes_are_learned_from_real_parameter_transfers():
    ff=frames();c,_=discover_graphs(ff[:2]);full=next(x for x in c if len(x['compiled']['nodes'])==3)
    p=certify_graph(full['compiled'],ff[2]);assert len(p['artifact']['request_lane_contracts'])==3
    assert len([w for w in witnesses(ff[2]['rows'],ff[2]['tools'],ff[2]['scope']) if len(w['nodes'])==3])==2

def test_unscoped_or_unregistered_peer_preparation_is_a_barrier():
    for damage in ('scope','hash','isolated','unknown_contract'):
        ff=frames();f=ff[0]
        if damage=='scope':f['rows'][1]['out']['_sss_scope']={}
        if damage=='hash':f['rows'][1]['out']['_sss_request_lane']['request_sha256']='wrong'
        if damage=='isolated':f['rows'][1]['out']['_sss_request_lane']['isolated_outputs']=False
        if damage=='unknown_contract':f['tools'][NAMES[0]]['contract'].pop('request_lane')
        assert not any(len(w['nodes'])==3 and w['calls'][0]==f['rows'][0]['call_id'] for w in witnesses(f['rows'],f['tools'],f['scope']))

def test_independent_verifier_replays_concurrent_paths_and_rejects_cross_binding(monkeypatch):
    from src.adapters import continuous_motif_learning as m
    ff=frames();c,_=discover_graphs(ff[:2]);p=certify_graph(next(x['compiled'] for x in c if len(x['compiled']['nodes'])==3),ff[2]);f=ff[2]
    for r in f['rows']:r['generated']=False
    monkeypatch.setattr(m,'frame',lambda record:f)
    roots=[r['call_id'] for r in f['rows'][:2]];a=[{'kind':'operation_root_verified','entry_id':p['policy_digest'],'call_id':r} for r in roots]
    for j,root in enumerate(roots):a.append({'kind':'operation_graph_complete','entry_id':p['policy_digest'],'root_call_id':root,'operation_call_ids':[f'2-{i}-{j}' for i in range(3)],'nodes':3})
    record={'verified_motif_batches':4,'deferred':[]};assert m.verify_operation_execution(p,record,a)
    bad=copy.deepcopy(a);bad[-1]['operation_call_ids'][1]='2-1-0';assert not m.verify_operation_execution(p,record,bad)
    assert not m.verify_operation_execution(p,{**record,'deferred':[{'reason':'other actual failure'}]},a)

def test_unknown_business_can_prepare_without_claiming_isolated_execution():
    f=frames()[0];peer=copy.deepcopy(f['rows'][1]);peer['out']['status']='prepared'
    peer['out']['_sss_request_lane'].update(isolated_outputs=False,stage_only=True)
    f['rows'][1]=peer
    assert any(len(w['nodes'])==3 and w['calls'][0]==f['rows'][0]['call_id'] for w in witnesses(f['rows'],f['tools'],f['scope']))
    # The same declaration never allows an unsupported business execution.
    unknown=copy.deepcopy(f['rows'][2]);unknown['out']['_sss_request_lane'].update(isolated_outputs=False,stage_only=True)
    f['rows'][2]=unknown
    assert not any(len(w['nodes'])==3 and w['calls'][0]==f['rows'][0]['call_id'] for w in witnesses(f['rows'],f['tools'],f['scope']))
