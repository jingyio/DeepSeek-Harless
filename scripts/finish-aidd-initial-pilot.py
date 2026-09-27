#!/usr/bin/env python3
"""Finish an incomplete AIDD answer using only its original approved budget."""

from __future__ import annotations

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
PARENT = BASE / "paid-run-01"
OUT = PARENT / "finish-01"
SCOPE = BASE / "baseline-scope-approved.json"
PATCH = ROOT / "config/aidd-scoped-baseline.patch.yml"
PROMPT = """请完成刚才已经开始的 AIDD 决定材料。你已经完成资料检索与阅读，上一轮在最终输出开头被 token 上限截断。现在直接综合已经取得的证据，停止新的文献搜索和工具探索。

请给研究者本人一份**完整、简明、可审阅**的中文决定材料：当前 Idea State 的真实状态；抗体–抗原与蛋白–配体路线的最强支持、反证及未知；首个最小反证实验、同预算基线、泛化划分和泄漏检查；本周的决定、暂停条件和最有价值的下一项取证。区分研究者想法、个人批注、论文作者声称、已核验实验和你的推断。重要事实给出已读取的笔记行号、Zotero 批注页码或论文 PDF 页码；若某项只见摘要或缺正文，标为待核验。不要伪造数据或宣称研究者已经批准。控制在约 2000–3000 汉字，以“【材料结束】”结束。"""


def remaining() -> tuple[str, int, Decimal]:
    from importlib.util import module_from_spec, spec_from_file_location
    spec = spec_from_file_location("aidd_original", ROOT / "scripts/run-aidd-initial-pilot.py")
    assert spec and spec.loader
    original = module_from_spec(spec)
    spec.loader.exec_module(original)
    original._check_scope(paid=True)
    metrics = json.loads((PARENT / "agent-metrics.json").read_text(encoding="utf-8"))
    if metrics.get("status") != "incomplete" or metrics.get("finish_reason") != "max-tokens":
        raise ValueError("parent run is not the expected incomplete answer")
    ledger_path = PARENT / "budget-ledger.jsonl"
    rows = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    requests = [row for row in rows if "request_id" in row]
    if len(requests) < int(metrics["model_requests"]):
        raise ValueError("parent ledger has fewer requests than model usage")
    requests_left = 30 - len(requests)
    reserved = sum((Decimal(str(row["reserved_upper_usd"])) for row in requests), Decimal(0))
    usd_left = Decimal("2") - reserved
    if requests_left < 1 or usd_left <= 0:
        raise ValueError("original approved request or cost limit is exhausted")
    session_id = (PARENT / "session-id.txt").read_text(encoding="utf-8").strip()
    session_file = ROOT / ".local/dsh/storages/session_projcache/sessions" / f"{session_id}.json"
    if not session_file.is_file():
        raise ValueError("parent DSH session is unavailable")
    return session_id, requests_left, usd_left


def save(name: str, value: str) -> None:
    path = OUT / name
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--call-model", action="store_true")
    args = parser.parse_args()
    session_id, requests_left, usd_left = remaining()
    print(json.dumps({"session_id": session_id, "remaining_requests": requests_left,
                      "remaining_approved_usd": str(usd_left), "paid": args.call_model}), flush=True)
    if not args.call_model:
        return 0
    require_budget_gate()
    if Decimal(os.environ["SSS_BUDGET_CAP_USD"]) > usd_left:
        raise ValueError("continuation gate exceeds unspent approved dollars")
    from deepseek_harness import DeepSeekHarness

    OUT.mkdir(parents=True, exist_ok=True)
    OUT.chmod(0o700)
    if (OUT / "agent-answer.md").exists() or (OUT / "agent-events.jsonl").exists():
        raise ValueError("continuation output already exists")
    fd = os.open(OUT / "paid-attempt.marker", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write("same approved trial, remaining budget only\n")
    save("agent-prompt.txt", PROMPT + "\n")
    guard = NativeBudgetGuard(max_model_requests=requests_left,
                              max_observed_input_tokens=1_000_000)
    started = time.monotonic()
    os.environ.update({"SSS_MCP_PYTHON": str(ROOT / ".venv312/bin/python"),
                       "SSS_PROJECT_ROOT": str(ROOT),
                       "SSS_RESEARCH_SCOPE_FILE": str(SCOPE)})

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
            patches=(str(PATCH),), dsh_home=str(ROOT / ".local/dsh"),
            request_timeout_seconds=900,
        ) as harness:
            result = harness.run(PROMPT, session_id=session_id, on_notification=observe)
        save("agent-answer.md", result.final_response)
        metrics = {"status": "done" if result.finish_reason == "completed" and result.final_response.strip()
                   else "incomplete", "finish_reason": result.finish_reason,
                   "session_id": session_id, "elapsed_seconds": round(time.monotonic() - started, 3),
                   "started_requests": guard.started_requests, **_usage(guard.events)}
    except Exception as exc:
        metrics = {"status": "budget_stopped" if isinstance(exc, NativeBudgetExceeded) else "error",
                   "error_type": type(exc).__name__, "error": str(exc)[:300],
                   "session_id": session_id, "elapsed_seconds": round(time.monotonic() - started, 3),
                   "started_requests": guard.started_requests, **_usage(guard.events)}
    save("agent-metrics.json", json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: metrics[key] for key in ("status", "finish_reason", "started_requests",
                                                   "elapsed_seconds") if key in metrics}), flush=True)
    return 0 if metrics["status"] == "done" else 2


if __name__ == "__main__":
    raise SystemExit(main())
