import json
import pytest
from src.adapters.reuse_snapshot import restore_boundary
from src.adapters.script_motif_compiler import sha


def evidence(tmp_path):
    task=tmp_path/'task';(task/'reuse-evidence').mkdir(parents=True)
    data=b'{"value":"before"}';h=sha(data);(task/'reuse-evidence'/h).write_bytes(data)
    return task,{'call_id':'call','before':{'files':{'code/input.json':{'sha256':h,'bytes':len(data)}}}}


def test_restore_real_boundary_bytes_without_using_final_workspace(tmp_path):
    task,boundary=evidence(tmp_path)
    (task/'input.json').write_text('after')
    out=restore_boundary(task,boundary,tmp_path/'replay')
    assert json.loads((out/'code/input.json').read_text())=={'value':'before'}
    assert (task/'input.json').read_text()=='after'
    with pytest.raises(ValueError,match='new'):restore_boundary(task,boundary,out)


def test_invalid_blob_or_path_never_publishes_workspace(tmp_path):
    task,boundary=evidence(tmp_path)
    for name in ['../escape','/tmp/escape','code/../../escape','code//input.json','other/file']:
        b={'call_id':'call','before':{'files':{name:next(iter(boundary['before']['files'].values()))}}}
        with pytest.raises(ValueError):restore_boundary(task,b,tmp_path/'replay')
        assert not (tmp_path/'replay').exists()
    record=next(iter(boundary['before']['files'].values()))
    (task/'reuse-evidence'/record['sha256']).write_text('changed')
    with pytest.raises(ValueError,match='changed'):restore_boundary(task,boundary,tmp_path/'replay')
    assert not (tmp_path/'replay').exists()


def test_parent_symlink_is_not_a_fixed_snapshot(tmp_path):
    task,boundary=evidence(tmp_path)
    (task/'reuse-evidence').rename(task/'outside')
    (task/'reuse-evidence').symlink_to(task/'outside',target_is_directory=True)
    with pytest.raises(ValueError,match='not_fixed'):restore_boundary(task,boundary,tmp_path/'replay')


def test_native_record_materialization_is_marked_and_preserves_real_data(tmp_path):
    from src.adapters.reuse_snapshot import restore_call_records
    task=tmp_path/'task';task.mkdir()
    events=[]
    for cid in ['native','sss-reuse-internal']:
        events.extend([{'type':'tool/call','data':{'callId':cid,'name':'mcp__case__read','arguments':{'id':'current'}}}, {'type':'tool/result','data':{'message':{'content':[{'toolCallId':cid,'content':[{'type':'text','text':'{"ok":false,"checks":["real-error"]}'}]}]}}}])
    (task/'events.jsonl').write_text('\n'.join(map(json.dumps,events)))
    from pathlib import Path
    records=restore_call_records(task,tmp_path/'records');assert len(records)==1
    record=json.loads((Path(records[0])/'code/native-call.json').read_text())
    assert record['arguments']=={'id':'current'} and record['failure']['checks']==['real-error']
    manifest=json.loads((Path(records[0])/'snapshot.json').read_text())
    assert manifest['scope']=='native_record_materialization_not_pre_call_file'
    assert manifest['events_sha256']==sha((task/'events.jsonl').read_bytes())
