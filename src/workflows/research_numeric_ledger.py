"""Render source-bound numeric calculations without semantic model claims."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def collect_numeric_ledger(pages: list[dict[str, Any]]) -> dict[str, Any]:
    sources = []
    for page in pages:
        if page.get("evidence_kind") != "derived_numeric_summary":
            continue
        name, digest = page["source"], page["source_sha256"]
        bounds, fields = page["derived_from_pages"], page["numeric_fields"]
        if (not isinstance(name, str) or not name or not isinstance(digest, str)
                or len(digest) != 64 or not isinstance(bounds, list)
                or len(bounds) != 2 or bounds[0] != 1 or type(bounds[1]) is not int
                or bounds[1] < 1 or not isinstance(fields, dict) or not fields):
            raise ValueError("invalid derived numeric evidence")
        sources.append({"source": name, "source_sha256": digest,
                        "derived_from_records": bounds, "fields": fields})
    sources.sort(key=lambda item: item["source"])
    if len({item["source"] for item in sources}) != len(sources):
        raise ValueError("duplicate derived numeric source")
    payload = json.dumps(sources, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":")).encode("utf-8")
    return {"schema_version": 1, "sources": sources,
            "ledger_sha256": hashlib.sha256(payload).hexdigest()}


def render_numeric_ledger(ledger: dict[str, Any]) -> str:
    if ledger.get("schema_version") != 1 or not isinstance(ledger.get("sources"), list):
        raise ValueError("invalid numeric ledger")

    def cell(value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")

    lines = ["# 结构层数值核对账本", "",
             "本文件由带 SHA-256 版本的 JSON 原始记录确定性计算；不引用模型回答。"
             "字段的科学含义、组间可比性和结论仍需研究者判断。", "",
             f"账本 SHA-256：`{ledger['ledger_sha256']}`", ""]
    for source in ledger["sources"]:
        first, last = source["derived_from_records"]
        lines.extend([f"## {cell(source['source'])}", "",
                      f"来源 SHA-256：`{source['source_sha256']}`；原始记录：{first}–{last}。",
                      "", "| 数值字段 | 有值记录数 | 和 | 均值（可能四舍五入） |",
                      "| --- | ---: | ---: | ---: |"])
        for name, values in sorted(source["fields"].items()):
            lines.append(f"| {cell(name)} | {cell(values['count'])} | "
                         f"{cell(values['sum'])} | {cell(values['mean'])} |")
        lines.append("")
    if not ledger["sources"]:
        lines.extend(["当前来源没有满足完整字段约束的 JSON 数值摘要。", ""])
    return "\n".join(lines)
