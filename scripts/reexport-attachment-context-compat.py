#!/usr/bin/env python3
"""Re-export existing certified IR after reviewed attachment/context integration.

Default is a read-only compatibility review. Pass --write only after the final
integration code is stable. No training, source-trace replay, model calls, or
changes to certified tools, source evidence, online programs, or bypass guards.
Published releases are immutable; this script only creates fresh directories.
"""
import argparse
import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.tool_contract_loader import parse_tool_contracts
from src.adapters.tool_schema_contracts import bind_mcp_descriptions

spec = importlib.util.spec_from_file_location('exporter', ROOT / 'scripts/export-online-motif-manifest.py')
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
read = lambda path: json.loads(path.read_text(encoding='utf-8'))

# This is an explicit review boundary, not a blanket renewal of arbitrary locks.
# Contracts, compiler and the bypass runtime keep their original locks. The
# reviewed orchestration delta still has to export the original serialized IR;
# compatibility does not create new execution authority or a quality claim.
REVIEWED_CHANGES = {
    'src/adapters/dsh_web_tasks.ts',
    'src/adapters/geneloop_pdf.py',
    'src/adapters/geneloop_pdf_vision.ts',
    'src/adapters/geneloop_presentation.ts',
    'src/adapters/geneloop_presentation_render.py',
    'src/adapters/harless_attachment_text.py',
    'src/adapters/harless_comparison.ts',
    'src/adapters/harless_task_scope.ts',
}
ADDITIONAL_LOCKS = {
    'src/adapters/harless_attachment_context.ts',
    'src/adapters/geneloop_attachment_cache.ts',
    'src/adapters/harless_public_output.ts',
    'src/adapters/harless_task_progress.ts',
    'scripts/reexport-attachment-context-compat.py',
}
RELEASES = [
    ('paper-web-v13', 'paper-web-v14', 'paper-proofreading',
     'scenarios/paper_proofreading/document-read-contracts.json'),
    ('ppt-master-v8', 'ppt-master-v9', 'ppt', 'scenarios/ppt_master/contracts.json'),
]
VALIDATION_RECORD = 'docs/experiments/attachment-context-streaming-20261019.md'


def write(path, value):
    # Certificates bind committed bytes. Windows text-mode CRLF translation
    # must not create hashes that change when Git applies the repository LF rule.
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))


def review():
    candidates = []
    registry_path = ROOT / 'config/harless-scenes.json'
    registry_text = registry_path.read_text(encoding='utf-8')
    for old_name, new_name, scene, contracts_path in RELEASES:
        old, new = (ROOT / 'motif-libraries' / name for name in (old_name, new_name))
        if new.exists():
            raise ValueError('Use fresh release directories; never overwrite published certificates')
        entry, cert = read(old / 'entry.json'), read(old / 'certification.json')
        for name, expected in entry['files'].items():
            if sha(old / name) != expected:
                raise ValueError('Published release artifact changed: ' + old_name + '/' + name)
        differences = {name for name, expected in cert['code_locks'].items() if sha(ROOT / name) != expected}
        if differences != REVIEWED_CHANGES:
            raise ValueError('Unexpected code-lock differences: ' + repr(sorted(differences)))
        manifest, library = read(old / 'online-manifest.json'), read(old / 'library.json')
        contracts = read(ROOT / contracts_path)
        schemas = [{'name': row['name'], 'description': row['description'], 'inputSchema': row['parameters']}
                   for row in read(old / 'tool-schemas.json')]
        bound = bind_mcp_descriptions(parse_tool_contracts(contracts), schemas)
        contracts = {name: {**contracts[name], 'description': row.description} for name, row in bound.items()}
        exported = exporter.export_manifest(library, contracts, manifest['slot_rules'], manifest['version_fields'])
        if exported != manifest:
            raise ValueError('Re-export must preserve the exact certified online program: ' + old_name)
        if registry_text.count('motif-libraries/' + old_name) != 1:
            raise ValueError('Registry no longer selects the expected previous release: ' + old_name)
        registry_text = registry_text.replace('motif-libraries/' + old_name, 'motif-libraries/' + new_name)
        locks = set(cert['code_locks']) | ADDITIONAL_LOCKS
        candidates.append((old_name, new_name, scene, old, new, entry, cert,
                           {name: sha(ROOT / name) for name in sorted(locks)}))
    return candidates, registry_text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='create fresh releases and select them in the registry')
    args = parser.parse_args()
    candidates, registry_text = review()
    if not args.write:
        for old_name, new_name, scene, *_ in candidates:
            print(json.dumps({'scene': scene, 'previous_release': old_name, 'candidate_release': new_name,
                              'same_online_program': True, 'model_requests': 0, 'written': False}))
        return
    for old_name, new_name, scene, old, new, entry, cert, code_locks in candidates:
        shutil.copytree(old, new)
        report = read(old / 'learning-report.json')
        report['attachment_context_compatibility'] = {
            'method': 'reexport_certified_serialized_library',
            'previous_release': old_name, 'previous_certification_sha256': sha(old / 'certification.json'),
            'same_library_and_evidence': True, 'same_online_program': True,
            'changed_code_locks': sorted(REVIEWED_CHANGES), 'additional_code_locks': sorted(ADDITIONAL_LOCKS),
            'raw_traces_replayed': False, 'new_training_tasks': 0,
            'model_requests': 0, 'quality_cost_promoted': False,
            'validation_record': VALIDATION_RECORD,
        }
        write(new / 'learning-report.json', report)
        cert.update(code_locks=code_locks,
                    learning_report_sha256=sha(new / 'learning-report.json'),
                    file_locks={name: sha(new / name) for name in cert['file_locks']})
        write(new / 'certification.json', cert)
        entry['files'] = {name: sha(new / name) for name in entry['files']}
        write(new / 'entry.json', entry)
        # Raw library, evidence, task, schema and manifest bytes are copied
        # unchanged. Loader admission independently checks the new source locks.
        from src.adapters.harless_rsi_bundle import load_product_bundle
        if load_product_bundle(ROOT, new, scene)['runtime_kind'] != entry['runtime_kind']:
            raise ValueError('Unexpected admitted runtime kind: ' + new_name)
        print(json.dumps({'release': new_name, 'same_online_program': True,
                          'model_requests': 0, 'written': True}))
    (ROOT / 'config/harless-scenes.json').write_bytes(registry_text.encode('utf-8'))


if __name__ == '__main__':
    main()
