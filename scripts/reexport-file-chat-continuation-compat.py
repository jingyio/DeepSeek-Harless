#!/usr/bin/env python3
"""Re-export unchanged Paper/PPT IR after reviewed public-context continuation.

Preview by default; --write creates fresh Paper24/PPT21 without rewriting the
previous releases. Only gateway and task-host locks may differ. No MCP schema,
online program, source evidence, model authority, or quality/cost promotion.
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
compat.REVIEWED_CHANGES = {'scripts/harless_gateway.mjs', 'src/adapters/dsh_web_tasks.ts'}
compat.ADDITIONAL_LOCKS = {'scripts/reexport-file-chat-continuation-compat.py'}
compat.RELEASES = [
    ('paper-web-v23', 'paper-web-v24', 'paper-proofreading',
     'scenarios/paper_proofreading/document-read-contracts.json'),
    ('ppt-master-v20', 'ppt-master-v21', 'ppt', 'scenarios/ppt_master/contracts.json'),
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
        report['file_chat_public_context_compatibility'] = {
            'method': 'reexport_certified_serialized_library',
            'repairs': ['same_host_owned_public_conversation_reader',
                        'carry_human_text_and_public_final_assistant_context',
                        'continue_started_external_parent_in_fresh_private_chat_scope',
                        'reject_new_prompt_while_external_native_turn_is_unclosed',
                        'remove_cross_user_cold_start_count_gate_keep_per_user_deduplication'],
            'preserved_guards': ['session_ownership_and_host_identity',
                                 'tool_argument_result_and_extraction_filtering',
                                 'member_credentials_and_budget_route_ownership',
                                 'immutable_started_parent_presets'],
            'previous_release': old_name,
            'previous_certification_sha256': compat.sha(old / 'certification.json'),
            'same_library_and_evidence': True, 'same_online_program': True,
            'same_tool_schema': True, 'new_capabilities': False,
            'changed_code_locks': sorted(compat.REVIEWED_CHANGES),
            'additional_code_locks': sorted(compat.ADDITIONAL_LOCKS),
            'raw_traces_replayed': False, 'new_training_tasks': 0, 'model_requests': 0,
            'larger_concurrency_capacity_measured': False,
            'quality_cost_promoted': False, 'validation_record': RECORD,
        }
        compat.write(new / 'learning-report.json', report)
        (new / 'README.md').write_bytes((
            '# ' + new_name + '\n\n'
            + '基于 ' + old_name + ' 的公开上下文与宿主生命周期兼容版本。'
            + '仅更新已审阅的任务宿主与网关源码锁：同宿主读者先校验会话归属，再提供用户原文及公开最终助手文本，'
            + '排除工具参数、结果和附件解析记录；独立执行器已启动的父会话继续通过新私有 Chat scope 承接，'
            + '原生轮次未闭合时仍拒绝新的并发发送。'
            + '网关移除跨用户首次启动总数闸门，保留同用户启动去重、凭证、路由归属及通信检查。'
            + '不宣称已测更大容量。MCP、工具 schema、来源边界及模型权限不变。'
            + '原 IR、manifest、任务、工具 schema 和来源证据字节不变。'
            + '旧库保留，无新训练、私有轨迹重放或模型调用，不代表质量或成本效果晋级。'
            + 'File SDK 源码由其独立真实认证负责，不通过本兼容库替代。'
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
