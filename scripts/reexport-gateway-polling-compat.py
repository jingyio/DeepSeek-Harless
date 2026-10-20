#!/usr/bin/env python3
"""Re-export unchanged Paper/PPT IR after member watcher environment hardening.

Preview by default; --write creates fresh Paper23/PPT20 without rewriting their
previous releases. Only the gateway source lock may differ. No MCP, schema,
model/task authority, trace replay, training, or quality/cost promotion changes.
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
compat.REVIEWED_CHANGES = {'scripts/harless_gateway.mjs'}
compat.ADDITIONAL_LOCKS = {'scripts/reexport-gateway-polling-compat.py'}
compat.RELEASES = [
    ('paper-web-v22', 'paper-web-v23', 'paper-proofreading',
     'scenarios/paper_proofreading/document-read-contracts.json'),
    ('ppt-master-v19', 'ppt-master-v20', 'ppt', 'scenarios/ppt_master/contracts.json'),
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
        report['gateway_watcher_environment_compatibility'] = {
            'method': 'reexport_certified_serialized_library',
            'repairs': ['explicit_allowlisted_member_chokidar_polling_environment',
                        'validate_boolean_polling_and_positive_integer_interval',
                        'default_member_polling_without_native_inotify_handles'],
            'previous_release': old_name,
            'previous_certification_sha256': compat.sha(old / 'certification.json'),
            'same_library_and_evidence': True, 'same_online_program': True,
            'same_tool_schema': True, 'new_capabilities': False,
            'changed_code_locks': sorted(compat.REVIEWED_CHANGES),
            'additional_code_locks': sorted(compat.ADDITIONAL_LOCKS),
            'raw_traces_replayed': False, 'new_training_tasks': 0, 'model_requests': 0,
            'quality_cost_promoted': False, 'validation_record': RECORD,
        }
        compat.write(new / 'learning-report.json', report)
        (new / 'README.md').write_bytes((
            '# ' + new_name + '\n\n'
            + '基于 ' + old_name + ' 的成员文件监听执行环境兼容版本。'
            + '只更新已审阅的账号网关源码锁：成员后端显式接收经过校验的 Chokidar polling/interval，'
            + '默认使用官方 polling，避免依赖宿主共享的 inotify 配额；不继承其他父进程环境。'
            + 'MCP、工具 schema、文件边界、任务权限与模型调用流程不变。'
            + '原 IR、manifest、任务、工具 schema 和来源证据字节不变。'
            + '旧库保留，无新训练、私有轨迹重放或模型调用，不代表质量或成本效果晋级。'
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
