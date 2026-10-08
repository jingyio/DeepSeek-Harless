#!/usr/bin/env python3
"""Recompute a public eight-target statistic and render it through the real MCP.

This is the simple deterministic baseline for the local Python/Quarto category.
It sends no model request and never writes to a user application.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path

from mcp import Client, StdioServerParameters


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "benchmarks/research_weekly_loop_v1/pbcnet_mutation_public_manifest.json"
DATA = ROOT / ".local/benchmarks/research-weekly-loop/aidd-next-preflight/public-data-preflight/mutation"
INDEPENDENT = DATA.parent / "mutation-recomputation.json"
OUT = ROOT / ".local/benchmarks/mcp-app-internal-v2/local-data-script"
QMD = "app-internal-data-baseline/pbcnet-mutation-statistics.qmd"
MEASURES = [
    {"name": "pairs", "op": "count"},
    {"name": "pearson", "op": "pearson_correlation", "left": "Label", "right": "pre"},
    {"name": "spearman", "op": "spearman_correlation", "left": "Label", "right": "pre"},
]


def write_private(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


async def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entries = manifest["mutation_files"]
    if len(entries) != 8 or len({row["directory"] for row in entries}) != 8:
        raise ValueError("Expected eight distinct frozen mutation sources")
    started = time.monotonic()
    params = StdioServerParameters(command=sys.executable,
                                   args=["-m", "src.mcp.local_research_tools_server"],
                                   cwd=ROOT)
    calls = []

    async with Client(params, read_timeout_seconds=180) as client:
        async def call(name: str, arguments: dict) -> dict:
            reply = await client.call_tool(name, arguments)
            payload = getattr(reply, "structured_content", None)
            calls.append({"tool": name, "is_error": bool(getattr(reply, "is_error", False))})
            if getattr(reply, "is_error", False) or not isinstance(payload, dict):
                raise RuntimeError(f"{name} did not return a structured success result")
            return payload

        listing = await call("list_research_sources", {"directory": str(DATA)})
        listed = {Path(row["path"]).name for row in listing["files"]}
        expected = {row["directory"] + ".csv" for row in entries}
        if listed != expected:
            raise ValueError("Public mutation source set changed")
        results = []
        for entry in sorted(entries, key=lambda row: row["directory"]):
            path = DATA / (entry["directory"] + ".csv")
            pinned = await call("pin_source", {"path": str(path)})
            if pinned.get("sha256") != entry["sha256"]:
                raise ValueError("Public mutation source version changed")
            inspected = await call("inspect_records", {"source_id": pinned["source_id"]})
            if not {"Label", "pre"} <= set(inspected["fields"]):
                raise ValueError("Required prediction fields changed")
            aggregated = await call("aggregate_records", {
                "dataset_id": inspected["dataset_id"], "group_by": [],
                "measures": MEASURES,
            })
            if aggregated.get("group_count") != 1 or len(aggregated.get("groups", [])) != 1:
                raise ValueError("Expected one ungrouped statistic row")
            values = aggregated["groups"][0]["values"]
            if values["pairs"] != inspected["record_count"]:
                raise ValueError("Statistic denominator differs from source row count")
            results.append({"target": entry["target"], "file": path.name,
                            "source_sha256": pinned["sha256"], **values})
        n = sum(row["pairs"] for row in results)
        macro_pearson = statistics.mean(row["pearson"] for row in results)
        macro_spearman = statistics.mean(row["spearman"] for row in results)
        prior = json.loads(INDEPENDENT.read_text(encoding="utf-8"))
        prior_by_target = {row["target"]: row for row in prior["targets"]}
        if (n != prior["total_pair_rows"] or len(prior_by_target) != 8
                or abs(macro_pearson - prior["macro_pearson"]) > 1e-12
                or abs(macro_spearman - prior["macro_spearman"]) > 1e-12):
            raise ValueError("Recomputation differs from the prior independent audit")
        for row in results:
            reference = prior_by_target[row["target"]]
            if (row["pairs"] != reference["pair_rows"]
                    or row["source_sha256"] != reference["csv_sha256"]
                    or abs(row["pearson"] - reference["pearson"]) > 1e-12
                    or abs(row["spearman"] - reference["spearman"]) > 1e-12):
                raise ValueError("A target statistic differs from the independent audit")
        table = ["| Target | Pairs | Pearson | Spearman |", "| --- | ---: | ---: | ---: |"]
        table.extend(f"| {row['target']} | {row['pairs']} | {row['pearson']:.6f} | {row['spearman']:.6f} |"
                     for row in results)
        source_table = ["| Public CSV | SHA-256 |", "| --- | --- |"]
        source_table.extend(f"| {row['file']} | `{row['source_sha256']}` |" for row in results)
        content = "\n".join([
            "---", "title: PBCNet2.0 突变预测公开数据复算", "format: html", "---", "",
            "## 复算范围", "",
            "使用作者仓库固定版本中的八个公开 `predict.csv`，仅对每个目标的 `Label` 与 `pre` "
            "计算 Pearson 和平均秩 Spearman；每个目标等权平均。以下是机械复算，不评判模型泛化或泄漏。", "",
            *table, "", f"总配对记录：**{n}**。八目标宏平均 Pearson：**{macro_pearson:.12f}**；"
            f"宏平均 Spearman：**{macro_spearman:.12f}**。", "",
            "## 解释边界", "",
            "结果仅验证公开预测文件的汇总统计。未从蛋白／配体结构重新运行模型；"
            "这些 CSV 不足以独立证明训练与测试的生物学对应、时间切分或零样本泛化。", "",
            "## 来源版本", "",
            f"作者仓库 commit：`{manifest['commit']}`。文件哈希如下；完整来源清单见项目的公开 manifest。", "",
            *source_table, "",
        ])
        written = await call("write_workspace_text", {"path": QMD, "content": content})
        preview = await call("preview_quarto", {"path": QMD, "output_format": "html"})
        if not preview.get("quarto_available") or preview.get("source_sha256") != written["sha256"]:
            raise ValueError("Quarto preview did not match the generated source")
        rendered = await call("render_quarto", {"path": QMD, "output_format": "html",
                                                 "timeout_seconds": 180})
        if not rendered.get("ok"):
            raise RuntimeError("Quarto render failed")
    output = {
        "task_id": "app-internal-local-data-pbcnet-script-baseline",
        "model_requests": 0, "model_cost_usd": 0,
        "source_manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
        "independent_audit_sha256": hashlib.sha256(INDEPENDENT.read_bytes()).hexdigest(),
        "results": results, "total_pairs": n,
        "macro_pearson": macro_pearson, "macro_spearman": macro_spearman,
        "quarto_source": written["path"], "quarto_source_sha256": written["sha256"],
        "quarto_output_directory": rendered["output_directory"],
        "tool_calls": calls, "elapsed_seconds": round(time.monotonic() - started, 3),
    }
    write_private(OUT / "result.json", output)
    print(json.dumps({"status": "completed", "model_requests": 0,
                      "tool_calls": len(calls), "total_pairs": n,
                      "macro_spearman": macro_spearman,
                      "elapsed_seconds": output["elapsed_seconds"]}))


if __name__ == "__main__":
    asyncio.run(main())
