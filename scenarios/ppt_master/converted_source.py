"""Official PDF conversion with session-private, versioned derivative receipts.

Original uploads are never modified. Derivative files are not slide authoring;
their exact bytes are checked again before a learned read continuation.
"""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import uuid

from scenarios.ppt_master.package import read_verified


def digest(data):
    return hashlib.sha256(data).hexdigest()


class ConvertedSources:
    def __init__(self, sources, skill):
        self.sources, self.skill = sources, skill
        self.receipts = {}

    def _files(self, directory):
        result = {}
        for path in sorted(directory.rglob('*')):
            if path.is_symlink():
                raise ValueError('converted_source_symlink')
            if path.is_file():
                if path.stat().st_nlink != 1:
                    raise ValueError('converted_source_hardlink')
                result[path.relative_to(directory).as_posix()] = digest(path.read_bytes())
        return result

    def convert(self, source_id):
        name, data, version = self.sources.pinned(source_id)
        if Path(name).suffix.lower() != '.pdf':
            raise ValueError('pdf_source_required')
        # Verify all converter dependencies against the installed package.
        for relative in self.skill.lock['files']:
            if relative.startswith('scripts/'):
                read_verified(self.skill.root, relative, self.skill.lock)
        code = self.sources.root.parent / 'code'
        if code.is_symlink() or not code.is_dir():
            raise ValueError('session_code_directory_required')
        directory = Path(tempfile.mkdtemp(prefix='ppt-source-', dir=code))
        original = directory / 'source.pdf'
        original.write_bytes(data)
        env = {k: v for k, v in os.environ.items()
               if k in ('PATH', 'LANG', 'LC_ALL', 'LD_LIBRARY_PATH', 'SYSTEMROOT', 'WINDIR')}
        env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1', HOME=str(directory),
                   TMPDIR=str(directory), TEMP=str(directory), TMP=str(directory))
        completed = subprocess.run([sys.executable, str(self.skill.root / 'scripts/source_to_md.py'),
                                    str(original)], env=env, cwd=directory,
                                   capture_output=True, timeout=90)
        self.sources.pinned(source_id)
        if completed.returncode:
            raise ValueError('official_source_conversion_failed_exit_' + str(completed.returncode))
        markdown = directory / 'source.md'
        if not markdown.is_file() or not markdown.read_bytes().strip():
            raise ValueError('official_source_conversion_missing_text')
        files = self._files(directory)
        receipt = 'result-' + uuid.uuid4().hex
        self.receipts[receipt] = (source_id, version, name, directory, files)
        return {'converted_id': receipt, 'version_sha256': version,
                'conversion_sha256': digest(json.dumps(files, sort_keys=True).encode()),
                'file_count': len(files), 'status': 'converted',
                'original_modified': False, 'visual_checked': False}

    def read(self, converted_id):
        if converted_id not in self.receipts:
            raise ValueError('unknown_session_conversion')
        source_id, version, name, directory, files = self.receipts[converted_id]
        self.sources.pinned(source_id)
        if directory.is_symlink() or self._files(directory) != files:
            raise ValueError('converted_source_version_changed')
        raw = (directory / 'source.md').read_bytes()
        if digest(raw) != files.get('source.md'):
            raise ValueError('converted_source_version_changed')
        text = raw.decode('utf-8')
        self.sources.pinned(source_id)
        return {'version_sha256': version, 'name': name, 'text': text,
                'markdown_path': '/work/' + directory.name + '/source.md',
                'directory': '/work/' + directory.name, 'files': list(files),
                'truncated': False, 'visual_checked': False,
                'coverage': 'official_conversion_not_visual_or_scientific_review'}
