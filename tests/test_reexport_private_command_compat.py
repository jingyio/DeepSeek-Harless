"""Exact two-file public-target admission delta; original MCP evidence stays fixed."""
import importlib.util
from pathlib import Path

import pytest
from reexport_compat_fixture import prepare_checkout, remove_expected_difference

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('private_command_export',ROOT/'scripts/reexport-private-command-compat.py')
wrapper=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(wrapper)
compat=wrapper.compat


@pytest.fixture
def frozen_checkout(tmp_path,monkeypatch):
    root=tmp_path/'checkout'
    published=prepare_checkout(compat,ROOT,root)
    monkeypatch.setattr(compat,'ROOT',root)
    yield root
    assert all(path.read_bytes()==raw for path,raw in published.items())


def test_only_public_target_guard_delta_and_real_bundle_admission(frozen_checkout):
    registry=compat.sha(frozen_checkout/'config/harless-scenes.json')
    candidates,_=compat.review()
    assert [(row['previous'],row['release']) for row in candidates]==[
        ('paper-web-v27','paper-web-v28'),('ppt-master-v24','ppt-master-v25')]
    for row in candidates:
        assert row['reviewed_changes']==[
            'src/adapters/dsh_web_tasks.ts','src/adapters/geneloop_runtime_routes.ts']
        assert row['additional_locks']==['scripts/reexport-private-command-compat.py']
        before={path.name:path.read_bytes() for path in row['old'].iterdir() if path.is_file()}
        stage=frozen_checkout/'motif-libraries'/('unpublished-'+row['release']);stage.mkdir()
        compat.prepare(row,stage,'offline-private-command-compatibility-diagnostic')
        assert all((row['old']/name).read_bytes()==raw for name,raw in before.items())
        assert all((stage/name).read_bytes()==before[name] for name in compat.IMMUTABLE_ARTIFACTS)
        report=compat.read(stage/'learning-report.json')['native_capabilities_compatibility']
        assert report['repairs']==['restrict_public_Gateway_commands_to_owned_public_conversation_targets']
        assert report['same_online_program'] and report['same_mcp_schema']
        assert report['new_training_tasks']==report['model_requests']==0
        assert not report['net_cost_reduction_proven'] and not report['quality_cost_promoted']
        assert not row['new'].exists()
    assert compat.sha(frozen_checkout/'config/harless-scenes.json')==registry


def test_extra_runtime_delta_is_rejected(frozen_checkout):
    path=frozen_checkout/'src/adapters/geneloop_goal.ts'
    path.write_bytes(path.read_bytes()+b'\n')
    with pytest.raises(ValueError,match='Exact source review differs'):compat.review()


@pytest.mark.parametrize('name',sorted(wrapper.REVIEWED))
def test_missing_reviewed_difference_is_rejected(frozen_checkout,name):
    remove_expected_difference(compat,frozen_checkout,name)
    with pytest.raises(ValueError,match='Exact source review differs'):compat.review()


def test_changed_historical_evidence_is_rejected(frozen_checkout):
    path=frozen_checkout/'motif-libraries/paper-web-v27/source-evidence.json'
    path.write_bytes(path.read_bytes()+b'\n')
    with pytest.raises(ValueError,match='Previous published artifact changed'):compat.review()


def test_existing_destination_is_never_overwritten(frozen_checkout):
    path=frozen_checkout/'motif-libraries/paper-web-v28';path.mkdir()
    (path/'retained').write_text('retained evidence',encoding='utf-8')
    with pytest.raises(ValueError,match='Fresh release path already exists'):compat.review()
    assert (path/'retained').read_text(encoding='utf-8')=='retained evidence'
