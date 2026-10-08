#!/usr/bin/env python3
"""Freeze/run the same Calendar E task with a certified online Motif."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import argparse
import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location(
    "calendar_baseline", ROOT / "scripts/run-calendar-internal-agent-baseline.py")
assert SPEC and SPEC.loader
BASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASE)
BASE.TASKS["E"] = ("2026-10-16", "55 分钟", "09:00–12:00 或 14:00–16:00")
from src.adapters.dsh_client import _usage, require_budget_gate  # noqa: E402
from src.adapters.native_budget import NativeBudgetGuard  # noqa: E402

OUT = ROOT / ".local/benchmarks/mcp-app-internal-v2/calendar/motif-continuation-v1"
FOLDER = OUT / "agent-e-motif"
ARTIFACT = OUT / "calendar-certified-motif.json"
PLUGIN = ROOT / "src/adapters/dsh_calendar_motif.mjs"


def patch() -> str:
    return BASE.patch_text() + (
        "- insert:\n"
        "    - id: sss-calendar-certified-motif\n"
        f"      name: {json.dumps(PLUGIN.resolve().as_uri())}\n"
    )


def preview() -> dict:
    from importlib.util import spec_from_file_location, module_from_spec
    spec = spec_from_file_location("calendar_compile",
                                   ROOT / "scripts/compile-calendar-motif-certified.py")
    assert spec and spec.loader
    compiler = module_from_spec(spec)
    spec.loader.exec_module(compiler)
    artifact = json.loads(ARTIFACT.read_text())
    if compiler.compile_certified() != artifact:
        raise ValueError("certified Motif no longer matches training/held-out traces")
    return {"task_id": "synthetic-calendar-motif-e-online" +
            ("-retry-1" if FOLDER.name.endswith("retry-1") else ""), "case": "E",
            **({"retry_of": "agent-e-motif", "retry_reason":
                "first find-available-slots failed; Motif safely did not skip"}
               if FOLDER.name.endswith("retry-1") else {}),
            "model": "deepseek-flash", "reasoning_effort": "off",
            "budget_cap_usd": 0.50, "max_model_requests": 10,
            "max_output_tokens_per_request": 1600, "read_only": True,
            "same_prompt_as_ordinary_sha256": hashlib.sha256(BASE.prompt("E").encode()).hexdigest(),
            "same_calendar_bridge_sha256": BASE.sha(BASE.BRIDGE),
            "artifact_sha256": BASE.sha(ARTIFACT),
            "certified_digest": artifact["certified_digest"],
            "plugin_sha256": BASE.sha(PLUGIN),
            "patch_sha256": hashlib.sha256(patch().encode()).hexdigest(),
            "source_change_policy": "live validate; mismatch hands off to model"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--call-model", action="store_true")
    parser.add_argument("--attempt", choices=("primary", "retry-1"), default="primary")
    args = parser.parse_args()
    global FOLDER
    if args.attempt == "retry-1":
        first = OUT / "agent-e-motif"
        if not (first / "metrics.json").exists():
            parser.error("First online attempt must be recorded before retry")
        FOLDER = OUT / "agent-e-motif-retry-1"
    call_model = args.call_model
    current = preview()
    files = {FOLDER / "PREVIEW.json": json.dumps(current, ensure_ascii=False, indent=2) + "\n",
             FOLDER / "PROMPT.txt": BASE.prompt("E"), FOLDER / "patch.yml": patch()}
    print(json.dumps({**current, "paid_api_requested": call_model}, ensure_ascii=False), flush=True)
    if not call_model:
        for path, value in files.items():
            if path.exists() and path.read_text() != value:
                raise ValueError(f"Frozen {path.name} differs")
            if not path.exists():
                BASE.private(path, value)
        return 0
    approval = FOLDER / "APPROVAL.json"
    if not approval.exists() or any(not path.exists() or path.read_text() != value
                                     for path, value in files.items()):
        raise ValueError("Frozen preview and exact approval required")
    approved = json.loads(approval.read_text())
    if (approved.get("approved") is not True or
            approved.get("preview_sha256") != BASE.sha(FOLDER / "PREVIEW.json") or
            approved.get("budget_cap_usd") != 0.50):
        raise ValueError("Online Motif approval differs from frozen preview")
    require_budget_gate()
    if float(os.environ["SSS_BUDGET_CAP_USD"]) > 0.50:
        raise ValueError("Active cost gate exceeds task cap")
    marker = FOLDER / "paid-attempt.marker"
    with marker.open("x") as stream:
        stream.write("one approved read-only Calendar Motif attempt\n")
    marker.chmod(0o600)
    calendar = json.loads((ROOT / ".local/google-calendar/test-calendar.json").read_text())
    proxy = BASE.DOCTOR._google_proxy_env()
    os.environ.update({key: value for key, value in proxy.items()
                       if key in ("HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "NODE_OPTIONS")})
    session_id = f"sss-calendar-e-motif-{uuid4().hex}"
    os.environ.update({"SSS_PROJECT_ROOT": str(ROOT),
                       "SSS_BENCH_CALENDAR_ID": calendar["id"],
                       "GOOGLE_OAUTH_CREDENTIALS": str(ROOT / ".local/google-calendar/oauth-client.json"),
                       "GOOGLE_CALENDAR_MCP_TOKEN_PATH": str(ROOT / ".local/google-calendar/tokens.json"),
                       "DSH_PERMISSION_MODE": "read-only",
                       "SSS_CALENDAR_MOTIF_ARTIFACT": str(ARTIFACT),
                       "SSS_CALENDAR_MOTIF_SESSION": session_id,
                       "SSS_CALENDAR_MOTIF_PROMPT_SHA256": current["same_prompt_as_ordinary_sha256"],
                       "SSS_CALENDAR_MOTIF_MODE": "execute",
                       "SSS_CALENDAR_MOTIF_AUDIT_ROOT": str(FOLDER)})
    from deepseek_harness import DeepSeekHarness
    guard = NativeBudgetGuard(max_model_requests=10, max_observed_input_tokens=150_000)
    events = FOLDER / "agent-events.jsonl"

    def observe(notification) -> None:
        if getattr(notification, "method", None) != "session.event":
            return
        event = getattr(notification, "payload", {}).get("event")
        if isinstance(event, dict):
            with events.open("a") as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            events.chmod(0o600)
        guard.on_notification(notification)

    started = time.monotonic()
    try:
        with DeepSeekHarness(provider="deepseek-official", model="deepseek-flash",
                             reasoning_effort="off", max_tokens=1600,
                             cwd=str(FOLDER), runtime_cwd=str(FOLDER),
                             dsh_bin=str(ROOT / "node_modules/.bin/dsh"), profile="sdk",
                             patches=(str(FOLDER / "patch.yml"),),
                             dsh_home=str(ROOT / ".local/dsh"),
                             request_timeout_seconds=300) as harness:
            result = harness.run(BASE.prompt("E"), session_id=session_id,
                                 on_notification=observe)
        BASE.private(FOLDER / "answer.md", result.final_response)
        status = "completed" if result.finish_reason == "completed" else "incomplete"
    except Exception as exc:
        status = "error"
        BASE.private(FOLDER / "error.txt", f"{type(exc).__name__}: {str(exc)[:300]}\n")
    metrics = {"status": status, "case": "E", "mode": "certified_motif_online",
               "elapsed_seconds": round(time.monotonic() - started, 3),
               "started_requests": guard.started_requests, **_usage(guard.events)}
    BASE.private(FOLDER / "metrics.json", json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(metrics, ensure_ascii=False), flush=True)
    return 0 if status == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
