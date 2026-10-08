"""Preview or run one scoped, real-application Agent baseline.

This intentionally collects natural trajectories before any new Motif is
compiled. Every paid attempt needs a frozen preview and task approval record.
"""

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
from src.mcp.scoped_zotero_read_server import _verified as verify_zotero  # noqa: E402


BASE = ROOT / ".local/benchmarks/mcp-app-internal-v2"
SCOPE = ROOT / ".local/benchmarks/research-weekly-loop/paper-impact-p1-20260927/source-scope.json"
SOURCE_APPROVAL = SCOPE.parent / "APPROVAL.json"
CAP_USD = 0.50
MAX_REQUESTS = 12
MAX_OUTPUT = 2500

TASKS = {
    "zotero": {
        "server": "scoped_zotero_read",
        "module": "src.mcp.scoped_zotero_read_server",
        "scope_roles": ["antibody_item", *(f"antibody_annotation_{n}" for n in range(1, 7))],
        "prompt": (
            "请仅使用本任务授权的 Zotero 只读工具，检查一篇论文条目及研究者的六条批注。"
            "列出批注各自指出的证据、疑问或限制；区分论文原文与研究者解释，"
            "说明哪一项最需要回到论文正文核对。每项引用 Zotero 条目或批注角色。"
            "不访问其他应用，不写入 Zotero；仅凭批注不足以确定论文结论时明确说明。"
        ),
    },
    "obsidian": {
        "server": "scoped_research_read",
        "module": "src.mcp.scoped_obsidian_read_server",
        "scope_roles": ["current_state", "open_questions"],
        "prompt": (
            "请仅使用本任务授权的 Obsidian 只读工具，读取 current_state 与 open_questions 的批准摘录。"
            "给出当前研究判断、已经否决或收窄的说法、仍缺的两项关键证据，以及下一项最小核查行动。"
            "每个事实附笔记角色和行号；不能访问批准行段之外的内容，不写回笔记。"
            "若摘录不足以回答某项，标为未确定。"
        ),
    },
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def private(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)


def check_scope(category: str) -> str:
    scope = json.loads(SCOPE.read_text(encoding="utf-8"))
    approval = json.loads(SOURCE_APPROVAL.read_text(encoding="utf-8"))
    if (scope.get("status") != "approved_for_model" or approval.get("approved") is not True
            or approval.get("scope_sha256") != sha(SCOPE)):
        raise ValueError("previous approved source scope is unavailable or changed")
    rows = scope["zotero_sources"] if category == "zotero" else scope["sources"]
    selected = [row for row in rows if row.get("role") in TASKS[category]["scope_roles"]]
    if ({row["role"] for row in selected} != set(TASKS[category]["scope_roles"])
            or any(row.get("external_model_excerpt_allowed") is not True for row in selected)):
        raise ValueError("required roles are not approved for external model access")
    for row in selected:
        if category == "zotero":
            verify_zotero(row)
        path = row.get("path")
        if category == "obsidian" and (not path or sha(Path(path)) != row.get("sha256")):
            raise ValueError("approved note version changed")
        if category == "obsidian" and not row.get("allowed_line_ranges"):
            raise ValueError("approved note has no line bounds")
    return sha(SCOPE)


def patch_text(category: str) -> str:
    task = TASKS[category]
    disabled = ["plan-mode", "tool-bash", "tool-pwsh", "tool-fs", "tool-fs-search",
                "tool-jobs", "tool-web", "tool-skill", "tool-subagent-control",
                "tool-subagent-list-agents", "tool-subagent", "tool-subagent-fork",
                "tool-workflow", "tool-todo", "tool-goal", "tool-ralph", "session-title-llm"]
    text = "".join(f"- id: {name}\n  disabled: true\n" for name in disabled)
    text += (
        "- insert:\n"
        "    - id: sss-app-internal-scoped-read-mcp\n"
        "      name: '@deepseek-ai/dsh-mcp-client'\n"
        "      config:\n"
        f"        serverName: {task['server']}\n"
        "        transport: stdio\n"
        "        command: !!js process.env.SSS_MCP_PYTHON\n"
        f"        args: ['-m', '{task['module']}']\n"
        "        cwd: !!js process.env.SSS_PROJECT_ROOT\n"
        "        env:\n"
        "          SSS_RESEARCH_SCOPE_FILE: !!js process.env.SSS_RESEARCH_SCOPE_FILE\n"
        "          SSS_SCOPED_HANDLE_MODE: '1'\n"
        + ("          SSS_SCOPED_NOTES_ONLY: '1'\n" if category == "obsidian" else "") +
        "        failOnStartupError: true\n"
    )
    return text


def preview(category: str, out: Path) -> dict:
    task = TASKS[category]
    scope_digest = check_scope(category)
    patch = patch_text(category)
    prompt = task["prompt"]
    return {"task_id": f"app-internal-{category}-aidd-development",
            "category": category, "development_instance": True,
            "model": "deepseek-flash", "reasoning_effort": "off",
            "budget_cap_usd": CAP_USD, "max_model_requests": MAX_REQUESTS,
            "max_output_tokens_per_request": MAX_OUTPUT,
            "read_only": True, "server": task["server"],
            "source_roles": task["scope_roles"], "source_scope_sha256": scope_digest,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "patch_sha256": hashlib.sha256(patch.encode()).hexdigest(),
            "output_dir": str(out)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--category", choices=TASKS, required=True)
    parser.add_argument("--call-model", action="store_true")
    args = parser.parse_args()
    out = BASE / args.category
    current = preview(args.category, out)
    patch = patch_text(args.category)
    prompt = TASKS[args.category]["prompt"]
    preview_file, patch_file, prompt_file = (out / "PREVIEW.json", out / "patch.yml",
                                            out / "PROMPT.txt")
    print(json.dumps({**current, "paid_api_requested": args.call_model}, ensure_ascii=False),
          flush=True)
    if not args.call_model:
        for path, value in ((patch_file, patch), (prompt_file, prompt)):
            if path.is_file() and path.read_text(encoding="utf-8") != value:
                parser.error(f"frozen {path.name} differs")
            if not path.is_file():
                private(path, value)
        if preview_file.is_file() and json.loads(preview_file.read_text()) != current:
            parser.error("frozen preview differs")
        if not preview_file.is_file():
            private(preview_file, json.dumps(current, ensure_ascii=False, indent=2) + "\n")
        return 0
    approval_file = out / "APPROVAL.json"
    if not all(path.is_file() for path in (preview_file, patch_file, prompt_file, approval_file)):
        parser.error("frozen preview and task approval required")
    approved = json.loads(approval_file.read_text(encoding="utf-8"))
    if (json.loads(preview_file.read_text()) != current or
            patch_file.read_text() != patch or prompt_file.read_text() != prompt or
            approved.get("approved") is not True or
            approved.get("preview_sha256") != sha(preview_file) or
            approved.get("budget_cap_usd") != CAP_USD):
        parser.error("task approval does not match this exact preview")
    require_budget_gate()
    if float(os.environ["SSS_BUDGET_CAP_USD"]) > CAP_USD:
        parser.error("active cost gate exceeds the task cap")
    marker = out / "paid-attempt.marker"
    with marker.open("x", encoding="utf-8") as stream:
        stream.write("one approved app-internal baseline attempt reserved\n")
    marker.chmod(0o600)
    os.environ.update({"SSS_MCP_PYTHON": str(ROOT / ".venv312/bin/python"),
                       "SSS_PROJECT_ROOT": str(ROOT),
                       "SSS_RESEARCH_SCOPE_FILE": str(SCOPE),
                       "DSH_PERMISSION_MODE": "read-only"})
    from deepseek_harness import DeepSeekHarness

    guard = NativeBudgetGuard(max_model_requests=MAX_REQUESTS,
                              max_observed_input_tokens=200_000)
    events_file = out / "agent-events.jsonl"

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
            cwd=str(out), runtime_cwd=str(out),
            dsh_bin=str(ROOT / "node_modules/.bin/dsh"), profile="sdk",
            patches=(str(patch_file),), dsh_home=str(ROOT / ".local/dsh"),
            request_timeout_seconds=300,
        ) as harness:
            result = harness.run(prompt, session_id=f"sss-app-internal-{args.category}-{uuid4().hex}",
                                 on_notification=observe)
        private(out / "answer.md", result.final_response)
        status = "completed" if result.finish_reason == "completed" else "incomplete"
    except Exception as exc:
        status = "error"
        private(out / "error.txt", f"{type(exc).__name__}: {str(exc)[:300]}\n")
    metrics = {"status": status, "category": args.category,
               "elapsed_seconds": round(time.monotonic() - started, 3),
               "started_requests": guard.started_requests, **_usage(guard.events)}
    private(out / "metrics.json", json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(metrics, ensure_ascii=False), flush=True)
    return 0 if status == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
