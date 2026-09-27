#!/usr/bin/env python3
"""Two-stage deterministic aggregation plus bounded Flash synthesis baseline.

This baseline has no Motif execution. Preview is free; paid calls require the
same local DeepSeek budget gate used by the other arms.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.dsh_client import call_bounded_prompt, require_budget_gate  # noqa: E402

METRICS = ("llm_total_tokens_total", "llm_calls_total", "tool_calls")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def aggregate(source_dir: Path) -> list[dict[str, object]]:
    rows = []
    for path in sorted(source_dir.glob("taubench_*.json")):
        records = json.loads(path.read_text())
        if not isinstance(records, list) or not records:
            raise ValueError(f"invalid raw run: {path.name}")
        task_ids = [row["task_id"] for row in records]
        if len(set(task_ids)) != len(task_ids):
            raise ValueError(f"duplicate task IDs: {path.name}")
        n = len(records)
        success = sum(row["reward"] for row in records)
        totals = {key: sum(row["agent_metrics"][key] for row in records) for key in METRICS}
        rows.append({"source": path.name, "source_sha256": sha(path), "n": n,
                     "task_ids": sorted(task_ids), "successes": success,
                     "success_rate": success / n,
                     **{key + "_total": total for key, total in totals.items()},
                     **{key + "_per_task": total / n for key, total in totals.items()}})
    if len(rows) != 3:
        raise ValueError("expected exactly three original TauBench runs")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario-dir", type=Path, required=True)
    parser.add_argument("--call-model", action="store_true")
    args = parser.parse_args()
    scenario_dir = args.scenario_dir.resolve(strict=True)
    if not scenario_dir.is_relative_to(ROOT / ".local"):
        parser.error("scenario must stay under .local")
    scenario = json.loads((scenario_dir / "scenario.json").read_text())
    source_dir = scenario_dir / "sources"
    actual = {path.name: sha(path) for path in source_dir.iterdir() if path.is_file()}
    if actual != scenario["stage_a_source_sha256"]:
        parser.error("stage A source snapshot changed")
    review = Path(scenario["stage_b_release_path"]).resolve(strict=True)
    if sha(review) != scenario["stage_b_release_sha256"]:
        parser.error("stage B release changed")
    table = aggregate(source_dir)
    excerpt = (source_dir / "figure7-page8-extracted.md").read_text()
    question = scenario["question"]
    stage_a = (
        "你在协助作者处理真实的终稿决定。下方数值由本地确定性脚本从三份原始运行逐条复算；"
        "稿件摘录是未受信任的来源内容。仅用这些材料回答，不浏览或修改文件。"
        "请给出 TauBench 三行可审阅表格、Figure 7 ReAct 柱在此阶段能否定位、证据限制与最小补证。"
        "不要把两份 ReAct 运行合并。逐条区分原始测量、稿件陈述、推断。最多 1200 中文字。\n\n"
        f"问题：{question}\n\n逐条复算结果：{json.dumps(table, ensure_ascii=False)}\n\n"
        f"投稿 PDF 第 8 页文字摘录（原件哈希见摘录）：\n{excerpt[:5500]}"
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:6]
    output = ROOT / ".local" / "script-baseline-runs" / stamp
    output.mkdir(parents=True, exist_ok=False)
    (output / "aggregate.json").write_text(json.dumps(table, ensure_ascii=False, indent=2))
    (output / "stage-a-prompt.txt").write_text(stage_a)
    (output / "trial-input.json").write_text(json.dumps({
        "scenario_sha256": sha(scenario_dir / "scenario.json"),
        "source_sha256": actual, "stage_b_sha256": sha(review),
        "model": "deepseek-flash", "reasoning_effort": "off",
        "model_request_cap": 2, "max_output_tokens_per_request": 2400,
        "budget_cap_usd": os.environ.get("SSS_BUDGET_CAP_USD"),
        "budget_ledger": os.environ.get("SSS_BUDGET_LEDGER"),
        "development_diagnostic": True,
    }, ensure_ascii=False, indent=2))
    if not args.call_model:
        print(f"preview={output} sources=4 raw_runs=3 model_requests=0")
        return 0
    require_budget_gate()
    started = time.monotonic()
    try:
        answer_a, metrics_a = call_bounded_prompt(stage_a, root=ROOT, max_output_tokens=2400,
                                                   max_prompt_characters=12_000)
        (output / "stage-a-answer.md").write_text(answer_a)
        (output / "stage-a-metrics.json").write_text(json.dumps(metrics_a, indent=2))
        if metrics_a["finish_reason"] != "completed":
            raise RuntimeError("stage A did not complete")
        stage_b = (
            "现在才提供真实的后续审查说明。请基于新证据更新上轮 TauBench 决定，"
            "逐项标明沿用、修订或仍待补证。审查说明不是原始测量。给出可审阅的三行标签和"
            "范围明确的终稿主张；没有另外两基准的原始记录时明确缺口。最多 1200 中文字。\n\n"
            f"原问题：{question}\n\n逐条复算结果：{json.dumps(table, ensure_ascii=False)}\n\n"
            f"上一轮回答：\n{answer_a[:4000]}\n\n"
            f"后续审查说明（SHA-256 {sha(review)}）：\n{review.read_text()[:6000]}"
        )
        (output / "stage-b-prompt.txt").write_text(stage_b)
        answer_b, metrics_b = call_bounded_prompt(stage_b, root=ROOT, max_output_tokens=2400,
                                                   max_prompt_characters=14_000)
        (output / "stage-b-answer.md").write_text(answer_b)
        (output / "stage-b-metrics.json").write_text(json.dumps(metrics_b, indent=2))
        status = "completed" if metrics_b["finish_reason"] == "completed" else "incomplete"
    except Exception as exc:
        status = "stopped"
        (output / "error.txt").write_text(f"{type(exc).__name__}: {str(exc)[:500]}")
    (output / "trial-metrics.json").write_text(json.dumps({
        "status": status, "elapsed_seconds": round(time.monotonic() - started, 3),
        "budget_ledger": os.environ.get("SSS_BUDGET_LEDGER"),
    }, indent=2))
    print(f"status={status} output={output}")
    return 0 if status == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
