#!/usr/bin/env python3
"""Run the scoped real serving-baseline decision with a per-arm cost gate."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.dsh_client import _usage, require_budget_gate  # noqa: E402
from src.adapters.final_response_integrity import supplemental_final  # noqa: E402
from src.adapters.native_budget import NativeBudgetGuard  # noqa: E402
from src.mcp.scoped_obsidian_read_server import _approved_local, _approved_note  # noqa: E402
from src.mcp.scoped_zotero_read_server import _verified  # noqa: E402

TASK_ROOT = ROOT / ".local/benchmarks/research-weekly-loop/serving-cache-baseline-decision-20260928"
MANIFEST = ROOT / ".local/benchmarks/research-weekly-loop/annotation-motif-candidates-20260927/online-manifest.json"
CAP_USD = 2.0


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def verify_scope(scope_file: Path, task_id: str,
                 expected_sources: int, expected_zotero: int) -> dict:
    os.environ["SSS_RESEARCH_SCOPE_FILE"] = str(scope_file.resolve(strict=True))
    scope = json.loads(scope_file.read_text(encoding="utf-8"))
    if scope.get("task_id") != task_id:
        raise ValueError("wrong research task scope")
    if (len(scope.get("sources", [])) != expected_sources or
            len(scope.get("zotero_sources", [])) != expected_zotero):
        raise ValueError("research task scope changed")
    _approved_note("research_state")
    for source in scope["sources"][1:]:
        _approved_local(source["role"], {".pdf"})
    for source in scope["zotero_sources"]:
        _verified(source)
    return scope


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=["baseline", "motif"], required=True)
    parser.add_argument("--variant", choices=["v1", "v2", "v3", "triage", "ai4s"], default="v1")
    parser.add_argument("--call-model", action="store_true")
    args = parser.parse_args()
    base = (ROOT / ".local/benchmarks/research-weekly-loop/ai4s-affinity-literature-triage-20260928"
            if args.variant == "ai4s" else
            ROOT / ".local/benchmarks/research-weekly-loop/serving-baseline-triage-20260928"
            if args.variant == "triage" else
            TASK_ROOT if args.variant == "v1" else TASK_ROOT / args.variant)
    scope_file = base / "source-scope.json"
    prompt_file = base / "agent-prompt.md"
    task_file = base / "online-task.json"
    patch = (ROOT / "config/scoped-zotero-obsidian-only.patch.yml"
             if args.variant == "ai4s" else
             ROOT / "config/aidd-scoped-baseline.patch.yml" if args.variant == "v1"
             else ROOT / "config/serving-cache-pilot.patch.yml")
    task_id = ("ai4s-affinity-literature-triage-20260928" if args.variant == "ai4s"
               else "serving-baseline-triage-20260928" if args.variant == "triage"
               else "serving-cache-baseline-decision-20260928" if args.variant == "v1"
               else f"serving-cache-baseline-decision-{args.variant}-20260928")
    scope = verify_scope(scope_file, task_id, 1 if args.variant in {"triage", "ai4s"} else 3,
                         6 if args.variant in {"triage", "ai4s"} else 2)
    spec = importlib.util.spec_from_file_location("online_prepare", ROOT / "scripts/prepare-online-motif.py")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    online = helper.prepare(MANIFEST, task_file) if args.arm == "motif" else None
    preview = {"task_id": scope["task_id"], "arm": args.arm,
               "model": "deepseek-flash", "reasoning_effort": "off",
               "budget_cap_usd": CAP_USD, "read_only": True,
               "scope_sha256": sha(scope_file), "prompt_sha256": sha(prompt_file),
               "base_patch_sha256": sha(patch), "manifest_sha256": sha(MANIFEST)
               if online else None, "task_sha256": sha(task_file) if online else None,
               "output": str(base / args.arm)}
    preview_file = base / f"{args.arm}-preview.json"
    if preview_file.exists() and json.loads(preview_file.read_text(encoding="utf-8")) != preview:
        raise ValueError("frozen preview changed")
    if not preview_file.exists():
        save(preview_file, preview)
    print(json.dumps({**preview, "paid_api_requested": args.call_model}, ensure_ascii=False), flush=True)
    if not args.call_model:
        return 0
    require_budget_gate()
    if float(os.environ["SSS_BUDGET_CAP_USD"]) > CAP_USD:
        raise ValueError("active cost gate exceeds frozen cap")
    from deepseek_harness import DeepSeekHarness

    out = base / args.arm
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    marker = out / "paid-attempt.marker"
    with marker.open("x", encoding="utf-8") as file:
        file.write("one paid attempt reserved under prior user authorization\n")
    marker.chmod(0o600)
    session_id = (json.loads(task_file.read_text(encoding="utf-8"))["session_id"]
                  if online else "sss-serving-cache-baseline-" + uuid4().hex)
    os.environ.update({"SSS_MCP_PYTHON": str(ROOT / ".venv312/bin/python"),
                       "SSS_PROJECT_ROOT": str(ROOT),
                       "SSS_RESEARCH_SCOPE_FILE": str(scope_file)})
    patches = [str(patch)]
    if online:
        os.environ.update({
            "SSS_ONLINE_MOTIF_MANIFEST": online["manifest"],
            "SSS_ONLINE_MOTIF_TASK": online["task"],
            "SSS_ONLINE_MOTIF_MODE": "execute",
            "SSS_MOTIF_EMBEDDING_ENDPOINT": "http://127.0.0.1:8776/v1/embeddings",
            "SSS_MOTIF_EMBEDDING_MODEL": "Qwen/Qwen3-Embedding-0.6B",
            "SSS_ONLINE_MOTIF_PROMPT_SHA256": sha(prompt_file),
        })
        patches.append(online["patch"])
    guard = NativeBudgetGuard(max_model_requests=None, max_observed_input_tokens=None)
    events = out / "agent-events.jsonl"

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
                             reasoning_effort="off", max_tokens=8000,
                             cwd=str(out), runtime_cwd=str(out),
                             dsh_bin=str(ROOT / "node_modules/.bin/dsh"), profile="sdk",
                             patches=tuple(patches), dsh_home=str(ROOT / ".local/dsh"),
                             request_timeout_seconds=900) as harness:
            result = harness.run(prompt_file.read_text(encoding="utf-8"), session_id=session_id,
                                 on_notification=observe)
        answer = out / "answer.md"
        answer.write_text(result.final_response, encoding="utf-8")
        answer.chmod(0o600)
        recorded = ([json.loads(line) for line in events.read_text(encoding="utf-8").splitlines()]
                    if events.exists() else [])
        fragment = supplemental_final(recorded, result.final_response)
        metrics = {"status": "done" if result.finish_reason == "completed" and
                   result.final_response.strip() and not fragment else "incomplete",
                   "final_supplement_detected": fragment,
                   "finish_reason": result.finish_reason}
    except Exception as exc:
        metrics = {"status": "error", "error_type": type(exc).__name__,
                   "error": str(exc)[:300]}
    metrics.update({"session_id": session_id,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "started_requests": guard.started_requests,
                    "budget_ledger": os.environ.get("SSS_BUDGET_LEDGER"),
                    **_usage(guard.events)})
    if online:
        audit = out / ".local/online-motif" / (
            hashlib.sha256(session_id.encode()).hexdigest() + ".jsonl")
        decisions = ([json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
                     if audit.exists() else [])
        metrics["motif_bypass_attempts"] = sum(row.get("kind") == "motif_bypass_attempt"
                                               for row in decisions)
        metrics["model_requests_skipped_verified"] = sum(
            row.get("kind") == "model_request_skipped_verified" for row in decisions)
    save(out / "metrics.json", metrics)
    print(json.dumps({"output": str(out), **metrics}, ensure_ascii=False), flush=True)
    return 0 if metrics["status"] == "done" else 2


if __name__ == "__main__":
    raise SystemExit(main())
