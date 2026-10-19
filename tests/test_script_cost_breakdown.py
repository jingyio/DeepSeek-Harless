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

def test_typed_resolution_is_a_paid_decision_not_a_structural_skip():
    msg={'content':[{'type':'tool-call','name':'bash','arguments':{'command':'geneloop-resolve '+json.dumps({'status':'unknown','request_id':'current'})}}]}
    assert m.category(msg)=='semantic_slot_resolution'

def test_unknown_usage_failure_is_not_a_zero_cost_success(tmp_path):
    (tmp_path/'ledger.jsonl').write_text(json.dumps({'request_id':1,'request_utc_epoch':1,'response_usage':{},'observed_peak_usd':None}))
    result=m.analyze(tmp_path)
    assert result['requests_with_known_usage']==0
    assert result['requests_without_usage']==1
    assert not result['categories']


def test_bibliography_batch_starts_report_phase_and_is_report_protocol():
    message={'content':[{'type':'tool-call','name':'mcp__paper_checks__stage_current_bibliography_assessments','arguments':{}}]}
    assert m.report_start(message)
    assert m.category(message)=='report_protocol'


def test_soft_validation_rejection_counts_without_a_native_exception(tmp_path):
    events=[{'type':'assistant/message','time':1000,'data':{'usage':{'outputTokens':1},'message':{'content':[]}}},
      {'type':'tool/call','time':1100,'data':{'callId':'f','name':'mcp__paper_checks__finalize_current_audit','arguments':{}}},
      {'type':'tool/result','time':1200,'data':{'message':{'content':[{'toolCallId':'f','isError':False,'content':[{'type':'text','text':json.dumps({'finalized':False,'validation_error':'shape'})}]}]}}},
      {'type':'assistant/message','time':2000,'data':{'usage':{'outputTokens':1},'message':{'content':[]}}}]
    ledger=[{'request_id':1,'request_utc_epoch':1,'response_usage':{'completion_tokens':1},'observed_peak_usd':.01},
      {'request_id':2,'request_utc_epoch':2,'response_usage':{'completion_tokens':1},'observed_peak_usd':.01}]
    for name,rows in [('events',events),('ledger',ledger)]:
        (tmp_path/(name+'.jsonl')).write_text('\n'.join(map(json.dumps,rows)))
    result=m.analyze(tmp_path)
    assert result['requests_after_tool_errors']==0
    assert result['requests_after_structured_validation_failures']==1
    assert result['structured_validation_failures'][0]['code']=='shape'
    assert m.structured_validation_error({'content':[{'type':'text','text':json.dumps({'finalized':True,'validation_error':'old_metadata'})}]}) is None


def test_no_dash_heredoc_and_artifact_selection_are_not_unclassified_shell():
    for command,expected in [("cd /work && python3 << 'EOF'\nprint(1)\nEOF",'script_authoring_local'),('geneloop-reuse {"calls":[]}','artifact_reference_or_probe_selection')]:
        assert m.category({'content':[{'type':'tool-call','name':'bash','arguments':{'command':command}}]})==expected
    assert m.structured_validation_error({'content':[{'type':'text','text':'{"exported":false,"failed_checks":["all_text_preserved"]}'}]})=='checks:all_text_preserved'
