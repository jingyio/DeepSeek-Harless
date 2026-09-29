#!/usr/bin/env python3
"""Preview or run one scoped, real research-alert intake baseline."""

from __future__ import annotations

import argparse
import hashlib
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

BASE = ROOT / ".local/benchmarks/research-intake-20260929"
CASES = BASE / "cases.json"
SCOPE = BASE / "note-scope.json"
CAP_USD = 0.50
MAX_REQUESTS = 12
MAX_OUTPUT = 2500


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def save(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)


def patch_text() -> str:
    disabled = (
        "plan-mode", "tool-bash", "tool-pwsh", "tool-fs", "tool-fs-search",
        "tool-jobs", "tool-web", "tool-skill", "tool-subagent-control",
        "tool-subagent-list-agents", "tool-subagent", "tool-subagent-fork",
        "tool-workflow", "tool-todo", "tool-goal", "tool-ralph",
        "session-title-llm",
    )
    prefix = "".join(f"- id: {name}\n  disabled: true\n" for name in disabled)
    return prefix + """- insert:
    - id: sss-intake-gmail
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: scoped_gmail_request
        transport: stdio
        command: node
        args: ['scripts/gmail-guarded-mcp.cjs']
        cwd: !!js process.env.SSS_PROJECT_ROOT
        env:
          GMAIL_OAUTH_PATH: !!js process.env.SSS_GOOGLE_GMAIL_OAUTH
          GMAIL_CREDENTIALS_PATH: !!js process.env.SSS_GOOGLE_GMAIL_TOKENS
          GMAIL_MCP_STATE_DIR: !!js process.env.SSS_GOOGLE_GMAIL_STATE
          GMAIL_MCP_DRY_RUN: 'true'
          SSS_NO_OPEN: '1'
          SSS_GMAIL_TOOL_ALLOWLIST: 'search_emails,read_email'
          SSS_GMAIL_ALLOWED_QUERY: !!js process.env.SSS_GMAIL_ALLOWED_QUERY
          SSS_GMAIL_ALLOWED_MESSAGE_ID: !!js process.env.SSS_GMAIL_ALLOWED_MESSAGE_ID
          SSS_GMAIL_REQUIRE_UNIQUE_SEARCH_READ: '1'
        failOnStartupError: true
    - id: sss-intake-literature
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: literature_discovery
        transport: stdio
        command: !!js process.env.SSS_MCP_PYTHON
        args: ['-m', 'src.mcp.literature_discovery_server']
        cwd: !!js process.env.SSS_PROJECT_ROOT
        failOnStartupError: true
    - id: sss-intake-notes
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: scoped_research_read
        transport: stdio
        command: !!js process.env.SSS_MCP_PYTHON
        args: ['-m', 'src.mcp.scoped_obsidian_read_server']
        cwd: !!js process.env.SSS_PROJECT_ROOT
        env:
          SSS_RESEARCH_SCOPE_FILE: !!js process.env.SSS_RESEARCH_SCOPE_FILE
          SSS_SCOPED_HANDLE_MODE: '1'
        failOnStartupError: true
"""


