"""Gateway-only repair must preserve the generated v30/v27 candidates."""
import importlib.util
from pathlib import Path

import pytest
from reexport_compat_fixture import prepare_checkout, remove_expected_difference

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('transport_framing_export',ROOT/'scripts/reexport-transport-framing-compat.py')
wrapper=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(wrapper)
compat=wrapper.compat


@pytest.fixture
def frozen_checkout(tmp_path,monkeypatch):
    root=tmp_path/'checkout'
    published=prepare_checkout(compat,ROOT,root)
    monkeypatch.setattr(compat,'ROOT',root)
    yield root
    assert all(path.read_bytes()==raw for path,raw in published.items())


def test_exact_gateway_delta_and_real_bundle_admission(frozen_checkout):
    candidates,_=compat.review()
    assert [(row['previous'],row['release']) for row in candidates]==[
        ('paper-web-v30','paper-web-v31'),('ppt-master-v27','ppt-master-v28')]
    for row in candidates:
        assert row['reviewed_changes']==['scripts/harless_gateway.mjs']
        assert row['additional_locks']==['scripts/reexport-transport-framing-compat.py']
        before={path.name:path.read_bytes() for path in row['old'].iterdir() if path.is_file()}
        stage=frozen_checkout/'motif-libraries'/('unpublished-'+row['release']);stage.mkdir()
        compat.prepare(row,stage,'offline-transport-framing-compatibility-diagnostic')
        assert all((stage/name).read_bytes()==before[name] for name in compat.IMMUTABLE_ARTIFACTS)
        report=compat.read(stage/'learning-report.json')['native_capabilities_compatibility']
        assert report['repairs']==['remove_hop_by_hop_headers_when_forwarding_decoded_http_bodies']
        assert report['model_requests']==report['new_training_tasks']==0
        assert not report['quality_cost_promoted']


def test_unreviewed_transport_helper_edit_is_rejected(frozen_checkout):
    path=frozen_checkout/'src/adapters/model_transport.py'
    path.write_bytes(path.read_bytes()+b'\n')
    with pytest.raises(ValueError,match='Exact source review differs'):compat.review()


def test_missing_gateway_difference_is_rejected(frozen_checkout):
    remove_expected_difference(compat,frozen_checkout,'scripts/harless_gateway.mjs')
    with pytest.raises(ValueError,match='Exact source review differs'):compat.review()


def test_changed_historical_evidence_is_rejected(frozen_checkout):
    path=frozen_checkout/'motif-libraries/paper-web-v30/source-evidence.json'
    path.write_bytes(path.read_bytes()+b'\n')
    with pytest.raises(ValueError,match='Previous published artifact changed'):compat.review()


def test_existing_destination_is_not_overwritten(frozen_checkout):
    path=frozen_checkout/'motif-libraries/paper-web-v31';path.mkdir()
    with pytest.raises(ValueError,match='Fresh release path already exists'):compat.review()
