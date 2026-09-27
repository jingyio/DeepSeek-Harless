#!/usr/bin/env python3
"""Preview or run the approved, scoped AIDD baseline with a local cost gate."""

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
from src.mcp.scoped_zotero_read_server import _verified as verify_zotero  # noqa: E402

BASE = ROOT / ".local/benchmarks/research-weekly-loop/aidd-next-preflight"
REVIEW_SCOPE = BASE / "baseline-scope-review.json"
APPROVED_SCOPE = BASE / "baseline-scope-approved.json"
APPROVAL = BASE / "baseline-approval.json"
PATCH = ROOT / "config/aidd-scoped-baseline.patch.yml"
PROMPT_FILE = ROOT / "benchmarks/research_weekly_loop_v1/aidd_baseline_prompt.md"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_scope(*, paid: bool) -> tuple[dict, Path]:
    path = APPROVED_SCOPE if paid else REVIEW_SCOPE
    if paid and (not path.is_file() or not APPROVAL.is_file()):
        raise ValueError("AIDD baseline has no researcher-approved scope and approval record")
    scope = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(scope.get("sources"), list)
            or not isinstance(scope.get("zotero_sources"), list)
            or len(scope["sources"]) != 8 or len(scope["zotero_sources"]) != 8):
        raise ValueError("AIDD scope is incomplete")
    for row in scope["sources"]:
        source_path = Path(row["path"]).resolve(strict=True)
        if _digest(source_path) != row["sha256"]:
            raise ValueError("Scoped source changed since review")
    if paid:
        review = json.loads(REVIEW_SCOPE.read_text(encoding="utf-8"))
        def reviewed_shape(data: dict) -> dict:
            clone = json.loads(json.dumps(data))
            clone["status"] = "review_only"
            for row in clone["sources"] + clone["zotero_sources"]:
                row["external_model_excerpt_allowed"] = row.get("origin") == "public_research_workflow"
            return clone
        if reviewed_shape(scope) != review:
            raise ValueError("Approved scope differs from the reviewed source range")
        if scope.get("status") != "approved_for_model" or not all(
                row.get("external_model_excerpt_allowed") is True
                for row in scope["sources"] + scope["zotero_sources"]):
            raise ValueError("Explicit source approval is required for a paid run")
        approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
        expected = {"approved": True,
                    "review_scope_sha256": _digest(REVIEW_SCOPE),
                    "approved_scope_sha256": _digest(APPROVED_SCOPE),
                    "prompt_sha256": _digest(PROMPT_FILE),
                    "patch_sha256": _digest(PATCH),
                    "model": "deepseek-flash", "max_requests": 30,
                    "max_usd": 2}
        if any(approval.get(key) != value for key, value in expected.items()):
            raise ValueError("AIDD baseline approval does not match the reviewed trial")
        for row in scope["zotero_sources"]:
            verify_zotero(row)
    elif (scope.get("status") != "review_only"
          or any(row.get("external_model_excerpt_allowed") is not False
                 for row in scope["sources"] + scope["zotero_sources"]
                 if row.get("origin") != "public_research_workflow")):
        raise ValueError("AIDD review scope must keep all private sources disabled")
    return scope, path


def _save(output: Path, name: str, value: str) -> None:
    path = output / name
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--call-model", action="store_true",
                        help="requires source approval and a US$2 local budget gate")
    args = parser.parse_args()
    try:
        scope, scope_path = _check_scope(paid=args.call_model)
    except (ValueError, FileNotFoundError) as exc:
        parser.error(str(exc))
    prompt = PROMPT_FILE.read_text(encoding="utf-8")
    print(json.dumps({"status": scope["status"], "model": "deepseek-flash",
                      "max_requests": 30, "max_tokens_per_request": 8000,
                      "budget_cap_usd": 2, "paid": args.call_model,
                      "private_source_count": 12, "public_source_count": 4,
                      "approved_pdf_page_ranges": {row["role"]: row["allowed_page_ranges"]
                                                   for row in scope["sources"]
                                                   if row["role"].endswith("_pdf")},
                      "prompt_sha256": _digest(PROMPT_FILE),
                      "patch_sha256": _digest(PATCH)},
                     ensure_ascii=False), flush=True)
    if not args.call_model:
        return 0
    require_budget_gate()
    if float(os.environ["SSS_BUDGET_CAP_USD"]) > 2.0:
        raise ValueError("AIDD trial budget cap must be no more than US$2")
    from deepseek_harness import DeepSeekHarness

    output = BASE / "paid-run-01"
    output.mkdir(parents=True, exist_ok=True)
    output.chmod(0o700)
    if (output / "agent-events.jsonl").exists() or (output / "agent-answer.md").exists():
        raise ValueError("Trial output already exists; do not overwrite an existing attempt")
    marker = output / "paid-attempt.marker"
    fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write("one paid attempt reserved\n")
    _save(output, "agent-prompt.txt", prompt)
    session_id = "sss-aidd-initial-" + uuid4().hex
    _save(output, "session-id.txt", session_id + "\n")
    guard = NativeBudgetGuard(max_model_requests=30, max_observed_input_tokens=2_000_000)
    events_path = output / "agent-events.jsonl"
    started = time.monotonic()
    os.environ.update({"SSS_MCP_PYTHON": str(ROOT / ".venv312/bin/python"),
                       "SSS_PROJECT_ROOT": str(ROOT),
                       "SSS_RESEARCH_SCOPE_FILE": str(scope_path)})

    def observe(notification):
        if getattr(notification, "method", None) != "session.event":
            return
        event = getattr(notification, "payload", {}).get("event")
        if isinstance(event, dict):
            with events_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            events_path.chmod(0o600)
        guard.on_notification(notification)

    try:
        with DeepSeekHarness(
            provider="deepseek-official", model="deepseek-flash", reasoning_effort="high",
            max_tokens=8000, cwd=str(output), runtime_cwd=str(output),
            dsh_bin=str(ROOT / "node_modules/.bin/dsh"), profile="sdk",
            patches=(str(PATCH),), dsh_home=str(ROOT / ".local/dsh"),
            request_timeout_seconds=900,
        ) as harness:
            result = harness.run(prompt, session_id=session_id, on_notification=observe)
        _save(output, "agent-answer.md", result.final_response)
        metrics = {"status": "done" if result.finish_reason == "completed" and result.final_response.strip()
                   else "incomplete",
                   "finish_reason": result.finish_reason, "session_id": session_id,
                   "elapsed_seconds": round(time.monotonic() - started, 3),
                   "started_requests": guard.started_requests, **_usage(guard.events)}
    except Exception as exc:
        metrics = {"status": "budget_stopped" if isinstance(exc, NativeBudgetExceeded) else "error",
                   "error_type": type(exc).__name__, "error": str(exc)[:300],
                   "session_id": session_id,
                   "elapsed_seconds": round(time.monotonic() - started, 3),
                   "started_requests": guard.started_requests, **_usage(guard.events)}
    _save(output, "agent-metrics.json", json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: metrics[key] for key in
                      ("status", "finish_reason", "started_requests", "elapsed_seconds")
                      if key in metrics}, ensure_ascii=False), flush=True)
    return 0 if metrics["status"] == "done" else 2


if __name__ == "__main__":
    raise SystemExit(main())
