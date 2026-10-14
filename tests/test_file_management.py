"""Meaningful scope, provenance, conflict and restore checks for the file MCP."""
import importlib.util
from pathlib import Path
import sys
import pytest

HERE=Path(__file__).resolve().parents[1]/'scenarios/file-management'
spec=importlib.util.spec_from_file_location('fm_common_test',HERE/'common.py')
common=importlib.util.module_from_spec(spec);spec.loader.exec_module(common)
# Load explicit common module without adding a colliding generic module to other tests.
prior=sys.modules.get('common');sys.modules['common']=common
spec=importlib.util.spec_from_file_location('fm_tools_test',HERE/'file_tools.py')
fm=importlib.util.module_from_spec(spec);spec.loader.exec_module(fm)
fm.Action.model_rebuild(_types_namespace=vars(fm))
if prior is not None:sys.modules['common']=prior
else:sys.modules.pop('common',None)

@pytest.fixture
def scene(tmp_path,monkeypatch):
    monkeypatch.setattr(fm,'ROOT',tmp_path);monkeypatch.setattr(fm,'DATA',tmp_path/'data')
    root=tmp_path/'data/copy';root.mkdir(parents=True)
    (root/'.experiment-copy').write_text('test')
    (root/'a.txt').write_text('graph research')
    (root/'b.txt').write_text('administration')
    spec={'workspace':str(root),'task_id':'test','family':'test','objective':'test','rules':{},
          'initial_snapshot':common.snapshot(root),'allowed_operations':['move','copy','convert','quarantine','archive']}
    s=fm.FileScene(spec,tmp_path/'.local/output');s.read_task();return s

def test_scope_and_opaque_handle(scene):
    with pytest.raises(fm.ToolError):scene.path('../../secret.txt')
    with pytest.raises(fm.ToolError):scene.read_file('source-'+32*'a')
    row=scene.list_files()['files'][0];pin=scene.pin_file(row['file_id'])
    assert scene.read_file(pin['source_id'])['text'] in ('graph research','administration')
    scene.path(row['path']).write_text('external change')
    with pytest.raises(fm.ToolError):scene.read_file(pin['source_id'])

def test_plan_conflicts_no_write(scene):
    fid=scene.list_files()['files'][0]['file_id']
    with pytest.raises(fm.ToolError):scene.preview_actions([fm.Action(op='copy',file_ids=[fid],destination='b.txt')])
    with pytest.raises(fm.ToolError):scene.preview_actions([fm.Action(op='copy',file_ids=[fid],destination='../../a.txt')])
    assert common.snapshot(scene.root)==scene.spec['initial_snapshot']

def test_execution_idempotence_and_exact_restore(scene):
    fid=scene.list_files()['files'][0]['file_id']
    pin=scene.pin_file(fid)
    plan=scene.preview_actions([fm.Action(op='move',file_ids=[fid],destination='organized/a.txt')])
    receipt=scene.execute_plan(plan['plan_id'])
    assert scene.execute_plan(plan['plan_id'])==receipt
    assert scene.restore_plan(plan['plan_id'])['status']=='restored_verified'
    assert common.snapshot(scene.root)==scene.spec['initial_snapshot']
    assert scene.read_file(pin['source_id'])['text']=='graph research'

def test_later_plan_prevents_old_restore(scene):
    rows=scene.list_files()['files']
    p1=scene.preview_actions([fm.Action(op='copy',file_ids=[rows[0]['file_id']],destination='x.txt')]);scene.execute_plan(p1['plan_id'])
    p2=scene.preview_actions([fm.Action(op='copy',file_ids=[rows[1]['file_id']],destination='y.txt')]);scene.execute_plan(p2['plan_id'])
    with pytest.raises(fm.ToolError):scene.restore_plan(p1['plan_id'])

def test_unknown_input_and_no_unread_index(scene):
    with pytest.raises(fm.ToolError):scene.pin_file('file:local:invented')
    pin=scene.pin_file(scene.list_files()['files'][0]['file_id'])
    with pytest.raises(fm.ToolError):scene.build_index([pin['source_id']])
    scene.read_file(pin['source_id']);assert scene.build_index([pin['source_id']])['indexed']==1

def test_unauthorized_operation(scene):
    scene.spec['allowed_operations']=[]
    fid=scene.list_files()['files'][0]['file_id']
    with pytest.raises(fm.ToolError):scene.preview_actions([fm.Action(op='move',file_ids=[fid],destination='x.txt')])
