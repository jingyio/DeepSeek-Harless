"""Published Motifs must reject tampering, relabeled evidence and private additions."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'examples/motif-library/file-management-v1'
CHECK = ROOT / 'scripts/check-file-management-library.mjs'


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def copy_bundle(tmp_path):
    target = tmp_path / 'public-bundle'
    shutil.copytree(BUNDLE, target)
    return target


def check(bundle):
    return subprocess.run(['node', str(CHECK), '--bundle', str(bundle)], cwd=ROOT,
                          capture_output=True, text=True, timeout=20)


def relock(bundle, changed):
    """An attacker can rewrite a transport lock; role validation must still reject."""
    catalog = json.loads((bundle / 'catalog.json').read_text(encoding='utf-8'))
    row = next(r for r in catalog['files'] if r['path'] == changed)
    value = json.loads((bundle / changed).read_text(encoding='utf-8'))
    row['sha256'] = hashlib.sha256((bundle / changed).read_bytes()).hexdigest()
    row['policy_digest'] = value['policy_digest']
    save(bundle / 'catalog.json', catalog)
    lock = json.loads((bundle / 'files.lock.json').read_text(encoding='utf-8'))
    for name in [changed, 'catalog.json']:
        lock['sha256'][name] = hashlib.sha256((bundle / name).read_bytes()).hexdigest()
    save(bundle / 'files.lock.json', lock)


def test_published_originals_load_without_historical_trace_inputs():
    result = check(BUNDLE)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report['library_policy_files'] == 9
    assert report['exact_payload_files'] == 15
    assert report['automatic_activation'] is False
    assert report['cloud_requests'] == 0


def test_changed_original_bytes_rejected(tmp_path):
    bundle = copy_bundle(tmp_path)
    p = bundle / 'collection-v1/policy.json'
    p.write_bytes(p.read_bytes() + b' ')
    result = check(bundle)
    assert result.returncode != 0 and 'changed package file' in result.stderr


def test_resigned_training_certification_overlap_rejected(tmp_path):
    bundle = copy_bundle(tmp_path)
    name = 'collection-v1/policy.json'
    p = bundle / name
    value = json.loads(p.read_text(encoding='utf-8'))
    artifact = value['artifact']
    artifact['validation_task_fingerprint'] = artifact['source_task_fingerprints'][0]
    artifact['certified_digest'] = digest({k: v for k, v in artifact.items() if k != 'certified_digest'})
    value['policy_digest'] = digest({k: v for k, v in value.items() if k != 'policy_digest'})
    save(p, value)
    relock(bundle, name)
    result = check(bundle)
    assert result.returncode != 0 and 'decision overlap' in result.stderr


@pytest.mark.parametrize('private_string', ['/Users/private/papers', 'sk-' + 'X' * 24])
def test_private_catalog_additions_rejected_even_with_new_lock(tmp_path, private_string):
    bundle = copy_bundle(tmp_path)
    p = bundle / 'catalog.json'
    value = json.loads(p.read_text(encoding='utf-8'))
    value['private_locator'] = private_string
    save(p, value)
    lock = json.loads((bundle / 'files.lock.json').read_text(encoding='utf-8'))
    lock['sha256']['catalog.json'] = hashlib.sha256(p.read_bytes()).hexdigest()
    save(bundle / 'files.lock.json', lock)
    result = check(bundle)
    assert result.returncode != 0 and 'private path or credential' in result.stderr


def test_unlisted_log_is_rejected(tmp_path):
    bundle = copy_bundle(tmp_path)
    (bundle / 'agent-events.jsonl').write_text('{}\n', encoding='utf-8')
    result = check(bundle)
    assert result.returncode != 0 and 'unlocked or missing' in result.stderr
