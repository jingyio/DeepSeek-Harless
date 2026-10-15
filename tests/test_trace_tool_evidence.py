"""No-model diagnostics: source replay, trace provenance and hidden-case split."""
import importlib.util
import json
from pathlib import Path
import pytest
from src.adapters.trace_tool_evidence import (SourceReplay, digest, trace_run,
    project_inputs, stdout_match_kind, bounded_read)

SOURCE = '''import json
t=json.load(open('report.json'))
print("count:",len(t['rows']))
print("keys:",[r['key'] for r in t['rows']])
'''

def fixture(root):
    run = root/'.local/source-run'; work = run/'work'; work.mkdir(parents=True)
    raw = json.dumps({'rows':[{'key':'a'},{'key':'b'}]})
    (work/'report.json').write_text(raw)
    (run/'manifest.json').write_text(json.dumps({'mode':'baseline','session_id':'s1'}))
    (run/'metrics.json').write_text(json.dumps({'status':'completed','verified_skips':0}))
    result = SourceReplay({'report.json':raw}).run(SOURCE)
    events = [
        {'session_id':'child','event':{'type':'tool/call','data':{'callId':'other','name':'bash','arguments':{'command':'echo child'}}}},
        {'session_id':'s1','event':{'type':'tool/call','data':{'callId':'call1','step':1,'name':'bash',
            'arguments':{'command':"python3 - <<'EOF'\n"+SOURCE+"EOF",'description':'diagnostic source'}}}},
        {'session_id':'s1','event':{'type':'tool/result','data':{'message':{'content':[{'type':'tool-result',
            'toolCallId':'call1','isError':False,'content':[{'type':'text','text':result['stdout']}]}]}}}},
        {'session_id':'s1','event':{'type':'tool/call','data':{'callId':'call2','name':'bash','arguments':{'command':'sleep 10'}}}}
    ]
    (run/'session-events.jsonl').write_text('\n'.join(json.dumps(r) for r in events)+'\n')
    return run

def test_source_ast_replays_only_memory_data_and_captures_original_operations():
    result=SourceReplay({'report.json':'{"rows":[{"key":"x"},{"key":"y"}]}' }).run(SOURCE)
    assert result['outputs']=={'count':2,'keys':['x','y']}
    assert result['stdout']=="count: 2\nkeys: ['x', 'y']\n"
    for text in ["import os\nprint('x:',os.getcwd())", "x=__import__('os')", "x=eval('42')",
                 "x=open('/etc/passwd').read()", "x=open('report.json','w')", "x=(1).__class__"]:
        with pytest.raises(ValueError): SourceReplay({'report.json':'{}'}).run(text)

def test_source_replay_rejects_nonfinite_deep_or_oversized_data():
    for data in ['{"x":NaN}','['*1100+'0'+']'*1100]:
        with pytest.raises(ValueError): SourceReplay({'report.json':data}).run("import json\nx=json.load(open('report.json'))")
    nested={'report.json':json.dumps({'indices':list(range(50))})}
    with pytest.raises(ValueError,match='container_limit'):
        SourceReplay(nested).run("import json\nt=json.load(open('report.json'))\nx=[1 for a in t['indices'] for b in t['indices']]")
    # Multiplication is unsupported, so use a bounded input whose derived
    # repeated strings exceed the aggregate byte cap before print formats it.
    files={'report.json':json.dumps({'s':'x'*1000,'indices':list(range(250))})}
    source="import json\nt=json.load(open('report.json'))\nx=[t['s'] for i in t['indices']]\nprint('x:',x)"
    with pytest.raises(ValueError,match='byte_limit'): SourceReplay(files).run(source)

def test_trace_pairing_uses_root_session_call_id_and_keeps_unsupported(tmp_path):
    run=fixture(tmp_path)
    rows=trace_run(tmp_path,str(run.relative_to(tmp_path)))
    assert len(rows)==2 and rows[0]['call_id']=='call1'
    assert rows[0]['replay_status']=='observed_replay_match'
    assert rows[1]['replay_status']=='unsupported'
    assert rows[0]['file_sha256'] and rows[0]['events_sha256']
    (run/'work/report.json').write_text('{"rows":[]}')
    assert trace_run(tmp_path,str(run.relative_to(tmp_path)))[0]['replay_reason']=='snapshot_does_not_reproduce_observed_stdout'

