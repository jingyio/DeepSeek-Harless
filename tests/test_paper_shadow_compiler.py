"""Diagnostic traces: provenance and local edges, no paid Provider."""
import hashlib
import json

import pytest

from src.adapters.paper_shadow_compiler import compile_paper_shadow, artifact_path, VALIDATOR_FILES
from src.adapters.native_motif_compiler import digest


def make_run(root, name, anchor='write', ok=True, interleave=False):
    run = root/name
    (run/'requests').mkdir(parents=True)
    session = 'session-'+name
    source = hashlib.sha256(name.encode()).hexdigest()
    content = '{"references":[]}'
    config = {'mode':'baseline','delivery_check_mode':'off','composite_evidence':True,
              'session_id':session,'input_version':source,
              'code_sha256':{p:'a'*64 for p in VALIDATOR_FILES}}
    check_config = {'session_id':session,'source_version':source,'case_id':'sample','work':'/private/work'}
    tools = [{'function':{'name':t,'parameters':{'type':'object'}}} for t in
             ['write','edit','check_paper_triage','mcp__paper_checks__collect_paper_citation_evidence','web_fetch']]
    check = {'check':'paper_citation_triage_structure','status':'passed','semantic_quality':'not_reviewed',
             'source_version':source,'report_sha256':hashlib.sha256(content.encode()).hexdigest()}
    operations = [('mcp__paper_checks__collect_paper_citation_evidence',{'case_id':'sample'},
                   {'case_id':'sample','version_sha256':source},True),
                  (anchor,{'file_path':'triage.json',**({'content':content} if anchor=='write' else
                   {'old_string':'old','new_string':'new'})},'written',ok)]
    if interleave:
        operations.append(('web_fetch',{'url':'https://example.org'},'unknown',True))
    operations.append(('check_paper_triage',{},check,True))
    rows = []
    for i,(tool,args,value,success) in enumerate(operations,1):
        call_id = 'call-'+str(i)
        events = [{'type':'assistant/message','data':{'message':{'content':[
            {'type':'text','text':'This narration is not a fitted acceptance rule.'},
            {'type':'tool-call','id':call_id,'name':tool,'arguments':json.dumps(args)}]}}},
            {'type':'tool/call','data':{'callId':call_id,'name':tool,'arguments':json.dumps(args)}},
            {'type':'tool/result','data':{'message':{'content':[{'type':'tool-result','toolCallId':call_id,
               'isError':not success,'content':[{'type':'text','text':json.dumps(value) if isinstance(value,dict) else value}]}]}}}]
        rows.extend({'session_id':session,'event':e} for e in events)
        (run/'requests'/f'{i:04}.json').write_text(json.dumps({'tools':tools}))
    rows.append({'session_id':session,'event':{'type':'assistant/message','data':{'message':{'content':[{'type':'text','text':'done'}]}}}})
    n = len(operations)+1
    (run/'requests'/f'{n:04}.json').write_text(json.dumps({'tools':tools}))
    for path,value in [('manifest.json',config),('delivery-check-config.json',check_config),
        ('metrics.json',{'status':'completed','source_unchanged':True,'output_coverage_valid':True,
                         'delivery_check_passed':True,'actual_requests':n})]:
        (run/path).write_text(json.dumps(value))
    (run/'session-events.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    return run


def test_mines_repeated_writes_and_separately_marks_one_edit(tmp_path):
    a,b,c = make_run(tmp_path,'a'),make_run(tmp_path,'b'),make_run(tmp_path,'c',anchor='edit')
    library = compile_paper_shadow([a,b,c])
    motifs = {m['graph']['anchor']['tool']:m for m in library['motifs']}
    assert motifs['write']['training_session_count'] == 2
    assert motifs['write']['support'] == 'repeated_trace'
    assert motifs['edit']['support'] == 'single_trace_candidate'
    assert all(m['status'] == 'shadow_candidate_not_execution_certified' for m in motifs.values())
    assert all(m['graph']['anchor']['ownership'] == 'model' for m in motifs.values())
    assert library['manifest_digest'] == digest({k:v for k,v in library.items() if k!='manifest_digest'})


@pytest.mark.parametrize('kwargs',[{'ok':False},{'interleave':True}])
def test_failed_or_interleaved_mutations_do_not_become_edges(tmp_path,kwargs):
    assert compile_paper_shadow([make_run(tmp_path,'a',**kwargs)])['motifs'] == []


def test_check_on_different_write_bytes_is_not_a_dependency_witness(tmp_path):
    run=make_run(tmp_path,'a')
    path=run/'session-events.jsonl'
    rows=[json.loads(x) for x in path.read_text().splitlines()]
    for row in rows:
        e=row['event']
        if e['type']=='tool/result':
            block=e['data']['message']['content'][0]
            if block['toolCallId']=='call-3':
                value=json.loads(block['content'][0]['text']);value['report_sha256']='f'*64
                block['content'][0]['text']=json.dumps(value)
    path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    assert compile_paper_shadow([run])['motifs'] == []


@pytest.mark.parametrize('field,value',[('mode','shadow'),('delivery_check_mode','shadow')])
def test_evaluation_runs_cannot_be_used_as_normal_baseline_training(tmp_path,field,value):
    run=make_run(tmp_path,'a');p=run/'manifest.json';cfg=json.loads(p.read_text());cfg[field]=value;p.write_text(json.dumps(cfg))
    with pytest.raises(ValueError,match='normal baseline'):compile_paper_shadow([run])


def test_duplicate_sessions_and_contract_drift_are_rejected(tmp_path):
    a,b=make_run(tmp_path,'a'),make_run(tmp_path,'b')
    with pytest.raises(ValueError,match='distinct'):compile_paper_shadow([a,a])
    p=b/'manifest.json';cfg=json.loads(p.read_text());cfg['code_sha256'][VALIDATOR_FILES[0]]='b'*64;p.write_text(json.dumps(cfg))
    with pytest.raises(ValueError,match='drift'):compile_paper_shadow([a,b])


@pytest.mark.parametrize('path',['../triage.json','/other/triage.json','sub/triage.json','triage.json\x00','..\\triage.json'])
def test_only_registered_artifact_paths_are_normalized(path):
    assert artifact_path(path,'/private/work') is None
