#!/usr/bin/env python3
"""Preview or run a public-metadata, literature-only Agent development task."""

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
from src.adapters.native_budget import NativeBudgetGuard  # noqa: E402


OUT = ROOT / ".local/benchmarks/mcp-app-internal-v2/literature"
SERVER = ROOT / "src/mcp/literature_discovery_server.py"
CAP_USD = 0.50
MAX_REQUESTS = 12
MAX_OUTPUT = 2500
PROMPT = (
    "请只使用本任务的公开文献发现工具，核查题名为 "
    "'Investigating the volume and diversity of data needed for generalizable "
    "antibody–antigen ΔΔG prediction' 的 2023 年预印本与 2025 年期刊记录。"
    "它们是否可判为同一研究工作的两个出版版本？研究者当前制作文献卡时应优先引用哪个记录？"
    "请列出查得的题名、DOI、日期、来源及足以支持版本关系的元数据；"
    "把仅凭题录不能判断的正文、实验或结果差异明确标为待核对。"
    "提供者不可用时记录失败并酌情使用本工具集内其他公开来源。"
    "不要访问本地文件、私人资料或其他应用，也不要写入任何应用。"
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def private(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)


def patch_text() -> str:
    disabled = ["plan-mode", "tool-bash", "tool-pwsh", "tool-fs", "tool-fs-search",
                "tool-jobs", "tool-web", "tool-skill", "tool-subagent-control",
                "tool-subagent-list-agents", "tool-subagent", "tool-subagent-fork",
                "tool-workflow", "tool-todo", "tool-goal", "tool-ralph", "session-title-llm"]
    text = "".join(f"- id: {name}\n  disabled: true\n" for name in disabled)
    return text + (
        "- insert:\n"
        "    - id: sss-public-literature-mcp\n"
        "      name: '@deepseek-ai/dsh-mcp-client'\n"
        "      config:\n"
        "        serverName: literature_discovery\n"
        "        transport: stdio\n"
        "        command: !!js process.env.SSS_MCP_PYTHON\n"
        "        args: ['-m', 'src.mcp.literature_discovery_server']\n"
        "        cwd: !!js process.env.SSS_PROJECT_ROOT\n"
        "        failOnStartupError: true\n"
    )


def preview() -> dict:
    patch = patch_text()
    return {
        "task_id": "app-internal-literature-aidd-versions-development",
        "category": "literature_discovery", "development_instance": True,
        "model": "deepseek-flash", "reasoning_effort": "off",
        "budget_cap_usd": CAP_USD, "max_model_requests": MAX_REQUESTS,
        "max_output_tokens_per_request": MAX_OUTPUT,
        "read_only": True, "public_sources_only": True,
        "server": "literature_discovery",
        "provider_code_sha256": sha(SERVER),
        "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(),
        "patch_sha256": hashlib.sha256(patch.encode()).hexdigest(),
        "output_dir": str(OUT),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--call-model", action="store_true")
    args = parser.parse_args()
    current = preview()
    patch = patch_text()
    files = {OUT / "PROMPT.txt": PROMPT, OUT / "patch.yml": patch,
             OUT / "PREVIEW.json": json.dumps(current, ensure_ascii=False, indent=2) + "\n"}
    print(json.dumps({**current, "paid_api_requested": args.call_model}, ensure_ascii=False), flush=True)
    if not args.call_model:
        for path, value in files.items():
            if path.is_file() and path.read_text(encoding="utf-8") != value:
                parser.error(f"frozen {path.name} differs")
            if not path.is_file():
                private(path, value)
        return 0
    approval_file = OUT / "APPROVAL.json"
    if not approval_file.is_file() or not all(path.is_file() for path in files):
        parser.error("frozen preview and explicit task approval required")
    approved = json.loads(approval_file.read_text(encoding="utf-8"))
    if (any(path.read_text(encoding="utf-8") != value for path, value in files.items())
            or approved.get("approved") is not True
            or approved.get("preview_sha256") != sha(OUT / "PREVIEW.json")
            or approved.get("budget_cap_usd") != CAP_USD):
        parser.error("task approval does not match this exact preview")
    require_budget_gate()
    if float(os.environ["SSS_BUDGET_CAP_USD"]) > CAP_USD:
        parser.error("active cost gate exceeds the task cap")
    marker = OUT / "paid-attempt.marker"
    with marker.open("x", encoding="utf-8") as stream:
        stream.write("one approved literature development attempt reserved\n")
    marker.chmod(0o600)
    os.environ.update({"SSS_MCP_PYTHON": str(ROOT / ".venv312/bin/python"),
                       "SSS_PROJECT_ROOT": str(ROOT), "DSH_PERMISSION_MODE": "read-only"})
    from deepseek_harness import DeepSeekHarness

    guard = NativeBudgetGuard(max_model_requests=MAX_REQUESTS,
                              max_observed_input_tokens=200_000)
    events_file = OUT / "agent-events.jsonl"

    def observe(notification) -> None:
        if getattr(notification, "method", None) != "session.event":
            return
        event = getattr(notification, "payload", {}).get("event")
        if isinstance(event, dict):
            with events_file.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            events_file.chmod(0o600)
        guard.on_notification(notification)

    started = time.monotonic()
    try:
        with DeepSeekHarness(
            provider="deepseek-official", model="deepseek-flash",
            reasoning_effort="off", max_tokens=MAX_OUTPUT,
            cwd=str(OUT), runtime_cwd=str(OUT),
            dsh_bin=str(ROOT / "node_modules/.bin/dsh"), profile="sdk",
            patches=(str(OUT / "patch.yml"),), dsh_home=str(ROOT / ".local/dsh"),
            request_timeout_seconds=300,
        ) as harness:
            result = harness.run(PROMPT, session_id=f"sss-app-literature-{uuid4().hex}",
                                 on_notification=observe)
        private(OUT / "answer.md", result.final_response)
        status = "completed" if result.finish_reason == "completed" else "incomplete"
    except Exception as exc:
        status = "error"
        private(OUT / "error.txt", f"{type(exc).__name__}: {str(exc)[:300]}\n")
    metrics = {"status": status, "category": "literature_discovery",
               "elapsed_seconds": round(time.monotonic() - started, 3),
               "started_requests": guard.started_requests, **_usage(guard.events)}
    private(OUT / "metrics.json", json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(metrics, ensure_ascii=False), flush=True)
    return 0 if status == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
