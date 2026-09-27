#!/usr/bin/env python3
"""Create a blind review form or score an equal-input research trial."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.workflows.research_trial import review_template, score_trial  # noqa: E402


def render_score(report: dict) -> str:
    lines = [f"# 同题调研对照：{report['task_id']}", "",
             f"共同来源清单 SHA-256：`{report['source_inventory_sha256']}`", "",
             "| 方法 | 严格合格 | 小幅降质可用 | 模型请求 | API 费用 | 准备与修订 | 总费用 |",
             "| --- | --- | --- | ---: | ---: | ---: | ---: |"]
    for row in report["runs"]:
        api = row["api_cost"]
        if api["kind"] == "actual":
            api_label = f"${api['usd']:.6f}（实际记录）"
        elif api["kind"] == "pinned_price_estimate":
            api_label = f"${api['offpeak_usd']:.6f}–${api['peak_usd']:.6f}（估算）"
        else:
            api_label = "未记录"
        total = f"${row['total_cost_usd']:.6f}" if row["total_cost_usd"] is not None else "未完整记录"
        lines.append(f"| {row['method']}（{row['label']}） | {'是' if row['qualified'] else '否'} | "
                     f"{'是' if row['practical_qualified'] else '否'} | "
                     f"{row['model_requests'] if row['model_requests'] is not None else '—'} | "
                     f"{api_label} | {row['human_minutes']:g} 分钟 | {total} |")
    lines.extend(["", "严格合格：每项支持与覆盖均为 2、无关键错误、整体可直接使用。"
                  "小幅降质可用：评审明确认可，所有事实支持为 2、无关键错误，至多一项覆盖为 1，"
                  "其余覆盖为 2；比较题仍须准确。人工修订时间计入费用。", ""])
    if not report["cost_comparison_ready"]:
        lines.append("总费用尚不可比较：需要实际 API 账单、人工时间单价和本地运行费用。")
    elif not report["qualified_cost_comparison_ready"]:
        lines.append("至少一组未交付合格结果，不能用失败结果的低费用宣称节省。")
    else:
        lines.append("各组均合格且总费用字段完整；可据上表比较本题总费用，仍需更多任务验证。")
    if report["practical_cost_comparison_ready"]:
        lines.append("各组满足小幅降质可用门槛且总费用完整，可另行比较这一档的总费用。")
    else:
        lines.append("小幅降质可用档尚不能做完整费用对照：需所有组通过该档并补齐真实账单与人工时间。")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    template = sub.add_parser("template", help="write an unfilled review form")
    template.add_argument("--answer-points", type=Path, required=True)
    template.add_argument("--label", required=True)
    template.add_argument("--out", type=Path, required=True)
    score = sub.add_parser("score", help="validate reviews and compare saved runs")
    score.add_argument("--manifest", type=Path, required=True)
    score.add_argument("--out-prefix", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "template":
            points = json.loads(args.answer_points.resolve(strict=True).read_text(encoding="utf-8"))
            result = review_template(args.label, points)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(args.out)
        else:
            manifest = json.loads(args.manifest.resolve(strict=True).read_text(encoding="utf-8"))
            result = score_trial(manifest)
            args.out_prefix.parent.mkdir(parents=True, exist_ok=True)
            json_path = args.out_prefix.with_suffix(".json")
            markdown_path = args.out_prefix.with_suffix(".md")
            json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            markdown_path.write_text(render_score(result), encoding="utf-8")
            print(markdown_path)
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"research trial stopped: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
