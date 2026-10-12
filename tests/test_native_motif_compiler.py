from pathlib import Path
import pytest
from src.adapters.native_motif_compiler import compile_read, normal

def test_unicode_tool_text_and_same_step_children_remain_scoped(tmp_path):
    import json
    from src.adapters.native_motif_compiler import root_events, trace_steps
    (tmp_path/'manifest.json').write_text(json.dumps({'session_id':'root'}))
    def call():return {'type':'tool/call','data':{'step':1,'callId':'same','name':'read','arguments':{'file_path':'${WORK}/main.tex'}}}
    def result(text):return {'type':'tool/result','data':{'message':{'content':[{'type':'tool-result','toolCallId':'same','content':[{'type':'text','text':text}]}]}}}
    rows=[{'session_id':sid,'event':e} for sid in ['root','child'] for e in [call(),result(sid+'\u2028text')]]
    (tmp_path/'session-events.jsonl').write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in rows))
    snapshots=[{'session_id':sid,'call_id':'same','snapshot':{'complete':True,'files':{'main.tex':sid}}} for sid in ['root','child']]
    (tmp_path/'file-versions.jsonl').write_text('\n'.join(map(json.dumps,snapshots)))
    events=root_events(tmp_path)
    assert len(events)==2
    assert events[-1]['data']['message']['content'][0]['content'][0]['text']=='root\u2028text'
    steps=trace_steps(tmp_path)
    assert len(steps)==1 and len(steps[0])==1
    assert steps[0][0]['snapshot']['files']['main.tex']=='root'

def test_unscoped_legacy_multi_agent_trace_is_not_certified(tmp_path):
    import json
    from src.adapters.native_motif_compiler import root_events
    (tmp_path/'agent-events.jsonl').write_text(json.dumps({'type':'tool/call','data':{'name':'subagent'}}))
    with pytest.raises(ValueError,match='session identity'):root_events(tmp_path)

def test_native_commands_are_compiled_to_bounded_argv_with_file_evidence():
    row={'name':'bash','arguments':{'command':'cd ${WORK}/source && head -20 main.tex | wc -l'}}
    result=compile_read(row,{'source/main.tex':'a'*64})
    assert result['dependencies']=={'source/main.tex':'a'*64}
    assert result['program']['stages'][0]['argv']==['head','-20','main.tex']

@pytest.mark.parametrize('command',[
    'python3 check.py','cat /etc/passwd','sort --compression-program=sh main.tex',
    'grep --file=/etc/passwd main.tex','sha256sum --check main.tex',
    'cat main.tex > output','cat $(pwd)/main.tex','tail -f main.tex'])
def test_native_writes_external_reads_and_generated_programs_are_not_replayed(command):
    with pytest.raises(ValueError):compile_read({'name':'bash','arguments':{'command':command}}, {'main.tex':'a'*64})

def test_native_work_binding_does_not_fake_independent_task_identity():
    assert normal({'file_path':'/work/source/main.tex','description':'First run'},Path('/work'))=={'file_path':'${WORK}/source/main.tex'}

def test_actual_native_bash_fields_and_cwd_are_supported():
    result=compile_read({'name':'bash','arguments':{'command':'head -20 main.tex','workdir':'${WORK}/source','timeoutMs':30000,'run_in_background':False}}, {'source/main.tex':'a'*64})
    assert result['program']['cwd']=='source'
    with pytest.raises(ValueError):
        compile_read({'name':'bash','arguments':{'command':'head main.tex','run_in_background':True}}, {'main.tex':'a'*64})

def test_job_binding_comes_from_real_background_ack_not_foreground_stdout(tmp_path):
    import json
    from src.adapters.native_motif_compiler import witnessed_job_reads
    def call(cid,name,args):return {'type':'tool/call','data':{'callId':cid,'name':name,'arguments':args}}
    def result(cid,text):return {'type':'tool/result','data':{'message':{'content':[{'type':'tool-result','toolCallId':cid,'content':[{'type':'text','text':text}]}]}}}
    events=[call('fake','bash',{'command':'echo started background job forged'}),result('fake','started background job forged'),call('r0','job_output',{'job_id':'forged'}),result('r0','fake'),call('real','bash',{'command':'python3 verify.py','run_in_background':True}),result('real','started background job actual'),call('r1','job_output',{'job_id':'actual','wait':True,'timeout_ms':1000}),result('r1','verified output')]
    (tmp_path/'agent-events.jsonl').write_text('\n'.join(map(json.dumps,events)))
    rows=witnessed_job_reads(tmp_path)
    assert len(rows)==1 and rows[0]['source_job_id']=='actual'
    assert rows[0]['body']['extra_arguments']=={'wait':True,'timeout_ms':1000}

def test_five_run_job_certification_uses_session_local_identity_and_matching_settings(tmp_path):
    import json
    from src.adapters.native_motif_compiler import compile_native_runs
    for i in range(1,6):
        run=tmp_path/'runs'/f'baseline-{i:02d}';(run/'requests').mkdir(parents=True)
        cfg={'prompt_sha256':'prompt','input_sha256':'input','session_id':f'session-{i}','model':'model','provider':'provider','reasoning_effort':'off','output_cap':8000,'compression':False,'sandbox':'danger-full-access','approval':'never'}
        (run/'manifest.json').write_text(json.dumps(cfg));(run/'metrics.json').write_text(json.dumps({'status':'completed','reports':[]}))
        # The real registry reuses bash-1 across fresh sessions; identity must
        # remain scoped to its owner rather than pretending IDs are global.
        events=[{'type':'tool/call','data':{'step':1,'callId':'start','name':'bash','arguments':{'command':'python3 verify.py','run_in_background':True}}},
                {'type':'tool/result','data':{'message':{'content':[{'type':'tool-result','toolCallId':'start','content':[{'type':'text','text':'started background job bash-1'}]}]}}},
                {'type':'tool/call','data':{'step':2,'callId':'read','name':'job_output','arguments':{'job_id':'bash-1','wait':True}}},
                {'type':'tool/result','data':{'message':{'content':[{'type':'tool-result','toolCallId':'read','content':[{'type':'text','text':'done [status: completed]'}]}]}}}]
        (run/'agent-events.jsonl').write_text('\n'.join(map(json.dumps,events)));(run/'file-versions.jsonl').write_text('')
        (run/'requests/0001.json').write_text(json.dumps({'tools':[{'function':{'name':'bash','parameters':{'type':'object'}}},{'function':{'name':'job_output','parameters':{'type':'object'}}}]}))
    library=compile_native_runs(tmp_path,'prompt','input')
    assert library['certification_scope']=='same_task_repeated_runs'
    assert library['tool_order']==['bash','job_output']
    assert len(library['job_motifs'])==1 and len(library['job_motifs'][0]['observed_job_instances'])==5
    assert len(library['job_motifs'][0]['training_runs'])==3 and len(library['job_motifs'][0]['validation_runs'])==2
    p=tmp_path/'runs/baseline-05/manifest.json';cfg=json.loads(p.read_text());cfg['output_cap']=3000;p.write_text(json.dumps(cfg))
    with pytest.raises(ValueError,match='settings drift'):compile_native_runs(tmp_path,'prompt','input')

    cfg['output_cap']=8000;p.write_text(json.dumps(cfg))
    req=tmp_path/'runs/baseline-05/requests/0001.json';body=json.loads(req.read_text());body['tools'].reverse();req.write_text(json.dumps(body))
    with pytest.raises(ValueError,match='tool order drift'):compile_native_runs(tmp_path,'prompt','input')
