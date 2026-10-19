"""Synthetic diagnostics of mining admission, not task effectiveness."""
import json
from src.adapters.probe_motif_compiler import compile_probes, collect, failure_signature, proper_subsequence


def rows():
    result=[]
    for task in ['one','two']:
        for call,args,out in [('base',{'items':['private-a','private-b']},{'ok':False,'checks':['unknown_reason']}),('probe',{'items':['private-a']},{'ok':True})]:
            result.append({'tool':'mcp__case__render','task_id':task,'call_id':call,'events_sha256':'hash','schema_sha256':'schema','arguments':args,'result':out})
    return result


def test_learns_field_and_error_signature_without_shipping_values():
    c=compile_probes(rows())
    assert len(c)==1 and c[0]['axes'][0]['path']==['items']
    assert c[0]['failure']=={'ok':False,'checks':['unknown_reason']}
    assert 'private-a' not in json.dumps(c)
    assert len({w['task_id'] for w in c[0]['axes'][0]['witnesses']})==2


def test_requires_two_tasks_and_successful_subset_and_matching_failure():
    r=rows()
    assert compile_probes(r[:2])==[]
    for row in r:row['result']={'ok':False,'checks':['unknown_reason']}
    assert compile_probes(r)==[]
    r=rows();r[-1]['arguments']={'items':['unrelated']}
    assert compile_probes(r)==[]
    assert failure_signature({'ok':False}) is None


def test_subset_does_not_conflate_json_types_duplicate_values_or_reorder():
    assert not proper_subsequence([False, 'a'], [0])
    assert not proper_subsequence(['a', 'b', 'c'], ['a', 'a'])
    assert not proper_subsequence(['a', 'b', 'c'], ['b', 'a'])
    assert proper_subsequence(['a', 'b', 'a', 'c'], ['a', 'a'])


def test_collector_excludes_bad_schema_and_synthetic_and_failed_transport(tmp_path):
    name='mcp__case__render'
    (tmp_path/'effective-config.json').write_text(json.dumps({'provider_mode':'real','tools':[{'name':name,'parameters':{'type':'object','properties':{'items':{'type':'array'}},'required':['items']}}]}))
    (tmp_path/'task-state.json').write_text('{"status":"completed"}')
    events=[]
    for cid,args,error in [('native',{'items':['a']},False),('bad',{'items':4},False),('sss-reuse-test',{'items':['a']},False),('transport',{'items':['a']},True)]:
        events.extend([{'type':'tool/call','data':{'name':name,'arguments':args,'callId':cid}}, {'type':'tool/result','data':{'message':{'content':[{'toolCallId':cid,'isError':error,'content':[{'type':'text','text':'{"ok":false,"checks":["reason"]}'}]}]}}}])
    (tmp_path/'events.jsonl').write_text('\n'.join(map(json.dumps,events)))
    assert [r['call_id'] for r in collect(tmp_path)]==['native']
