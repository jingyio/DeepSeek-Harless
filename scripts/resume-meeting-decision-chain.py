#!/usr/bin/env python3
"""Continue one truncated meeting-decision Harness session within its original cap."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.dsh_client import _usage, require_budget_gate  # noqa: E402
from src.adapters.native_budget import NativeBudgetGuard  # noqa: E402


BASE = ROOT / ".local/benchmarks/meeting-decision-chain-v1"
PATCH = ROOT / "config/meeting-decision-chain.patch.yml"
PROMPT = ("请继续同一会话中的合成组会研究决定。若上一轮尚未交付正文，"
          "现在直接写出完整的一页中文待审决定；若已有正文但被截断，就补完结尾。"
          "保留已核验数字与来源，避免重复调查，不改写应用资料。")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def private(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    path.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=("family_shift", "label_audit",
                                          "hardware_latency", "novel_queries"), required=True)
    parser.add_argument("--call-model", action="store_true")
    args = parser.parse_args()
    original = BASE / args.case / "baseline"
    out = original / "continuation-01"
    metrics_path = original / "agent-metrics.json"
    ledger = original / "budget.jsonl"
    if not metrics_path.is_file() or not ledger.is_file():
        parser.error("original paid run and budget ledger are required")
    first = json.loads(metrics_path.read_text(encoding="utf-8"))
    if first.get("status") != "incomplete" or first.get("finish_reason") != "max-tokens":
        parser.error("only a max-tokens incomplete run may be continued")
    session_id = first.get("session_id")
    session_file = (ROOT / ".local/dsh/storages/session_projcache/sessions"
                    / f"{session_id}.json")
    if not session_file.is_file():
        parser.error("original DSH session is unavailable")
    spent = sum(float(json.loads(line).get("observed_peak_usd") or 0)
                for line in ledger.read_text(encoding="utf-8").splitlines())
    current = {"case": args.case, "run_kind": "same_session_continuation",
               "session_id": session_id, "original_metrics_sha256": sha(metrics_path),
               "original_ledger_sha256": sha(ledger),
               "continuation_runner_sha256": sha(Path(__file__).resolve()),
               "source_task_sha256": sha(ROOT / "benchmarks/meeting_decision_chain_v1/tasks"
                                           / f"{args.case}.md"),
               "mcp_patch_sha256": sha(PATCH),
               "original_spent_estimate_usd": round(spent, 8),
               "original_total_cap_usd": 1.0, "continuation_cap_usd": 0.5,
               "max_model_requests": 3, "prompt": PROMPT}
    saved, approval = out / "PREVIEW.json", out / "APPROVAL.json"
    print(json.dumps({**current, "paid_api_requested": args.call_model},
                     ensure_ascii=False), flush=True)
    if not args.call_model:
        private(saved, current)
        return 0
    if not saved.is_file() or json.loads(saved.read_text(encoding="utf-8")) != current:
        parser.error("continuation preview changed")
    if not approval.is_file():
        parser.error("continuation needs the existing trial authorization")
    record = json.loads(approval.read_text(encoding="utf-8"))
    if (record.get("approved") is not True or
        record.get("preview_sha256") != sha(saved) or
        record.get("authorization_basis") != "可以运行真实试验"):
        parser.error("continuation authorization differs from preview")
    require_budget_gate()
    gate = float(os.environ["SSS_BUDGET_CAP_USD"])
    if gate > 0.5 or spent + gate > 1.0:
        parser.error("continuation would exceed the original US$1 cap")
    marker = out / "paid-attempt.marker"
    with marker.open("x", encoding="utf-8") as stream:
        stream.write("one same-session continuation reserved\n")
    marker.chmod(0o600)
    os.environ.update({"SSS_MCP_PYTHON": str(ROOT / ".venv312/bin/python"),
                       "SSS_PROJECT_ROOT": str(ROOT),
                       "SSS_MEETING_CASE": args.case,
                       "DSH_PERMISSION_MODE": "read-only"})
    guard = NativeBudgetGuard(max_model_requests=3,
                              max_observed_input_tokens=150_000)
    events_file = out / "agent-events.jsonl"

    def observe(notification) -> None:
        if getattr(notification, "method", None) != "session.event":
            return
        event = getattr(notification, "payload", {}).get("event")
        if isinstance(event, dict):
            with events_file.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            events_file.chmod(0o600)
        guard.on_notification(notification)

    started = time.monotonic()
    try:
        from deepseek_harness import DeepSeekHarness

        with DeepSeekHarness(
            provider="deepseek-official", model="deepseek-flash",
            reasoning_effort="off", max_tokens=8000,
            cwd=str(out), runtime_cwd=str(out),
            dsh_bin=str(ROOT / "node_modules/.bin/dsh"),
            profile="sss-native-resume-sdk", patches=(str(PATCH),),
            dsh_home=str(ROOT / ".local/dsh"), request_timeout_seconds=600,
        ) as harness:
            result = harness.run(PROMPT, session_id=session_id,
                                 on_notification=observe)
        answer = result.final_response.strip()
        if answer:
            target = out / "agent-answer.md"
            target.write_text(answer + "\n", encoding="utf-8")
            target.chmod(0o600)
        report = {"status": "done" if answer and result.finish_reason == "completed"
                  else "incomplete", "finish_reason": result.finish_reason,
                  "answer_characters": len(answer)}
    except Exception as exc:
        report = {"status": "error", "error_type": type(exc).__name__,
                  "error": str(exc)[:300]}
    report.update({"case": args.case, "run_kind": "same_session_continuation",
                   "session_id": session_id,
                   "elapsed_seconds": round(time.monotonic() - started, 3),
                   "started_requests": guard.started_requests,
                   "budget_ledger": os.environ.get("SSS_BUDGET_LEDGER"),
                   **_usage(guard.events)})
    private(out / "agent-metrics.json", report)
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "done" else 2


if __name__ == "__main__":
    raise SystemExit(main())
