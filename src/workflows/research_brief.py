"""Render accepted, quote-checked point claims as a reviewable research brief."""

from __future__ import annotations

from typing import Any


def render_brief(question: str, points: list[dict[str, Any]],
                 claims: list[dict[str, Any]], uncertainties: list[dict[str, Any]],
                 citations: dict[str, dict[str, Any]]) -> str:
    lines = ["# 调研简报（待人工审阅）", "", f"**问题：** {question.strip()}", "",
             "以下结论的引文已核对到本地来源；是否完整支持结论仍需人工审阅。"]
    for index, point in enumerate(points, 1):
        lines.extend(["", f"## {index}. {point['requirement']}", ""])
        rows = [row for row in claims if row.get("point_id") == point["id"]]
        if not rows:
            lines.append("尚无可引用的结论。")
        for row in rows:
            references = []
            for support in row["supports"]:
                evidence_id = support["evidence_id"]
                source = citations[evidence_id]
                location = ("派生数值摘要（记录 "
                            f"{source['derived_from_pages'][0]}–{source['derived_from_pages'][1]}）"
                            if source.get("evidence_kind") == "derived_numeric_summary"
                            else f"第 {source['page']} 页/条")
                references.append(f"[{evidence_id}: {source['source']}，{location}]")
            lines.append(f"- {row['text']} {' '.join(references)}")
        gaps = [item["text"] for item in uncertainties
                if isinstance(item, dict) and item.get("point_id") == point["id"]]
        for gap in gaps:
            lines.append(f"- **尚不确定：** {gap}")
    extra_gaps = [item["text"] for item in uncertainties
                  if isinstance(item, dict) and item.get("point_id") not in {p["id"] for p in points}]
    if extra_gaps:
        lines.extend(["", "## 其他待核查事项", ""])
        lines.extend(f"- {gap}" for gap in extra_gaps)
    lines.extend(["", "## 证据索引", ""])
    used = {support["evidence_id"] for claim in claims for support in claim["supports"]}
    if used:
        for evidence_id in sorted(used, key=lambda key: int(key[1:])):
            row = citations[evidence_id]
            location = ("派生数值摘要（记录 "
                        f"{row['derived_from_pages'][0]}–{row['derived_from_pages'][1]}）"
                        if row.get("evidence_kind") == "derived_numeric_summary"
                        else f"第 {row['page']} 页/条")
            lines.append(f"- {evidence_id}：{row['source']}，{location}，"
                         f"SHA-256 {row['source_sha256'][:12]}…")
    else:
        lines.append("暂无可引用证据。")
    return "\n".join(lines) + "\n"
