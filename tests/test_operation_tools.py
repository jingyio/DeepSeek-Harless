import pytest
from pathlib import Path
from uuid import uuid4
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from common import snapshot
import file_tools
from operation_tools import OperationScene
from mcp.server.mcpserver.exceptions import ToolError

@pytest.fixture
def scene(tmp_path,monkeypatch):
    monkeypatch.setattr(file_tools,'DATA',tmp_path)
    monkeypatch.setattr(file_tools,'ROOT',tmp_path)
    work=tmp_path/'copy';work.mkdir();(work/'.experiment-copy').write_text('authorized');(work/'note.txt').write_text('original bytes')
    spec={'schema_version':1,'task_id':uuid4().hex,'role':'bootstrap','family':'inventory','objective':'copy one declared file',
          'workspace':str(work),'initial_snapshot':snapshot(work),'rules':{},'allowed_operations':['copy'],
          'report_contract':{'version':'sss-file-report-v3','kind':'task_result'},
          'operation_contract':{'version':'sss-file-operation-contract-v1','require_result_read':True,
             'actions':[{'op':'copy','source':'note.txt','destination':'results/note.txt','format':'none'}]}}
    result=OperationScene(spec,tmp_path/'.local/delivery');result.read_task();return result

def actions(scene,destination='results/note.txt'):
    return [{'op':'copy','file_ids':[scene.file_id('note.txt')],'destination':destination,'format':'none'}]

def test_effect_grant_rejects_changed_goal_before_any_write(scene):
    before=snapshot(scene.root)
    with pytest.raises(ToolError,match='original task'):scene.preview_actions(actions(scene,'wrong/target.txt'))
    assert snapshot(scene.root)==before and not scene.plans

def test_actual_result_handle_and_scope_replay_preserve_original_bytes(scene):
    p=scene.preview_actions(actions(scene));r=scene.execute_plan(p['plan_id']);assert r['_sss_authorized']
    assert scene.execute_plan(p['plan_id'])['receipt_id']==r['receipt_id']
    inspected=scene.inspect_plan_result(r['receipt_id']);pin=scene.pin_file(inspected['primary_file_id']);read=scene.read_file(pin['source_id'])
    assert read['text']=='original bytes' and read['_sss_scope']==p['_sss_scope']
    assert (scene.root/'results/note.txt').read_bytes()==(scene.root/'note.txt').read_bytes()
    with pytest.raises(ToolError):scene.inspect_plan_result('guessed')

def test_external_version_change_prevents_authorized_execution(scene):
    p=scene.preview_actions(actions(scene));(scene.root/'note.txt').write_text('new unapproved source')
    with pytest.raises(ToolError):scene.execute_plan(p['plan_id'])
    assert not (scene.root/'results/note.txt').exists()
