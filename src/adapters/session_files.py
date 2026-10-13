"""Bounded uploaded-file reads shared by scene MCPs; no model or host paths."""
from pathlib import Path
import hashlib
import os
import stat
import json
from uuid import uuid4


class SessionFiles:
    def __init__(self, directory: Path):
        if directory.is_symlink(): raise ValueError('session_directory_symlink')
        self.root = directory.resolve(strict=True)
        self.identity = self.root.stat()
        self.handles = {}
        manifest=self.root.parent/'approved-inputs.json'
        self.approved=json.loads(manifest.read_text())['files'] if manifest.exists() else None

    def read(self, name: str, expected: str | None = None, limit=20 * 1024 * 1024):
        current = self.root.stat()
        if (current.st_dev, current.st_ino) != (self.identity.st_dev, self.identity.st_ino):
            raise ValueError('session_directory_changed')
        if (not isinstance(name, str) or not name or Path(name).name != name or
                name in ('.', '..') or '\\' in name or '\x00' in name):
            raise ValueError('file_not_in_session')
        path = self.root / name
        if path.is_symlink(): raise ValueError('file_not_in_session')
        with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)), 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise ValueError('private_regular_file_required')
            if before.st_size > limit: raise ValueError('scene_file_too_large')
            data = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
            if len(data) > limit or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError('file_changed_during_read')
        version = hashlib.sha256(data).hexdigest()
        if self.approved is not None and self.approved.get(name)!=version:
            raise ValueError('file_version_changed_from_task_admission')
        if expected is not None and version != expected: raise ValueError('file_version_changed')
        return data, version

    def list_files(self):
        if self.approved is not None and set(self.approved)!={p.name for p in self.root.iterdir() if p.is_file() and not p.is_symlink()}:
            raise ValueError('approved_file_set_changed')
        rows = []
        for path in sorted(self.root.iterdir()):
            if not path.is_file() or path.is_symlink(): continue
            data, version = self.read(path.name)
            rows.append({'name': path.name, 'bytes': len(data), 'sha256': version})
            if len(rows) > 8: raise ValueError('scene_input_limit')
        return {'files': rows}

    def pin(self, name: str, sha256: str):
        data, version = self.read(name, sha256)
        handle = 'source-' + uuid4().hex
        self.handles[handle] = (name, version)
        return {'source_id': handle, 'name': name, 'version_sha256': version, 'bytes': len(data)}

    def pinned(self, source_id: str):
        if source_id not in self.handles: raise ValueError('source_not_in_session')
        name, version = self.handles[source_id]
        data, _ = self.read(name, version)
        return name, data, version
