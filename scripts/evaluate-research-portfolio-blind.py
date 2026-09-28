#!/usr/bin/env python3
"""Budgeted arm-blind Pro review of one synthetic portfolio answer pair."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.dsh_client import _usage, require_budget_gate  # noqa: E402
from src.adapters.native_budget import NativeBudgetGuard  # noqa: E402

PRIVATE = (ROOT / ".local").resolve()
PATCH = ROOT / "config/meeting-script-dossier.patch.yml"
MODEL = "deepseek-v4-pro"
CAP_USD = 0.5
MAX_OUTPUT_TOKENS = 6000


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def private(path: Path, value: dict | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    content = (json.dumps(value, ensure_ascii=False, indent=2) + "\n"
               if isinstance(value, dict) else value)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)


def prompt_for(packet: Path, source_file: Path) -> str:
    evidence = {
        "task": (packet / "task.md").read_text(encoding="utf-8"),
        "source_objects": json.loads(source_file.read_text(encoding="utf-8")),
        "rubric": json.loads((packet / "rubric.json").read_text(encoding="utf-8")),
        "answer_A": (packet / "answer-A.md").read_text(encoding="utf-8"),
        "answer_B": (packet / "answer-B.md").read_text(encoding="utf-8"),
    }
    return (
        "你是科研决定材料的匿名评审。A/B 是随机代号；不要猜测系统身份，也不要比较文风。"
        "只依据下面的任务、完整来源和冻结 rubric，分别审核两份回答。"
        "核对 rubric.must 的每项是否被正确覆盖，rubric.fatal 是否发生，所有关键数字、"
        "版本关系和科学推断是否受来源支持。回答中额外的实质性事实错误也要指出。"
        "严格合格：全部 must 正确覆盖、无 fatal、无影响决定的事实或因果错误。"
        "小幅降质可用：最多一项 must 只有轻微缺口，且无影响决定的事实、来源或数字错误。"
        "缺口不能靠另一个回答补齐。若证据不清，判待核实，不推定通过。"
        "只输出 JSON 对象，不输出 Markdown 或前言。格式为"
        '{"A":{"must":[{"criterion":"原文","met":true,"evidence":"简述"}],'
        '"fatal_errors":[],"other_material_errors":[],"strict_pass":true,'
        '"practical_pass":true,"reason":"简述"},"B":{同样字段}}。'
        "must 数组要逐项对应 rubric.must，错误说明应引用来源或回答中的具体短句。\n\n"
        + json.dumps(evidence, ensure_ascii=False, sort_keys=True)
    )


def parse_verdict(raw: str, must_count: int) -> dict:
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("judge returned no JSON object")
    result = json.loads(raw[start:end + 1])
    if set(result) != {"A", "B"}:
        raise ValueError("judge did not score both blinded answers")
    for label in ("A", "B"):
        row = result[label]
        if (not isinstance(row, dict) or
                not isinstance(row.get("must"), list) or
                len(row["must"]) != must_count or
                not all(isinstance(item, dict) and
                        isinstance(item.get("criterion"), str) and
                        isinstance(item.get("met"), bool) and
                        isinstance(item.get("evidence"), str)
                        for item in row["must"]) or
                not isinstance(row.get("fatal_errors"), list) or
                not isinstance(row.get("other_material_errors"), list) or
                not isinstance(row.get("strict_pass"), bool) or
                not isinstance(row.get("practical_pass"), bool)):
            raise ValueError(f"judge verdict for {label} is incomplete")
        if row["strict_pass"] and (not all(item["met"] for item in row["must"])
                                   or row["fatal_errors"] or
                                   row["other_material_errors"]):
            raise ValueError("judge strict pass conflicts with its own findings")
        if row["practical_pass"] and (row["fatal_errors"] or
                                      row["other_material_errors"]):
            raise ValueError("judge practical pass conflicts with material errors")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", choices=("v1", "v2"), required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--call-model", action="store_true")
    args = parser.parse_args()
    packet = ROOT / f".local/benchmarks/research-portfolio-blind-{args.benchmark}" / args.case
    source_file = (ROOT / f"benchmarks/research_decision_portfolio_{args.benchmark}"
                   / "cases" / args.case / "sources.json")
    output_root = args.output_root.resolve()
    if not output_root.is_relative_to(PRIVATE):
        parser.error("review output must stay under .local")
    if not all(path.is_file() for path in (packet / "task.md", packet / "rubric.json",
                                            packet / "answer-A.md", packet / "answer-B.md",
                                            source_file)):
        parser.error("frozen blinded packet or source is incomplete")
    out = output_root / args.benchmark / args.case
    files = [packet / name for name in ("task.md", "rubric.json", "answer-A.md",
                                        "answer-B.md")] + [source_file, PATCH,
                                                            Path(__file__).resolve()]
    preview = {"benchmark": args.benchmark, "case": args.case,
               "judge_model": MODEL, "reasoning_effort": "off",
               "max_model_requests": 1, "budget_cap_usd": CAP_USD,
               "max_output_tokens": MAX_OUTPUT_TOKENS,
               "blinded": True, "source_file_access": "synthetic_case_only",
               "output_dir": str(out),
               "input_sha256": {str(path.relative_to(ROOT)): sha(path)
                                for path in files}}
    saved, approval = out / "PREVIEW.json", out / "APPROVAL.json"
    if not args.call_model:
        private(saved, preview)
        print(json.dumps({"preview": str(saved), "case": args.case,
                          "benchmark": args.benchmark, "budget_cap_usd": CAP_USD}))
        return 0
    if not saved.is_file() or json.loads(saved.read_text()) != preview:
        parser.error("frozen judge preview missing or changed")
    if not approval.is_file():
        parser.error("judge authorization record missing")
    record = json.loads(approval.read_text())
    if (record.get("approved") is not True or
            record.get("preview_sha256") != sha(saved) or
            record.get("budget_cap_usd") != CAP_USD or
            record.get("authorization_basis") != "开始评测吧"):
        parser.error("judge authorization does not match preview")
    require_budget_gate()
    if float(os.environ["SSS_BUDGET_CAP_USD"]) > CAP_USD:
        parser.error("cost gate exceeds judge cap")
    prompt = prompt_for(packet, source_file)
    if len(prompt) > 100_000:
        parser.error("judge prompt exceeds frozen maximum")
    marker = out / "paid-attempt.marker"
    with marker.open("x", encoding="utf-8") as stream:
        stream.write("one authorized blinded judge request reserved\n")
    marker.chmod(0o600)
    guard = NativeBudgetGuard(max_model_requests=1,
                              max_observed_input_tokens=100_000)

    def observe(notification) -> None:
        guard.on_notification(notification)

    from deepseek_harness import DeepSeekHarness
    started = time.monotonic()
    try:
        with DeepSeekHarness(provider="deepseek-official", model=MODEL,
                             reasoning_effort="off", max_tokens=MAX_OUTPUT_TOKENS,
                             cwd=str(out), runtime_cwd=str(out),
                             dsh_bin=str(ROOT / "node_modules/.bin/dsh"), profile="sdk",
                             patches=(str(PATCH),), dsh_home=str(ROOT / ".local/dsh"),
                             request_timeout_seconds=600) as harness:
            result = harness.run(prompt,
                                 session_id=f"sss-blind-review-{args.case}-{uuid4().hex}",
                                 on_notification=observe)
        raw = result.final_response.strip()
        private(out / "judge-raw.txt", raw + "\n")
        must_count = len(json.loads((packet / "rubric.json").read_text())["must"])
        verdict = parse_verdict(raw, must_count)
        private(out / "judge-verdict.json", verdict)
        status = "done" if result.finish_reason == "completed" else "incomplete"
    except Exception as exc:
        status = "error"
        error = {"type": type(exc).__name__, "message": str(exc)[:300]}
    metrics = {"status": status, "benchmark": args.benchmark, "case": args.case,
               "model": MODEL, "reasoning_effort": "off",
               "elapsed_seconds": round(time.monotonic() - started, 3),
               "started_requests": guard.started_requests,
               "budget_ledger": os.environ.get("SSS_BUDGET_LEDGER"),
               **_usage(guard.events)}
    if status == "error":
        metrics["error"] = error
    private(out / "judge-metrics.json", metrics)
    print(json.dumps(metrics, ensure_ascii=False), flush=True)
    return 0 if status == "done" else 2


if __name__ == "__main__":
    raise SystemExit(main())