def prompt_for(case: dict) -> str:
    return (
        "你在帮研究者处理一封实际收到的 Google Scholar 提醒，决定其中是否有一篇论文"
        "值得本周进一步阅读。当前研究问题：" + case["focus"] + "\n"
        "本任务只批准 Gmail 查询：" + case["query"] + "。"
        "仅当搜索结果唯一时读取该邮件。你可自行使用公开文献发现工具，"
        "以及本任务已批准的 Obsidian 当前状态笔记；不需要为了增加工具调用而访问无关资料。"
        "从邮件中选择至多一篇最值得核查的候选，用公开题录确认其身份、版本及可获取的"
        "原文范围；若没有合适候选，说明原因和仍未核实之处。"
        "交付一张中文待审阅读决定卡：候选、与当前问题的关系、已核实来源、尚缺证据、"
        "建议读或暂缓及下一步。邮件摘要与题录不能充当论文实验结果；没有读到正文时"
        "不得声称验证了方法或数字。不得写入 Zotero、Obsidian，不得发邮件或创建日程。"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    parser.add_argument("--attempt", default="primary")
    parser.add_argument("--call-model", action="store_true")
    args = parser.parse_args()
    if args.attempt != "primary" and not re.fullmatch(r"retry-[1-9][0-9]*", args.attempt):
        parser.error("attempt must be primary or retry-N")
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    if args.case not in cases:
        parser.error("unknown frozen case")
    case = cases[args.case]
    scope = json.loads(SCOPE.read_text(encoding="utf-8"))
    if (scope.get("status") != "approved_for_model"
            or len(scope.get("sources", [])) != 2
            or {row.get("role") for row in scope["sources"]}
            != {"current_state", "open_questions"}):
        parser.error("expected exactly two approved Model RSI notes")
    for row in scope["sources"]:
        source = Path(row["path"]).resolve(strict=True)
        if (not row.get("vault_path") or row.get("external_model_excerpt_allowed") is not True
                or digest(source.read_bytes()) != row.get("sha256")):
            parser.error("approved note version or access changed")
    oauth = ROOT / ".local/google-gmail/oauth-client.json"
    if not oauth.is_file():
        oauth = ROOT / ".local/google-calendar/oauth-client.json"
    tokens = ROOT / ".local/google-gmail/tokens.json"
    oauth.resolve(strict=True)
    tokens.resolve(strict=True)
    patch = patch_text()
    prompt = prompt_for(case)
    output = BASE / args.case / ("baseline" if args.attempt == "primary"
                                 else f"baseline-{args.attempt}")
    preview = {
        "case": args.case, "model": "deepseek-flash", "reasoning_effort": "off",
        "read_only": True, "max_model_requests": MAX_REQUESTS,
        "max_output_tokens_per_request": MAX_OUTPUT,
        "budget_cap_usd": CAP_USD,
        "query_sha256": digest(case["query"].encode()),
        "message_id_sha256": digest(case["message_id"].encode()),
        "prompt_sha256": digest(prompt.encode()),
        "patch_sha256": digest(patch.encode()),
        "note_scope_sha256": digest(SCOPE.read_bytes()),
        "paid_api_requested": args.call_model,
    }
    print(json.dumps(preview, ensure_ascii=False), flush=True)
    if not args.call_model:
        return 0
    require_budget_gate()
    if float(os.environ["SSS_BUDGET_CAP_USD"]) > CAP_USD:
        parser.error("active cost gate exceeds frozen task cap")
    from deepseek_harness import DeepSeekHarness

    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    marker = output / "paid-attempt.marker"
    with marker.open("x", encoding="utf-8") as stream:
        stream.write("one real, read-only research intake baseline\n")
    marker.chmod(0o600)
    patch_path = output / "patch.yml"
    save(patch_path, patch)
    save(output / "prompt.md", prompt)
    save(output / "preview.json", json.dumps(preview, ensure_ascii=False, indent=2) + "\n")
    os.environ.update({
        "SSS_PROJECT_ROOT": str(ROOT),
        "SSS_MCP_PYTHON": str(ROOT / ".venv312/bin/python"),
        "SSS_RESEARCH_SCOPE_FILE": str(SCOPE),
        "SSS_GOOGLE_GMAIL_OAUTH": str(oauth),
        "SSS_GOOGLE_GMAIL_TOKENS": str(tokens),
        "SSS_GOOGLE_GMAIL_STATE": str(ROOT / ".local/google-gmail"),
        "SSS_GMAIL_ALLOWED_QUERY": case["query"],
        "SSS_GMAIL_ALLOWED_MESSAGE_ID": case["message_id"],
    })
    events_path = output / "agent-events.jsonl"
    guard = NativeBudgetGuard(max_model_requests=MAX_REQUESTS,
                              max_observed_input_tokens=500_000)

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
        with DeepSeekHarness(
            provider="deepseek-official", model="deepseek-flash",
            reasoning_effort="off", max_tokens=MAX_OUTPUT,
            cwd=str(output), runtime_cwd=str(output),
            dsh_bin=str(ROOT / "node_modules/.bin/dsh"), profile="sdk",
            patches=(str(patch_path),), dsh_home=str(ROOT / ".local/dsh"),
            request_timeout_seconds=300,
        ) as harness:
            result = harness.run(prompt, session_id=f"sss-intake-{uuid4().hex}",
                                 on_notification=observe)
        save(output / "answer.md", result.final_response)
        status = "done" if result.finish_reason == "completed" and result.final_response.strip() else "incomplete"
    except Exception as exc:
        status = "error"
        save(output / "error.txt", f"{type(exc).__name__}: {str(exc)[:300]}\n")
    metrics = {
        "status": status, "elapsed_seconds": round(time.monotonic() - started, 3),
        "started_requests": guard.started_requests,
        "tool_calls": sum(1 for line in events_path.read_text().splitlines()
                          if json.loads(line).get("type") == "tool/call")
        if events_path.exists() else 0,
        "budget_ledger": os.environ.get("SSS_BUDGET_LEDGER"),
        **_usage(guard.events),
    }
    save(output / "metrics.json", json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output_dir": str(output), **metrics}, ensure_ascii=False), flush=True)
    return 0 if status == "done" else 2


if __name__ == "__main__":
    raise SystemExit(main())
