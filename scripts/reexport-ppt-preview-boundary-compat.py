#!/usr/bin/env python3
"""Re-export unchanged PPT IR after documenting generated-preview limits.

Preview by default; --write creates PPT19 without rewriting PPT18. Only the
shared PPT scene prompt may differ. No tool/schema/capability changes, deck
edits, model calls, new training, trace replay, or quality/cost promotion.
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
compat.ADDITIONAL_LOCKS = {'scripts/reexport-ppt-preview-boundary-compat.py'}
compat.RELEASES = [
    ('ppt-master-v18', 'ppt-master-v19', 'ppt', 'scenarios/ppt_master/contracts.json'),
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
        report['ppt_generated_preview_boundary_compatibility'] = {
            'method': 'reexport_certified_serialized_library',
            'repairs': ['document_no_generated_png_pixel_return_tool_in_current_roster',
                        'preserve_generated_previews_for_human_visual_review',
                        'do_not_claim_text_geometry_or_ascii_as_pixel_visual_review',
                        'keep_output_files_outside_approved_source_mcp_scope'],
            'preserved_workflow': ['soffice_launcher_with_session_private_profile',
                                   'actual_font_family_calibration',
                                   'official_gates_without_standalone_span_overlap_hard_gate'],
            'shared_by': ['baseline', 'motif'],
            'previous_release': old_name,
            'previous_certification_sha256': compat.sha(old / 'certification.json'),
            'same_library_and_evidence': True, 'same_online_program': True,
            'same_tool_schema': True, 'new_capabilities': False,
            'changed_code_locks': sorted(compat.REVIEWED_CHANGES),
            'additional_code_locks': sorted(compat.ADDITIONAL_LOCKS),
            'raw_traces_replayed': False, 'new_training_tasks': 0, 'model_requests': 0,
            'deck_files_edited': False, 'budget_or_step_caps_added': False,
            'quality_cost_promoted': False, 'validation_record': RECORD,
        }
        compat.write(new / 'learning-report.json', report)
        (new / 'README.md').write_bytes((
            '# ' + new_name + '\n\n'
            + '基于 ' + old_name + ' 的自产预览能力边界兼容版本。'
            + '仅更新 Baseline / Motif 共用的场景提示：当前工具不能将自产 PNG 像素返回模型，'
            + '不得把路径、base64、ASCII 或几何统计冒充已看过页面；'
            + '交付完整预览及实际检查结果，并如实注明逐页视觉复核尚未完成，留给用户或人工审阅。'
            + '保持来源 MCP 的上传审批边界，保留 soffice 包装脚本、字体校准及防重复 bbox 微调流程。'
            + '不增加工具或能力，不修改实际 PPT，不限制预算或步数，不降低官方要求。'
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
