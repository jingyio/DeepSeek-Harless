"""Actual bundle admission under the exact one-file injection compatibility delta."""
import importlib.util
from pathlib import Path
import pytest
from reexport_compat_fixture import prepare_checkout, remove_expected_difference

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('cordis_inject_export',ROOT/'scripts/reexport-cordis-inject-compat.py')
wrapper=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(wrapper)
compat=wrapper.compat

@pytest.fixture
def frozen_checkout(tmp_path,monkeypatch):
    root=tmp_path/'checkout'
    published=prepare_checkout(compat,ROOT,root)
    monkeypatch.setattr(compat,'ROOT',root)
    yield root
    assert all(path.read_bytes()==raw for path,raw in published.items())

def test_exact_injection_delta_only_and_real_unchanged_bundle_admission(frozen_checkout):
    candidates,_=compat.review()
    assert len(candidates)==2
    for row in candidates:
        assert row['reviewed_changes']==['src/adapters/dsh_web_tasks.ts']
        assert row['additional_locks']==['scripts/reexport-cordis-inject-compat.py']
        before={p.name:p.read_bytes() for p in row['old'].iterdir() if p.is_file()}
        stage=frozen_checkout/'motif-libraries'/('unpublished-'+row['release']);stage.mkdir()
        compat.prepare(row,stage,'offline-injection-compatibility-diagnostic')
        assert all((row['old']/name).read_bytes()==raw for name,raw in before.items())
        assert all((stage/name).read_bytes()==before[name] for name in compat.IMMUTABLE_ARTIFACTS)
        report=compat.read(stage/'learning-report.json')['native_capabilities_compatibility']
        assert report['new_training_tasks']==report['model_requests']==0
        assert report['repairs']==['declare_tools_systemPrompt_sessions_for_shared_Cordis_controller_context']
        assert not report['net_cost_reduction_proven']
        assert not row['new'].exists()

def test_extra_runtime_delta_is_rejected(frozen_checkout):
    file=frozen_checkout/'src/adapters/geneloop_goal.ts';file.write_bytes(file.read_bytes()+b'\n')
    with pytest.raises(ValueError,match='Exact source review differs'):compat.review()


def test_missing_reviewed_difference_is_rejected(frozen_checkout):
    remove_expected_difference(compat,frozen_checkout,'src/adapters/dsh_web_tasks.ts')
    with pytest.raises(ValueError,match='Exact source review differs'):compat.review()
