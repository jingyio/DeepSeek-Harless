"""Protocol and failure-path diagnostics; API acceptance is recorded separately."""
import json
from pathlib import Path
import pytest
from src.adapters import script_negative_learning as learning
from src.adapters.script_negative_compiler import collect_negative, RUNTIME_FILES, sha, digest


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value))


def setup(tmp_path,monkeypatch):
    root=tmp_path;store=root/'.local/store';output=store/'round-aaa';output.mkdir(parents=True)
    for name in (*RUNTIME_FILES,*learning.AUTO_LOCKS,'src/tool.py'):
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('current implementation')
    config={'schema_version':1,'implementation_files':['src/tool.py'],'model':'deepseek-flash',
            'max_output_tokens':1024,'max_rules':2,'cap_usd':None}
    write(store/'negative-learning.json',config)
    monkeypatch.setattr(learning,'certify_library',lambda *a:None)
    return root,store,output


def task(root,name,status='failed',start=0):
    path=root/'.local/web/runs'/name/'tasks'/name
    write(path/'task-state.json',{'user_id':'owner','status':status,'mode':'baseline'})
    write(path/'effective-config.json',{'user_id':'owner','provider_mode':'real','trace_start_index':start})
    write(path/'model-request-config.json',{'tools_sha256':'a'*64})
    write(root/'.local/script-motif-experiments'/name/'source-snapshot.json',{'src/tool.py':sha((root/'src/tool.py').read_bytes())})
    def events(call):
        return [{'type':'tool/call','data':{'callId':call,'name':'mcp__docs__export','arguments':{'version':'b'*64}}},
                {'type':'tool/result','data':{'message':{'content':[{'toolCallId':call,'content':[{'type':'text','text':json.dumps({'exported':False,'validation_error':'invalid_shape','validation_context':{'checks':['section_coverage']}})}]}]}}}]
    rows=events('native-'+name)
    (path/'events.jsonl').write_text('\n'.join(map(json.dumps,rows)))
    return path,events


def model(calls,accept=True):
    def request(phase,system,value):
        calls.append(phase)
        if phase=='negative-propose':
            return {'updates':[{'rule_id':r['rule_id'],'evidence_id':r['evidence_id'],
                 'guidance':'Inspect the reported section coverage check; preserve the complete current document and revise only fields supported by current evidence.'} for r in value['patterns']]}
        return {'verdicts':[{'rule_id':r['rule_id'],'accepted':accept,'reason':'Cautious inspection advice; does not claim a cause.'} for r in value['proposal']['updates']]}
    return request


def test_native_recurrence_review_publish_cache_and_exact_evidence(tmp_path,monkeypatch):
    root,store,output=setup(tmp_path,monkeypatch)
    a,_=task(root,'a');b,_=task(root,'b','cancelled');calls=[]
    library,status=learning.learn_negatives([a,b],store,output,root,'owner',request=model(calls))
    assert status['model_requests']==2 and calls==['negative-propose','negative-review']
    assert library['rules'][0]['retry_policy']=='prompt_only'
    assert library['rules'][0]['guidance_review']['evidence_digest']
    assert {w['task_id'] for w in library['rules'][0]['certification']['failures']}=={'a','b'}
    c,_=task(root,'c')
    next_library,status=learning.learn_negatives([a,b,c],store,output,root,'owner',request=lambda *a:pytest.fail('cached review requested model'))
    assert status['status']=='cached' and status['model_requests']==0
    assert len(next_library['rules'][0]['certification']['failures'])==3


@pytest.mark.parametrize('variant',['single_task','drift','foreign','rejected','malformed_review'])
def test_no_publication_without_sufficient_compatible_reviewed_evidence(tmp_path,monkeypatch,variant):
    root,store,output=setup(tmp_path,monkeypatch)
    a,_=task(root,'a');b,_=task(root,'b');tasks=[a,b];calls=[]
    request=model(calls,variant!='rejected')
    if variant=='single_task':tasks=[a,a]
    if variant=='drift':(root/'src/tool.py').write_text('changed')
    if variant=='foreign':write(b/'task-state.json',{'user_id':'foreign','status':'failed'})
    if variant=='malformed_review':
        original=request
        request=lambda phase,*args: {'verdicts':[]} if phase=='negative-review' else original(phase,*args)
    library,status=learning.learn_negatives(tasks,store,output,root,'owner',request=request)
    assert library is None
    if variant in ('single_task','drift','foreign'):assert not calls
    if variant=='drift':assert len(status['rejected_evidence'])==2
    if variant=='malformed_review':assert status['reason']=='incomplete_negative_guidance_review'


def test_trace_window_synthetic_and_opaque_errors_cannot_teach_negative(tmp_path,monkeypatch):
    root,_,_=setup(tmp_path,monkeypatch);path,events=task(root,'a',start=2)
    rows=events('previous-task')+events('sss-reuse-new')+events('native-new')
    rows[-1]['data']['message']['content'][0]['isError']=True
    (path/'events.jsonl').write_text('\n'.join(map(json.dumps,rows)))
    assert collect_negative(path)==[]
    rows+=events('current-native')
    (path/'events.jsonl').write_text('\n'.join(map(json.dumps,rows)))
    assert [r['call_id'] for r in collect_negative(path)]==['current-native']


def test_model_cannot_change_match_or_execution_policy():
    evidence={'rule':{'tool':'mcp__docs__export'}}
    with pytest.raises(ValueError,match='unbound_negative_guidance'):
        learning.validate_proposal({'updates':[{'rule_id':'rule','evidence_id':digest(evidence['rule']),
          'guidance':'Inspect the current structured failure evidence.', 'retry_policy':'enforce'}]},evidence)
