#!/usr/bin/env python3
"""Use only the unspent part of the approved Model RSI continuation budget."""

from __future__ import annotations

import argparse
import hashlib
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

PARENT = ROOT / ".local/benchmarks/research-weekly-loop/model-rsi-first-pilot"
CONTINUATION = PARENT / "continuation-01"
OUT = CONTINUATION / "finish-01"
SCOPE = PARENT / "scope-preview.json"
PATCH = PARENT / "scoped-mcp.patch.yml"
PROMPT = """请继续刚才的 Model RSI 研究任务，并在本轮直接给研究者一份完整、简明、可审阅的中文决定材料。你已经读过四份批准资料和若干论文正文；现在优先综合，不要再扩展文献清单。若一项科学判断缺少可定位正文证据，就如实标为证据缺口，勿用摘要代替正文。

请从结论开始，随后给出：内部能力状态与外部检索／长上下文／重复题记忆的可检验区别；最强支持和反证及准确来源；最小可证伪实验、同预算简单基线、停止条件；哪些是研究者设想、论文作者声称、已验证结果、你的推断。允许结论为暂缓原型。关键判断附本地行号或 PDF 页码、公开论文 ID/版本及 PDF 页码。无需为了凑齐论文而继续搜索，也不要修改笔记、邮件或日历。"""
TAIL_PROMPT = """请从你刚才被 3000 token 上限截断的决定材料继续。前文已经写到“## 4. 可能使原型暂停的停止条件”，第 1 条未完。不要重复前文，不要调用工具或扩展检索。只补齐：停止条件、证据缺口及下一步取证、研究者可执行的简短决定清单。控制在 1200 个汉字以内，并在末尾写“【材料结束】”。若前文某个数字或引文尚未核验，请明确标记需复核，不要新增未经核验的断言。"""


def _save(name: str, content: str) -> None:
    path = OUT / name
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)


