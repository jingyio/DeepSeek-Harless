#!/usr/bin/env python3
"""Finish a capped Model RSI intake run in the original DSH session."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.dsh_client import _usage, require_budget_gate  # noqa: E402
from src.adapters.native_budget import NativeBudgetExceeded, NativeBudgetGuard  # noqa: E402

PARENT = ROOT / ".local/benchmarks/research-weekly-loop/model-rsi-handle-20260927"
OUT = PARENT / "finish-02"
SCOPE = ROOT / ".local/benchmarks/research-weekly-loop/model-rsi-first-pilot/scope-preview.json"
PATCH = ROOT / "config/model-rsi-handle-pilot.patch.yml"
PROMPT = (
    "请基于本会话已经读取的 Model RSI 笔记与论文，结束工具探索并直接交付研究者可审阅的中文决定材料。"
    "回答是否现在做内部可更新能力状态最小原型；给出与外部检索、长上下文和重复题记忆的公平反证实验、"
    "关键来源定位、不能确定的部分和暂停条件。不要继续搜索，不要声称看过尚未读取的页段，"
    "不要修改应用。请以‘【材料结束】’结束。"
)


def preview() -> dict:
    spec = importlib.util.spec_from_file_location(
        "model_rsi_handle_pilot", ROOT / "scripts/run-model-rsi-handle-pilot.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("pilot source unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = module.preview()
    metrics = json.loads((PARENT / "agent-metrics.json").read_text(encoding="utf-8"))
    if (metrics.get("status") != "budget_stopped"
            or metrics.get("error_type") != "NativeBudgetExceeded"):
        raise ValueError("parent pilot is not the stopped run")
    session_id = (PARENT / "session-id.txt").read_text().strip()
    session_file = ROOT / ".local/dsh/storages/session_projcache/sessions" / (session_id + ".json")
    if not session_file.is_file():
        raise ValueError("original DSH session is unavailable")
    return {"parent": str(PARENT), "condition": original["condition"],
            "scope_sha256": original["scope_sha256"],
            "patch_sha256": original["patch_sha256"],
            "session_id": session_id, "model": "deepseek-flash",
            "max_requests": 3, "max_usd": 0.10,
            "instruction": "synthesize already read evidence; no new search",
            "output_dir": str(OUT)}


def save(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--call-model", action="store_true")
    args = parser.parse_args()
    details = preview()
    print(json.dumps({**details, "paid_requested": args.call_model}, ensure_ascii=False), flush=True)
    if not args.call_model:
        return 0
    require_budget_gate()
    if float(os.environ["SSS_BUDGET_CAP_USD"]) > 0.10:
        parser.error("continuation gate exceeds US$0.10")
    if OUT.exists():
        parser.error("continuation output exists; never overwrite")
    OUT.mkdir(parents=True, mode=0o700)
    save(OUT / "PREVIEW.json", json.dumps(details, ensure_ascii=False, indent=2) + "\n")
    save(OUT / "agent-prompt.txt", PROMPT + "\n")
    save(OUT / "paid-attempt.marker", "one supervised continuation\n")
    os.environ.update({"SSS_MCP_PYTHON": str(ROOT / ".venv312/bin/python"),
                       "SSS_PROJECT_ROOT": str(ROOT),
                       "SSS_RESEARCH_SCOPE_FILE": str(SCOPE)})
    guard = NativeBudgetGuard(max_model_requests=3, max_observed_input_tokens=450_000)
    events_path = OUT / "agent-events.jsonl"
    started = time.monotonic()

    def observe(notification) -> None:
        if getattr(notification, "method", None) != "session.event":
            return
        event = getattr(notification, "payload", {}).get("event")
        if isinstance(event, dict):
            with events_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            events_path.chmod(0o600)
        guard.on_notification(notification)

    try:
        from deepseek_harness import DeepSeekHarness

        with DeepSeekHarness(
            provider="deepseek-official", model="deepseek-flash", reasoning_effort="off",
            max_tokens=8000, cwd=str(PARENT), runtime_cwd=str(PARENT),
            dsh_bin=str(ROOT / "node_modules/.bin/dsh"), profile="sss-native-resume-sdk",
            patches=(str(PATCH),), dsh_home=str(ROOT / ".local/dsh"),
            request_timeout_seconds=900,
        ) as harness:
            result = harness.run(PROMPT, session_id=details["session_id"],
                                 on_notification=observe)
        save(OUT / "agent-answer.md", result.final_response)
        metrics = {"status": "done" if result.finish_reason == "completed"
                   and result.final_response.strip() else "incomplete",
                   "finish_reason": result.finish_reason,
                   "elapsed_seconds": round(time.monotonic() - started, 3),
                   "started_requests": guard.started_requests, **_usage(guard.events)}
    except Exception as exc:
        metrics = {"status": "budget_stopped" if isinstance(exc, NativeBudgetExceeded) else "error",
                   "error_type": type(exc).__name__, "error": str(exc)[:300],
                   "elapsed_seconds": round(time.monotonic() - started, 3),
                   "started_requests": guard.started_requests, **_usage(guard.events)}
    save(OUT / "agent-metrics.json", json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(metrics, ensure_ascii=False), flush=True)
    return 0 if metrics["status"] == "done" else 2


if __name__ == "__main__":
    raise SystemExit(main())
