"""No model calls. Unknown/mixed failures are never successful contrasts."""
import json
from src.adapters.negative_outcome import negative_outcome
from src.adapters.script_negative_compiler import collect_negative,compile_negative

def cases():
    return [None,{}, {'exported':False},{'exported':True},{'exported':False,'done':True},
        {'exported':False,'failed_checks':['layout','shape','layout']},
        {'exported':True,'failed_checks':['shape']},{'exported':False,'failed_checks':[{}]},
        {'exported':False,'validation_error':'invalid'}, {'exported':False,'failed_checks':[]},
        {'exported':True,'error':{}},{'exported':False,'error':[]},
        {'validation_error':'invalid','failed_checks':['shape']}, {'failed_checks':None}]

def test_unknown_failure_is_not_a_successful_contrast(tmp_path):
    for file,value in [('effective-config.json',{'provider_mode':'real'}),('task-state.json',{'status':'completed'}),('model-request-config.json',{'tools_sha256':'a'*64})]:
        (tmp_path/file).write_text(json.dumps(value))
    events=[]
    for i,value in enumerate(cases()):
        events.extend([{'type':'tool/call','data':{'callId':str(i),'name':'mcp__test__export','arguments':{}}},
            {'type':'tool/result','data':{'message':{'content':[{'toolCallId':str(i),'content':[{'type':'text','text':json.dumps(value)}]}]}}}])
    (tmp_path/'events.jsonl').write_text('\n'.join(map(json.dumps,events)))
    rows=collect_negative(tmp_path)
    assert sum(r['outcome']=='success' for r in rows)==1
    assert {r['code'] for r in rows if r['code']}=={'shape','layout','invalid'}
    rules=compile_negative(rows,{}, {})['rules']
    assert all(r['retry_policy']=='prompt_only' for r in rules if r['failure_source']=='failed_checks')
    assert negative_outcome({'exported':False,'failed_checks':['shape']})['status']=='failure'
