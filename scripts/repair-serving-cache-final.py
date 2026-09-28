#!/usr/bin/env python3
"""One budgeted continuation when a trial's final answer is only a supplement."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.dsh_client import _usage, require_budget_gate  # noqa: E402
from src.adapters.native_budget import NativeBudgetGuard  # noqa: E402

BASE = ROOT / ".local/benchmarks/research-weekly-loop/serving-cache-baseline-decision-20260928/v2"
ARM = BASE / "motif"
PROMPT = BASE / "agent-prompt.md"
TASK = BASE / "online-task.json"
SCOPE = BASE / "source-scope.json"
MANIFEST = ROOT / ".local/benchmarks/research-weekly-loop/annotation-motif-candidates-20260927/online-manifest.json"
PATCH = ROOT / "config/serving-cache-pilot.patch.yml"
REPAIR = "请把本会话中已经核查的资料和上一条完整草稿整合成一份可单独阅读的最终决定。上一条简短补充不能独立交付。按原始任务的必答项和不超过 1200 个汉字要求作答；不要再调用工具，不要补造新的事实。"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def main() -> int:
    require_budget_gate()
    if float(os.environ["SSS_BUDGET_CAP_USD"]) > 0.1:
        raise ValueError("repair gate may not exceed US$0.10")
    original = json.loads((ARM / "metrics.json").read_text(encoding="utf-8"))
    if (original.get("status") != "done" or
            original.get("model_requests_skipped_verified") != 1 or
            not original.get("session_id")):
        raise ValueError("repair requires the completed Motif pilot")
    session = (ROOT / ".local/dsh/storages/session_projcache/sessions" /
               (original["session_id"] + ".json"))
    if not session.is_file():
        raise ValueError("original DSH session is unavailable")
    out = ARM / "repair-final-01"
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    marker = out / "paid-attempt.marker"
    if marker.exists():
        prior = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
        if prior.get("model_requests") != 0 or prior.get("error_type") != "JsonRpcError":
            raise ValueError("repair attempt already used")
    else:
        with marker.open("x", encoding="utf-8") as file:
            file.write("one supervised answer repair\n")
        marker.chmod(0o600)
    spec = importlib.util.spec_from_file_location("online_prepare", ROOT / "scripts/prepare-online-motif.py")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    online = helper.prepare(MANIFEST, TASK)
    os.environ.update({
        "SSS_MCP_PYTHON": str(ROOT / ".venv312/bin/python"),
        "SSS_PROJECT_ROOT": str(ROOT),
        "SSS_RESEARCH_SCOPE_FILE": str(SCOPE),
        "SSS_ONLINE_MOTIF_MANIFEST": online["manifest"],
        "SSS_ONLINE_MOTIF_TASK": online["task"],
        "SSS_ONLINE_MOTIF_MODE": "execute",
        "SSS_MOTIF_EMBEDDING_ENDPOINT": "http://127.0.0.1:8776/v1/embeddings",
        "SSS_MOTIF_EMBEDDING_MODEL": "Qwen/Qwen3-Embedding-0.6B",
        "SSS_ONLINE_MOTIF_PROMPT_SHA256": sha(PROMPT),
    })
    from deepseek_harness import DeepSeekHarness

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
                             cwd=str(ARM), runtime_cwd=str(ARM),
                             dsh_bin=str(ROOT / "node_modules/.bin/dsh"),
                             profile="sss-native-resume-sdk",
                             patches=(str(PATCH), online["patch"]),
                             dsh_home=str(ROOT / ".local/dsh"),
                             request_timeout_seconds=900) as harness:
            result = harness.run(REPAIR, session_id=original["session_id"],
                                 on_notification=observe)
        answer = out / "answer.md"
        answer.write_text(result.final_response, encoding="utf-8")
        answer.chmod(0o600)
        metrics = {"status": "done" if result.finish_reason == "completed" and
                   result.final_response.strip() else "incomplete",
                   "finish_reason": result.finish_reason}
    except Exception as exc:
        metrics = {"status": "error", "error_type": type(exc).__name__,
                   "error": str(exc)[:300]}
    metrics.update({"elapsed_seconds": round(time.monotonic() - started, 3),
                    "model_requests_started": guard.started_requests,
                    "budget_ledger": os.environ.get("SSS_BUDGET_LEDGER"),
                    **_usage(guard.events)})
    save(out / "metrics.json", metrics)
    print(json.dumps({"output": str(out), **metrics}, ensure_ascii=False), flush=True)
    return 0 if metrics["status"] == "done" else 2


if __name__ == "__main__":
    raise SystemExit(main())
