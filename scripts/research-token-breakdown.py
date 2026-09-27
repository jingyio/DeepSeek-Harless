#!/usr/bin/env python3
"""Break down saved DeepSeek research runs by stage and billed token class.

The input manifest names local, already completed budget ledgers. This script
does not call a model or read credentials. Prices are an explicit estimate.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


OFFPEAK_USD_PER_MILLION = {"miss": 0.15, "hit": 0.003, "output": 0.6}


def _request(row: dict) -> dict:
    usage = row.get("response_usage")
    if row.get("response_status") != 200 or not isinstance(usage, dict):
        raise ValueError("ledger contains a request without complete successful usage")
    miss = usage["prompt_cache_miss_tokens"]
    hit = usage["prompt_cache_hit_tokens"]
    output = usage["completion_tokens"]
    if any(type(value) is not int or value < 0 for value in (miss, hit, output)):
        raise ValueError("invalid token usage")
    if miss + hit != usage["prompt_tokens"] or miss + hit + output != usage["total_tokens"]:
        raise ValueError("provider token totals do not reconcile")
    return {"miss": miss, "hit": hit, "output": output,
            "input": miss + hit, "total": miss + hit + output}


def _sum(rows: list[dict]) -> dict:
    result = {key: sum(row[key] for row in rows) for key in ("miss", "hit", "output", "input", "total")}
    result["offpeak_usd_by_class"] = {
        key: round(result[key] * price / 1_000_000, 8)
        for key, price in OFFPEAK_USD_PER_MILLION.items()}
    result["offpeak_usd"] = round(sum(result["offpeak_usd_by_class"].values()), 8)
    result["requests"] = len(rows)
    return result


def analyze(manifest: dict, *, root: Path) -> dict:
    output = []
    for item in manifest["runs"]:
        ledger = (root / item["ledger"]).resolve(strict=True)
        requests = [_request(json.loads(line)) for line in ledger.read_text().splitlines() if line.strip()]
        stages = item["stages"]
        if sum(stage["requests"] for stage in stages) != len(requests):
            raise ValueError(f"{item['name']}: stage counts do not match ledger")
        offset = 0
        stage_rows = []
        for stage in stages:
            count = stage["requests"]
            stage_rows.append({"name": stage["name"], **_sum(requests[offset:offset + count])})
            offset += count
        output.append({"name": item["name"], "ledger": str(ledger),
                       "total": _sum(requests), "stages": stage_rows,
                       "requests": requests})
    return {"pricing": "DeepSeek Flash, 2026-09-27 off-peak USD estimate",
            "rates_per_million": OFFPEAK_USD_PER_MILLION, "runs": output}


def render(report: dict) -> str:
    lines = ["# 真实科研任务 token 与估算费用拆解", "",
             "依据 API usage 逐请求汇总；缓存命中仍计入总 token，但按独立低价计费。"
             "下面不能凭 usage 判定某段上下文是否可安全删除。", "",
             "| 路线／阶段 | 请求 | 未缓存输入 | 缓存命中输入 | 输出 | 总 token | 未缓存费 | 缓存费 | 输出费 | 合计费 |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for run in report["runs"]:
        for label, row in [(run["name"] + " 合计", run["total"])] + [
                (run["name"] + " " + stage["name"], stage) for stage in run["stages"]]:
            cost = row["offpeak_usd_by_class"]
            lines.append(f"| {label} | {row['requests']} | {row['miss']:,} | {row['hit']:,} | "
                         f"{row['output']:,} | {row['total']:,} | ${cost['miss']:.6f} | "
                         f"${cost['hit']:.6f} | ${cost['output']:.6f} | ${row['offpeak_usd']:.6f} |")
    lines.extend(["", "费用只是固定价格估算，不是实际账单；人工修订和本地计算另计。", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out-prefix", type=Path, required=True)
    args = parser.parse_args()
    manifest_path = args.manifest.resolve(strict=True)
    result = analyze(json.loads(manifest_path.read_text()), root=manifest_path.parent)
    args.out_prefix.parent.mkdir(parents=True, exist_ok=True)
    args.out_prefix.with_suffix(".json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    args.out_prefix.with_suffix(".md").write_text(render(result))
    print(args.out_prefix.with_suffix(".md"))


if __name__ == "__main__":
    main()
