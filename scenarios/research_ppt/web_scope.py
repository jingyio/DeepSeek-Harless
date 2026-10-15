"""Explicit host-bound Web job scope; environment variables never enable it."""
from __future__ import annotations

from pathlib import Path

_WEB_PRIVATE_ROOT: Path | None = None


def configure_web_scope(job_path: Path, private_root: Path) -> None:
    global _WEB_PRIVATE_ROOT
    job = job_path.resolve(strict=True)
    root = private_root.resolve(strict=True)
    if (not root.is_dir() or not job.is_file() or job.name != 'job.json'
            or job.parent != root or job_path.is_symlink() or private_root.is_symlink()):
        raise ValueError('Web PPT scope must be the exact host-approved job directory')
    if _WEB_PRIVATE_ROOT is not None and _WEB_PRIVATE_ROOT != root:
        raise ValueError('A Web PPT process cannot switch jobs')
    _WEB_PRIVATE_ROOT = root


def web_private_root() -> Path | None:
    return _WEB_PRIVATE_ROOT


def private_root(repository: Path) -> Path:
    return _WEB_PRIVATE_ROOT if _WEB_PRIVATE_ROOT is not None else (repository / '.local').resolve()


# Only the audited directory-scope compatibility patch may restore these
# known schema-2 implementations. Future edits must not widen this allowlist.
LEGACY_SCOPE_VERSIONS = {
    'scene/service.py': 'fa236527754a7c1ba06bfd049a97047a79f82070386192d8b3813955b2db1da5',
    'scene/validation.py': '2d224c4ed0a5e0db1c00fa531aee00d76ec8606c97a9f015b31fcd439c3c9328',
    'scene/delivery_server.py': '7a58d66c270b89fd3d87e992ade17738a97b408f2435d20d815f18942cd5cd90',
    'scene/recovery.py': '4478e70643b72e0b7bb0430b493c5b23aa845f010224e0d546ba3b8a4a38635a',
}
CURRENT_SCOPE_VERSIONS = {'scene/service.py': '5f621cee0f722301ca0b1c7b05071f908725020726f61e0c67af2807c6e014b1', 'scene/validation.py': 'ec398e55fdb42a77a37cb839ec2acac15975f3ab444c3317cd0045292a57af32', 'scene/delivery_server.py': '3178667dab68bccd3283161dc1412cd6e03874dfb43dfd8ca96671bee8c6eeab', 'scene/recovery.py': '45fcadd48b0fd18c4f572f31c064924272dab6b278645b405d6e43c7b646108d'}


def compatible_scope_bindings(previous: dict, current: dict) -> bool:
    if _WEB_PRIVATE_ROOT is None or not isinstance(previous, dict) or not isinstance(current, dict):
        return False
    if set(previous) != set(current) or any(previous[k] != current[k] for k in current if k != 'versions'):
        return False
    old, new = previous.get('versions'), current.get('versions')
    if not isinstance(old, dict) or not isinstance(new, dict) or set(new) != set(old) | {'scene/web_scope.py'}:
        return False
    if any(old.get(k) != v for k, v in LEGACY_SCOPE_VERSIONS.items()):
        return False
    if set(CURRENT_SCOPE_VERSIONS) != set(LEGACY_SCOPE_VERSIONS) or any(new.get(k) != v for k, v in CURRENT_SCOPE_VERSIONS.items()):
        return False
    return all(old[k] == new[k] for k in old if k not in LEGACY_SCOPE_VERSIONS)
