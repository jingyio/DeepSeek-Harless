#!/usr/bin/env python3
"""Run one bounded Gmail self-mail draft diagnostic without sending it."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.dsh_client import _usage, require_budget_gate  # noqa: E402
from src.adapters.native_budget import NativeBudgetGuard  # noqa: E402

BASE = ROOT / ".local/benchmarks/research-weekly-loop/gmail-request-pilot-20260928"
PATCH = ROOT / "config/gmail-request-pilot.patch.yml"
CAP_USD = 2.0


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    path.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true",
                        help="technical search/read replay, not an independent research task")
    parser.add_argument("--probe-after-metadata-fix", action="store_true",
                        help="repeat the technical probe after the DSH metadata fix")
    parser.add_argument("--call-model", action="store_true")
    args = parser.parse_args()
    if args.probe and args.probe_after_metadata_fix:
        parser.error("choose only one probe mode")
    probe = args.probe or args.probe_after_metadata_fix
    scope_file = BASE / "scope.json"
    prompt_file = BASE / ("probe-prompt.md" if probe else "agent-prompt.md")
    scope = json.loads(scope_file.read_text(encoding="utf-8"))
    if (scope.get("task_id") != "gmail-request-pilot-20260928"
            or scope.get("query") != "subject:SSS newer_than:180d"
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", scope.get("message_id", ""))
            or not re.fullmatch(r"[^\s@]+@[^\s@]+", scope.get("recipient", ""))):
        raise ValueError("frozen Gmail scope is invalid")
    gmail = ROOT / ".local/google-gmail"
    oauth = gmail / "oauth-client.json"
    if not oauth.is_file():
        oauth = ROOT / ".local/google-calendar/oauth-client.json"
    for path in (gmail / "tokens.json", oauth, PATCH):
        path.resolve(strict=True)
    preview = {"task_id": scope["task_id"], "probe": probe,
               "model": "deepseek-flash",
               "reasoning_effort": "off", "budget_cap_usd": CAP_USD,
               "allowed_tools": ["search_emails", "read_email", "prepare_email",
                                 "get_prepared_email"], "sent": False,
               "scope_sha256": digest(scope_file),
               "prompt_sha256": digest(prompt_file),
               "patch_sha256": digest(PATCH)}
    preview_file = BASE / ("probe-after-metadata-fix-preview.json"
                           if args.probe_after_metadata_fix else
                           "probe-preview.json" if args.probe else "preview.json")
    if preview_file.exists() and json.loads(preview_file.read_text(encoding="utf-8")) != preview:
        raise ValueError("frozen Gmail preview changed")
    if not preview_file.exists():
        save(preview_file, preview)
    print(json.dumps({**preview, "paid_api_requested": args.call_model},
                     ensure_ascii=False), flush=True)
    if not args.call_model:
        return 0
    require_budget_gate()
    if float(os.environ["SSS_BUDGET_CAP_USD"]) > CAP_USD:
        raise ValueError("active cost gate exceeds frozen cap")
    from deepseek_harness import DeepSeekHarness

    output = BASE / ("probe-after-metadata-fix" if args.probe_after_metadata_fix
                     else "probe" if args.probe else "baseline")
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    marker = output / "paid-attempt.marker"
    with marker.open("x", encoding="utf-8") as file:
        file.write("one paid Gmail draft diagnostic under prior user authorization\n")
    marker.chmod(0o600)
    os.environ.update({"SSS_PROJECT_ROOT": str(ROOT),
                       "SSS_GOOGLE_GMAIL_OAUTH": str(oauth),
                       "SSS_GOOGLE_GMAIL_TOKENS": str(gmail / "tokens.json"),
                       "SSS_GOOGLE_GMAIL_STATE": str(gmail),
                       "SSS_GMAIL_ALLOWED_QUERY": scope["query"],
                       "SSS_GMAIL_ALLOWED_MESSAGE_ID": scope["message_id"],
                       "SSS_GMAIL_ALLOWED_RECIPIENT": scope["recipient"]})
    events = output / "agent-events.jsonl"
    guard = NativeBudgetGuard(max_model_requests=None, max_observed_input_tokens=None)

    def observe(notification) -> None:
        if getattr(notification, "method", None) != "session.event":
            return
        event = getattr(notification, "payload", {}).get("event")
        if isinstance(event, dict):
            with events.open("a", encoding="utf-8") as file:
                file.write(json.dumps(event, ensure_ascii=False) + "\n")
            events.chmod(0o600)
        guard.on_notification(notification)

    started = time.monotonic()
    try:
        with DeepSeekHarness(provider="deepseek-official", model="deepseek-flash",
                             reasoning_effort="off", max_tokens=4000,
                             cwd=str(output), runtime_cwd=str(output),
                             dsh_bin=str(ROOT / "node_modules/.bin/dsh"), profile="sdk",
                             patches=(str(PATCH),), dsh_home=str(ROOT / ".local/dsh"),
                             request_timeout_seconds=900) as harness:
            result = harness.run(prompt_file.read_text(encoding="utf-8"),
                                 session_id="sss-gmail-request-" + uuid4().hex,
                                 on_notification=observe)
        answer = output / "answer.md"
        answer.write_text(result.final_response, encoding="utf-8")
        answer.chmod(0o600)
        rows = ([json.loads(line) for line in events.read_text(encoding="utf-8").splitlines()]
                if events.exists() else [])
        tools = [row.get("data", {}).get("name", "") for row in rows
                 if row.get("type") == "tool/call"]
        metrics = {"status": "done" if result.finish_reason == "completed" else "incomplete",
                   "finish_reason": result.finish_reason,
                   "tool_calls_by_name": {name: tools.count(name) for name in sorted(set(tools))},
                   "prepared_call_observed": any(name.endswith("__prepare_email") for name in tools)}
    except Exception as exc:
        metrics = {"status": "error", "error_type": type(exc).__name__,
                   "error": str(exc)[:300]}
    metrics.update({"elapsed_seconds": round(time.monotonic() - started, 3),
                    "started_requests": guard.started_requests,
                    "budget_ledger": os.environ.get("SSS_BUDGET_LEDGER"),
                    **_usage(guard.events)})
    save(output / "metrics.json", metrics)
    print(json.dumps(metrics, ensure_ascii=False), flush=True)
    return 0 if metrics["status"] == "done" else 2


if __name__ == "__main__":
    raise SystemExit(main())
