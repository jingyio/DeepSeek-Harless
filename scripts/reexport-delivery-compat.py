#!/usr/bin/env python3
"""Validate published certified IR for the additive file-delivery wiring release.

No raw-trace re-mining, new training, model calls, or quality/cost promotion.
Old releases remain immutable. This is a serialized-library compatibility check.
"""
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

def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    changed = {'src/adapters/dsh_web_tasks.ts', 'src/adapters/harless_comparison.ts'}
    releases = [('paper-web-v12', 'paper-web-v13', 'paper-proofreading',
                 'scenarios/paper_proofreading/document-read-contracts.json'),
                ('ppt-master-v7', 'ppt-master-v8', 'ppt', 'scenarios/ppt_master/contracts.json')]
    for old_name, new_name, scene, contracts_path in releases:
        old, new = (ROOT / 'motif-libraries' / name for name in (old_name, new_name))
        if new.exists():
            raise ValueError('Use a fresh release directory; never overwrite a certificate')
        entry, cert = read(old / 'entry.json'), read(old / 'certification.json')
        for name, version in entry['files'].items():
            assert sha(old / name) == version, name
        # Only the reviewed delivery wiring can differ. Contracts, compilers,
        # tools, model dispatch, source/lane binding and bypass rules stay fixed.
        differences = {name for name, version in cert['code_locks'].items() if sha(ROOT / name) != version}
        assert differences == changed, differences
        manifest, library = read(old / 'online-manifest.json'), read(old / 'library.json')
        contracts = read(ROOT / contracts_path)
        schemas = [{'name': row['name'], 'description': row['description'], 'inputSchema': row['parameters']}
                   for row in read(old / 'tool-schemas.json')]
        bound = bind_mcp_descriptions(parse_tool_contracts(contracts), schemas)
        contracts = {name: {**contracts[name], 'description': row.description} for name, row in bound.items()}
        exported = exporter.export_manifest(library, contracts, manifest['slot_rules'], manifest['version_fields'])
        assert exported == manifest, 'Certified IR must export exactly the previous online program'
        shutil.copytree(old, new)
        # Retain the same validated program, source evidence and original claims.
        write(new / 'online-manifest.json', exported)
        report = read(old / 'learning-report.json')
        report['delivery_compatibility'] = {
            'method': 'reexport_certified_serialized_library',
            'previous_release': old_name, 'previous_certification_sha256': sha(old / 'certification.json'),
            'same_library_and_evidence': True, 'same_online_program': True,
            'changed_code_locks': sorted(changed), 'raw_traces_replayed': False,
            'new_training_tasks': 0, 'model_requests': 0, 'quality_cost_promoted': False,
            'validation_record': 'docs/experiments/clickable-generated-files-20261019.md',
        }
        write(new / 'learning-report.json', report)
        locks = set(cert['code_locks']) | {'src/adapters/harless_comparison_artifacts.ts', 'scripts/reexport-delivery-compat.py'}
        cert.update(code_locks={name: sha(ROOT / name) for name in sorted(locks)},
                    learning_report_sha256=sha(new / 'learning-report.json'),
                    file_locks={name: sha(new / name) for name in cert['file_locks']})
        write(new / 'certification.json', cert)
        entry['files'] = {name: sha(new / name) for name in entry['files']}
        write(new / 'entry.json', entry)
        from src.adapters.harless_rsi_bundle import load_product_bundle
        assert load_product_bundle(ROOT, new, scene)['runtime_kind'] == entry['runtime_kind']
        print(json.dumps({'release': new_name, 'same_online_program': True, 'model_requests': 0}))
    registry = ROOT / 'config/harless-scenes.json'
    text = registry.read_text(encoding='utf-8')
    for old_name, new_name, _, _ in releases:
        assert text.count('motif-libraries/' + old_name) == 1
        text = text.replace('motif-libraries/' + old_name, 'motif-libraries/' + new_name)
    registry.write_text(text, encoding='utf-8')

if __name__ == '__main__':
    main()
