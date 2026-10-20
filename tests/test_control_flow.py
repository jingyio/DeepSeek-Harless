"""Finite branch/loop discovery, independent evidence and real-path replay."""
import copy
import pytest
from src.motif_core.offline.experience_registry import digest
from src.motif_core.offline.operation_graph import catalog
from src.motif_core.offline.control_flow import discover_flows,certify_flow,verify_execution_path,guard


def frames(counts=(3,4)):
    names=['mcp__reader__open','mcp__reader__chunk','mcp__audit__coverage']
    contracts=[{'exports':['request_id','document_id'],'auto_continue':False},
               {'exports':['next_request_id','document_id'],'auto_continue':True,'control_fields':{'next_request_id':'nullable_handle','empty_text':'boolean'}},
               {'exports':[],'auto_continue':True,'control_fields':{'complete':'boolean'}}]
    tools=catalog([{'name':n,'input_schema':{'type':'object','properties':{key:{'type':'string'}},'required':[key]},
        '_meta':{'sss_learning':{'format':'sss-mcp-learning-v1','effect':'read',**c}}}
        for n,key,c in zip(names,['source_id','request_id','document_id'],contracts)])
    result=[]
    for k in ['train-one','train-two','independent']:
        scope={'execution_version':'a'*64,'input_sha256':digest(k)};rows=[]
        def add(name,args,out):
            i=len(rows);rows.append({'name':name,'args':args,'out':{**out,'_sss_scope':scope},'call_id':k+'-'+str(i),'message_seq':i+1})
        for episode,count in enumerate(counts):
            did=k+'-'+str(episode)
            add(names[0],{'source_id':did+'source'},{'request_id':did+'-0','document_id':did})
            for i in range(count):
                add(names[1],{'request_id':did+'-'+str(i)}, {'document_id':did,'next_request_id':did+'-'+str(i+1) if i+1<count else None,'empty_text':i==1 or episode==1 and i==count-1})
            add(names[2],{'document_id':did},{'complete':True})
        result.append({'tools':tools,'scope':scope,'rows':rows,'fingerprint':digest(k),'trace_id':k,'record':{'events_sha256':digest(rows)}})
    return result


def test_learns_variable_loop_and_four_actual_conditional_cases_without_written_route():
    ff=frames();cc,rejected=discover_flows(ff[:2]);assert not rejected
    c=next(c['compiled'] for c in cc if c['compiled']['root'].endswith('__open'));assert len(c['edges'])==6
    assert len([e for e in c['edges'] if e['from'].endswith('__chunk')])==4
    p=certify_flow(c,ff[2]);assert p['format']=='sss-operation-flow-v3'
    assert len(c['nodes'])==3 and c['max_steps']==64


@pytest.mark.parametrize('damage',['one_source','failed_barrier','constant','ambiguous','missing_control','generated_new'])
def test_no_learning_from_missing_or_ambiguous_branch_proof(damage):
    ff=copy.deepcopy(frames()[:2])
    if damage=='one_source':ff=ff[:1]
    elif damage=='failed_barrier':
        for f in ff:
            for i in [7,2]:f['rows'].insert(i,{'name':'mcp__unknown__failure','out':None,'args':{},'message_seq':None,'call_id':'failed-'+str(i)})
    elif damage=='constant':
        for f in ff:
            for i in [0,5]:f['rows'][i]['out']['request_id']='constant';f['rows'][i+1]['args']['request_id']='constant'
    elif damage=='ambiguous':
        f=ff[1];f['rows'][2]['out']['next_request_id']=None
    elif damage=='missing_control':
        for f in ff:
            for r in f['rows']:
                if r['name'].endswith('__chunk'):r['out'].pop('empty_text')
    else:
        for f in ff:
            for r in f['rows'][1:]:r.update(generated=True,message_seq=None)
    assert not any(c['compiled']['root'].endswith('__open') for c in discover_flows(ff)[0])


def test_each_independent_native_certificate_must_cover_all_branches():
    ff=frames();c=discover_flows(ff[:2])[0][0]['compiled']
    with pytest.raises(ValueError,match='overlaps'):certify_flow(c,ff[0])
    bad=copy.deepcopy(ff[2]);bad['rows']=bad['rows'][:5]
    with pytest.raises(ValueError,match='every branch'):certify_flow(c,bad)


def test_actual_control_path_replay_rejects_false_exit_and_changed_bindings():
    ff=frames();p=certify_flow(discover_flows(ff[:2])[0][0]['compiled'],ff[2]);f=ff[2];path=f['rows'][:5]
    edges=[]
    for r in path:
        edges.append(next(e for e in p['artifact']['edges'] if e['from']==r['name'] and e['guard']==guard(r['out'],f['tools'][r['name']]['contract'])))
    completion={'root_call_id':path[0]['call_id'],'nodes':5,'control_edges':[digest(e) for e in edges],'control_call_ids':[r['call_id'] for r in path],'control_flow':True}
    assert verify_execution_path(p,f,completion)
    assert not verify_execution_path(p,f,{**completion,'nodes':4})
    bad=copy.deepcopy(f);bad['rows'][2]['args']['request_id']='guessed'
    assert not verify_execution_path(p,bad,completion)


