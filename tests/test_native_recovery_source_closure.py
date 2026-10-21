"""Changed dependencies invalidate current locks without changing historical evidence."""
import hashlib
from pathlib import Path

import pytest

from src.adapters import continuous_rsi
from src.adapters.experience_library import sources
from src.adapters.mcp_learning import ManagementOperations

ROOT = Path(__file__).resolve().parents[1]
TRANSPORT = ('src/adapters/model_transport.py', 'config/geneloop-transport.json')
TRACE = 'src/adapters/geneloop_task_trace.ts'


@pytest.mark.parametrize('name', [*TRANSPORT, TRACE])
def test_new_dependency_changes_learner_evidence_digest(tmp_path, monkeypatch, name):
    assert name in continuous_rsi.LEARNER
    original = (ROOT / name).read_bytes()
    target = tmp_path / name
    target.parent.mkdir(parents=True)
    target.write_bytes(original)
    monkeypatch.setattr(continuous_rsi, 'ROOT', tmp_path)
    before = continuous_rsi.source_map([name])
    assert before[name] == hashlib.sha256(original).hexdigest()
    target.write_bytes(original + b'\n')
    assert continuous_rsi.source_map([name])[name] != before[name]


@pytest.mark.parametrize('name', TRANSPORT)
def test_file_public_runtime_lock_includes_imported_transport(tmp_path, monkeypatch, name):
    assert name in ManagementOperations().runtime_sources()
    current = sources()
    assert current[name] == hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    for source in ManagementOperations().runtime_sources():
        target = tmp_path / source
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / source).read_bytes())
    monkeypatch.setattr(continuous_rsi, 'ROOT', tmp_path)
    assert sources() == current
    target = tmp_path / name
    target.write_bytes(target.read_bytes() + b'\n')
    changed = sources()
    assert {key for key in current if current[key] != changed[key]} == {name}


def test_task_mirror_is_wider_web_evidence_not_standalone_file_runtime():
    assert TRACE in continuous_rsi.LEARNER
    assert TRACE not in ManagementOperations().runtime_sources()
