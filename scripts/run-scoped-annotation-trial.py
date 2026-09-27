#!/usr/bin/env python3
"""Run a frozen, approved cross-app annotation decision in DeepSeek Harness."""

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

import importlib.util  # noqa: E402

PREPARE = ROOT / "scripts/prepare-scoped-annotation-trial.py"
PREPARE_ONLINE = ROOT / "scripts/prepare-online-motif.py"
PATCH = ROOT / "config/aidd-scoped-baseline.patch.yml"


def _load_script(path: Path, name: str):
    module_spec = importlib.util.spec_from_file_location(name, path)
    if module_spec is None or module_spec.loader is None:
        raise RuntimeError(f"trial helper is unavailable: {path.name}")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _private(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    path.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--arm", choices=["baseline", "motif"], default="baseline")
    parser.add_argument("--online-manifest", type=Path)
    parser.add_argument("--online-task", type=Path)
    parser.add_argument("--embedding-endpoint", default="http://127.0.0.1:8776/v1/embeddings")
    parser.add_argument("--embedding-model", default="Qwen3-Embedding-0.6B")
    parser.add_argument("--call-model", action="store_true")
    args = parser.parse_args()
    spec_path = args.spec.resolve(strict=True)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    preview = _load_script(PREPARE, "scoped_trial_prepare").prepare(spec_path)
    out = Path(spec["out"]).resolve(strict=True)
    arm_budgets = preview["arm_budget_usd"]
    if args.arm not in arm_budgets:
        parser.error(f"{args.arm} arm is not budgeted in the frozen preview")
    scope = out / "source-scope.json"
    preview_file = out / "RUN-PREVIEW.json"
    prompt = Path(spec["prompt_path"]).resolve(strict=True)
    online = None
    if args.arm == "motif":
        if args.online_manifest is None or args.online_task is None:
            parser.error("Motif arm needs a certified manifest and frozen task")
        online = _load_script(PREPARE_ONLINE, "online_prepare").prepare(
            args.online_manifest, args.online_task)
    elif args.online_manifest or args.online_task:
        parser.error("baseline arm must not receive an online Motif manifest")
    print(json.dumps({"task_id": spec["task_id"], "paper_title": preview["paper_title"],
                      "annotation_count": preview["annotation_count"],
                      "arm": args.arm, "budget_cap_usd": arm_budgets[args.arm],
                      "online_manifest": online["manifest"] if online else None,
                      "paid_api_requested": args.call_model}, ensure_ascii=False), flush=True)
    if not args.call_model:
        return 0
    approval_file = out / "RUN-APPROVAL.json"
    if not approval_file.is_file():
        parser.error("the frozen source preview requires user approval")
    approval = json.loads(approval_file.read_text(encoding="utf-8"))
    if (approval.get("approved") is not True
            or approval.get("preview_sha256") != _digest(preview_file)
            or approval.get("scope_sha256") != _digest(scope)
            or approval.get("prompt_sha256") != _digest(prompt)
            or preview["scope_sha256"] != _digest(scope)):
        parser.error("approved preview, source scope or prompt changed")
    require_budget_gate()
    if float(os.environ["SSS_BUDGET_CAP_USD"]) > float(arm_budgets[args.arm]):
        parser.error("active cost gate exceeds the approved task budget")
    run_out = out / args.arm
    run_out.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (run_out / "paid-attempt.marker").open("x", encoding="utf-8") as stream:
        stream.write("one approved paid trial reserved\n")
    session_id = (json.loads(args.online_task.read_text(encoding="utf-8"))["session_id"]
                  if online else "sss-scoped-annotation-" + uuid4().hex)
    os.environ.update({"SSS_MCP_PYTHON": str(ROOT / ".venv312/bin/python"),
                       "SSS_PROJECT_ROOT": str(ROOT),
                       "SSS_RESEARCH_SCOPE_FILE": str(scope)})
    patches = [str(PATCH)]
    if online:
        os.environ.update({
            "SSS_ONLINE_MOTIF_MANIFEST": online["manifest"],
            "SSS_ONLINE_MOTIF_TASK": online["task"],
            "SSS_ONLINE_MOTIF_MODE": "execute",
            "SSS_MOTIF_EMBEDDING_ENDPOINT": args.embedding_endpoint,
            "SSS_MOTIF_EMBEDDING_MODEL": args.embedding_model,
            "SSS_ONLINE_MOTIF_PROMPT_SHA256": _digest(prompt),
        })
        patches.append(online["patch"])
    guard = NativeBudgetGuard(max_model_requests=None,
                              max_observed_input_tokens=None)
    events = run_out / "agent-events.jsonl"

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
        from deepseek_harness import DeepSeekHarness

        with DeepSeekHarness(
            provider="deepseek-official", model="deepseek-flash",
            reasoning_effort="high", max_tokens=6000,
            cwd=str(run_out), runtime_cwd=str(run_out),
            dsh_bin=str(ROOT / "node_modules/.bin/dsh"), profile="sdk",
            patches=tuple(patches), dsh_home=str(ROOT / ".local/dsh"),
            request_timeout_seconds=900,
        ) as harness:
            result = harness.run(prompt.read_text(encoding="utf-8"),
                                 session_id=session_id, on_notification=observe)
        answer = run_out / "agent-answer.md"
        answer.write_text(result.final_response, encoding="utf-8")
        answer.chmod(0o600)
        status = ("done" if result.finish_reason == "completed"
                  and result.final_response.strip() else "incomplete")
        metrics = {"status": status, "finish_reason": result.finish_reason}
    except Exception as exc:
        metrics = {"status": "error", "error_type": type(exc).__name__,
                   "error": str(exc)[:300]}
    metrics.update({"session_id": session_id,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "started_requests": guard.started_requests,
                    **_usage(guard.events)})
    if online:
        audit = run_out / ".local/online-motif" / (
            hashlib.sha256(session_id.encode()).hexdigest() + ".jsonl")
        decisions = ([json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
                     if audit.exists() else [])
        metrics["motif_bypass_attempts"] = sum(
            row.get("kind") == "motif_bypass_attempt" for row in decisions)
        metrics["model_requests_skipped_verified"] = sum(
            row.get("kind") == "model_request_skipped_verified" for row in decisions)
    _private(run_out / "agent-metrics.json", metrics)
    print(json.dumps({"output": str(run_out), **metrics}, ensure_ascii=False), flush=True)
    return 0 if metrics["status"] == "done" else 2


if __name__ == "__main__":
    raise SystemExit(main())
