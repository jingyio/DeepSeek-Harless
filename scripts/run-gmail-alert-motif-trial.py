#!/usr/bin/env python3
"""Run one private, budget-gated Google Scholar alert triage task."""

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

BASE = ROOT / ".local/benchmarks/research-weekly-loop/gmail-alert-motif-20260928"
BASE_PATCH = ROOT / "config/gmail-alert-read.patch.yml"
PREPARE = ROOT / "scripts/prepare-online-motif.py"


def write_private(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def prompt_for(query: str, version: int = 1) -> str:
    if version == 2:
        return (
            "请为研究者分拣一封真实的 Google Scholar 论文提醒。仅使用 Gmail MCP 搜索和读取；"
            "不访问网页，不写入应用，不发送邮件。\n"
            f"精确使用查询：{query}\n"
            "仅在恰好一封时读取；否则停止说明。只根据邮件的标题和摘要片段分类："
            "‘直接相关’须明确涉及模型内部能力自评/状态表示，或 Agent 根据反馈自主修订策略、技能；"
            "一般微调、联邦训练、静态记忆或路由只可列为‘相邻参考’，不能列为直接相关。"
            "输出不超过 450 个汉字，严格按以下三行：\n"
            "直接相关：最多 3 个标题，各附邮件中的一个具体线索；没有则写‘无’。\n"
            "相邻参考：最多 2 个标题，各说明缺少什么关键自改进证据；没有则写‘无’。\n"
            "阅读决定：指出最值得打开全文的一篇及原因；若均不值得则写‘暂不优先’。"
            "邮件只是发现线索，不能把摘要当成已核实论文结论。\n"
        )
    if version != 1:
        raise ValueError("unsupported frozen prompt version")
    return (
        "你在为研究者分拣一封真实的 Google Scholar 论文提醒邮件。"
        "只用已提供的 Gmail MCP 工具；不访问网页，不写入应用，也不发送邮件。\n"
        f"精确使用这个查询：{query}\n"
        "若搜索结果恰好一封，读取该邮件；若不是一封，停止并说明需要选择。"
        "只依据邮件实际内容，列出至多三篇与模型内部能力状态、模型自我改进或 Agent "
        "自我改进直接相关的论文。若没有明确相关的论文，回答‘未发现明确相关论文’。"
        "对每篇给出邮件中的标题、支持相关性的具体线索和是否值得研究者点开全文。"
        "邮件只是发现线索，不要把邮件摘要当成已核实论文结论，也不要猜测未见的原文。\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    parser.add_argument("--mode", choices=["baseline", "motif"], required=True)
    parser.add_argument("--attempt", default="primary",
                        help="use retry-N after a recorded failed attempt")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--call-model", action="store_true")
    args = parser.parse_args()
    if args.attempt != "primary" and not re.fullmatch(r"retry-[1-9][0-9]*", args.attempt):
        parser.error("attempt must be primary or retry-N")
    cases = json.loads((BASE / "cases.json").read_text(encoding="utf-8"))
    selected = cases.get("cases", {}).get(args.case)
    if not selected or selected.get("query") is None:
        parser.error("case is absent from the private frozen manifest")
    if args.mode == "motif" and args.manifest is None:
        parser.error("motif mode requires a certified manifest")
    query = selected["query"]
    if not isinstance(query, str) or len(query) > 300:
        raise ValueError("invalid frozen query")
    prompt_version = selected.get("prompt_version", 1)
    prompt = prompt_for(query, prompt_version)
    prompt_file = BASE / args.case / "prompt.md"
    if prompt_file.exists() and prompt_file.read_text(encoding="utf-8") != prompt:
        raise ValueError("frozen prompt changed")
    if not prompt_file.exists():
        write_private(prompt_file, prompt)
    oauth = ROOT / ".local/google-gmail/oauth-client.json"
    if not oauth.is_file():
        oauth = ROOT / ".local/google-calendar/oauth-client.json"
    gmail = ROOT / ".local/google-gmail"
    for path in (oauth, gmail / "tokens.json", BASE_PATCH):
        path.resolve(strict=True)
    preview = {"case": args.case, "mode": args.mode,
               "attempt": args.attempt,
               "case_role": selected.get("role"),
               "prompt_version": prompt_version,
               "query_sha256": sha(query), "prompt_sha256": sha(prompt),
               "model": "deepseek-flash", "reasoning_effort": "off",
               "allowed_tools": ["search_emails", "read_email"],
               "budget_cap_usd": 2.0, "read_only": True,
               "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest()
               if args.manifest else None,
               "paid_api_requested": args.call_model}
    print(json.dumps(preview, ensure_ascii=False), flush=True)
    if not args.call_model:
        return 0
    require_budget_gate()
    if float(os.environ["SSS_BUDGET_CAP_USD"]) > 2.0:
        raise ValueError("active cost gate exceeds frozen cap")
    from deepseek_harness import DeepSeekHarness

    output = BASE / args.case / (args.mode if args.attempt == "primary"
                                 else f"{args.mode}-{args.attempt}")
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    marker = output / "paid-attempt.marker"
    with marker.open("x", encoding="utf-8") as file:
        file.write("one paid, read-only Gmail alert task\n")
    marker.chmod(0o600)
    session_id = "sss-gmail-alert-" + uuid4().hex
    patches = [str(BASE_PATCH)]
    os.environ.update({"SSS_PROJECT_ROOT": str(ROOT),
                       "SSS_GOOGLE_GMAIL_OAUTH": str(oauth),
                       "SSS_GOOGLE_GMAIL_TOKENS": str(gmail / "tokens.json"),
                       "SSS_GOOGLE_GMAIL_STATE": str(gmail),
                       "SSS_GMAIL_ALLOWED_QUERY": query})
    if args.mode == "motif":
        spec = importlib.util.spec_from_file_location("online_prepare", PREPARE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        search = "mcp__scoped_gmail_request__search_emails"
        read = "mcp__scoped_gmail_request__read_email"
        task = {"schema_version": 1, "task_id": args.case,
                "session_id": session_id,
                "intent": "Read the unique Google Scholar research alert for triage",
                "input_version": "query-" + sha(query),
                "bindings": {search: {"query": query}},
                "source_versions": {search: "@observed", read: "@from_anchor"}}
        task_file = output / "task.json"
        write_private(task_file, json.dumps(task, ensure_ascii=False, indent=2) + "\n")
        prepared = module.prepare(args.manifest, task_file)
        patches.append(prepared["patch"])
        os.environ.update({"SSS_ONLINE_MOTIF_MANIFEST": str(args.manifest.resolve()),
                           "SSS_ONLINE_MOTIF_TASK": str(task_file),
                           "SSS_ONLINE_MOTIF_MODE": "execute",
                           "SSS_ONLINE_MOTIF_PROMPT_SHA256": sha(prompt),
                           "SSS_MOTIF_EMBEDDING_ENDPOINT":
                               "http://127.0.0.1:12345/v1/embeddings",
                           "SSS_MOTIF_EMBEDDING_MODEL": "unused-for-closed-read"})
    write_private(output / "preview.json",
                  json.dumps(preview, ensure_ascii=False, indent=2) + "\n")
    events_path = output / "agent-events.jsonl"
    guard = NativeBudgetGuard(max_model_requests=None,
                              max_observed_input_tokens=None)

    def observe(notification) -> None:
        if getattr(notification, "method", None) != "session.event":
            return
        event = getattr(notification, "payload", {}).get("event")
        if isinstance(event, dict):
            with events_path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(event, ensure_ascii=False) + "\n")
            events_path.chmod(0o600)
        guard.on_notification(notification)

    started = time.monotonic()
    try:
        with DeepSeekHarness(provider="deepseek-official", model="deepseek-flash",
                             reasoning_effort="off", max_tokens=4000,
                             cwd=str(output), runtime_cwd=str(output),
                             dsh_bin=str(ROOT / "node_modules/.bin/dsh"), profile="sdk",
                             patches=tuple(patches), dsh_home=str(ROOT / ".local/dsh"),
                             request_timeout_seconds=900) as harness:
            result = harness.run(prompt, session_id=session_id,
                                 on_notification=observe)
        write_private(output / "answer.md", result.final_response)
        metrics = {"status": "done" if result.finish_reason == "completed"
                   and result.final_response.strip() else "incomplete",
                   "finish_reason": result.finish_reason}
    except Exception as exc:
        metrics = {"status": "error", "error_type": type(exc).__name__,
                   "error": str(exc)[:300]}
    rows = ([json.loads(line) for line in events_path.read_text().splitlines()]
            if events_path.exists() else [])
    tools = [row.get("data", {}).get("name", "") for row in rows
             if row.get("type") == "tool/call"]
    audit = output / ".local/online-motif" / (sha(session_id) + ".jsonl")
    decisions = ([json.loads(line) for line in audit.read_text().splitlines()]
                 if audit.exists() else [])
    metrics.update({"elapsed_seconds": round(time.monotonic() - started, 3),
                    "started_requests": guard.started_requests,
                    "tool_calls_by_name": {name: tools.count(name)
                                           for name in sorted(set(tools))},
                    "motif_bypass_attempts": sum(row.get("kind") == "motif_bypass_attempt"
                                                 for row in decisions),
                    "model_requests_skipped_verified": sum(
                        row.get("kind") == "model_request_skipped_verified"
                        for row in decisions),
                    "budget_ledger": os.environ.get("SSS_BUDGET_LEDGER"),
                    **_usage(guard.events)})
    write_private(output / "metrics.json",
                  json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output_dir": str(output), **metrics}, ensure_ascii=False), flush=True)
    return 0 if metrics["status"] == "done" else 2


if __name__ == "__main__":
    raise SystemExit(main())
