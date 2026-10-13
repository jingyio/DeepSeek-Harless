"""从当前授权来源独立核验结果侧表；不将来源摘录等同于科学验收。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .documents import file_hash
from .evidence import source_snapshot, validate_scientific_evidence
from .service import PPTService, private_path


def audit_evidence(job: Path, sidecar: Path, *, reviewed_facts: Path | None = None) -> dict:
    job, sidecar = private_path(job), private_path(sidecar)
    # 仅使用任务准备阶段批准的源文件，重新pin/read；不加载侧表中的文件路径。
    service = PPTService(job)
    for row in service.job['inputs']:
        pinned = service.pin_source(row['document_id'])
        service.read_source(pinned['source_id'])
    for item in service.handles.values():
        service.current(item['row'])
    facts = None
    if reviewed_facts is not None:
        reviewed_facts = private_path(reviewed_facts)
        if reviewed_facts == sidecar:
            raise ValueError('独立已审事实不能与模型声明使用同一文件')
        facts = json.loads(reviewed_facts.read_text(encoding='utf-8'))
        if not isinstance(facts, dict):
            raise ValueError('独立已审事实须为fact_id映射')
    report = validate_scientific_evidence(json.loads(sidecar.read_text(encoding='utf-8')),
                                         source_snapshot(service.handles), trusted_facts=facts)
    # 来源验收前后都重核，防止解析/核验期间来源变化。
    for item in service.handles.values():
        service.current(item['row'])
    report.update(job_sha256=file_hash(job), sidecar_file_sha256=file_hash(sidecar),
                  reviewed_facts_sha256=file_hash(reviewed_facts) if reviewed_facts else None,
                  slide_binding='not_checked', rendered_delivery_quality='not_reviewed',
                  quality_gate_passed=False)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job', type=Path, required=True)
    parser.add_argument('--sidecar', type=Path, required=True)
    parser.add_argument('--reviewed-facts', type=Path,
                        help='宿主独立人工审阅侧表；不能用Agent自填review字段代替人评')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    output = private_path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    report = audit_evidence(args.job, args.sidecar, reviewed_facts=args.reviewed_facts)
    with output.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    print(json.dumps({'report': str(output), 'status': report['status'],
                      'quality_gate_passed': False}, ensure_ascii=False))
    return 1 if report['status'] == 'fail' else 0


if __name__ == '__main__':
    raise SystemExit(main())
