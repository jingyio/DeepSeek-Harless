#!/usr/bin/env python3
"""Run one budget-gated DSH research task with the opt-in online Motif adapter."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.dsh_client import _usage, require_budget_gate  # noqa: E402
from src.adapters.native_budget import NativeBudgetGuard  # noqa: E402

PREPARE = ROOT / "scripts/prepare-online-motif.py"


def prepare_patch(manifest: Path, task: Path) -> dict:
    spec = importlib.util.spec_from_file_location("online_prepare", PREPARE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.prepare(manifest, task)


def save(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--base-patch", type=Path, required=True)
    parser.add_argument("--prompt", type=Path, required=True)
    parser.add_argument("--embedding-endpoint", required=True)
    parser.add_argument("--embedding-model", required=True)
    parser.add_argument("--model", default="deepseek-flash",
                        choices=["deepseek-flash", "deepseek-pro"])
    parser.add_argument("--mode", default="shadow", choices=["shadow", "execute"])
    parser.add_argument("--projection-artifact", type=Path,
                        help="SSS certified Motif for latest tool-output projection")
    parser.add_argument("--budget-usd", type=float,
                        help="required with projection when starting the local cost gate")
    parser.add_argument("--call-model", action="store_true")
    args = parser.parse_args()
    endpoint = urlparse(args.embedding_endpoint)
    if (endpoint.scheme != "http"
            or endpoint.hostname not in {"127.0.0.1", "localhost", "::1"}
            or not endpoint.path.endswith("/v1/embeddings")):
        parser.error("embedding endpoint must be local loopback /v1/embeddings")
    prepared = prepare_patch(args.manifest, args.task)
    base_patch = args.base_patch.resolve(strict=True)
    prompt_file = args.prompt.resolve(strict=True)
    prompt = prompt_file.read_text(encoding="utf-8")
    if not prompt.strip() or len(prompt) > 100_000:
        raise ValueError("research task prompt is missing or unbounded")
    task = json.loads(args.task.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    projection_digest = None
    if args.projection_artifact is not None:
        from src.adapters.motif_output_projection import load_certified_projection

        projection_digest, _ = load_certified_projection(
            args.projection_artifact.resolve(strict=True))
        if projection_digest not in {
            row["certified_digest"] for row in manifest["artifacts"]
        }:
            raise ValueError("projection artifact is not in this online Motif manifest")
        if args.budget_usd is None or not 0 < args.budget_usd <= 100:
            parser.error("projection runs require a positive --budget-usd (at most US$100)")
    elif args.budget_usd is not None:
        parser.error("--budget-usd belongs to a --projection-artifact run")
    preview = {
        "task_id": task["task_id"], "session_id": task["session_id"],
        "model": args.model, "mode": args.mode,
        "base_patch": str(base_patch), "online_patch": prepared["patch"],
        "manifest_digest": manifest["manifest_digest"],
        "task_sha256": hashlib.sha256(args.task.read_bytes()).hexdigest(),
        "prompt_sha256": hashlib.sha256(prompt_file.read_bytes()).hexdigest(),
        "embedding_endpoint": args.embedding_endpoint,
        "max_model_requests": None,
        "provider_budget_cap_usd": (args.budget_usd if projection_digest
                                    else os.environ.get("SSS_BUDGET_CAP_USD")),
        "projection_artifact_digest": projection_digest,
        "projection_mode": "SSS latest tool batch" if projection_digest else "off",
        "paid_api_called": args.call_model,
    }
    print(json.dumps(preview, ensure_ascii=False, indent=2), flush=True)
    if not args.call_model:
        return 0
    if projection_digest and os.environ.get("SSS_ONLINE_PROJECTION_CHILD") != "1":
        command = [sys.executable, str(ROOT / "scripts/run-distil-dsh.py"),
                   "--mode", "plain", "--budget-usd", str(args.budget_usd),
                   "--budget-max-output", "8000", "--motif-output-projection",
                   str(args.projection_artifact.resolve(strict=True)), "--",
                   sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]]
        env = os.environ.copy()
        env["SSS_ONLINE_PROJECTION_CHILD"] = "1"
        return subprocess.call(command, env=env, cwd=ROOT)
    if projection_digest and os.environ.get("SSS_PROJECTION_ARTIFACT_DIGEST") != projection_digest:
        raise ValueError("running projection proxy does not match the certified Motif")
    require_budget_gate()
    lock_dir = ROOT / ".local/online-motif/session-locks"
    lock_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = lock_dir / (hashlib.sha256(task["session_id"].encode()).hexdigest() + ".json")
    try:
        with lock.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps({"task_id": task["task_id"],
                                     "task_sha256": preview["task_sha256"],
                                     "mode": args.mode}) + "\n")
        lock.chmod(0o600)
    except FileExistsError as exc:
        raise ValueError("session_id already used by an online Motif run") from exc
    run_id = hashlib.sha256(task["task_id"].encode()).hexdigest()[:12] + "-" + uuid4().hex
    out = ROOT / ".local/online-motif/runs" / run_id
    out.mkdir(parents=True, mode=0o700)
    save(out / "PREVIEW.json", json.dumps(preview, ensure_ascii=False, indent=2) + "\n")
    os.environ.update({
        "SSS_ONLINE_MOTIF_MANIFEST": str(args.manifest.resolve(strict=True)),
        "SSS_ONLINE_MOTIF_TASK": str(args.task.resolve(strict=True)),
        "SSS_ONLINE_MOTIF_MODE": args.mode,
        "SSS_MOTIF_EMBEDDING_ENDPOINT": args.embedding_endpoint,
        "SSS_MOTIF_EMBEDDING_MODEL": args.embedding_model,
        "SSS_ONLINE_MOTIF_PROMPT_SHA256": preview["prompt_sha256"],
    })
    guard = NativeBudgetGuard(max_model_requests=None,
                              max_observed_input_tokens=None)
    events_path = out / "agent-events.jsonl"

    def observe(notification) -> None:
        if getattr(notification, "method", None) != "session.event":
            return
        event = getattr(notification, "payload", {}).get("event")
        if isinstance(event, dict):
            with events_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            events_path.chmod(0o600)
        guard.on_notification(notification)

    started = time.monotonic()
    try:
        from deepseek_harness import DeepSeekHarness

        with DeepSeekHarness(
            provider="deepseek-official", model=args.model,
            reasoning_effort="off", max_tokens=8000,
            cwd=str(out), runtime_cwd=str(out),
            dsh_bin=str(ROOT / "node_modules/.bin/dsh"), profile="sdk",
            patches=(str(base_patch), prepared["patch"]),
            dsh_home=str(ROOT / ".local/dsh"), request_timeout_seconds=900,
        ) as harness:
            result = harness.run(prompt, session_id=task["session_id"],
                                 on_notification=observe)
        save(out / "answer.md", result.final_response)
        status = "done" if result.finish_reason == "completed" and result.final_response.strip() else "incomplete"
        metrics = {"status": status, "finish_reason": result.finish_reason,
                   "elapsed_seconds": round(time.monotonic() - started, 3),
                   "agent_steps": guard.started_requests,
                   **_usage(guard.events)}
    except Exception as exc:
        metrics = {"status": "error", "error_type": type(exc).__name__,
                   "error": str(exc)[:300],
                   "elapsed_seconds": round(time.monotonic() - started, 3),
                   "agent_steps": guard.started_requests,
                   **_usage(guard.events)}
    audit = out / ".local/online-motif" / (
        hashlib.sha256(task["session_id"].encode()).hexdigest() + ".jsonl")
    decisions = ([json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
                 if audit.exists() else [])
    metrics["motif_bypass_attempts"] = sum(row.get("kind") == "motif_bypass_attempt"
                                          for row in decisions)
    metrics["model_requests_skipped_verified"] = sum(
        row.get("kind") == "model_request_skipped_verified" for row in decisions)
    save(out / "metrics.json", json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output_dir": str(out), **metrics}, ensure_ascii=False), flush=True)
    return 0 if metrics["status"] == "done" else 2


if __name__ == "__main__":
    raise SystemExit(main())