def test_trace_rejects_runtime_self_evidence_and_symlink_inputs(tmp_path):
    run=fixture(tmp_path)
    (run/'manifest.json').write_text(json.dumps({'mode':'execute','session_id':'s1'}))
    with pytest.raises(ValueError,match='normal_completed'): trace_run(tmp_path,str(run.relative_to(tmp_path)))
    (run/'manifest.json').write_text(json.dumps({'mode':'baseline','session_id':'s1'}))
    original=run/'work/report.json'; original.unlink(); original.symlink_to(run/'manifest.json')
    assert trace_run(tmp_path,str(run.relative_to(tmp_path)))[0]['replay_status']=='unsupported'
    with pytest.raises(ValueError): bounded_read(original)

def test_only_printed_dict_key_order_is_normalized():
    assert stdout_match_kind("x: {'a': 1, 'b': 2}\n","x: {'b': 2, 'a': 1}\n")=='printed_dict_order_only'
    assert stdout_match_kind('x: True\n','x: True\n')=='exact_bytes'
    with pytest.raises(ValueError): stdout_match_kind('x: [1, 2]\n','x: [2, 1]\n')
    with pytest.raises(ValueError): stdout_match_kind("x: {'a': 1}\n","x: {'a': 2}\n")

def test_input_projections_are_explicit_and_preserve_order():
    files={'report.json':'{"rows":[{"key":"a","id":1},{"key":"b","id":2}]}'}
    assert project_inputs(files,{'keys':{'file':'report.json','pointer':'/rows/*/key'}})=={'keys':['a','b']}
    assert project_inputs(files,{'rows':{'file':'report.json','pointer':'/rows','fields':['id']}})=={'rows':[{'id':1},{'id':2}]}
    with pytest.raises(ValueError): project_inputs(files,{'x':{'file':'report.json','pointer':'/constructor'}})
    with pytest.raises(KeyError): project_inputs(files,{'x':{'file':'elsewhere.json','pointer':''}})

