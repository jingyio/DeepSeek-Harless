import sys
from pathlib import Path
from uuid import uuid4
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from management_goals import compile_goal
from management_prepare import prepare
from management_tools import ManagementScene
from management_contract import VERSION

@pytest.fixture
def case(tmp_path):
    w=tmp_path/'work';w.mkdir();(w/'note.txt').write_text('original text');(w/'table.csv').write_text('label,value\nx,17\n')
    out=ROOT/'.local/management-goal-tests'/uuid4().hex
    def scene(goal):
        spec=prepare(out,w,task_id=uuid4().hex,objective=goal,owner='goal-test',workspace_id='test')
        s=ManagementScene(spec,out/'delivery');s.read_task();return s
    return w,scene

def report(s):return s.submit_report('actual result',list(s.files()),[])

def test_goal_freezes_complete_source_coverage_and_rejects_extra_effects(case):
    w,create=case;s=create('按文件类型复制整理到 organized，保留全部原件和内容，并创建 organized/empty 空目录。完成后核验并提交报告。')
    assert s.spec['quality']['goal']['state']=='frozen' and s.spec['quality']['version']==VERSION
    p=s.preview_actions([{'op':'copy','source':'note.txt','destination':'organized/notes/note.txt'}]);s.execute_plan(p['plan_id'])
    with pytest.raises(Exception,match='delivery rejected'):report(s)
    p=s.preview_actions([{'op':'copy','source':'table.csv','destination':'organized/tables/table.csv'},{'op':'mkdir','destination':'organized/empty'}]);s.execute_plan(p['plan_id'])
    assert report(s)['semantic_quality_verified']
    p=s.preview_actions([{'op':'copy','source':'note.txt','destination':'unrequested.txt'}]);s.execute_plan(p['plan_id'])
    with pytest.raises(Exception,match='coverage differs'):report(s)

def test_move_goal_checks_removed_source_and_unchanged_other_files(case):
    w,create=case;s=create('把note.txt移动到 arranged/note.txt，保留其他文件不变。完成后核验并提交报告。')
    assert s.spec['quality']['goal']['state']=='frozen'
    p=s.preview_actions([{'op':'copy','source':'note.txt','destination':'arranged/note.txt'}]);s.execute_plan(p['plan_id'])
    with pytest.raises(Exception,match='required removal missing'):report(s)
    s.restore_plan(p['plan_id'])
    p=s.preview_actions([{'op':'move','source':'note.txt','destination':'arranged/note.txt'}]);s.execute_plan(p['plan_id'])
    assert report(s)['semantic_quality_verified'] and (w/'table.csv').read_text()=='label,value\nx,17\n'

def test_full_read_goal_rejects_omission_and_truncation(case):
    w,create=case;s=create('通读全部文本文件，给出完整读取覆盖清单，不修改任何文件。完成后核验并提交报告。')
    assert s.spec['quality']['goal']['state']=='frozen'
    rows=s.list_files()['files'];first=next(r for r in rows if r['path']=='note.txt');r=s.read_file(s.pin_file(first['file_id'])['source_id'])
    with pytest.raises(Exception,match='required complete read missing'):report(s)
    last=next(r for r in rows if r['path']=='table.csv');s.read_file(s.pin_file(last['file_id'])['source_id'])
    assert report(s)['semantic_quality_verified']
    s.reads[r['source_id']]['truncated']=True;s.persist()
    with pytest.raises(Exception,match='required complete read missing'):report(s)

@pytest.mark.parametrize('objective',['按内容判断重要性，然后整理一下','把note.txt复制到 copy.txt，然后永久删除所有原件','按文件类型移动整理到 arranged，保留全部原件。','把note.txt复制到 ../escape.txt。'])
def test_partial_or_ambiguous_objectives_are_never_claimed_as_fully_verified(case,objective):
    w,create=case;s=create(objective)
    assert s.spec['quality']['goal']['state']=='review_required' and not s.spec['quality']['requirements']
    assert report(s)['semantic_quality_verified'] is False

def test_unknown_goal_exports_honest_review_state(case):
    w,create=case;s=create('整理我认为重要的材料，无法判断时保留原件')
    assert report(s)['semantic_quality_verified'] is False
    import json
    r=json.loads((s.output/'acceptance.json').read_text());assert r['effect_integrity_verified'] and r['goal_status']=='review_required'
