#!/usr/bin/env python3
"""Run a frozen real research-data task with the focused read-only MCP surface.

Preview is free. Paid runs must be wrapped by scripts/run-distil-dsh.py in
plain mode with a per-run cost cap; this script also limits model requests.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.dsh_client import _usage, require_budget_gate  # noqa: E402
from src.adapters.native_budget import NativeBudgetExceeded, NativeBudgetGuard  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_dir", type=Path)
    parser.add_argument("--call-model", action="store_true")
    parser.add_argument("--max-requests", type=int, default=16)
    parser.add_argument("--max-output-tokens", type=int, default=1800)
    parser.add_argument("--profile", choices=("sdk", "sdk-minimal"), default="sdk")
    parser.add_argument("--patch", type=Path)
    args = parser.parse_args()
    task = args.task_dir.resolve(strict=True)
    if not task.is_relative_to((ROOT / ".local" / "benchmarks").resolve()):
        parser.error("task_dir must be under .local/benchmarks")
    if not 1 <= args.max_requests <= 40 or not 100 <= args.max_output_tokens <= 3000:
        parser.error("invalid model limits")
    workspace = task / "workspace"
    patch = args.patch or ROOT / "config" / ("structured-research-minimal.patch.yml"
                                                if args.profile == "sdk-minimal"
                                                else "structured-research-phase.patch.yml")
    patch = patch.resolve(strict=True)
    manifest = json.loads((task / "manifest.json").read_text(encoding="utf-8"))
    prompt = (task / "prompt.txt").read_text(encoding="utf-8").strip()
    if not prompt or len(prompt) > 10_000:
        parser.error("prompt.txt must contain 1–10,000 characters")
    for item in manifest["sources"]:
        path = workspace / "sources" / item["name"]
        if sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise RuntimeError(f"frozen source changed: {item['name']}")
    print(json.dumps({"task": manifest["task_id"], "sources": len(manifest["sources"]),
                      "max_requests": args.max_requests,
                      "max_output_tokens": args.max_output_tokens,
                      "profile": args.profile,
                      "patch": str(patch),
                      "paid": args.call_model}, ensure_ascii=False), flush=True)
    if not args.call_model:
        return 0

    require_budget_gate()
    os.environ["SSS_MCP_PYTHON"] = str(ROOT / ".venv312/bin/python")
    os.environ["SSS_PROJECT_ROOT"] = str(ROOT)
    os.environ["SSS_RESEARCH_INPUT_DIR"] = str(workspace)
    os.environ["DSH_PERMISSION_MODE"] = "read-only"
    from deepseek_harness import DeepSeekHarness

    session_id = f"sss-structured-{manifest['task_id']}-{uuid4().hex}"
    (task / "session-id.txt").write_text(session_id + "\n", encoding="utf-8")
    os.chmod(task / "session-id.txt", 0o600)
    guard = NativeBudgetGuard(max_model_requests=args.max_requests,
                              max_observed_input_tokens=3_000_000)
    events = task / "events.jsonl"
    started = time.monotonic()

    def observe(notification):
        if getattr(notification, "method", None) != "session.event":
            return
        event = getattr(notification, "payload", {}).get("event")
        if isinstance(event, dict):
            with events.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            os.chmod(events, 0o600)
        guard.on_notification(notification)

    try:
        with DeepSeekHarness(
            provider="deepseek-official", model="deepseek-flash", reasoning_effort="off",
            max_tokens=args.max_output_tokens, cwd=str(workspace),
            runtime_cwd=str(workspace), dsh_bin=str(ROOT / "node_modules/.bin/dsh"),
            profile=args.profile, patches=(str(patch),),
            dsh_home=str(ROOT / ".local/dsh"), request_timeout_seconds=900,
        ) as harness:
            result = harness.run(prompt, session_id=session_id, on_notification=observe)
        (task / "answer.md").write_text(result.final_response, encoding="utf-8")
        os.chmod(task / "answer.md", 0o600)
        status = "done" if result.final_response.strip() and result.finish_reason == "completed" else "incomplete"
        report = {"status": status, "finish_reason": result.finish_reason,
                  "answer_characters": len(result.final_response),
                  "elapsed_seconds": round(time.monotonic() - started, 3),
                  "started_requests": guard.started_requests, **_usage(guard.events)}
    except Exception as exc:
        report = {"status": "budget_stopped" if isinstance(exc, NativeBudgetExceeded) else "error",
                  "error_type": type(exc).__name__, "error": str(exc)[:300],
                  "elapsed_seconds": round(time.monotonic() - started, 3),
                  "started_requests": guard.started_requests, **_usage(guard.events)}
    (task / "metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8")
    os.chmod(task / "metrics.json", 0o600)
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "done" else 2


if __name__ == "__main__":
    raise SystemExit(main())
