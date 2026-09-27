#!/usr/bin/env python3
"""Preview or run the first scoped Model RSI research decision trial."""

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
from src.adapters.native_budget import NativeBudgetExceeded, NativeBudgetGuard  # noqa: E402


OUT = ROOT / ".local" / "benchmarks" / "research-weekly-loop" / "model-rsi-first-pilot"
SCOPE = OUT / "scope-preview.json"
PATCH = OUT / "scoped-mcp.patch.yml"
PROMPT = """你是普通 DeepSeek Harness 科研 Agent。研究者正在决定：模型主干之外、跨任务持久且可更新的内部能力状态，是否值得现在做最小原型？第一个反证实验怎样把未来任务的能力变化与外部检索、长上下文和重复题目记忆区分开？允许结论是先不做原型。

你能使用本次试点的 scoped_research_read MCP，只能读取其中列出的已批准资料；也能用 literature_discovery MCP 搜索公开论文并按页读可用的 arXiv PDF 或 Europe PMC 开放全文。请自行判断需要哪些路线和工具，不设最低调用次数。不要读取其他项目或账号资料，不猜测未提供的实验数字，不写用户的 Obsidian/Zotero 笔记，不发邮件或建会。题录和摘要只用于筛选，科学主张需要论文正文证据。若公开接口失败，请记录失败和证据缺口。

交付给研究者一份可审阅的中文决定材料：当前 idea 的准确边界；最强支持与反证；现有方法与该 idea 在更新对象、持久性和未来任务迁移上的可检验区别；一个最小、可证伪的实验及同预算简单基线；可能使原型暂停的停止条件。每条关键判断给出本地资料的角色、行号或 PDF 页码，或公开论文的 ID、版本和 PDF 页码。明确区分研究者原有想法、论文作者声称、实测证据和你的推断。若来源不足，写清下一个最有价值的取证行动。不要声称这份报告已被研究者验收。"""


def _scope() -> dict:
    data = json.loads(SCOPE.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("sources"), list):
        raise ValueError("invalid trial scope")
    for row in data["sources"]:
        path = Path(row["path"]).resolve(strict=True)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("selected research source changed since preview")
    return data


def _save(name: str, content: str) -> None:
    path = OUT / name
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--call-model", action="store_true",
                        help="paid run; requires approved scope and local budget gate")
    args = parser.parse_args()
    scope = _scope()
    summary = {"status": scope.get("status"), "roles": [row["role"] for row in scope["sources"]],
               "model": "deepseek-flash", "max_requests": 20,
               "max_output_tokens_per_request": 3000, "max_observed_input_tokens": 1_500_000,
               "paid": args.call_model}
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    if not args.call_model:
        return 0
    if (scope.get("status") != "approved_for_model"
            or not all(row.get("external_model_excerpt_allowed") is True
                       for row in scope["sources"])):
        raise ValueError("researcher approval for every source is required")
    require_budget_gate()
    if float(os.environ["SSS_BUDGET_CAP_USD"]) > 2.0:
        raise ValueError("this trial's approved USD cap is at most 2")
    from deepseek_harness import DeepSeekHarness

    os.environ.update({"SSS_MCP_PYTHON": str(ROOT / ".venv312/bin/python"),
                       "SSS_PROJECT_ROOT": str(ROOT),
                       "SSS_RESEARCH_SCOPE_FILE": str(SCOPE)})
    OUT.mkdir(parents=True, exist_ok=True)
    OUT.chmod(0o700)
    if (OUT / "agent-events.jsonl").exists() or (OUT / "agent-answer.md").exists():
        raise ValueError("trial output already exists; use a new task instance")
    attempt = OUT / "paid-attempt.marker"
    fd = os.open(attempt, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as marker:
        marker.write("one paid attempt reserved\n")
    _save("agent-prompt.txt", PROMPT + "\n")
    session_id = "sss-model-rsi-pilot-" + uuid4().hex
    _save("session-id.txt", session_id + "\n")
    guard = NativeBudgetGuard(max_model_requests=20,
                              max_observed_input_tokens=1_500_000)
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
            provider="deepseek-official", model="deepseek-flash", reasoning_effort="off",
            max_tokens=3000, cwd=str(OUT), runtime_cwd=str(OUT),
            dsh_bin=str(ROOT / "node_modules/.bin/dsh"), profile="sdk",
            patches=(str(PATCH),), dsh_home=str(ROOT / ".local/dsh"),
            request_timeout_seconds=900,
        ) as harness:
            result = harness.run(PROMPT, session_id=session_id, on_notification=observe)
        _save("agent-answer.md", result.final_response)
        metrics = {"status": "done", "finish_reason": result.finish_reason,
                   "session_id": session_id,
                   "elapsed_seconds": round(time.monotonic() - started, 3),
                   "started_requests": guard.started_requests, **_usage(guard.events)}
    except Exception as exc:
        metrics = {"status": "budget_stopped" if isinstance(exc, NativeBudgetExceeded) else "error",
                   "error_type": type(exc).__name__, "error": str(exc)[:300],
                   "session_id": session_id,
                   "elapsed_seconds": round(time.monotonic() - started, 3),
                   "started_requests": guard.started_requests, **_usage(guard.events)}
    _save("agent-metrics.json", json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(metrics, ensure_ascii=False), flush=True)
    return 0 if metrics["status"] == "done" else 2


if __name__ == "__main__":
    raise SystemExit(main())
