"""Private experiment utilities, not another agent loop."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DATA = ROOT / 'testpdf/file-management-experiment'
PREFIX = 'mcp__file_management__'

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    path.chmod(0o600)

def snapshot(root):
    root = Path(root)
    files = {}
    for p in sorted(root.rglob('*')):
        if p.is_symlink():
            raise ValueError('symlinks are outside experimental file scope')
        if p.is_file():
            files[p.relative_to(root).as_posix()] = sha(p)
    return files

def source_code():
    paths = sorted(HERE.glob('*.py')) + sorted(HERE.glob('*.md'))
    paths += [ROOT / n for n in ('scripts/run-scenario.py', 'src/adapters/dsh_trajectory.py',
               'src/motif_core/offline/edge_compiler.py', 'scripts/export-online-motif-manifest.py',
               'src/motif_core/online_skill_runtime.mjs', 'src/adapters/dsh_online_motif.mjs',
               'src/motif_core/source_dereference.ts','src/motif_core/source_dereference.generated.mjs',
               'src/motif_core/collection_read_policy.ts','src/adapters/dsh_entry_motif.ts',
               'src/motif_core/offline/collection_compiler.py')]
    return {str(p.relative_to(ROOT)): sha(p) for p in paths}
