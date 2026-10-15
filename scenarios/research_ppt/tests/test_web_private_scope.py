"""No-model diagnostics for the real Python Web backend and legacy checkpoint guard."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from scenarios.research_ppt import web_scope
from scenarios.research_ppt.service import PPTService, private_path
from scenarios.research_ppt.validation import _private
from scenarios.research_ppt.recovery import CheckpointPPTService, CheckpointRejected, _digest


@pytest.fixture
def job(tmp_path, monkeypatch):
    monkeypatch.setattr(web_scope, '_WEB_PRIVATE_ROOT', None)
    area = tmp_path / 'account' / 'job'; area.mkdir(parents=True)
    path = area / 'job.json'
    path.write_text(json.dumps({'schema_version': 1, 'job_id': 'private-scope-test', 'inputs': [],
        'instruction': 'No model diagnostic', 'slides': 1, 'template': 'academic',
        'operation': 'generate', 'allow_output': False, 'allow_rsi': False,
        'document_cache': False, 'rsi_dir': str(area / 'rsi')}))
    return path


def test_env_alone_never_expands_cli_scope(job, monkeypatch):
    monkeypatch.setenv('HARLESS_PRIVATE_ROOT', str(job.parent))
    with pytest.raises(ValueError):
        PPTService(job)
    with pytest.raises(ValueError):
        _private(job)
    web_scope.configure_web_scope(job, job.parent)
    assert PPTService(job).list_inputs()['inputs'] == []
    assert private_path(job) == _private(job) == job
    foreign = job.parent.parent / 'foreign'; foreign.mkdir()
    (foreign / 'source.pdf').write_bytes(b'foreign')
    for path in [foreign / 'source.pdf', job.parent / '..' / 'foreign' / 'source.pdf']:
        with pytest.raises(ValueError):
            private_path(path)
        with pytest.raises(ValueError):
            _private(path)
    with pytest.raises(ValueError):
        PPTService(job).current({'path': str(foreign / 'source.pdf'), 'version_sha256': hashlib.sha256(b'foreign').hexdigest()})


def test_scope_rejects_foreign_jobs_and_symlink_sources(job):
    with pytest.raises(ValueError):
        web_scope.configure_web_scope(job, job.parent.parent)
    web_scope.configure_web_scope(job, job.parent)
    foreign = job.parent.parent / 'other'; foreign.mkdir()
    (foreign / 'job.json').write_bytes(job.read_bytes())
    with pytest.raises(ValueError):
        web_scope.configure_web_scope(foreign / 'job.json', foreign)
    source = foreign / 'file'; source.write_text('outside')
    link = job.parent / 'escape'
    try:
        link.symlink_to(source)
    except OSError:
        pytest.skip('This platform does not grant symlink permission')
    with pytest.raises(ValueError):
        private_path(link)
    with pytest.raises(ValueError):
        _private(link)


def test_known_scope_checkpoint_upgrade_keeps_original_bytes_and_rejects_unknown_versions(job):
    web_scope.configure_web_scope(job, job.parent)
    service = CheckpointPPTService(job); service.save_checkpoint('test setup')
    path = service.checkpoint_path
    previous = json.loads(path.read_text())
    previous['bindings']['versions'].pop('scene/web_scope.py')
    previous['bindings']['versions'].update(web_scope.LEGACY_SCOPE_VERSIONS)
    previous['payload_sha256'] = _digest({'bindings': previous['bindings'], 'state': previous['state']})
    original = json.dumps(previous).encode(); path.write_bytes(original)
    restored = CheckpointPPTService(job)
    assert restored.restore_status['compatibility_migration'] == 'web-job-scope-v1'
    assert path.read_bytes() == original, 'read-only restore must not rewrite the checkpoint'
    backups = list(job.parent.glob('checkpoint-before-web-scope-*.json'))
    assert len(backups) == 1 and backups[0].read_bytes() == original
    assert 'checkpoint_web_scope_compatibility' in (job.parent / 'feedback.jsonl').read_text()
    restored.save_checkpoint('explicit normal save')
    assert backups[0].read_bytes() == original
    assert CheckpointPPTService(job).restore_status['restored']
    for damage in ['job', 'code', 'source']:
        changed = copy.deepcopy(previous)
        if damage == 'job': changed['bindings']['job_sha256'] = '0' * 64
        elif damage == 'code': changed['bindings']['versions']['scene/service.py'] = '0' * 64
        else: changed['bindings']['versions']['scene/documents.py'] = '0' * 64
        changed['payload_sha256'] = _digest({'bindings': changed['bindings'], 'state': changed['state']})
        path.write_text(json.dumps(changed))
        with pytest.raises(CheckpointRejected):
            CheckpointPPTService(job)
