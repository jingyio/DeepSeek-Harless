#!/usr/bin/env python3
"""Publish a witnessed uploaded-file read Motif without copying private traces into Git."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scenarios.research_ppt.motif_v6 import validate_compilation

PAIRS = {
    'paper-proofreading': ('paper_proofreading', 'mcp__paper_checks__pin_paper_sources',
                           'mcp__paper_checks__read_pinned_paper_sources', 13),
    'research-data-analysis': ('data_analysis', 'mcp__data_analysis__pin_dataset',
                               'mcp__data_analysis__read_pinned_dataset_summary', 4),
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    path.chmod(0o600)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scene', choices=PAIRS, required=True)
    parser.add_argument('--compiled-manifest', type=Path, required=True)
    parser.add_argument('--schemas', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / '.local').resolve()):
        raise ValueError('private output required')
    scene_dir, pin, read, tool_count = PAIRS[args.scene]
    manifest_path = args.compiled_manifest.resolve(strict=True)
    validate_compilation(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if (not manifest['artifacts'] or set(manifest['contracts']) != {pin, read} or
        set(manifest['version_fields']) != {pin, read} or
        manifest['contracts'][pin].get('observed_anchor') is not True or
        any(item.get('tools') != [pin, read] or len(item.get('transfer_evidence', [])) != 1
            for item in manifest['artifacts'])):
        raise ValueError('no compatible witnessed uploaded read')
    schemas = json.loads(args.schemas.read_text(encoding='utf-8'))
    scenario = json.loads((ROOT / 'scenarios' / scene_dir / 'scenario.json').read_text(encoding='utf-8'))
    if (not isinstance(schemas, list) or len(schemas) != tool_count or
        [item['name'] for item in schemas] != sorted(scenario['allowed_tools'])):
        raise ValueError('actual whole scene tool schema required')
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True, mode=0o700)
    bundle = output / 'runtime'
    bundle.mkdir(mode=0o700)
    for name in ('online-manifest.json', 'library.json'):
        shutil.copyfile(manifest_path.parent / name, bundle / name)
        (bundle / name).chmod(0o600)
    write(bundle / 'tool-schemas.json', schemas)
    write(bundle / 'task.json', {'schema_version': 1, 'task_id': 'uploaded-read-admission',
                                'session_id': 'uploaded-read-admission',
                                'intent': 'Read only a model-selected approved uploaded source.',
                                'input_version': '0' * 64, 'bindings': {},
                                'source_versions': {pin: '@observed', read: '@from_anchor'}})
    code = [
        'src/adapters/dsh_online_motif.mjs', 'src/motif_core/online_skill_runtime.mjs',
        'src/motif_core/approved_plan_continuation.generated.mjs',
        'src/motif_core/source_dereference.generated.mjs',
        'src/adapters/dsh_web_tasks.ts', 'src/adapters/harless_rsi_binding.ts',
        'src/adapters/harless_rsi_bundle.py', 'src/adapters/harless_task_scope.ts',
        'src/adapters/session_files.py', f'scenarios/{scene_dir}/server.py',
    ]
    if args.scene == 'paper-proofreading':
        code.extend(['src/adapters/paper_static_checks.py',
                     'scenarios/paper-submission/checks.py',
                     'src/adapters/paper_bibliography.py',
                     'src/adapters/arxiv_metadata.py',
                     'src/adapters/crossref_metadata.py',
                     'src/adapters/paper_query_recovery.py'])
        code.extend(['src/adapters/native_motif_compiler.py', 'src/adapters/trace_paths.py',
                     'src/adapters/paper_renderer.py', 'src/adapters/harless_paper_renderer.py'])
    write(bundle / 'certification.json', {
        'schema_version': 1, 'scene': args.scene,
        'certification_scope': 'independent_trace_structure',
        'binding_policy': 'approved_uploaded_reads_v1',
        'matching_policy': 'structural_only', 'quality_cost_promoted': False,
        'source_evidence_sha256': sha(manifest_path.parent / 'evidence-lock.json'),
        'learning_report_sha256': sha(manifest_path.parent / 'learning-report.json'),
        'manifest_digest': manifest['manifest_digest'],
        'file_locks': {p.name: sha(p) for p in bundle.iterdir() if p.is_file()},
        'code_locks': {name: sha(ROOT / name) for name in sorted(code)},
    })
    subprocess.run(['node', '--input-type=module', '-e',
                    "import fs from 'node:fs'; import {validateOnlineManifest} from './src/motif_core/online_skill_runtime.mjs'; validateOnlineManifest(JSON.parse(fs.readFileSync(process.argv[1])));",
                    str(bundle / 'online-manifest.json')], cwd=ROOT, check=True)
    print(json.dumps({'scene': args.scene, 'runtime_bundle': str(bundle),
                      'artifacts': len(manifest['artifacts']), 'model_requests': 0,
                      'quality_cost_promoted': False}))


if __name__ == '__main__':
    main()
