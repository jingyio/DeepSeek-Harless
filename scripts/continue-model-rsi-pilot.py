#!/usr/bin/env python3
"""Preview or make one bounded continuation of the approved Model RSI pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.dsh_client import _usage, require_budget_gate  # noqa: E402
from src.adapters.native_budget import NativeBudgetExceeded, NativeBudgetGuard  # noqa: E402

PARENT = ROOT / ".local/benchmarks/research-weekly-loop/model-rsi-first-pilot"
OUT = PARENT / "continuation-01"
SCOPE = PARENT / "scope-preview.json"
PATCH = PARENT / "scoped-mcp.patch.yml"
SESSION = PARENT / "session-id.txt"
PROMPT = """请继续同一 Model RSI 科研决定任务。本次是有上限的续跑：此前 20 次请求已经耗尽，且没有最终交付。此前 arXiv 查询曾返回提供方错误，PDF 读取工具现在支持无版本 ID，并会明确标记未固定版本；不要把旧失败当作论文不存在。

请优先完成对已有笔记和已找到的公开论文的证据综合。若必要，可再检索或按页读少量最相关的论文正文；在本次 12 次请求内交付一份完整中文决定材料，不要无限扩展文献列表。引用来源必须能追溯到具体本地行号或 PDF 页码、公开论文 ID/版本或 PDF 页码；没有正文支持的结论请标为未证实。保留反证、简单基线、可证伪实验和暂停条件。你可以建议暂缓原型，不能捏造实验结果。不要修改笔记、发送邮件或建会。"""


def _save(name: str, value: str) -> None:
    path = OUT / name
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)


def _validate() -> tuple[dict, str]:
    scope = json.loads(SCOPE.read_text(encoding="utf-8"))
    if scope.get("status") != "approved_for_model":
        raise ValueError("source scope is not approved for external model excerpts")
    for row in scope["sources"]:
        if row.get("external_model_excerpt_allowed") is not True:
            raise ValueError("source scope has an unapproved item")
        path = Path(row["path"]).resolve(strict=True)
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("selected source changed since approval")
    metrics = json.loads((PARENT / "agent-metrics.json").read_text(encoding="utf-8"))
    if metrics.get("status") != "budget_stopped" or metrics.get("model_requests") != 20:
        raise ValueError("parent pilot is not the expected stopped run")
    session_id = SESSION.read_text(encoding="utf-8").strip()
    session_file = ROOT / ".local/dsh/storages/session_projcache/sessions" / f"{session_id}.json"
    if not session_id.startswith("sss-model-rsi-pilot-") or not session_file.is_file():
        raise ValueError("parent DSH session is unavailable")
    return scope, session_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--call-model", action="store_true")
    args = parser.parse_args()
    scope, session_id = _validate()
    print(json.dumps({"parent_session": session_id, "source_roles":
                      [row["role"] for row in scope["sources"]],
                      "model": "deepseek-flash", "additional_max_requests": 12,
                      "additional_usd_cap": 1.0, "max_output_tokens_per_request": 3000,
                      "paid": args.call_model}, ensure_ascii=False), flush=True)
    if not args.call_model:
        return 0
    if not (OUT / "APPROVAL.json").is_file():
        raise ValueError("continuation budget approval has not been recorded")
    approval = json.loads((OUT / "APPROVAL.json").read_text(encoding="utf-8"))
    if approval.get("additional_max_requests") != 12 or approval.get("additional_usd_cap") != 1.0:
        raise ValueError("continuation approval does not match limits")
    require_budget_gate()
    if float(os.environ["SSS_BUDGET_CAP_USD"]) > 1.0:
        raise ValueError("continuation USD cap exceeds approval")
    from deepseek_harness import DeepSeekHarness

    os.environ.update({"SSS_MCP_PYTHON": str(ROOT / ".venv312/bin/python"),
                       "SSS_PROJECT_ROOT": str(ROOT),
                       "SSS_RESEARCH_SCOPE_FILE": str(SCOPE)})
    OUT.mkdir(parents=True, exist_ok=True)
    OUT.chmod(0o700)
    if (OUT / "agent-events.jsonl").exists() or (OUT / "agent-answer.md").exists():
        raise ValueError("continuation output already exists")
    attempt = OUT / "paid-attempt.marker"
    fd = os.open(attempt, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as marker:
        marker.write("one paid continuation reserved\n")
    _save("agent-prompt.txt", PROMPT + "\n")
    guard = NativeBudgetGuard(max_model_requests=12, max_observed_input_tokens=800_000)
    events_path = OUT / "agent-events.jsonl"
    started = time.monotonic()

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
            max_tokens=3000, cwd=str(PARENT), runtime_cwd=str(PARENT),
            dsh_bin=str(ROOT / "node_modules/.bin/dsh"), profile="sss-native-resume-sdk",
            patches=(str(PATCH),), dsh_home=str(ROOT / ".local/dsh"),
            request_timeout_seconds=900,
        ) as harness:
            result = harness.run(PROMPT, session_id=session_id, on_notification=observe)
        _save("agent-answer.md", result.final_response)
        metrics = {"status": "done" if result.final_response.strip() else "incomplete",
                   "finish_reason": result.finish_reason,
                   "session_id": session_id, "elapsed_seconds": round(time.monotonic() - started, 3),
                   "started_requests": guard.started_requests, **_usage(guard.events)}
    except Exception as exc:
        metrics = {"status": "budget_stopped" if isinstance(exc, NativeBudgetExceeded) else "error",
                   "error_type": type(exc).__name__, "error": str(exc)[:300],
                   "session_id": session_id, "elapsed_seconds": round(time.monotonic() - started, 3),
                   "started_requests": guard.started_requests, **_usage(guard.events)}
    _save("agent-metrics.json", json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(metrics, ensure_ascii=False), flush=True)
    return 0 if metrics["status"] == "done" else 2


if __name__ == "__main__":
    raise SystemExit(main())