def test_control_domains_are_finite_and_do_not_infer_meaning_from_text():
    with pytest.raises(ValueError):guard({'next':'raw paragraph'},{'control_fields':{'next':'infer_semantics'}})
    with pytest.raises(ValueError):guard({},{'control_fields':{'next':'nullable_handle'}})
    assert guard({'route':'right'},{'control_fields':{'route':['left','right']}})=={'route':'right'}


def branch_frames():
    names=['mcp__source__observe','mcp__service_a__read','mcp__service_b__read']
    schemas=[]
    for i,n in enumerate(names):
        schemas.append({'name':n,'input_schema':{'type':'object','required':['handle'],'properties':{'handle':{'type':'string'}}},
            '_meta':{'sss_learning':{'format':'sss-mcp-learning-v1','effect':'read','auto_continue':i>0,
             'exports':['next'] if i==0 else [],**({'control_fields':{'route':['left','right'],'flag':'boolean'}} if i==0 else {})}}})
    result=[]
    for k in ['one','two','new-cert']:
        scope={'execution_version':'b'*64};rows=[]
        for route in ['left','right']:
            for flag in [False,True]:
                token=k+route+str(flag);target=names[1 if (route=='left')==flag else 2]
                for name,args,out in [(names[0],{'handle':token},{'next':token+'next','route':route,'flag':flag}),
                                      (target,{'handle':token+'next'},{'ok':True})]:
                    rows.append({'name':name,'args':args,'out':{**out,'_sss_scope':scope},'call_id':token+name,'message_seq':len(rows)+1})
        result.append({'tools':catalog(schemas),'scope':scope,'rows':rows,'fingerprint':digest(k),'trace_id':k,'record':{'events_sha256':digest(rows)}})
    return result


def test_nested_conditions_choose_different_actual_provider_routes():
    ff=branch_frames();c,rejected=discover_flows(ff[:2]);assert not rejected and len(c)==1
    p=certify_flow(c[0]['compiled'],ff[2]);edges=[e for e in p['artifact']['edges'] if e['from']==ff[0]['rows'][0]['name']]
    assert len(edges)==4 and len({e['to'] for e in edges})==2


def test_verified_v2_generated_prefix_does_not_block_new_native_loop_decisions():
    ff=frames((5,6));chunk=ff[0]['rows'][1]['name']
    parent={'format':'sss-operation-graph-v2','policy_digest':'parent','artifact':{'nodes':[
        {'tool':chunk,'bindings':{}},{'tool':chunk,'bindings':{'request_id':{'node':0,'path':'next_request_id'}}}]}}
    for f in ff[:2]:
        f['parents']=[parent];page=0
        for row in f['rows']:
            if row['name'].endswith('__open'):page=0
            if row['name']==chunk:
                page+=1
                if page%2==0:row.update(generated=True,message_seq=None)
    cc,_=discover_flows(ff[:2]);assert any(c['compiled']['root']==ff[0]['rows'][0]['name'] for c in cc)
    for f in ff[:2]:f['parents']=[]
    assert not discover_flows(ff[:2])[0]


def test_independent_document_read_interleaving_preserves_each_real_loop_route():
    ff=frames()
    for f in ff:
        for tc in f['tools'].values():tc['contract']['flow_interleaving']=True
        a,b=f['rows'][:5],f['rows'][5:];out=[]
        for i in range(max(len(a),len(b))):
            if i<len(a):out.append(a[i])
            if i<len(b):out.append(b[i])
        f['rows']=out
    cc,_=discover_flows(ff[:2]);p=certify_flow(next(c['compiled'] for c in cc if c['compiled']['root'].endswith('__open')),ff[2])
    assert p['artifact']['interleaving_contracts']
    for f in ff:
        for tc in f['tools'].values():tc['contract'].pop('flow_interleaving',None)
    assert not any(c['compiled']['root'].endswith('__open') for c in discover_flows(ff[:2])[0])


def test_new_independently_observed_branches_can_upgrade_an_active_flow(tmp_path):
    from src.adapters.continuous_motif_learning import learning_job
    from src.motif_core.offline.experience_registry import durable
    compiled=discover_flows(frames()[:2])[0][0]['compiled'];job=tmp_path/'learning/old';job.mkdir(parents=True)
    durable(job/'compiled.json',compiled);durable(job/'activation.json',{'opportunity_key':'route','policy_digest':'active'})
    candidate={'key':'route','compiled':copy.deepcopy(compiled)}
    assert learning_job(tmp_path,candidate,{'active'}) is None
    candidate['compiled']['edges'].append({'from':'new','guard':{},'to':None,'bindings':{}})
    # The caller must independently discover/certify the new edge; an active
    # earlier version must not suppress scheduling its new frozen candidate.
    assert learning_job(tmp_path,candidate,{'active'})!=job


def test_management_text_read_is_declared_as_scope_checked_read_interleaving():
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scenarios/file-management'))
    from management_tools import operator_contract
    c=operator_contract('read_file')
    assert c['effect']=='read' and c['flow_interleaving'] is True
    assert operator_contract('execute_plan').get('flow_interleaving') is not True
