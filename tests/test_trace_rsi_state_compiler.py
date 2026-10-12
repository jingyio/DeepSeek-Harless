"""正常正反轨迹学习诊断；非跨论文或效果认证。"""
import copy
import json
from pathlib import Path
import pytest

from src.adapters.trace_rsi_state_compiler import (
    ADDITIONS, FEATURE, compile_stateful_trace_motifs, learn_binary_condition,
)
from src.adapters.trace_rsi_motif_compiler import file_sha256
from test_trace_rsi_motif_compiler import make_run, events, write_events, save


def terminal_read(run):
    rows=events(run)
    first=[r for r in rows if r['event']['type']=='assistant/message'][0]
    sid=first['sessionId'];final=rows.pop()
    templates=[r for r in rows if r.get('sessionId')==sid][:3]
    # Repeat the original successful read after the successful check, then end.
    copied=copy.deepcopy(templates)
    for row in copied:
        event=row['event'];data=event['data']
        if event['type']=='assistant/message':
            data['step']=3;data['message']['content'][-1]['id']='terminal-read'
        elif event['type']=='tool/call':data['step']=3;data['callId']='terminal-read'
        else:
            data['message']['source']['callId']='terminal-read'
            data['message']['content'][0]['toolCallId']='terminal-read'
    final['event']['data']['step']=4;rows+=copied+[final];write_events(run,rows)
    provider=json.loads((run/'requests/1.json').read_text());save(run/'requests/4.json',provider)
    metrics=json.loads((run/'metrics.json').read_text());metrics['actual_requests']=4;save(run/'metrics.json',metrics)


def additions(root):
    values={}
    for name in ADDITIONS:
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('diagnostic observer only')
        values[str(path)]=file_sha256(path)
    return values


def test_learns_state_from_positive_and_terminal_negative_without_changing_base(tmp_path):
    a=make_run(tmp_path,'a');b=make_run(tmp_path,'b');terminal_read(a)
    lib=compile_stateful_trace_motifs([a,b],additions(tmp_path),root=tmp_path)
    guard,=lib['guards']
    assert guard['condition']=={'feature':FEATURE,'equals':False}
    assert guard['positive_count']==2 and guard['negative_count']==1
    assert len(guard['observations'])==3
    assert [o['anchor_call_id'] for o in guard['observations'] if not o['continues']]==['terminal-read']
    assert lib['base_library']['code_files_sha256'].items()<=lib['derived_library']['code_files_sha256'].items()
    assert lib['base_library']['motifs']==lib['derived_library']['motifs']
    assert len(lib['derived_library']['code_files_sha256'])==len(lib['base_library']['code_files_sha256'])+3
    assert {o['features'][FEATURE] for o in guard['observations'] if not o['continues']}=={True}


@pytest.mark.parametrize('positive,negative,expected',[(False,True,'learned_condition'),(True,False,'learned_condition'),(False,False,'ambiguous_state')])
def test_condition_value_is_learned_not_preset(positive,negative,expected):
    obs=[{'continues':True,'features':{FEATURE:positive}},{'continues':False,'features':{FEATURE:negative}}]
    result=learn_binary_condition(obs);assert result['status']==expected
    if expected=='learned_condition':assert result['condition']['equals']==positive


def test_without_counterexample_does_not_invent_a_guard():
    assert learn_binary_condition([{'continues':True,'features':{FEATURE:False}}])=={'status':'no_negative_evidence','condition':None}
    assert learn_binary_condition([{'continues':True,'features':{FEATURE:True}},{'continues':True,'features':{FEATURE:False}},
        {'continues':False,'features':{FEATURE:True}}])['status']=='ambiguous_state'


def test_rejects_source_code_drift_or_unregistered_observer_changes(tmp_path):
    a=make_run(tmp_path,'a');b=make_run(tmp_path,'b');extra=additions(tmp_path)
    with pytest.raises(ValueError,match='explicit_observer'):compile_stateful_trace_motifs([a,b],{},root=tmp_path)
    first=Path(next(iter(extra)));first.write_text('changed observer')
    with pytest.raises(ValueError,match='observer_addition'):compile_stateful_trace_motifs([a,b],extra,root=tmp_path)
    extra=additions(tmp_path);(tmp_path/'engine.ts').write_text('changed original tool')
    with pytest.raises(ValueError,match='registered_file_version'):compile_stateful_trace_motifs([a,b],extra,root=tmp_path)
