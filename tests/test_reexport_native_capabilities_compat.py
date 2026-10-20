"""No model calls: unchanged real IR/evidence, exact source allowlists and native/MCP separation."""
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('native_capabilities_compat',ROOT/'scripts/reexport-native-capabilities-compat.py')
compat=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(compat)

@pytest.fixture
def reviewed_checkout(tmp_path,monkeypatch):
    root=tmp_path/'checkout';root.mkdir()
    names=set(compat.ADDITIONAL_LOCKS)
    for old_name,_,_,_,_ in compat.RELEASES:
        old=ROOT/'motif-libraries'/old_name
        shutil.copytree(old,root/'motif-libraries'/old_name)
        names.update(compat.read(old/'certification.json')['code_locks'])
    for name in names:
        destination=root/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,destination)
    registry=compat.read(ROOT/'config/harless-scenes.json')
    for old,_,scene,*_ in compat.RELEASES:
        row=next(row for row in registry['scenes'] if row['id']==scene)
        row['rsi']['runtime_bundle']='motif-libraries/'+compat.REGISTRY_SELECTED[old]
    compat.write(root/'config/harless-scenes.json',registry)
    monkeypatch.setattr(compat,'ROOT',root)
    return root

def test_preview_is_read_only_and_records_exact_per_release_changes(reviewed_checkout):
    registry=compat.sha(reviewed_checkout/'config/harless-scenes.json')
    candidates,_=compat.review()
    assert len(candidates)==2
    assert [len(row['reviewed_changes']) for row in candidates]==[14,12]
    assert 'scripts/harness-web.py' in candidates[0]['reviewed_changes']
    assert 'scripts/learn-web-paper-document-motif.py' in candidates[0]['reviewed_changes']
    assert 'scripts/harness-web.py' not in candidates[1]['reviewed_changes']
    assert 'scenarios/ppt_master/prompt.md' in candidates[1]['reviewed_changes']
    assert all({'src/adapters/geneloop_plan.ts','src/adapters/geneloop_goal.ts'} <= set(row['additional_locks']) for row in candidates)
    assert all(not row['new'].exists() for row in candidates)
    assert compat.sha(reviewed_checkout/'config/harless-scenes.json')==registry

def test_prepared_clones_keep_real_ir_schema_and_evidence_bytes_without_new_training(reviewed_checkout):
    candidates,_=compat.review()
    for row in candidates:
        stage=reviewed_checkout/'motif-libraries'/('unpublished-'+row['release'])
        stage.mkdir();compat.prepare(row,stage,'private-unpublished-diagnostic')
        for name in compat.IMMUTABLE_ARTIFACTS:
            assert (stage/name).read_bytes()==(row['old']/name).read_bytes()
        report=compat.read(stage/'learning-report.json')['native_capabilities_compatibility']
        assert report['same_online_program'] and report['same_mcp_schema']
        assert not report['public_native_tools_in_certified_mcp_schema']
        assert not report['public_native_tools_learned_or_certified']
        assert not report['net_cost_reduction_proven'] and not report['quality_cost_promoted']
        assert report['model_requests']==report['new_training_tasks']==0
        assert all(name.startswith('mcp__') for name in [row['name'] for row in compat.read(stage/'tool-schemas.json')])
        assert not row['new'].exists()

def test_extra_source_change_is_rejected(reviewed_checkout):
    path=reviewed_checkout/'src/adapters/geneloop_pdf_vision.ts';path.write_bytes(path.read_bytes()+b'\n')
    with pytest.raises(ValueError,match='Exact source review differs'):compat.review()

def test_changed_historical_evidence_is_rejected(reviewed_checkout):
    path=reviewed_checkout/'motif-libraries/paper-web-v24/source-evidence.json'
    path.write_bytes(path.read_bytes()+b'\n')
    with pytest.raises(ValueError,match='Previous published artifact changed'):compat.review()

@pytest.mark.parametrize('name',['mcp__paper_checks__read_pinned_document','bad tool name',{'name':'read'}])
def test_public_native_mcp_or_invalid_name_injection_is_rejected(reviewed_checkout,name):
    path=reviewed_checkout/'config/geneloop-capabilities.json';value=compat.read(path)
    value['tools'].append(name);compat.write(path,value)
    with pytest.raises(ValueError,match='distinct native vocabulary'):compat.review()
