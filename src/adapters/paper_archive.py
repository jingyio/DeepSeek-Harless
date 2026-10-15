"""Read a task-approved LaTeX ZIP into an immutable, session-private source view."""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from src.adapters.file_lock import exclusive_lock


MAX_ENTRIES = 128
MAX_ENTRY_BYTES = 20 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024


def _entries(data: bytes):
    rows = []
    names = set()
    total = 0
    try:
        with ZipFile(BytesIO(data)) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                name = info.filename
                path = PurePosixPath(name)
                mode = stat.S_IFMT(info.external_attr >> 16)
                if (info.flag_bits & 1 or not name or not path.parts or name.startswith('/') or
                        '\\' in name or ':' in name or str(path) != name or
                        any(part in ('.', '..') or part.startswith('.') or len(part) > 120
                            for part in path.parts) or len(name) > 255 or len(path.parts) > 8 or
                        mode not in (0, stat.S_IFREG) or name in names):
                    raise ValueError('paper_archive_entry_invalid')
                names.add(name)
                if (len(names) > MAX_ENTRIES or info.file_size > MAX_ENTRY_BYTES or
                        total + info.file_size > MAX_TOTAL_BYTES):
                    raise ValueError('paper_archive_size_limit')
                with archive.open(info) as stream:
                    content = stream.read(MAX_ENTRY_BYTES + 1)
                if len(content) != info.file_size or len(content) > MAX_ENTRY_BYTES:
                    raise ValueError('paper_archive_size_limit')
                total += len(content)
                rows.append((name, content, sha256(content).hexdigest()))
    except BadZipFile as error:
        raise ValueError('paper_archive_invalid') from error
    mains = [name for name, _, _ in rows if PurePosixPath(name).name == 'main.tex']
    if not rows or len(mains) != 1:
        raise ValueError('paper_archive_main_not_unambiguous')
    return rows, mains[0]


def materialize_approved_archive(files):
    """Use only the one approved ZIP; reject a changed derived view on every call."""
    listing = files.list_files()['files']
    archives = [row for row in listing if Path(row['name']).suffix.lower() == '.zip']
    if len(archives) != 1:
        raise ValueError('paper_archive_not_unambiguous')
    name = archives[0]['name']
    data, version = files.read(name, archives[0]['sha256'])
    rows, main = _entries(data)
    workspace = files.root.parent
    parent = workspace / 'paper-archive'
    if parent.is_symlink():
        raise ValueError('paper_archive_private_directory_required')
    parent.mkdir(mode=0o700, exist_ok=True)
    target = parent / version
    expected = {'source_name': name, 'source_sha256': version, 'main': main,
                'files': {name: digest for name, _, digest in rows}}
    with exclusive_lock(parent / '.lock'):
        if target.is_symlink():
            raise ValueError('paper_archive_derived_view_changed')
        if not target.exists():
            staging = parent / ('.staging-' + uuid4().hex)
            staging.mkdir(mode=0o700)
            try:
                source = staging / 'files'
                source.mkdir(mode=0o700)
                for relative, content, _ in rows:
                    destination = source / relative
                    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    with destination.open('xb') as stream:
                        stream.write(content)
                    destination.chmod(0o600)
                manifest = staging / 'manifest.json'
                manifest.write_text(json.dumps(expected, sort_keys=True))
                manifest.chmod(0o600)
                os.replace(staging, target)
            finally:
                if staging.exists():
                    shutil.rmtree(staging)
        source = target / 'files'
        manifest = target / 'manifest.json'
        if (target.is_symlink() or source.is_symlink() or manifest.is_symlink() or
                not source.is_dir() or not manifest.is_file() or
                json.loads(manifest.read_text()) != expected):
            raise ValueError('paper_archive_derived_view_changed')
        actual = {}
        for path in source.rglob('*'):
            if path.is_symlink() or (path.is_file() and (path.stat().st_nlink != 1 or
                    not stat.S_ISREG(path.stat().st_mode))):
                raise ValueError('paper_archive_derived_view_changed')
            if path.is_file():
                actual[path.relative_to(source).as_posix()] = sha256(path.read_bytes()).hexdigest()
        if actual != expected['files']:
            raise ValueError('paper_archive_derived_view_changed')
    return {'root': source, 'main': main, 'archive_sha256': version,
            'files': [{'name': name, 'bytes': len(content), 'sha256': digest}
                      for name, content, digest in rows]}
