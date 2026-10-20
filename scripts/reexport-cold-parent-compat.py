#!/usr/bin/env python3
"""Re-export unchanged certified IR after reviewed cold-parent tool recovery.

Preview by default; --write only creates fresh immutable release directories.
Only dsh_web_tasks.ts may differ from Paper21/PPT16. No model calls, new
training, private trace replay, or quality/cost promotion are performed.
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
compat.REVIEWED_CHANGES = {'src/adapters/dsh_web_tasks.ts'}
compat.ADDITIONAL_LOCKS = {'scripts/reexport-cold-parent-compat.py'}
compat.RELEASES = [
    ('paper-web-v21', 'paper-web-v22', 'paper-proofreading',
     'scenarios/paper_proofreading/document-read-contracts.json'),
    ('ppt-master-v16', 'ppt-master-v17', 'ppt', 'scenarios/ppt_master/contracts.json'),
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
        report['cold_parent_tool_scope_compatibility'] = {
            'method': 'reexport_certified_serialized_library',
            'repairs': ['compare_restored_public_parent_tools_without_ordinary_task_record',
                        'close_obsolete_parent_tools_through_existing_legacy_history_path',
                        'admit_later_prompts_in_fresh_current_private_scopes'],
            'preserved_guards': ['immutable_historical_presets', 'session_scoped_authorization',
                                 'unchanged_current_preset_capabilities'],
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
            + '基于 ' + old_name + ' 的历史父会话冷恢复兼容版本。'
            + '只更新已审阅的 dsh_web_tasks.ts 代码锁：没有普通任务记录的旧对照父会话，'
            + '恢复时核验实际挂载能力；能力缺失则沿既有历史只读路径关闭旧工具，'
            + '保留旧 preset 字节与账号权限，后续请求在新私有 scope 使用当前能力。'
            + '当前兼容 preset 不降级；原 IR、manifest、任务、工具 schema 和来源证据字节不变。'
            + '旧库保留，无新训练、私有轨迹重放或模型调用，不代表科研质量或成本效果晋级。'
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