def controller():
    path=Path(__file__).parents[1]/'scripts/paper-rsi-trace.py'
    spec=importlib.util.spec_from_file_location('trace_controller_diagnostic',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def test_proposal_derives_oracle_cases_from_source_and_freezes_hidden_split(tmp_path,monkeypatch):
    run=fixture(tmp_path); module=controller();monkeypatch.setattr(module,'ROOT',tmp_path)
    # The schema-validation subprocess imports the real repo execution module.
    real_root=Path(__file__).parents[1]
    real_run=module.subprocess.run
    monkeypatch.setattr(module.subprocess,'run',lambda *args,**kwargs:real_run(*args,**{**kwargs,'cwd':real_root}))
    exp=tmp_path/'.local/learning'; data=module.bundle(exp,[str(run.relative_to(tmp_path))])
    work=exp/'runs/learning/work'; work.mkdir(parents=True)
    module.save_once(exp/'active-learning.json',{'work':str(work)})
    array={'type':'array','items':{'type':'string'}}
    contract={'name':'diagnostic_selected_tool','description':'手写机制夹具，不是模型生成',
        'input_schema':{'type':'object','properties':{'keys':array},'required':['keys'],'additionalProperties':False},
        'output_schema':{'type':'object','properties':{'count':{'type':'integer'},'keys':array},'required':['count','keys'],'additionalProperties':False}}
    proposal={'source':{'run_id':data['entries'][0]['run_id'],'call_id':'call1'},'contract':contract,
        'input_bindings':{'keys':{'file':'report.json','pointer':'/rows/*/key'}},'output_bindings':{'count':'count','keys':'keys'}}
    feedback=module.prepare_proposal(exp,proposal)
    assert len(feedback['training'])==3 and feedback['heldout_cases']>=2
    hidden=module.load(exp/'heldout.json'); accepted=module.load(exp/'accepted-proposal.json')
    assert digest(hidden)==accepted['heldout_sha256']
    assert not set(accepted['training_input_sha256']) & set(accepted['heldout_input_sha256'])
    assert all(row['expected']['count']==len(row['input']['keys']) for row in feedback['training']+hidden)
    assert 'heldout' not in feedback and 'memory_files' not in accepted
    with pytest.raises(ValueError,match='already_frozen'): module.prepare_proposal(exp,proposal)

@pytest.mark.parametrize('variation,reason',[
    ('echo','derived_output_required'),
    ('incomplete_input','input_projection_loses_output_dependencies'),
    ('wrong_schema','contract_does_not_cover_source_cases'),
    ('inferred',None),
])
def test_proposal_checks_real_values_and_nontrivial_dependencies(tmp_path,monkeypatch,variation,reason):
    run=fixture(tmp_path); module=controller();monkeypatch.setattr(module,'ROOT',tmp_path)
    real_root=Path(__file__).parents[1]; real_run=module.subprocess.run
    monkeypatch.setattr(module.subprocess,'run',lambda *a,**kw:real_run(*a,**{**kw,'cwd':real_root}))
    exp=tmp_path/'.local/learning';data=module.bundle(exp,[str(run.relative_to(tmp_path))])
    work=exp/'runs/learning/work';work.mkdir(parents=True)
    module.save_once(exp/'active-learning.json',{'work':str(work)})
    proposal={'source':{'run_id':data['entries'][0]['run_id'],'call_id':'call1'},
        'contract':{'name':'diagnostic_derived_count','description':'机制诊断夹具'},
        'input_bindings':{'keys':{'file':'report.json','pointer':'/rows/*/key'}},
        'output_bindings':{'count':'count'}}
    if variation=='echo': proposal['output_bindings']={'keys':'keys'}
    if variation=='incomplete_input':proposal['input_bindings']['keys']['pointer']='/rows/0/key'
    if variation=='wrong_schema':
        proposal['contract'].update(
            input_schema={'type':'object','properties':{'keys':{'type':'array','items':{'type':'string'}}},'required':['keys'],'additionalProperties':False},
            output_schema={'type':'object','properties':{'count':{'type':'string'}},'required':['count'],'additionalProperties':False})
    if reason:
        with pytest.raises((ValueError,RuntimeError),match=reason):module.prepare_proposal(exp,proposal)
        assert not (exp/'accepted-proposal.json').exists()
    else:
        feedback=module.prepare_proposal(exp,proposal)
        assert feedback['contract']['output_schema']['properties']['count']=={'type':'integer'}
        assert 'enum' not in feedback['contract']['input_schema']['properties']['keys']['items']
        assert module.load(exp/'accepted-proposal.json')['schema_origin']=='generic_structure_inference_before_implementation'

def test_nested_input_echo_is_not_a_derived_tool():
    module=controller()
    cases=[{'input':{'report':{'scope':v}},'expected':{'scope':v}} for v in ['a','b']]
    with pytest.raises(ValueError,match='derived_output_required'):module.require_derived_output(cases)
    for row in cases:row['expected']['count']=len(row['input']['report']['scope'])
    # A derived value still needs changing counterexamples.
    with pytest.raises(ValueError,match='derived_output_required'):module.require_derived_output(cases)
    cases[-1]['input']['report']['scope']='long';cases[-1]['expected']['count']=4
    module.require_derived_output(cases)

def test_failed_trial_cannot_authorize_frozen_tool(tmp_path,monkeypatch):
    module=controller();monkeypatch.setattr(module,'ROOT',tmp_path)
    exp=tmp_path/'.local/freeze';run=exp/'runs/diagnostic';work=run/'work';work.mkdir(parents=True)
    candidate={'name':'diagnostic','description':'diagnostic'};sha=digest(candidate)
    module.save_once(run/'metrics.json',{'status':'completed'})
    module.save_once(exp/'accepted-proposal.json',{'contract':candidate})
    module.save_once(work/'current-candidate.json',candidate)
    audit=[{'kind':'development_test','passed':True,'candidate_sha256':sha},
        {'kind':'trial','candidate_sha256':sha,'error':'invalid input'}]
    (work/'learning.jsonl').write_text('\n'.join(json.dumps(x) for x in audit)+'\n')
    with pytest.raises(ValueError,match='no_successful_real_trial'):module.freeze(exp,'diagnostic')
    assert not (exp/'frozen-tool.json').exists()
