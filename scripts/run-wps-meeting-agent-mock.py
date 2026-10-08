#!/usr/bin/env python3
"""Preview or run one bounded DeepSeek agent trial on the synthetic meeting task.

The free preview freezes inputs. A paid run additionally requires an approval
record matching that preview and the local provider cost gate. This is one
native Agent development trial, not an SSS effectiveness comparison.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.dsh_client import _usage, require_budget_gate  # noqa: E402
from src.adapters.native_budget import NativeBudgetExceeded, NativeBudgetGuard  # noqa: E402


TASK = ROOT / "benchmarks/wps_meeting_mock_v1/agent_task.md"
APP_SOURCES = ROOT / "benchmarks/wps_meeting_mock_v1/mock_app_sources.json"
BOOK = ROOT / "outputs/wps-meeting-mock-v1/experiment_log.xlsx"
SERVER = ROOT / "benchmarks/wps_meeting_mock_v1/mock_apps_server.py"
PATCH = ROOT / "config/wps-meeting-agent-mock.patch.yml"
CONTRACTS = ROOT / "config/wps-meeting-mock-contracts.json"
NUMBERS = ROOT / "benchmarks/wps_meeting_mock_v1/run_mock.py"
REVIEW = ROOT / "benchmarks/wps_meeting_mock_v1/agent_review.md"
OUT = ROOT / ".local/benchmarks/wps-meeting-agent-mock-v1/native-03"
BUDGET_USD = 1.0
MAX_REQUESTS = 10


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def private_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def preview() -> dict:
    sources = {str(path.relative_to(ROOT)): digest(path)
               for path in (TASK, APP_SOURCES, BOOK, SERVER, PATCH, CONTRACTS,
                            NUMBERS, REVIEW, Path(__file__).resolve())}
    return {
        "task": "synthetic_wps_meeting_agent_v1",
        "classification": "synthetic_development_trial_not_motif_effectiveness",
        "model": "deepseek-flash",
        "reasoning_effort": "off",
        "budget_cap_usd": BUDGET_USD,
        "max_model_requests": MAX_REQUESTS,
        "max_output_tokens_per_request": 3500,
        "max_observed_input_tokens": 250_000,
        "tools": "four read-only synthetic_meeting_apps MCP tools",
        "report": "Agent Markdown rendered by Quarto with --no-execute",
        "input_sha256": sources,
        "output_dir": str(OUT),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--call-model", action="store_true")
    args = parser.parse_args()
    current = preview()
    saved = OUT / "PREVIEW.json"
    approval = OUT / "APPROVAL.json"
    print(json.dumps({**current, "paid_api_requested": args.call_model}, ensure_ascii=False), flush=True)
    if not args.call_model:
        if approval.exists() and (not saved.exists()
                                  or json.loads(saved.read_text(encoding="utf-8")) != current):
            parser.error("approved preview changed")
        private_json(saved, current)
        return 0

    if not saved.is_file() or json.loads(saved.read_text(encoding="utf-8")) != current:
        parser.error("frozen preview is missing or changed")
    if not approval.is_file():
        parser.error("explicit approval for the frozen paid preview is missing")
    record = json.loads(approval.read_text(encoding="utf-8"))
    if record != {"approved": True, "preview_sha256": digest(saved)}:
        parser.error("approval does not match the frozen preview")
    require_budget_gate()
    if float(os.environ["SSS_BUDGET_CAP_USD"]) > BUDGET_USD:
        parser.error("provider cost gate exceeds the approved cap")
    marker = OUT / "paid-attempt.marker"
    with marker.open("x", encoding="utf-8") as stream:
        stream.write(datetime.now(timezone.utc).isoformat() + "\n")
    marker.chmod(0o600)

    os.environ.update({"SSS_MCP_PYTHON": str(ROOT / ".venv312/bin/python"),
                       "SSS_PROJECT_ROOT": str(ROOT),
                       "DSH_PERMISSION_MODE": "read-only"})
    from deepseek_harness import DeepSeekHarness

    guard = NativeBudgetGuard(max_model_requests=MAX_REQUESTS,
                              max_observed_input_tokens=250_000)
    events = OUT / "agent-events.jsonl"
    session_id = "sss-wps-meeting-mock-" + uuid4().hex

    def observe(notification) -> None:
        if getattr(notification, "method", None) != "session.event":
            return
        event = getattr(notification, "payload", {}).get("event")
        if isinstance(event, dict):
            with events.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            events.chmod(0o600)
        guard.on_notification(notification)

    started = time.monotonic()
    try:
        with DeepSeekHarness(
            provider="deepseek-official", model="deepseek-flash",
            reasoning_effort="off", max_tokens=3500,
            cwd=str(OUT), runtime_cwd=str(OUT),
            dsh_bin=str(ROOT / "node_modules/.bin/dsh"), profile="sdk",
            patches=(str(PATCH),), dsh_home=str(ROOT / ".local/dsh"),
            request_timeout_seconds=900,
        ) as harness:
            result = harness.run(TASK.read_text(encoding="utf-8"),
                                 session_id=session_id, on_notification=observe)
        answer = result.final_response.strip()
        status = "done" if answer and result.finish_reason == "completed" else "incomplete"
        if answer:
            raw = OUT / "agent-answer.md"
            raw.write_text(answer + "\n", encoding="utf-8")
            raw.chmod(0o600)
            qmd = OUT / "agent-answer.qmd"
            qmd.write_text('---\ntitle: "合成组会 Agent 草稿"\nformat: html\n---\n\n'
                           + answer + "\n", encoding="utf-8")
            qmd.chmod(0o600)
            subprocess.run(["quarto", "render", str(qmd), "--to", "html",
                            "--no-execute"], check=True, capture_output=True, text=True)
    except Exception as exc:
        status = "budget_stopped" if isinstance(exc, NativeBudgetExceeded) else "error"
        result = None
        answer = ""
        error = {"error_type": type(exc).__name__, "error": str(exc)[:300]}
    else:
        error = {}
    report = {"status": status, "session_id": session_id,
              "finish_reason": result.finish_reason if result else None,
              "answer_characters": len(answer),
              "elapsed_seconds": round(time.monotonic() - started, 3),
              "started_requests": guard.started_requests,
              **_usage(guard.events), **error}
    private_json(OUT / "metrics.json", report)
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0 if status == "done" else 2


if __name__ == "__main__":
    raise SystemExit(main())
