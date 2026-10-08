#!/usr/bin/env python3
"""Freeze or run one paid read-only Agent case on the SSS synthetic test calendar."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
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

DOCTOR_PATH = ROOT / "scripts/doctor-mcp.py"
SPEC = importlib.util.spec_from_file_location("sss_doctor_mcp", DOCTOR_PATH)
assert SPEC and SPEC.loader
DOCTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DOCTOR)

OUT = ROOT / ".local/benchmarks/mcp-app-internal-v2/calendar"
BRIDGE = ROOT / "scripts/calendar-scoped-benchmark-mcp.cjs"
CAP_USD = 0.50
MAX_REQUESTS = 10
MAX_OUTPUT = 1600
TASKS = {
    "A": ("2026-10-12", "60 分钟", "10:00–12:00 或 14:00–17:00"),
    "B": ("2026-10-13", "45 分钟", "15:00–17:30"),
    "C": ("2026-10-14", "90 分钟", "09:00–13:00 或 14:00–17:00"),
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def private(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)


def prompt(case: str) -> str:
    day, duration, windows = TASKS[case]
    return (
        "这是专用 SSS MCP Test 测试日历上的合成排期题，所有事件均为无参与者的测试占用，不是真实会议。"
        "请只用本任务提供的日历只读工具查询该测试日历，不能访问其他日历，也不能准备、创建或修改事件。"
        f"按 Asia/Shanghai 时区，在 {day} 的 {windows} 窗口内，为一个连续 {duration} 的讨论找到最早可行时段。"
        "请根据实际返回的事件或忙闲区间给出推荐的开始和结束时间，列出影响选择的占用时段与来源事件 ID；"
        "若工具失败、无法核对时区或不存在可用时段，明确报告，不要猜测。"
    )


def patch_text() -> str:
    disabled = ["plan-mode", "tool-bash", "tool-pwsh", "tool-fs", "tool-fs-search",
                "tool-jobs", "tool-web", "tool-skill", "tool-subagent-control",
                "tool-subagent-list-agents", "tool-subagent", "tool-subagent-fork",
                "tool-workflow", "tool-todo", "tool-goal", "tool-ralph", "session-title-llm"]
    return "".join(f"- id: {name}\n  disabled: true\n" for name in disabled) + (
        "- insert:\n"
        "    - id: sss-calendar-fixture-scoped-mcp\n"
        "      name: '@deepseek-ai/dsh-mcp-client'\n"
        "      config:\n"
        "        serverName: calendar_fixture\n"
        "        transport: stdio\n"
        "        command: 'node'\n"
        "        args: ['scripts/calendar-scoped-benchmark-mcp.cjs']\n"
        "        cwd: !!js process.env.SSS_PROJECT_ROOT\n"
        "        env:\n"
        "          SSS_BENCH_CALENDAR_ID: !!js process.env.SSS_BENCH_CALENDAR_ID\n"
        "          GOOGLE_OAUTH_CREDENTIALS: !!js process.env.GOOGLE_OAUTH_CREDENTIALS\n"
        "          GOOGLE_CALENDAR_MCP_TOKEN_PATH: !!js process.env.GOOGLE_CALENDAR_MCP_TOKEN_PATH\n"
        "          HTTPS_PROXY: !!js process.env.HTTPS_PROXY\n"
        "          HTTP_PROXY: !!js process.env.HTTP_PROXY\n"
        "          NO_PROXY: !!js process.env.NO_PROXY\n"
        "          NODE_OPTIONS: !!js process.env.NODE_OPTIONS\n"
        "        failOnStartupError: true\n"
    )


def preview(case: str) -> dict:
    calendar = json.loads((ROOT / ".local/google-calendar/test-calendar.json").read_text())
    if calendar.get("summary") != "SSS MCP Test" or not calendar.get("createdBySSS"):
        raise ValueError("Dedicated test calendar record is missing")
    manifest = json.loads((OUT / "fixture-manifest.json").read_text())
    baseline = json.loads((OUT / "script-baseline.json").read_text())
    if manifest.get("calendarId") != calendar["id"] or baseline.get("status") != "passed":
        raise ValueError("Fixture or script baseline is not verified")
    return {
        "task_id": f"synthetic-calendar-internal-{case.lower()}-development",
        "synthetic_fixture": True, "real_calendar_mcp": True,
        "case": case, "model": "deepseek-flash", "reasoning_effort": "off",
        "budget_cap_usd": CAP_USD, "max_model_requests": MAX_REQUESTS,
        "max_output_tokens_per_request": MAX_OUTPUT,
        "read_only": True, "no_attendees_or_invitations": True,
        "test_calendar_id_sha256": hashlib.sha256(calendar["id"].encode()).hexdigest(),
        "fixture_sha256": sha(OUT / "fixture-manifest.json"),
        "script_baseline_sha256": sha(OUT / "script-baseline.json"),
        "bridge_sha256": sha(BRIDGE),
        "prompt_sha256": hashlib.sha256(prompt(case).encode()).hexdigest(),
        "patch_sha256": hashlib.sha256(patch_text().encode()).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=TASKS, required=True)
    parser.add_argument("--call-model", action="store_true")
    parser.add_argument("--refresh-preview", action="store_true",
                        help="Replace a draft preview only before approval or a paid attempt")
    args = parser.parse_args()
    out = OUT / f"agent-{args.case.lower()}"
    current = preview(args.case)
    files = {out / "PREVIEW.json": json.dumps(current, ensure_ascii=False, indent=2) + "\n",
             out / "PROMPT.txt": prompt(args.case), out / "patch.yml": patch_text()}
    print(json.dumps({**current, "paid_api_requested": args.call_model}, ensure_ascii=False), flush=True)
    if not args.call_model:
        if args.refresh_preview and ((out / "APPROVAL.json").exists() or
                                     (out / "paid-attempt.marker").exists()):
            parser.error("Cannot refresh an approved or attempted preview")
        for path, value in files.items():
            if path.is_file() and path.read_text(encoding="utf-8") != value:
                if not args.refresh_preview:
                    parser.error(f"Frozen {path.name} differs")
                private(path, value)
            elif not path.is_file():
                private(path, value)
        return 0
    approval_path = out / "APPROVAL.json"
    if not approval_path.is_file() or not all(path.is_file() for path in files):
        parser.error("Frozen preview and exact task approval required")
    approved = json.loads(approval_path.read_text(encoding="utf-8"))
    if (any(path.read_text(encoding="utf-8") != value for path, value in files.items())
            or approved.get("approved") is not True
            or approved.get("preview_sha256") != sha(out / "PREVIEW.json")
            or approved.get("budget_cap_usd") != CAP_USD):
        parser.error("Approval does not match frozen preview")
    require_budget_gate()
    if float(os.environ["SSS_BUDGET_CAP_USD"]) > CAP_USD:
        parser.error("Active cost gate exceeds task cap")
    marker = out / "paid-attempt.marker"
    with marker.open("x", encoding="utf-8") as stream:
        stream.write("one approved synthetic calendar attempt reserved\n")
    marker.chmod(0o600)
    calendar = json.loads((ROOT / ".local/google-calendar/test-calendar.json").read_text())
    proxy = DOCTOR._google_proxy_env()
    os.environ.update({key: value for key, value in proxy.items()
                       if key in ("HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "NODE_OPTIONS")})
    os.environ.update({"SSS_PROJECT_ROOT": str(ROOT),
                       "SSS_BENCH_CALENDAR_ID": calendar["id"],
                       "GOOGLE_OAUTH_CREDENTIALS": str(ROOT / ".local/google-calendar/oauth-client.json"),
                       "GOOGLE_CALENDAR_MCP_TOKEN_PATH": str(ROOT / ".local/google-calendar/tokens.json"),
                       "DSH_PERMISSION_MODE": "read-only"})
    from deepseek_harness import DeepSeekHarness
    guard = NativeBudgetGuard(max_model_requests=MAX_REQUESTS,
                              max_observed_input_tokens=150_000)
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
        with DeepSeekHarness(provider="deepseek-official", model="deepseek-flash",
                             reasoning_effort="off", max_tokens=MAX_OUTPUT,
                             cwd=str(out), runtime_cwd=str(out),
                             dsh_bin=str(ROOT / "node_modules/.bin/dsh"), profile="sdk",
                             patches=(str(out / "patch.yml"),), dsh_home=str(ROOT / ".local/dsh"),
                             request_timeout_seconds=300) as harness:
            result = harness.run(prompt(args.case), session_id=f"sss-calendar-{args.case}-{uuid4().hex}",
                                 on_notification=observe)
        private(out / "answer.md", result.final_response)
        status = "completed" if result.finish_reason == "completed" else "incomplete"
    except Exception as exc:
        status = "error"
        private(out / "error.txt", f"{type(exc).__name__}: {str(exc)[:300]}\n")
    metrics = {"status": status, "category": "calendar_fixture", "case": args.case,
               "elapsed_seconds": round(time.monotonic() - started, 3),
               "started_requests": guard.started_requests, **_usage(guard.events)}
    private(out / "metrics.json", json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(metrics, ensure_ascii=False), flush=True)
    return 0 if status == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
