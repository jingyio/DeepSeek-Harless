#!/usr/bin/env python3
"""Run one frozen research portfolio case through budget-gated DeepSeek Harness."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.dsh_client import _usage, require_budget_gate  # noqa: E402
from src.adapters.native_budget import NativeBudgetGuard  # noqa: E402


BENCH = ROOT / "benchmarks/research_decision_portfolio_v1"
PATCH = ROOT / "config/research-decision-portfolio.patch.yml"
CONTRACTS = ROOT / "config/research-portfolio-tool-contracts.json"
OUT = ROOT / ".local/benchmarks/research-decision-portfolio-v1"
CAP_USD = 1.0
MAX_REQUESTS = 15
MAX_OUTPUT_TOKENS = 8000
DELIVERY = ("\n\n只输出 400–800 字可审阅的 Markdown 科研决定，第一行必须以 # 开始，"
            "不要加入英文前言或思考过程；正文说明来源对象与版本、"
            "关键证据或数字、当前能下与不能下的结论，以及下一项最小核查。"
            "仅当事件返回了 Gmail 或日历对象，才讨论邮件或排期；此时只给待审文字和建议时段，"
            "不声称已经发送或创建。"
            "缺少必要对象或分母时明确停在待核实，不能猜测。")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def private(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    path.chmod(0o600)


def prompt_for(case: str) -> str:
    return (BENCH / "cases" / case / "task.md").read_text(encoding="utf-8") + DELIVERY


def preview(case: str, arm: str, output_root: Path,
            manifest: Path | None, task: Path | None) -> dict:
    case_dir = BENCH / "cases" / case
    if not case_dir.is_dir():
        raise ValueError("unknown frozen portfolio case")
    files = [case_dir / name for name in ("task.md", "sources.json", "review.json")]
    files += [BENCH / "fixtures.lock.json", BENCH / "mock_apps_server.py",
              PATCH, CONTRACTS, Path(__file__).resolve()]
    if arm == "motif":
        if manifest is None or task is None:
            raise ValueError("Motif requires a certified manifest and scoped task")
        files += [manifest.resolve(strict=True), task.resolve(strict=True),
                  ROOT / "src/adapters/dsh_online_motif.mjs",
                  ROOT / "src/motif_core/online_skill_runtime.mjs"]
    elif manifest is not None or task is not None:
        raise ValueError("ordinary baseline cannot receive a Motif artifact")
    return {"task_id": f"research-portfolio-{case}", "case": case,
            "arm": arm, "classification": "synthetic_development_trial",
            "model": "deepseek-flash", "reasoning_effort": "off",
            "budget_cap_usd": CAP_USD, "max_model_requests": MAX_REQUESTS,
            "max_output_tokens_per_request": MAX_OUTPUT_TOKENS,
            "read_only": True, "output_dir": str(output_root / case / arm),
            "input_sha256": {str(path.relative_to(ROOT)) if path.is_relative_to(ROOT)
                             else str(path): sha(path) for path in files}}


def online_prepare(manifest: Path, task: Path) -> dict:
    script = ROOT / "scripts/prepare-online-motif.py"
    spec = importlib.util.spec_from_file_location("portfolio_online_prepare", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("online Motif preparer unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.prepare(manifest, task)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    parser.add_argument("--arm", choices=("baseline", "motif"), required=True)
    parser.add_argument("--output-root", type=Path, default=OUT)
    parser.add_argument("--online-manifest", type=Path)
    parser.add_argument("--online-task", type=Path)
    parser.add_argument("--call-model", action="store_true")
    args = parser.parse_args()
    output_root = args.output_root.resolve()
    if not output_root.is_relative_to((ROOT / ".local").resolve()):
        parser.error("run output must stay under .local")
    out = output_root / args.case / args.arm
    current = preview(args.case, args.arm, output_root,
                      args.online_manifest, args.online_task)
    saved, approval = out / "PREVIEW.json", out / "APPROVAL.json"
    print(json.dumps({**current, "paid_api_requested": args.call_model},
                     ensure_ascii=False), flush=True)
    if not args.call_model:
        private(saved, current)
        return 0
    if not saved.is_file() or json.loads(saved.read_text()) != current:
        parser.error("frozen preview missing or changed")
    if not approval.is_file():
        parser.error("authorization record missing")
    record = json.loads(approval.read_text())
    if (record.get("approved") is not True or
            record.get("preview_sha256") != sha(saved) or
            record.get("budget_cap_usd") != CAP_USD or
            record.get("authorization_basis") != "开始吧"):
        parser.error("authorization does not match this frozen trial")
    require_budget_gate()
    if float(os.environ["SSS_BUDGET_CAP_USD"]) > CAP_USD:
        parser.error("cost gate exceeds task cap")
    marker = out / "paid-attempt.marker"
    with marker.open("x", encoding="utf-8") as stream:
        stream.write("one authorized paid trial reserved\n")
    marker.chmod(0o600)
    online = (online_prepare(args.online_manifest, args.online_task)
              if args.arm == "motif" else None)
    session_id = (json.loads(args.online_task.read_text())["session_id"]
                  if online else f"sss-portfolio-{args.case}-{uuid4().hex}")
    os.environ.update({"SSS_MCP_PYTHON": str(ROOT / ".venv312/bin/python"),
                       "SSS_PROJECT_ROOT": str(ROOT),
                       "SSS_PORTFOLIO_CASE": args.case,
                       "DSH_PERMISSION_MODE": "read-only"})
    patches = [str(PATCH)]
    if online:
        os.environ.update({
            "SSS_ONLINE_MOTIF_MANIFEST": online["manifest"],
            "SSS_ONLINE_MOTIF_TASK": online["task"],
            "SSS_ONLINE_MOTIF_MODE": "execute",
            "SSS_ONLINE_MOTIF_PROMPT_SHA256": hashlib.sha256(
                prompt_for(args.case).encode()).hexdigest(),
            "SSS_MOTIF_EMBEDDING_ENDPOINT": "http://127.0.0.1:8776/v1/embeddings",
            "SSS_MOTIF_EMBEDDING_MODEL": "Qwen/Qwen3-Embedding-0.6B",
        })
        patches.append(online["patch"])
    guard = NativeBudgetGuard(max_model_requests=MAX_REQUESTS,
                              max_observed_input_tokens=500_000)
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

    from deepseek_harness import DeepSeekHarness
    started = time.monotonic()
    try:
        with DeepSeekHarness(
            provider="deepseek-official", model="deepseek-flash",
            reasoning_effort="off", max_tokens=MAX_OUTPUT_TOKENS,
            cwd=str(out), runtime_cwd=str(out),
            dsh_bin=str(ROOT / "node_modules/.bin/dsh"), profile="sdk",
            patches=tuple(patches), dsh_home=str(ROOT / ".local/dsh"),
            request_timeout_seconds=600,
        ) as harness:
            result = harness.run(prompt_for(args.case), session_id=session_id,
                                 on_notification=observe)
            if not result.final_response.strip() and result.finish_reason != "completed":
                result = harness.run("继续完成原任务；请输出可审阅的 Markdown 决定。",
                                     session_id=session_id, on_notification=observe)
        answer = result.final_response.strip()
        if answer:
            target = out / "agent-answer.md"
            target.write_text(answer + "\n", encoding="utf-8")
            target.chmod(0o600)
        status = ("done" if answer and result.finish_reason == "completed" else "incomplete")
        report = {"status": status, "finish_reason": result.finish_reason,
                  "answer_characters": len(answer)}
    except Exception as exc:
        report = {"status": "error", "error_type": type(exc).__name__,
                  "error": str(exc)[:300]}
    report.update({"case": args.case, "arm": args.arm, "session_id": session_id,
                   "git_head": subprocess.check_output(
                       ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                   "elapsed_seconds": round(time.monotonic() - started, 3),
                   "started_requests": guard.started_requests,
                   "budget_ledger": os.environ.get("SSS_BUDGET_LEDGER"),
                   **_usage(guard.events)})
    private(out / "agent-metrics.json", report)
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "done" else 2


if __name__ == "__main__":
    raise SystemExit(main())