def _validate(tail: bool = False) -> tuple[str, int, Decimal]:
    approval = json.loads((CONTINUATION / "APPROVAL.json").read_text(encoding="utf-8"))
    if approval.get("additional_max_requests") != 12 or approval.get("additional_usd_cap") != 1.0:
        raise ValueError("unexpected continuation approval")
    scope = json.loads(SCOPE.read_text(encoding="utf-8"))
    if scope.get("status") != "approved_for_model":
        raise ValueError("sources not approved")
    for row in scope["sources"]:
        path = Path(row["path"]).resolve(strict=True)
        if row.get("external_model_excerpt_allowed") is not True or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("source scope or version changed")
    previous = json.loads((CONTINUATION / "agent-metrics.json").read_text(encoding="utf-8"))
    if previous.get("status") != "incomplete" or previous.get("finish_reason") != "max-tokens":
        raise ValueError("previous continuation is not the expected incomplete turn")
    used_requests = int(previous["model_requests"])
    if tail:
        first_finish = json.loads((CONTINUATION / "finish-01/agent-metrics.json").read_text(encoding="utf-8"))
        if first_finish.get("finish_reason") != "max-tokens" or first_finish.get("model_requests") != 1:
            raise ValueError("first synthesis segment is not the expected truncated output")
        used_requests += int(first_finish["model_requests"])
    requests_left = 12 - used_requests
    if not 1 <= requests_left <= 11:
        raise ValueError("no approved model requests remain")
    ledger = CONTINUATION / "budget-ledger.jsonl"
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != previous["model_requests"] or any(row.get("response_status") != 200 for row in rows):
        raise ValueError("prior budget ledger does not match model request count")
    if tail:
        finish_rows = [json.loads(line) for line in (CONTINUATION / "finish-01/budget-ledger.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        if len(finish_rows) != 1 or any(row.get("response_status") != 200 for row in finish_rows):
            raise ValueError("first synthesis ledger does not match model request count")
        rows.extend(finish_rows)
    reserved = sum((Decimal(str(row["reserved_upper_usd"])) for row in rows), Decimal(0))
    remaining = Decimal("1.0") - reserved
    if remaining <= 0:
        raise ValueError("approved cost ceiling exhausted")
    session_id = (PARENT / "session-id.txt").read_text(encoding="utf-8").strip()
    if not (ROOT / ".local/dsh/storages/session_projcache/sessions" / f"{session_id}.json").is_file():
        raise ValueError("parent DSH session is unavailable")
    return session_id, requests_left, remaining


def main() -> int:
    global OUT, PROMPT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--call-model", action="store_true")
    parser.add_argument("--tail", action="store_true", help="complete a truncated synthesis inside the same approval")
    args = parser.parse_args()
    if args.tail:
        OUT = CONTINUATION / "finish-02"
        PROMPT = TAIL_PROMPT
    session_id, requests_left, remaining = _validate(args.tail)
    print(json.dumps({"session_id": session_id, "requests_left": requests_left,
                      "approved_usd_remaining": str(remaining), "paid": args.call_model}), flush=True)
    if not args.call_model:
        return 0
    require_budget_gate()
    if Decimal(os.environ["SSS_BUDGET_CAP_USD"]) > remaining:
        raise ValueError("new budget gate exceeds the unspent approved amount")
    from deepseek_harness import DeepSeekHarness

    os.environ.update({"SSS_MCP_PYTHON": str(ROOT / ".venv312/bin/python"),
                       "SSS_PROJECT_ROOT": str(ROOT),
                       "SSS_RESEARCH_SCOPE_FILE": str(SCOPE)})
    OUT.mkdir(parents=True, exist_ok=True)
    OUT.chmod(0o700)
    if (OUT / "agent-events.jsonl").exists() or (OUT / "agent-answer.md").exists():
        raise ValueError("finish output already exists")
    fd = os.open(OUT / "paid-attempt.marker", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as marker:
        marker.write("approved remaining-budget completion attempt\n")
    _save("agent-prompt.txt", PROMPT + "\n")
    guard = NativeBudgetGuard(max_model_requests=requests_left, max_observed_input_tokens=700_000)
    started = time.monotonic()

    def observe(notification):
        if getattr(notification, "method", None) != "session.event":
            return
        event = getattr(notification, "payload", {}).get("event")
        if isinstance(event, dict):
            path = OUT / "agent-events.jsonl"
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            path.chmod(0o600)
        guard.on_notification(notification)

    try:
        with DeepSeekHarness(
            provider="deepseek-official", model="deepseek-flash", reasoning_effort="off",
            max_tokens=3000, cwd=str(PARENT), runtime_cwd=str(PARENT),
            dsh_bin=str(ROOT / "node_modules/.bin/dsh"), profile="sss-native-resume-sdk",
            patches=(str(PATCH),), dsh_home=str(ROOT / ".local/dsh"),
            request_timeout_seconds=900,
        ) as harness:
            result = harness.run(PROMPT, session_id=session_id, on_notification=observe)
        _save("agent-answer.md", result.final_response)
        metrics = {"status": "done" if result.final_response.strip() and result.finish_reason == "completed" else "incomplete",
                   "finish_reason": result.finish_reason, "session_id": session_id,
                   "elapsed_seconds": round(time.monotonic() - started, 3),
                   "started_requests": guard.started_requests, **_usage(guard.events)}
    except Exception as exc:
        metrics = {"status": "budget_stopped" if isinstance(exc, NativeBudgetExceeded) else "error",
                   "error_type": type(exc).__name__, "error": str(exc)[:300], "session_id": session_id,
                   "elapsed_seconds": round(time.monotonic() - started, 3),
                   "started_requests": guard.started_requests, **_usage(guard.events)}
    _save("agent-metrics.json", json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(metrics, ensure_ascii=False), flush=True)
    return 0 if metrics["status"] == "done" else 2


if __name__ == "__main__":
    raise SystemExit(main())
