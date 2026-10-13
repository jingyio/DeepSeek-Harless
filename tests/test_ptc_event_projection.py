import copy
import pytest
from src.adapters.dsh_event_projection import project_ptc_dispatches
from src.adapters.dsh_trajectory import ToolContract, extract_dsh_trace


def events(error=False):
    identity={'rootCallId':'root','parentCallId':'root','subCallId':'root:ptc:1','name':'mcp__demo__read','arguments':{'source_id':'source-'+'a'*32}}
    return [{'type':'tool/call','seq':1,'data':{'callId':'root','name':'run_code','arguments':'{}'}},
            {'type':'tool/ptc-dispatch-start','seq':2,'data':copy.deepcopy(identity)},
            {'type':'tool/ptc-dispatch','seq':3,'data':{**identity,'isError':error,'content':[{'type':'text','text':'{"ok":true}'}]}}]


def test_projection_is_explicit_analysis_and_preserves_original_events():
    raw=events();original=copy.deepcopy(raw);projected=project_ptc_dispatches(raw)
    assert raw==original and len(projected)==5
    assert all(e.get('ptc_analysis_source',{}).get('kind')=='derived_ptc_analysis' for e in projected if e not in raw)
    contracts={'mcp__demo__read':ToolContract(required_params=('source_id',),read_only=True)}
    trace=extract_dsh_trace(projected,contracts,trace_id='projection')
    assert trace.records[-1].eligible and trace.records[-1].observation=={'ok':True}
    failed=extract_dsh_trace(project_ptc_dispatches(events(True)),contracts,trace_id='failure')
    assert not failed.records[-1].eligible


@pytest.mark.parametrize('change',['root','args','duplicate','missing','parent'])
def test_unmatched_or_ambiguous_dispatch_cannot_create_a_receipt(change):
    raw=events()
    if change=='root':raw=raw[1:]
    elif change=='args':raw[-1]['data']['arguments']={'source_id':'changed'}
    elif change=='duplicate':raw.append(copy.deepcopy(raw[-1]))
    elif change=='missing':raw.pop()
    else:raw[-1]['data']['parentCallId']='other'
    with pytest.raises(ValueError):project_ptc_dispatches(raw)
