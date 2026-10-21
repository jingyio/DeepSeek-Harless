#!/usr/bin/env python3
"""Re-export unchanged certified IR after the reviewed sandbox mount repair.

Preview by default; --write creates fresh releases without replacing old files.
Only geneloop_shell.ts may differ from the preceding source certificates. This
does not train new programs, replay private traces, or promote quality/cost.
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
compat.REVIEWED_CHANGES = {'src/adapters/geneloop_shell.ts'}
compat.ADDITIONAL_LOCKS = {'scripts/reexport-sandbox-mount-compat.py'}
compat.RELEASES = [
    ('paper-web-v20', 'paper-web-v21', 'paper-proofreading',
     'scenarios/paper_proofreading/document-read-contracts.json'),
    ('ppt-master-v15', 'ppt-master-v16', 'ppt', 'scenarios/ppt_master/contracts.json'),
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
        report['sandbox_mountpoint_compatibility'] = {
            'method': 'reexport_certified_serialized_library',
            'repairs': ['prepare_fixed_scratch_child_mountpoints_before_readonly_parent_bind',
                        'reject_symlink_and_nondirectory_mountpoints'],
            'preserved_guards': ['readonly_inputs_and_scratch', 'network_namespace_isolation',
                                 'session_scoped_workspaces'],
            'previous_release': old_name,
            'previous_certification_sha256': compat.sha(old / 'certification.json'),
            'same_library_and_evidence': True, 'same_online_program': True,
            'changed_code_locks': sorted(compat.REVIEWED_CHANGES),
            'additional_code_locks': sorted(compat.ADDITIONAL_LOCKS),
            'raw_traces_replayed': False, 'new_training_tasks': 0, 'model_requests': 0,
            'quality_cost_promoted': False, 'validation_record': RECORD,
        }
        compat.write(new / 'learning-report.json', report)
        (new / 'README.md').write_bytes((
            '# ' + new_name + '\n\n'
            + '基于 ' + old_name + ' 的 Linux 只读沙箱挂载准备兼容版本。'
            + '只更新已审阅的 geneloop_shell.ts 代码锁：固定会话 scratch 内预建 inputs/outputs 挂载点，'
            + '拒绝符号链接和非目录；输入、scratch 只读以及网络隔离守卫保持。'
            + '原 IR、manifest、任务、工具 schema 与来源证据字节不变；旧库保留，'
            + '无新训练、原始轨迹重放或模型请求，不代表科研质量或成本效果晋级。'
            + '验证与限制见 [' + RECORD + '](../../' + RECORD + ')。\n'
        ).encode('utf-8'))
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
