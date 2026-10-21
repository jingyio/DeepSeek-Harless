#!/usr/bin/env python3
"""Re-export unchanged certified IR after the reviewed public paging repair.

Preview by default; --write creates fresh releases and retains every old byte.
The source review, evidence hashes and deterministic manifest re-export are
shared with the previous compatibility exporter. This is not new training.
"""
import argparse
import importlib.util
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location('compat', ROOT / 'scripts/reexport-provider-output-compat.py')
compat = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compat)
compat.REVIEWED_CHANGES = {'src/adapters/dsh_web_tasks.ts', 'src/adapters/harless_public_output.ts'}
compat.ADDITIONAL_LOCKS = {'scripts/reexport-multiuser-page-compat.py'}
compat.RELEASES = [
    ('paper-web-v19', 'paper-web-v20', 'paper-proofreading',
     'scenarios/paper_proofreading/document-read-contracts.json'),
    ('ppt-master-v14', 'ppt-master-v15', 'ppt', 'scenarios/ppt_master/contracts.json'),
]
RECORD = 'docs/experiments/five-user-stress-20261020.md'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    candidates, registry = compat.review()
    if not args.write:
        for old_name, new_name, *_ in candidates:
            print({'previous': old_name, 'candidate': new_name, 'same_online_program': True,
                   'model_requests': 0, 'written': False})
        return
    for old_name, new_name, scene, old, new, entry, cert, locks in candidates:
        shutil.copytree(old, new)
        report = compat.read(old / 'learning-report.json')
        report['public_history_paging_compatibility'] = {
            'method': 'reexport_certified_serialized_library',
            'repairs': ['resolve_native_session_page_address',
                        'require_existing_task_before_original_content_resolution'],
            'previous_release': old_name,
            'previous_certification_sha256': compat.sha(old / 'certification.json'),
            'same_library_and_evidence': True, 'same_online_program': True,
            'changed_code_locks': sorted(compat.REVIEWED_CHANGES),
            'additional_code_locks': sorted(compat.ADDITIONAL_LOCKS),
            'raw_traces_replayed': False, 'new_training_tasks': 0, 'model_requests': 0,
            'quality_cost_promoted': False, 'validation_record': RECORD,
        }
        compat.write(new / 'learning-report.json', report)
        cert.update(code_locks=locks, learning_report_sha256=compat.sha(new / 'learning-report.json'),
                    file_locks={name: compat.sha(new / name) for name in cert['file_locks']})
        compat.write(new / 'certification.json', cert)
        entry['files'] = {name: compat.sha(new / name) for name in entry['files']}
        compat.write(new / 'entry.json', entry)
        from src.adapters.harless_rsi_bundle import load_product_bundle
        if load_product_bundle(ROOT, new, scene)['runtime_kind'] != entry['runtime_kind']:
            raise ValueError('Unexpected admitted runtime kind: ' + new_name)
        print({'release': new_name, 'same_online_program': True, 'model_requests': 0, 'written': True})
    (ROOT / 'config/harless-scenes.json').write_bytes(registry.encode('utf-8'))


if __name__ == '__main__':
    main()
