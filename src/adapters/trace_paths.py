"""Lexical trace paths are interpreted by their recorded platform, not the host.

Returned dependency keys always use '/' and must stay below an explicit root.
This does not resolve files, grant permissions or bypass snapshot verification.
"""
from pathlib import PurePosixPath, PureWindowsPath


def _lexical(value):
    return PureWindowsPath(value) if '\\' in value or PureWindowsPath(value).drive else PurePosixPath(value)


def relative_trace_path(value, roots, *, allow_relative=False):
    if not isinstance(value, str) or '\x00' in value:
        return None
    path = _lexical(value)
    if '..' in path.parts:
        return None
    for root in roots:
        parent = _lexical(str(root))
        if type(path) is not type(parent):
            continue
        try:
            relative = path.relative_to(parent)
        except ValueError:
            continue
        return relative.as_posix()
    if allow_relative and not path.anchor:
        return path.as_posix()
    return None
