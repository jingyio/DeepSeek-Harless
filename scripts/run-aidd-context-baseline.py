#!/usr/bin/env python3
"""Preview or run a separately approved early-compaction AIDD baseline."""

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
from src.adapters.native_budget import NativeBudgetExceeded, NativeBudgetGuard  # noqa: E402

BASE = ROOT / ".local/benchmarks/research-weekly-loop/aidd-next-preflight"
SCOPE = BASE / "baseline-scope-approved.json"
APPROVAL = BASE / "context-baseline-approval.json"
OUT = BASE / "paid-context-baseline-01"
PROMPT = ROOT / "benchmarks/research_weekly_loop_v1/aidd_baseline_prompt.md"
SCOPE_PATCH = ROOT / "config/aidd-scoped-baseline.patch.yml"
CONTEXT_PATCH = ROOT / "config/aidd-early-compaction.patch.yml"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preview() -> dict:
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location("aidd_original", ROOT / "scripts/run-aidd-initial-pilot.py")
    assert spec and spec.loader
    original = module_from_spec(spec)
    spec.loader.exec_module(original)
    original._check_scope(paid=True)
    return {"task": "AIDD ordinary Harness with early context compaction",
            "model": "deepseek-flash", "reasoning_effort": "off",
            "max_agent_requests": 30,
            "compaction_requests": "additional, counted in proxy spending ledger",
            "max_output_tokens_per_request": 8000,
            "budget_cap_usd": 2.0,
            "compaction_threshold_ratio": 0.05, "retain_tokens": 12000,
            "scope_sha256": digest(SCOPE), "prompt_sha256": digest(PROMPT),
            "scope_patch_sha256": digest(SCOPE_PATCH),
            "context_patch_sha256": digest(CONTEXT_PATCH),
            "output": str(OUT)}


def save(name: str, value: str) -> None:
    path = OUT / name
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--call-model", action="store_true")
    args = parser.parse_args()
    details = preview()
    print(json.dumps({**details, "call_model_requested": args.call_model,
                      "status": "approval_check" if args.call_model else "preview_only"},
                     ensure_ascii=False), flush=True)
    if not args.call_model:
        return 0
    if not APPROVAL.is_file():
        parser.error("separate context-baseline approval record is missing")
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    expected = {key: details[key] for key in
                ("scope_sha256", "prompt_sha256", "scope_patch_sha256",
                 "context_patch_sha256", "model", "max_agent_requests",
                 "budget_cap_usd", "output")}
    if approval.get("approved") is not True or any(approval.get(k) != v for k, v in expected.items()):
        parser.error("approval does not match this exact preview")
    require_budget_gate()
    if float(os.environ["SSS_BUDGET_CAP_USD"]) > 2.0:
        parser.error("cost gate exceeds the approved US$2 cap")

    from deepseek_harness import DeepSeekHarness

    OUT.mkdir(parents=True, exist_ok=True)
    OUT.chmod(0o700)
    if (OUT / "agent-events.jsonl").exists() or (OUT / "agent-answer.md").exists():
        parser.error("context baseline output already exists")
    fd = os.open(OUT / "paid-attempt.marker", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write("separately approved paid attempt\n")
    session_id = "sss-aidd-context-" + uuid4().hex
    save("session-id.txt", session_id + "\n")
    save("agent-prompt.txt", PROMPT.read_text(encoding="utf-8"))
    guard = NativeBudgetGuard(max_model_requests=30, max_observed_input_tokens=2_000_000)
    os.environ.update({"SSS_MCP_PYTHON": str(ROOT / ".venv312/bin/python"),
                       "SSS_PROJECT_ROOT": str(ROOT),
                       "SSS_RESEARCH_SCOPE_FILE": str(SCOPE)})
    started = time.monotonic()

    def observe(notification):
        if getattr(notification, "method", None) != "session.event":
            return
        event = getattr(notification, "payload", {}).get("event")
        if isinstance(event, dict):
            with (OUT / "agent-events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            (OUT / "agent-events.jsonl").chmod(0o600)
        guard.on_notification(notification)

    try:
        with DeepSeekHarness(
            provider="deepseek-official", model="deepseek-flash", reasoning_effort="off",
            max_tokens=8000, cwd=str(OUT), runtime_cwd=str(OUT),
            dsh_bin=str(ROOT / "node_modules/.bin/dsh"), profile="sdk",
            patches=(str(SCOPE_PATCH), str(CONTEXT_PATCH)),
            dsh_home=str(ROOT / ".local/dsh"), request_timeout_seconds=900,
        ) as harness:
            result = harness.run(PROMPT.read_text(encoding="utf-8"),
                                 session_id=session_id, on_notification=observe)
        save("agent-answer.md", result.final_response)
        metrics = {"status": "done" if result.finish_reason == "completed"
                   and result.final_response.strip() else "incomplete",
                   "finish_reason": result.finish_reason, "session_id": session_id,
                   "elapsed_seconds": round(time.monotonic() - started, 3),
                   "started_agent_requests": guard.started_requests,
                   "compaction_summaries": sum(
                       event.get("type") == "compaction/summary" for event in guard.events),
                   **_usage(guard.events)}
    except Exception as exc:
        metrics = {"status": "budget_stopped" if isinstance(exc, NativeBudgetExceeded) else "error",
                   "error_type": type(exc).__name__, "error": str(exc)[:300],
                   "session_id": session_id,
                   "elapsed_seconds": round(time.monotonic() - started, 3),
                   "started_agent_requests": guard.started_requests,
                   "compaction_summaries": sum(
                       event.get("type") == "compaction/summary" for event in guard.events),
                   **_usage(guard.events)}
    save("agent-metrics.json", json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: metrics[key] for key in
                      ("status", "finish_reason", "started_agent_requests",
                       "compaction_summaries", "elapsed_seconds") if key in metrics},
                     ensure_ascii=False), flush=True)
    return 0 if metrics["status"] == "done" else 2


if __name__ == "__main__":
    raise SystemExit(main())
