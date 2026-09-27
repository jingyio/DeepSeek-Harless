#!/usr/bin/env python3
"""Create a method-blind human review packet from a saved research run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.workflows.research_brief import render_brief  # noqa: E402


def _score_form(points: list[dict]) -> list[str]:
    lines = ["## 评分（由评审填写）", "",
             "每项分别填：事实与引文支持 0/1/2；要求覆盖 0/1/2。0=错误或缺失，"
             "1=部分成立，2=充分成立。请记录关键错误与人工修订分钟数。", ""]
    for point in points:
        lines.extend([f"- `{point['id']}`：支持 __/2；覆盖 __/2；关键错误／缺口：____", ""])
    lines.extend(["- 整体可直接用于组会：是 / 否",
                  "- 允许至多一项覆盖不全后，是否仍可用于当前研究决定：是 / 否",
                  "- 实际人工修订：____ 分钟",
                  "- 对比项是否准确说明两种方法的相同与不同：是 / 部分 / 否 / 不适用", "",
                  "**合格判定：** 所有必答点的支持与覆盖均为 2，且无重要事实错误；"
                  "比较项需确实比较不同方法。小幅降质档仍要求所有事实得到充分支持、"
                  "无关键错误、至多一项仅部分覆盖，且评审明确认为可用。", ""])
    return lines


def build_packet(label: str, question: str, points: list[dict], claims: list[dict],
                 uncertainties: list[dict], citations: dict[str, dict]) -> str:
    if not label or any(char in label for char in "\n\r`#[]"):
        raise ValueError("review label must be a short plain identifier")
    brief = render_brief(question, points, claims, uncertainties, citations)
    lines = [f"# 盲评材料 {label}", "", brief.rstrip(), "", "## 引文原文核查", ""]
    used = {support["evidence_id"] for claim in claims for support in claim["supports"]}
    for evidence_id in sorted(used, key=lambda key: int(key[1:])):
        row = citations[evidence_id]
        lines.extend([f"### {evidence_id} · {row['source']} 第 {row['page']} 页", "",
                      "> " + row["snippet"].replace("\n", "\n> "), ""])
    lines.extend(_score_form(points))
    return "\n".join(lines)


def build_brief_only_packet(label: str, question: str,
                            answer: str, points: list[dict]) -> str:
    if not label or any(char in label for char in "\n\r`#[]"):
        raise ValueError("review label must be a short plain identifier")
    if not answer.strip():
        raise ValueError("run has no answer to review")
    lines = [f"# 盲评材料 {label}", "", f"**共同题目：** {question.strip()}", "",
             "请使用统一提供的来源快照核对以下提交内容的事实、引文和覆盖范围。", "",
             "## 提交内容", "", answer.strip(), ""]
    lines.extend(_score_form(points))
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--question-file", type=Path, required=True)
    parser.add_argument("--answer-points", type=Path, required=True)
    parser.add_argument("--label", required=True, help="blinded label such as A or B")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--brief-only", action="store_true",
                        help="use the same answer-only packet format for structured and native agents")
    args = parser.parse_args()
    run = args.run.resolve(strict=True)
    points = json.loads(args.answer_points.read_text(encoding="utf-8"))
    question = args.question_file.read_text(encoding="utf-8")
    if args.brief_only:
        packet = build_brief_only_packet(args.label, question,
                                         (run / "answer.md").read_text(encoding="utf-8"), points)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(packet, encoding="utf-8")
        print(args.out)
        return
    claims = json.loads((run / "claims.json").read_text(encoding="utf-8"))
    uncertainty_path = run / "uncertainties.json"
    uncertainties = json.loads(uncertainty_path.read_text(encoding="utf-8")) if uncertainty_path.exists() else []
    citations_path = next((run / name for name in ("selected-evidence.json", "evidence.json")
                           if (run / name).exists()), None)
    if citations_path is None:
        parser.error("run has no saved citation ledger")
    citations = json.loads(citations_path.read_text(encoding="utf-8"))
    packet = build_packet(args.label, question, points, claims, uncertainties, citations)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(packet, encoding="utf-8")
    print(args.out)


if __name__ == "__main__":
    main()
