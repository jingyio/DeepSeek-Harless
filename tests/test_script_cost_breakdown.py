"""Accounting diagnostics, never a substitute for real model efficacy."""
import importlib.util
import json
from pathlib import Path
spec=importlib.util.spec_from_file_location('script_cost',Path(__file__).resolve().parents[1]/'scripts/analyze-script-motif-cost.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def test_complete_requests_and_search_aux_are_not_confused(tmp_path):
    msg={'content':[{'type':'tool-call','name':'bash','arguments':json.dumps({'command':"python3 - <<'PY'\nprint('hello')\nPY"})}]}
    events=[{'type':'assistant/message','time':2000,'data':{'step':1,'usage':{'outputTokens':10},'message':msg}},
      {'type':'tool/call','time':3000,'data':{'callId':'search','name':'web_search','arguments':{}}},
      {'type':'tool/result','time':5000,'data':{'message':{'content':[{'toolCallId':'search'}]}}}]
    ledger=[{'request_id':1,'request_utc_epoch':2,'response_usage':{'completion_tokens':10},'observed_peak_usd':.01},
      {'request_id':2,'request_utc_epoch':4,'response_usage':{'completion_tokens':20},'observed_peak_usd':.02}]
    for name,rows in [('events',events),('ledger',ledger)]:
        (tmp_path/(name+'.jsonl')).write_text('\n'.join(map(json.dumps,rows)))
    value=m.analyze(tmp_path)
    assert value['categories']['script_authoring_local']['requests']==1
    assert value['categories']['web_search_internal_model']['requests']==1
    assert sum(c['estimated_usd'] for c in value['categories'].values())==.03
    assert value['requests_with_known_usage']==2

def test_saved_script_dispatch_is_not_code_generation():
    msg={'content':[{'type':'tool-call','name':'bash','arguments':{'command':'python3 query.py new-id'}}]}
    assert m.category(msg)=='saved_script_dispatch'


def test_wrapped_cache_attempt_is_counted_even_if_dispatch_failed():
    msg={'content':[{'type':'tool-call','name':'bash','arguments':{'command':"cd /work/input && geneloop-cache '{}' 2>&1 | head -60"}}]}
    assert m.category(msg)=='cached_script_dispatch'


def test_report_source_urls_are_not_network_code_generation():
    message={'content':[{'type':'tool-call','name':'bash','arguments':{'command':"python3 - <<'PY'\nprint('https://example.org/source')\nPY"}}]}
    assert m.category(message)=='script_authoring_local'
