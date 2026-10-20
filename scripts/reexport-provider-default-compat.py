#!/usr/bin/env python3
"""Re-export certified IR for account-wide concurrent header-routed conversations.

Read-only by default; --write creates fresh immutable paper/PPT releases.
Only the reviewed task admission and comparison scheduler code locks may differ.
No new mining, training, online program, source evidence or quality promotion.
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
REVIEWED_CHANGES = {'src/adapters/dsh_web_tasks.ts'}
ADDITIONAL_LOCKS = {'scripts/reexport-provider-default-compat.py', 'src/adapters/harless_reasoning.ts'}
RELEASES = [
    ('paper-web-v18', 'paper-web-v19', 'paper-proofreading',
     'scenarios/paper_proofreading/document-read-contracts.json'),
    ('ppt-master-v13', 'ppt-master-v14', 'ppt', 'scenarios/ppt_master/contracts.json'),
]
VALIDATION_RECORD = 'docs/experiments/concurrent-chat-20261020.md'


def write(path, value):
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))


def review():
    candidates = []
    registry = (ROOT / 'config/harless-scenes.json').read_text(encoding='utf-8')
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
            raise ValueError('Re-export changed the certified online program: ' + old_name)
        if registry.count('motif-libraries/' + old_name) != 1:
            raise ValueError('Registry no longer selects the expected previous release: ' + old_name)
        registry = registry.replace('motif-libraries/' + old_name, 'motif-libraries/' + new_name)
        locks = set(cert['code_locks']) | ADDITIONAL_LOCKS
        candidates.append((old_name, new_name, scene, old, new, entry, cert,
                           {name: sha(ROOT / name) for name in sorted(locks)}))
    return candidates, registry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    candidates, registry = review()
    if not args.write:
        for old_name, new_name, scene, *_ in candidates:
            print(json.dumps({'scene': scene, 'previous_release': old_name, 'candidate_release': new_name,
                              'same_online_program': True, 'model_requests': 0, 'written': False}))
        return
    for old_name, new_name, scene, old, new, entry, cert, code_locks in candidates:
        shutil.copytree(old, new)
        report = read(old / 'learning-report.json')
        report['concurrent_chat_and_provider_output_compatibility'] = {
            'method': 'reexport_certified_serialized_library',
            'repairs': ['header_routed_tasks_without_account_concurrency_cap',
                        'independent_comparison_scheduler_runs',
                        'retry_readiness_inside_admission_lock',
                        'provider_documented_maximum_instead_of_omitted_8k_default'],
            'previous_release': old_name, 'previous_certification_sha256': sha(old / 'certification.json'),
            'same_library_and_evidence': True, 'same_online_program': True,
            'changed_code_locks': sorted(REVIEWED_CHANGES), 'additional_code_locks': sorted(ADDITIONAL_LOCKS),
            'raw_traces_replayed': False, 'new_training_tasks': 0,
            'model_requests': 0, 'quality_cost_promoted': False,
            'validation_record': VALIDATION_RECORD,
        }
        write(new / 'learning-report.json', report)
        cert.update(code_locks=code_locks, learning_report_sha256=sha(new / 'learning-report.json'),
                    file_locks={name: sha(new / name) for name in cert['file_locks']})
        write(new / 'certification.json', cert)
        entry['files'] = {name: sha(new / name) for name in entry['files']}
        write(new / 'entry.json', entry)
        from src.adapters.harless_rsi_bundle import load_product_bundle
        if load_product_bundle(ROOT, new, scene)['runtime_kind'] != entry['runtime_kind']:
            raise ValueError('Unexpected admitted runtime kind: ' + new_name)
        print(json.dumps({'release': new_name, 'same_online_program': True, 'model_requests': 0, 'written': True}))
    (ROOT / 'config/harless-scenes.json').write_bytes(registry.encode('utf-8'))


if __name__ == '__main__':
    main()
