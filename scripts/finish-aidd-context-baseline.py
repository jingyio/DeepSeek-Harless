#!/usr/bin/env python3
"""Complete the truncated AIDD context trial inside its original approval."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.dsh_client import _usage, require_budget_gate  # noqa: E402
from src.adapters.native_budget import NativeBudgetExceeded, NativeBudgetGuard  # noqa: E402

BASE = ROOT / ".local/benchmarks/research-weekly-loop/aidd-next-preflight"
PARENT = BASE / "paid-context-baseline-01"
OUT = PARENT / "finish-01"
SCOPE = BASE / "baseline-scope-approved.json"
SCOPE_PATCH = ROOT / "config/aidd-scoped-baseline.patch.yml"
CONTEXT_PATCH = ROOT / "config/aidd-early-compaction.patch.yml"
PROMPT = """请完成刚才已开始的 AIDD 决定材料。你已检索并阅读资料，但上一轮最终输出因 token 上限截断。现在直接综合已取得的证据，停止新的文献搜索和工具探索。

给研究者本人一份完整、简明、可审阅的中文决定材料：当前 Idea State、抗体–抗原与蛋白–配体路线的支持与反证、最小反证实验和公平基线、泛化划分与泄漏核查、本周决定和暂停条件。区分研究者想法、私人批注、论文结果与你的推断。关键事实给出已读取来源的笔记行号、批注页码或论文 PDF 页码；未见正文或缺少原始数据时明确标记。不要声称已经验证泄漏或获得研究者批准。控制在约 2000–3000 汉字，以“【材料结束】”结束。"""


def remaining() -> tuple[str, int, Decimal]:
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location("aidd_context", ROOT / "scripts/run-aidd-context-baseline.py")
    assert spec and spec.loader
    original = module_from_spec(spec)
    spec.loader.exec_module(original)
    details = original.preview()
    approval = json.loads((BASE / "context-baseline-approval.json").read_text(encoding="utf-8"))
    checked = ("scope_sha256", "prompt_sha256", "scope_patch_sha256",
               "context_patch_sha256", "model", "max_agent_requests",
               "budget_cap_usd", "output")
    if approval.get("approved") is not True or any(approval.get(k) != details[k] for k in checked):
        raise ValueError("context-baseline approval changed")
    metrics = json.loads((PARENT / "agent-metrics.json").read_text(encoding="utf-8"))
    if metrics.get("status") != "incomplete" or metrics.get("finish_reason") != "max-tokens":
        raise ValueError("parent is not a truncated answer")
    rows = [json.loads(line) for line in (PARENT / "budget-ledger.jsonl").read_text(
        encoding="utf-8").splitlines() if line.strip()]
    requests = [row for row in rows if "request_id" in row]
    if len(requests) < int(metrics["model_requests"]):
        raise ValueError("parent ledger has fewer requests than observed messages")
    requests_left = 30 - int(metrics["started_agent_requests"])
    reserved = sum((Decimal(str(row["reserved_upper_usd"])) for row in requests), Decimal(0))
    usd_left = Decimal("2") - reserved
    if requests_left < 1 or usd_left <= 0:
        raise ValueError("original approval is exhausted")
    session_id = metrics["session_id"]
    session_file = ROOT / ".local/dsh/storages/session_projcache/sessions" / f"{session_id}.json"
    if not session_file.is_file():
        raise ValueError("original DSH session is unavailable")
    return session_id, requests_left, usd_left


def save(name: str, text: str) -> None:
    path = OUT / name
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--call-model", action="store_true")
    args = parser.parse_args()
    session_id, requests_left, usd_left = remaining()
    print(json.dumps({"status": "approval_check" if args.call_model else "preview_only",
                      "remaining_agent_requests": requests_left,
                      "remaining_approved_usd": str(usd_left),
                      "call_model_requested": args.call_model}), flush=True)
    if not args.call_model:
        return 0
    require_budget_gate()
    if Decimal(os.environ["SSS_BUDGET_CAP_USD"]) > usd_left:
        parser.error("continuation gate exceeds the original remaining approval")

    from deepseek_harness import DeepSeekHarness

    OUT.mkdir(parents=True, exist_ok=True)
    OUT.chmod(0o700)
    if (OUT / "agent-events.jsonl").exists() or (OUT / "agent-answer.md").exists():
        parser.error("continuation output already exists")
    fd = os.open(OUT / "paid-attempt.marker", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write("same approved trial, remaining budget only\n")
    save("agent-prompt.txt", PROMPT + "\n")
    guard = NativeBudgetGuard(max_model_requests=requests_left,
                              max_observed_input_tokens=1_000_000)
    os.environ.update({"SSS_MCP_PYTHON": str(ROOT / ".venv312/bin/python"),
                       "SSS_PROJECT_ROOT": str(ROOT),
                       "SSS_RESEARCH_SCOPE_FILE": str(SCOPE)})
    started = time.monotonic()

    def observe(notification):
        if getattr(notification, "method", None) != "session.event":
            return
        event = getattr(notification, "payload", {}).get("event")
        if isinstance(event, dict):
            with (OUT / "agent-events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            (OUT / "agent-events.jsonl").chmod(0o600)
        guard.on_notification(notification)

    try:
        with DeepSeekHarness(
            provider="deepseek-official", model="deepseek-flash", reasoning_effort="off",
            max_tokens=8000, cwd=str(PARENT), runtime_cwd=str(PARENT),
            dsh_bin=str(ROOT / "node_modules/.bin/dsh"), profile="sss-native-resume-sdk",
            patches=(str(SCOPE_PATCH), str(CONTEXT_PATCH)),
            dsh_home=str(ROOT / ".local/dsh"), request_timeout_seconds=900,
        ) as harness:
            result = harness.run(PROMPT, session_id=session_id, on_notification=observe)
        save("agent-answer.md", result.final_response)
        metrics = {"status": "done" if result.finish_reason == "completed"
                   and result.final_response.strip() else "incomplete",
                   "finish_reason": result.finish_reason, "session_id": session_id,
                   "elapsed_seconds": round(time.monotonic() - started, 3),
                   "started_agent_requests": guard.started_requests,
                   "compaction_summaries": sum(
                       event.get("type") == "compaction/summary" for event in guard.events),
                   **_usage(guard.events)}
    except Exception as exc:
        metrics = {"status": "budget_stopped" if isinstance(exc, NativeBudgetExceeded) else "error",
                   "error_type": type(exc).__name__, "error": str(exc)[:300],
                   "session_id": session_id,
                   "elapsed_seconds": round(time.monotonic() - started, 3),
                   "started_agent_requests": guard.started_requests,
                   "compaction_summaries": sum(
                       event.get("type") == "compaction/summary" for event in guard.events),
                   **_usage(guard.events)}
    save("agent-metrics.json", json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: metrics[key] for key in
                      ("status", "finish_reason", "started_agent_requests",
                       "compaction_summaries", "elapsed_seconds") if key in metrics},
                     ensure_ascii=False), flush=True)
    return 0 if metrics["status"] == "done" else 2


if __name__ == "__main__":
    raise SystemExit(main())
