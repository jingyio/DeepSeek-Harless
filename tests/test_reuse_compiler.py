import json
from pathlib import Path
from src.adapters.reuse_compiler import collect, compile_library, successful, LOCKS


def test_soft_failures_and_synthetic_calls_are_not_training_successes(tmp_path):
    tool='mcp__case__render'
    (tmp_path/'effective-config.json').write_text(json.dumps({'provider_mode':'real','tools':[{'name':tool,'parameters':{'type':'object','properties':{'text':{'type':'string'}},'required':['text']}}]}))
    (tmp_path/'task-state.json').write_text('{"status":"completed"}')
    events=[]
    for call_id,args,value in [('native',{'text':'current'},{'exported':True}),('bad',{'text':'current'},{'exported':False}),('wrong',{'text':4},{'exported':True}),('sss-reuse-generated',{'text':'cached'},{'exported':True})]:
        events.extend([{'type':'tool/call','data':{'callId':call_id,'name':tool,'arguments':args}},
                       {'type':'tool/result','data':{'message':{'content':[{'type':'tool-result','toolCallId':call_id,'content':[{'type':'text','text':json.dumps(value)}]}]}}}])
    (tmp_path/'events.jsonl').write_text('\n'.join(map(json.dumps,events)))
    rows=collect(tmp_path)
    assert [r['call_id'] for r in rows]==['native']
    assert all('text' not in r for r in rows)


def test_contracts_require_two_tasks_and_do_not_ship_historical_arguments(tmp_path):
    for name in LOCKS:
        p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('implementation')
    base={'tool':'mcp__case__read','schema':{'type':'object'},'edges':[],
          'call_id':'a','task_id':'one','events_sha256':'a','arguments_sha256':'b','result_sha256':'c'}
    assert compile_library([base,base],tmp_path)['contracts']==[]
    library=compile_library([base,{**base,'task_id':'two'}],tmp_path)
    assert len(library['contracts'])==1
    assert 'arguments' not in library['contracts'][0]
    assert library['compilation_model_requests']==0


def test_semantic_quality_false_is_not_an_execution_failure():
    assert successful({'exported':True,'scientific_content_certified':False})
    assert not successful({'validation_error':'invalid_count'})
