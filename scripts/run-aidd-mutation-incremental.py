#!/usr/bin/env python3
"""Run the frozen AIDD mutation-data increment in a budgeted MCP-only DSH arm."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
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
from src.mcp.scoped_zotero_read_server import _verified as verify_zotero  # noqa: E402

BASE = ROOT / ".local/benchmarks/research-weekly-loop/aidd-mutation-incremental-20260928"
SCOPE = BASE / "source-scope.json"
PROMPT = BASE / "agent-prompt.md"
DATA_VIEW = BASE / "data-input"
PATCHES = (ROOT / "config/aidd-scoped-baseline.patch.yml",
           ROOT / "config/aidd-sar-mcp.patch.yml")
CAP_USD = 2.0


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def private_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def check_scope() -> dict:
    scope = json.loads(SCOPE.read_text(encoding="utf-8"))
    if (scope.get("status") != "approved_for_model_by_current_task_authorization"
            or scope.get("task_id") != "aidd-mutation-incremental-20260928"
            or len(scope.get("sources", [])) != 8
            or len(scope.get("zotero_sources", [])) != 1
            or len(scope.get("public_data_sources", [])) != 10):
        raise ValueError("AIDD mutation task scope is incomplete or unapproved")
    for row in scope["sources"] + scope["public_data_sources"]:
        path = Path(row["path"]).resolve(strict=True)
        if sha(path) != row["sha256"]:
            raise ValueError(f"Source version changed: {row['role']}")
    for row in scope["zotero_sources"]:
        verify_zotero(row)
    listed = sorted(DATA_VIEW.iterdir())
    approved = {Path(row["path"]).resolve() for row in scope["public_data_sources"]}
    if len(listed) != 10 or {item.resolve() for item in listed} != approved:
        raise ValueError("Data view differs from the approved CSV sources")
    return scope


def preview(arm: str, online: dict | None = None,
            attempt: str | None = None) -> dict:
    scope = check_scope()
    details = {"task_id": scope["task_id"], "arm": arm,
            "classification": "real_AIDD_historical_increment_same_decision_chain",
            "model": "deepseek-flash", "reasoning_effort": "off",
            "budget_cap_usd": CAP_USD, "max_model_requests": None,
            "max_output_tokens_per_request": 8000,
            "read_only_external_apps": True,
            "source_roles": [item["role"] for item in scope["sources"]],
            "zotero_roles": [item["role"] for item in scope["zotero_sources"]],
            "public_data_file_count": len(scope["public_data_sources"]),
            "scope_sha256": sha(SCOPE), "prompt_sha256": sha(PROMPT),
            "patch_sha256": [sha(path) for path in PATCHES],
            "output": str(BASE / (arm if attempt is None else f"{arm}-{attempt}"))}
    if online:
        details.update({"online_manifest_sha256": sha(Path(online["manifest"])),
                        "online_task_sha256": sha(Path(online["task"])),
                        "online_patch_sha256": sha(Path(online["patch"])),
                        "embedding_endpoint": "http://127.0.0.1:8776/v1/embeddings"})
    return details


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=("baseline", "motif"), default="baseline")
    parser.add_argument("--online-manifest", type=Path)
    parser.add_argument("--online-task", type=Path)
    parser.add_argument("--attempt", help="new isolated attempt name, e.g. diagnostic-1")
    parser.add_argument("--call-model", action="store_true")
    args = parser.parse_args()
    if args.attempt and not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,39}", args.attempt):
        parser.error("attempt must be a short lowercase name")
    online = None
    if args.arm == "motif":
        if args.online_manifest is None or args.online_task is None:
            parser.error("Motif arm requires a certified manifest and structured task")
        helper = ROOT / "scripts/prepare-online-motif.py"
        spec = importlib.util.spec_from_file_location("sar_online_prepare", helper)
        if spec is None or spec.loader is None:
            parser.error("Online Motif helper is unavailable")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        online = module.prepare(args.online_manifest, args.online_task)
    elif args.online_manifest or args.online_task:
        parser.error("Baseline cannot receive a Motif manifest")
    details = preview(args.arm, online, args.attempt)
    prefix = args.arm.upper() if args.attempt is None else f"{args.arm}-{args.attempt}".upper()
    frozen_path = BASE / f"{prefix}-PREVIEW.json"
    approval_path = BASE / f"{prefix}-APPROVAL.json"
    if not frozen_path.exists():
        private_json(frozen_path, details)
    elif json.loads(frozen_path.read_text(encoding="utf-8")) != details:
        parser.error("Frozen preview changed")
    print(json.dumps({**details, "paid_api_requested": args.call_model}, ensure_ascii=False), flush=True)
    if not args.call_model:
        return 0
    if not approval_path.exists():
        parser.error("Task authorization record is missing")
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    if (approval.get("approved") is not True
            or approval.get("authorization_basis") != "可以的，测一下"
            or approval.get("preview_sha256") != sha(frozen_path)
            or approval.get("budget_cap_usd") != CAP_USD):
        parser.error("Task authorization does not match the frozen preview")
    require_budget_gate()
    if float(os.environ["SSS_BUDGET_CAP_USD"]) > CAP_USD:
        parser.error("Cost gate exceeds the approved task cap")

    from deepseek_harness import DeepSeekHarness

    out = Path(details["output"])
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    marker = out / "paid-attempt.marker"
    with marker.open("x", encoding="utf-8") as stream:
        stream.write("one authorized paid attempt reserved\n")
    marker.chmod(0o600)
    session_id = (json.loads(args.online_task.read_text(encoding="utf-8"))["session_id"]
                  if online else "sss-aidd-mutation-incremental-" + uuid4().hex)
    (out / "session-id.txt").write_text(session_id + "\n", encoding="utf-8")
    (out / "session-id.txt").chmod(0o600)
    os.environ.update({"SSS_MCP_PYTHON": str(ROOT / ".venv312/bin/python"),
                       "SSS_PROJECT_ROOT": str(ROOT),
                       "SSS_RESEARCH_SCOPE_FILE": str(SCOPE),
                       "SSS_RESEARCH_INPUT_DIR": str(DATA_VIEW),
                       "SSS_PYTHON_WORKSPACE": str(out / "python-workspace")})
    patches = [str(path) for path in PATCHES]
    if online:
        os.environ.update({"SSS_ONLINE_MOTIF_MANIFEST": online["manifest"],
                           "SSS_ONLINE_MOTIF_TASK": online["task"],
                           "SSS_ONLINE_MOTIF_MODE": "execute",
                           "SSS_MOTIF_EMBEDDING_ENDPOINT": "http://127.0.0.1:8776/v1/embeddings",
                           "SSS_MOTIF_EMBEDDING_MODEL": "Qwen/Qwen3-Embedding-0.6B",
                           "SSS_ONLINE_MOTIF_PROMPT_SHA256": sha(PROMPT)})
        patches.append(online["patch"])
    actual_prompt = PROMPT.read_text(encoding="utf-8")
    guard = NativeBudgetGuard(max_model_requests=None, max_observed_input_tokens=None)
    events = out / "agent-events.jsonl"

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
            reasoning_effort="off", max_tokens=8000,
            cwd=str(out), runtime_cwd=str(out),
            dsh_bin=str(ROOT / "node_modules/.bin/dsh"), profile="sdk",
            patches=tuple(patches),
            dsh_home=str(ROOT / ".local/dsh"), request_timeout_seconds=900,
        ) as harness:
            result = harness.run(actual_prompt, session_id=session_id,
                                 on_notification=observe)
        answer = out / "agent-answer.md"
        answer.write_text(result.final_response, encoding="utf-8")
        answer.chmod(0o600)
        status = "done" if result.finish_reason == "completed" and result.final_response.strip() else "incomplete"
        metrics = {"status": status, "finish_reason": result.finish_reason}
    except Exception as exc:
        metrics = {"status": "error", "error_type": type(exc).__name__,
                   "error": str(exc)[:300]}
    metrics.update({"session_id": session_id,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "started_requests": guard.started_requests,
                    "budget_ledger": os.environ.get("SSS_BUDGET_LEDGER"),
                    **_usage(guard.events)})
    if online:
        audit = out / ".local/online-motif" / (hashlib.sha256(session_id.encode()).hexdigest() + ".jsonl")
        decisions = ([json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
                     if audit.exists() else [])
        metrics["motif_bypass_attempts"] = sum(
            row.get("kind") == "motif_bypass_attempt" for row in decisions)
        metrics["model_requests_skipped_verified"] = sum(
            row.get("kind") == "model_request_skipped_verified" for row in decisions)
    private_json(out / "agent-metrics.json", metrics)
    print(json.dumps({"output": str(out), **metrics}, ensure_ascii=False), flush=True)
    return 0 if metrics["status"] == "done" else 2


if __name__ == "__main__":
    raise SystemExit(main())
