"""Pinned external skill installation; never modifies upstream package contents."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import os

ROOT = Path(__file__).resolve().parents[2]
LOCK = Path(__file__).with_name('skill-lock.json')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def installation():
    return Path(os.environ.get('GENELOOP_PPT_MASTER_ROOT', '/opt/geneloop/ppt-master'))


def read_lock():
    lock = json.loads(LOCK.read_text(encoding='utf-8'))
    if lock.get('schema_version') != 1 or lock.get('version') != '6.6.0' or not lock.get('files'):
        raise ValueError('invalid_ppt_master_lock')
    for name, digest in lock['files'].items():
        p = PurePosixPath(name)
        if p.is_absolute() or '..' in p.parts or '\\' in name or len(digest) != 64:
            raise ValueError('invalid_ppt_master_lock_path')
    expected = sha(json.dumps(lock['files'], sort_keys=True, separators=(',', ':')).encode())
    if lock['package_sha256'] != expected:
        raise ValueError('invalid_ppt_master_package_digest')
    return lock


def read_verified(root, name, lock=None):
    lock = lock or read_lock()
    root = Path(root).absolute()
    path = root / name
    if (root.resolve(strict=True) != root or root.is_symlink() or
            name not in lock['files'] or path.is_symlink() or path.resolve(strict=True) != path or
            not path.is_file()):
        raise ValueError('ppt_master_path_invalid')
    data = path.read_bytes()
    if sha(data) != lock['files'][name]:
        raise ValueError('ppt_master_file_changed: ' + name)
    return data


def verify_installation(root):
    lock = read_lock()
    for name in lock['files']:
        read_verified(root, name, lock)
    # Reject injected Python modules, executables, links, or secrets as well.
    actual = {p.relative_to(root).as_posix() for p in Path(root).rglob('*') if p.is_file() or p.is_symlink()}
    if actual != set(lock['files']):
        raise ValueError('ppt_master_unregistered_files')
    return lock
