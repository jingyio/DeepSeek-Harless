"""Validate an administrator-provided reviewed renderer before scene exposure."""
import hashlib
import json
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def configure_paper_renderer(scene: dict, root: Path) -> None:
    if root.is_symlink(): raise ValueError('renderer_symlink')
    root = root.resolve(strict=True)
    if not root.is_dir(): raise ValueError('renderer_directory_required')
    expected = {'deployment.json', 'review.json', 'package'}
    if {p.name for p in root.iterdir()} != expected: raise ValueError('renderer_files_changed')
    package = root / 'package'
    if package.is_symlink() or not package.is_dir(): raise ValueError('renderer_package_invalid')
    files = {'manifest.json', 'generated-original.py', 'generated-bound.py', 'font.ttf', 'input-schema.json'}
    if {p.name for p in package.iterdir()} != files: raise ValueError('renderer_package_files_changed')
    for p in [root / 'deployment.json', root / 'review.json', *(package / n for n in files)]:
        if p.is_symlink() or not p.is_file() or p.stat().st_nlink != 1 or p.stat().st_size > 25_000_000:
            raise ValueError('renderer_regular_files_required')
    cert = json.loads((root / 'deployment.json').read_text())
    manifest = json.loads((package / 'manifest.json').read_text())
    review = json.loads((root / 'review.json').read_text())
    if (set(cert) != {'schema_version', 'manifest_sha256', 'review_sha256'} or cert['schema_version'] != 1 or
        sha(package / 'manifest.json') != cert['manifest_sha256'] or sha(root / 'review.json') != cert['review_sha256'] or
        manifest.get('schema') != 'paper-renderer-generated-v1' or
        review.get('schema') != 'paper-renderer-source-review-v1' or review.get('approved') is not True or
        review.get('manifest_sha256') != cert['manifest_sha256'] or
        any(sha(package / name) != manifest.get('files', {}).get(name) for name in files - {'manifest.json'})):
        raise ValueError('renderer_deployment_version_mismatch')
    paper_rows = [row for row in scene.get('mcp_rows', [])
                  if row.get('config', {}).get('serverName') == 'paper_checks']
    if scene.get('id') != 'paper-proofreading' or len(paper_rows) != 1:
        raise ValueError('paper_scene_mcp_required')
    paper_rows[0]['config']['args'].append(str(root))
    scene['paper_renderer_root'] = str(root)
    scene['config_sha256'] = hashlib.sha256((scene['config_sha256'] + cert['manifest_sha256'] + cert['review_sha256']).encode()).hexdigest()
