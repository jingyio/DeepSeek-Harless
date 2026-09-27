#!/usr/bin/env python3
"""Reconcile the frozen v3 paired ledgers, model turns, and Motif audit."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = ("site_transfer", "tail_terms", "lot_stability")


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def summarize_run(path: Path, arm: str) -> dict:
    metrics = json.loads((path / "agent-metrics.json").read_text(encoding="utf-8"))
    if metrics["status"] != "done" or metrics["finish_reason"] != "completed":
        raise ValueError(f"{path}: answer is not complete")
    ledger = load_jsonl(path / "budget.jsonl")
    if not ledger or any(row.get("response_status") != 200 for row in ledger):
        raise ValueError(f"{path}: ledger has unsuccessful or missing requests")
    events = load_jsonl(path / "agent-events.jsonl")
    turns = [event["data"] for event in events
             if event.get("type") == "assistant/message"
             and isinstance(event.get("data", {}).get("usage"), dict)]
    if len(turns) != len(ledger) or len(ledger) != metrics["model_requests"]:
        raise ValueError(f"{path}: model turns and paid API requests differ")
    if sum(turn["usage"]["outputTokens"] for turn in turns) != metrics["outputTokens"]:
        raise ValueError(f"{path}: output usage differs from event trace")
    if sum(turn["usage"]["reasoningTokens"] for turn in turns) != metrics["reasoningTokens"]:
        raise ValueError(f"{path}: reasoning usage differs from event trace")
    final = turns[-1]["message"]["content"]
    if any(block.get("type") == "tool-call" for block in final):
        raise ValueError(f"{path}: final paid request is not the delivery turn")
    calls = {event["data"]["callId"]: event["data"]["name"] for event in events
             if event.get("type") == "tool/call"}
    failed_tools = []
    for event in events:
        if event.get("type") != "tool/result":
            continue
        for block in event["data"].get("message", {}).get("content", []):
            if block.get("isError"):
                failed_tools.append(calls.get(block.get("toolCallId"), "unknown"))
    usage = [row["response_usage"] for row in ledger]
    if any(not isinstance(row, dict) for row in usage):
        raise ValueError(f"{path}: provider usage is missing")
    result = {
        "status": metrics["status"],
        "requests": len(ledger),
        "verified_skips": 0,
        "tool_calls": len(calls),
        "failed_tools": failed_tools,
        "elapsed_seconds": metrics["elapsed_seconds"],
        "api_seconds": round(sum(row["elapsed_seconds"] for row in ledger), 3),
        "estimated_usd": round(sum(row["observed_peak_usd"] for row in ledger), 8),
        "pre_final_usd": round(sum(row["observed_peak_usd"] for row in ledger[:-1]), 8),
        "final_usd": ledger[-1]["observed_peak_usd"],
        "cache_miss_input_tokens": sum(row["prompt_cache_miss_tokens"] for row in usage),
        "cache_hit_input_tokens": sum(row["prompt_cache_hit_tokens"] for row in usage),
        "output_tokens": metrics["outputTokens"],
        "reasoning_tokens": metrics["reasoningTokens"],
        "pre_final_reasoning_tokens": sum(
            turn["usage"]["reasoningTokens"] for turn in turns[:-1]),
        "final_reasoning_tokens": turns[-1]["usage"]["reasoningTokens"],
        "pre_final_output_tokens": sum(
            turn["usage"]["outputTokens"] for turn in turns[:-1]),
        "final_output_tokens": turns[-1]["usage"]["outputTokens"],
        "final_api_seconds": ledger[-1]["elapsed_seconds"],
    }
    if arm == "motif":
        task = json.loads((path / "online-task.json").read_text(encoding="utf-8"))
        audit = (path / ".local/online-motif"
                 / (hashlib.sha256(task["session_id"].encode()).hexdigest() + ".jsonl"))
        audit_rows = load_jsonl(audit)
        kinds = [row.get("kind") for row in audit_rows]
        result["verified_skips"] = kinds.count("model_request_skipped_verified")
        result["bypass_attempts"] = kinds.count("motif_bypass_attempt")
        result["unverified_bypasses"] = kinds.count("bypass_result_unverified")
        if (result["verified_skips"] != result["bypass_attempts"]
                or result["unverified_bypasses"]):
            raise ValueError(f"{path}: Motif bypass was not fully verified")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path,
                        default=ROOT / ".local/benchmarks/meeting-decision-chain-v3")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    base = args.root.resolve(strict=True)
    if not base.is_relative_to((ROOT / ".local").resolve()):
        parser.error("raw trial data must stay under .local")
    report = {case: {arm: summarize_run(base / case / arm, arm)
                     for arm in ("baseline", "motif")} for case in CASES}
    output = (args.output or base / "ANALYSIS.json").resolve()
    if not output.is_relative_to((ROOT / ".local").resolve()):
        parser.error("analysis output must stay under .local")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    output.chmod(0o600)
    print(json.dumps({case: {
        arm: {key: run[key] for key in ("requests", "verified_skips", "estimated_usd",
                                          "elapsed_seconds", "final_reasoning_tokens")}
        for arm, run in arms.items()} for case, arms in report.items()},
        ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
