"""Exact Gateway/member/host composition delta, preserving real prior evidence."""
import importlib.util
from pathlib import Path

import pytest
from reexport_compat_fixture import prepare_checkout, remove_expected_difference

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('member_path_export',ROOT/'scripts/reexport-member-path-compat.py')
wrapper=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(wrapper)
compat=wrapper.compat


@pytest.fixture
def frozen_checkout(tmp_path,monkeypatch):
    root=tmp_path/'checkout'
    published=prepare_checkout(compat,ROOT,root)
    monkeypatch.setattr(compat,'ROOT',root)
    yield root
    assert all(path.read_bytes()==raw for path,raw in published.items())


def test_exact_sandbox_path_delta_and_real_bundle_admission(frozen_checkout):
    candidates,_=compat.review()
    assert [(row['previous'],row['release']) for row in candidates]==[
        ('paper-web-v28','paper-web-v29'),('ppt-master-v25','ppt-master-v26')]
    registry=compat.sha(frozen_checkout/'config/harless-scenes.json')
    for row in candidates:
        assert row['reviewed_changes']==['scripts/harless_gateway.mjs','scripts/harless_member_scenes.mjs',
                                        'src/adapters/geneloop_native_host.mjs']
        assert row['additional_locks']==['scripts/reexport-member-path-compat.py']
        before={path.name:path.read_bytes() for path in row['old'].iterdir() if path.is_file()}
        stage=frozen_checkout/'motif-libraries'/('unpublished-'+row['release']);stage.mkdir()
        compat.prepare(row,stage,'offline-member-path-compatibility-diagnostic')
        assert all((row['old']/name).read_bytes()==raw for name,raw in before.items())
        assert all((stage/name).read_bytes()==before[name] for name in compat.IMMUTABLE_ARTIFACTS)
        report=compat.read(stage/'learning-report.json')['native_capabilities_compatibility']
        assert report['repairs']==['map_verified_native_resources_to_member_sandbox_mount_targets',
                                  'activate_reviewed_native_providers_with_official_host_patch_semantics']
        assert report['same_online_program'] and report['same_mcp_schema']
        assert report['new_training_tasks']==report['model_requests']==0
        assert not report['net_cost_reduction_proven'] and not report['quality_cost_promoted']
        assert not row['new'].exists()
    assert compat.sha(frozen_checkout/'config/harless-scenes.json')==registry


def test_additional_native_tool_edit_is_rejected(frozen_checkout):
    path=frozen_checkout/'src/adapters/geneloop_native_work.ts'
    path.write_bytes(path.read_bytes()+b'\n')
    with pytest.raises(ValueError,match='Exact source review differs'):compat.review()


@pytest.mark.parametrize('name',sorted(wrapper.REVIEWED))
def test_missing_reviewed_difference_is_rejected(frozen_checkout,name):
    remove_expected_difference(compat,frozen_checkout,name)
    with pytest.raises(ValueError,match='Exact source review differs'):compat.review()


def test_changed_historical_evidence_is_rejected(frozen_checkout):
    path=frozen_checkout/'motif-libraries/paper-web-v28/source-evidence.json'
    path.write_bytes(path.read_bytes()+b'\n')
    with pytest.raises(ValueError,match='Previous published artifact changed'):compat.review()


def test_existing_destination_is_not_overwritten(frozen_checkout):
    path=frozen_checkout/'motif-libraries/paper-web-v29';path.mkdir()
    (path/'retained').write_text('retained failed evidence',encoding='utf-8')
    with pytest.raises(ValueError,match='Fresh release path already exists'):compat.review()
    assert (path/'retained').read_text(encoding='utf-8')=='retained failed evidence'
