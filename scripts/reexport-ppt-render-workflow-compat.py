#!/usr/bin/env python3
"""Re-export unchanged PPT IR after reviewed renderer/font/visual-QA guidance.

Preview by default; --write creates PPT18 without rewriting PPT17. Only the
shared PPT scene prompt may differ. No deck edits, model calls, new training,
trace replay, budget/step caps, or quality/cost promotion are performed.
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
compat.REVIEWED_CHANGES = {'scenarios/ppt_master/prompt.md'}
compat.ADDITIONAL_LOCKS = {'scripts/reexport-ppt-render-workflow-compat.py'}
compat.RELEASES = [
    ('ppt-master-v17', 'ppt-master-v18', 'ppt', 'scenarios/ppt_master/contracts.json'),
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
        report['ppt_render_workflow_compatibility'] = {
            'method': 'reexport_certified_serialized_library',
            'repairs': ['use_deployed_soffice_launcher_with_session_private_profile',
                        'verify_actual_font_family_before_measurement_and_final_render',
                        'use_official_gates_and_rendered_page_visual_review',
                        'treat_pdf_span_overlap_as_candidate_not_standalone_hard_gate',
                        'diagnose_nonconverging_geometry_before_repeating_edits'],
            'shared_by': ['baseline', 'motif'],
            'previous_release': old_name,
            'previous_certification_sha256': compat.sha(old / 'certification.json'),
            'same_library_and_evidence': True, 'same_online_program': True,
            'changed_code_locks': sorted(compat.REVIEWED_CHANGES),
            'additional_code_locks': sorted(compat.ADDITIONAL_LOCKS),
            'raw_traces_replayed': False, 'new_training_tasks': 0, 'model_requests': 0,
            'deck_files_edited': False, 'budget_or_step_caps_added': False,
            'quality_cost_promoted': False, 'validation_record': RECORD,
        }
        compat.write(new / 'learning-report.json', report)
        (new / 'README.md').write_bytes((
            '# ' + new_name + '\n\n'
            + '基于 ' + old_name + ' 的 PPT 渲染流程兼容版本。'
            + '仅更新 Baseline / Motif 共用的场景提示：使用已部署 soffice 包装脚本与会话私有 profile，'
            + '先核对真实字体与最终渲染路径，再以官方门禁及实际页面视觉检查验收。'
            + 'PDF span 包围框相交仅用于定位候选问题，不作为独立清零门禁；'
            + '布局修复无进展时回查字体、测量、导出文件及坐标来源。'
            + '不修改实际 PPT，不限制模型预算或步数，不降低官方要求。'
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
