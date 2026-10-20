"""Actual bundle admission under the exact one-file injection compatibility delta."""
import importlib.util
from pathlib import Path
import shutil
import pytest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('cordis_inject_export',ROOT/'scripts/reexport-cordis-inject-compat.py')
wrapper=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(wrapper)
compat=wrapper.compat

@pytest.fixture
def frozen_checkout(tmp_path,monkeypatch):
    root=tmp_path/'checkout';root.mkdir();names=set(compat.ADDITIONAL_LOCKS)
    for old,*_ in compat.RELEASES:
        source=ROOT/'motif-libraries'/old;shutil.copytree(source,root/'motif-libraries'/old)
        names.update(compat.read(source/'certification.json')['code_locks'])
    for name in names:
        target=root/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
    registry=compat.read(ROOT/'config/harless-scenes.json')
    for old,_,scene,*_ in compat.RELEASES:
        next(row for row in registry['scenes'] if row['id']==scene)['rsi']['runtime_bundle']='motif-libraries/'+old
    compat.write(root/'config/harless-scenes.json',registry);monkeypatch.setattr(compat,'ROOT',root)
    return root

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
