#!/usr/bin/env python3
"""Run one budgeted Model RSI decision with version-bound application reads.

This is a restricted MCP trace-collection condition, not a free-tool baseline.
The previously approved source scope is reused unchanged; no app writes occur.
"""

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

BASE = ROOT / ".local/benchmarks/research-weekly-loop/model-rsi-first-pilot"
SCOPE = BASE / "scope-preview.json"
LOCK = BASE / "approved-scope.lock.json"
OUT = ROOT / ".local/benchmarks/research-weekly-loop/model-rsi-handle-cost-only-20260927"
PATCH = ROOT / "config/model-rsi-handle-pilot.patch.yml"
PROMPT = ROOT / "benchmarks/research_weekly_loop_v1/model_rsi_handle_pilot_prompt.md"
MAX_USD = 2.0
MAX_REQUESTS = None  # The provider cost gate is the sole stopping budget.


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preview() -> dict:
    scope = json.loads(SCOPE.read_text(encoding="utf-8"))
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    if (scope.get("status") != "approved_for_model"
            or lock.get("scope_sha256") != digest(SCOPE)
            or lock.get("task") != "model-rsi-first-pilot"):
        raise ValueError("Model RSI source scope is not the previously approved snapshot")
    rows = scope.get("sources")
    if not isinstance(rows, list) or len(rows) != 4:
        raise ValueError("Expected four scoped sources")
    for row in rows:
        path = Path(row["path"]).resolve(strict=True)
        if (row.get("external_model_excerpt_allowed") is not True
                or digest(path) != row.get("sha256")
                or lock["source_versions"].get(row["role"]) != row["sha256"]):
            raise ValueError(f"Source approval or version changed: {row['role']}")
    return {"task": "Model RSI internal capability-state decision",
            "condition": "restricted_scoped_mcp_trace_collection",
            "model": "deepseek-flash", "thinking": "off",
            "source_roles": [row["role"] for row in rows],
            "scope_sha256": digest(SCOPE), "prompt_sha256": digest(PROMPT),
            "patch_sha256": digest(PATCH), "max_requests": MAX_REQUESTS,
            "max_output_tokens_per_request": 8000, "max_usd": MAX_USD,
            "request_limit": "none; provider cost gate only",
            "application_writes": False, "output_dir": str(OUT)}


def save(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--call-model", action="store_true")
    args = parser.parse_args()
    details = preview()
    print(json.dumps({**details, "paid_requested": args.call_model}, ensure_ascii=False), flush=True)
    if not args.call_model:
        return 0
    require_budget_gate()
    if float(os.environ["SSS_BUDGET_CAP_USD"]) > MAX_USD:
        parser.error("cost gate exceeds this pilot's US$2 cap")
    if OUT.exists():
        parser.error("pilot output exists; never overwrite an existing paid attempt")
    OUT.mkdir(parents=True, mode=0o700)
    save(OUT / "PREVIEW.json", json.dumps(details, ensure_ascii=False, indent=2) + "\n")
    save(OUT / "paid-attempt.marker", "one new paid Model RSI intake attempt\n")
    prompt = PROMPT.read_text(encoding="utf-8")
    save(OUT / "agent-prompt.txt", prompt)
    session_id = "sss-model-rsi-handle-" + uuid4().hex
    save(OUT / "session-id.txt", session_id + "\n")
    os.environ.update({"SSS_MCP_PYTHON": str(ROOT / ".venv312/bin/python"),
                       "SSS_PROJECT_ROOT": str(ROOT),
                       "SSS_RESEARCH_SCOPE_FILE": str(SCOPE)})
    guard = NativeBudgetGuard(max_model_requests=MAX_REQUESTS,
                              max_observed_input_tokens=None)
    started = time.monotonic()
    events_path = OUT / "agent-events.jsonl"

    def observe(notification) -> None:
        if getattr(notification, "method", None) != "session.event":
            return
        event = getattr(notification, "payload", {}).get("event")
        if isinstance(event, dict):
            with events_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            events_path.chmod(0o600)
        guard.on_notification(notification)

    try:
        from deepseek_harness import DeepSeekHarness

        with DeepSeekHarness(
            provider="deepseek-official", model="deepseek-flash", reasoning_effort="off",
            max_tokens=8000, cwd=str(OUT), runtime_cwd=str(OUT),
            dsh_bin=str(ROOT / "node_modules/.bin/dsh"), profile="sdk",
            patches=(str(PATCH),), dsh_home=str(ROOT / ".local/dsh"),
            request_timeout_seconds=900,
        ) as harness:
            result = harness.run(prompt, session_id=session_id, on_notification=observe)
        save(OUT / "agent-answer.md", result.final_response)
        metrics = {"status": "done" if result.finish_reason == "completed"
                   and result.final_response.strip() else "incomplete",
                   "finish_reason": result.finish_reason,
                   "elapsed_seconds": round(time.monotonic() - started, 3),
                   "started_requests": guard.started_requests,
                   **_usage(guard.events)}
    except Exception as exc:
        metrics = {"status": "budget_stopped" if isinstance(exc, NativeBudgetExceeded) else "error",
                   "error_type": type(exc).__name__, "error": str(exc)[:300],
                   "elapsed_seconds": round(time.monotonic() - started, 3),
                   "started_requests": guard.started_requests,
                   **_usage(guard.events)}
    save(OUT / "agent-metrics.json", json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(metrics, ensure_ascii=False), flush=True)
    return 0 if metrics["status"] == "done" else 2


if __name__ == "__main__":
    raise SystemExit(main())
