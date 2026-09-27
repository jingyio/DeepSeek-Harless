#!/usr/bin/env python3
"""Strong baseline: one generic versioned evidence script, then one model answer."""

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

from benchmarks.meeting_decision_chain_v1.script_baseline import run as gather  # noqa: E402
from src.adapters.dsh_client import _usage, require_budget_gate  # noqa: E402
from src.adapters.native_budget import NativeBudgetGuard  # noqa: E402


BASE = ROOT / "benchmarks/meeting_decision_chain_v5"
PATCH = ROOT / "config/meeting-script-dossier.patch.yml"
CASES = frozenset(("microscopy_vendor", "chemistry_substrate", "materials_scaleup"))
CAP_USD = 1.0


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_private(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    path.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=sorted(CASES), required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--call-model", action="store_true")
    args = parser.parse_args()
    root = args.output_root.resolve()
    if not root.is_relative_to((ROOT / ".local").resolve()):
        parser.error("output must stay under .local")
    out = root / args.case / "script_dossier"
    dossier = gather(args.case)
    if dossier["decision"] != "semantic_review_required":
        raise ValueError("script baseline unexpectedly made a semantic decision")
    dossier_path = out / "dossier.json"
    if not args.call_model:
        write_private(dossier_path, dossier)
    elif not dossier_path.is_file() or json.loads(dossier_path.read_text()) != dossier:
        parser.error("frozen script dossier changed")
    task_path = BASE / "tasks" / f"{args.case}.md"
    sources = sorted(path for path in (BASE / "sources" / args.case).iterdir()
                     if path.is_file())
    paths = [task_path, PATCH, Path(__file__).resolve(),
             ROOT / "benchmarks/meeting_decision_chain_v1/script_baseline.py",
             ROOT / "benchmarks/meeting_decision_chain_v1/mock_apps_server.py",
             dossier_path, *sources]
    current = {"case": args.case, "arm": "script_dossier",
               "classification": "synthetic_development_trial",
               "model": "deepseek-flash", "reasoning_effort": "off",
               "budget_cap_usd": CAP_USD, "max_model_requests": 1,
               "input_sha256": {str(path.resolve().relative_to(ROOT)): sha(path)
                                for path in paths},
               "output_dir": str(out)}
    preview = out / "PREVIEW.json"
    if not args.call_model:
        write_private(preview, current)
        print(json.dumps({"case": args.case, "preview": str(preview),
                          "dossier_bytes": dossier_path.stat().st_size}, ensure_ascii=False))
        return 0
    if not preview.is_file() or json.loads(preview.read_text()) != current:
        parser.error("frozen preview differs")
    approval = out / "APPROVAL.json"
    if not approval.is_file():
        parser.error("approved budget preview is required")
    record = json.loads(approval.read_text())
    if (record.get("approved") is not True or
            record.get("preview_sha256") != sha(preview) or
            record.get("budget_cap_usd") != CAP_USD or
            record.get("authorization_basis") != "可以，开始吧"):
        parser.error("approval does not match preview")
    require_budget_gate()
    if float(os.environ["SSS_BUDGET_CAP_USD"]) > CAP_USD:
        parser.error("cost gate exceeds frozen cap")
    from deepseek_harness import DeepSeekHarness
    marker = out / "paid-attempt.marker"
    with marker.open("x", encoding="utf-8") as stream:
        stream.write("one authorized script-dossier synthesis reserved\n")
    marker.chmod(0o600)
    question = task_path.read_text(encoding="utf-8")
    prompt = (question + "\n\n以下是通用只读脚本固定版本并复算的完整证据包。"
              "只根据它写可审阅的一页中文 Markdown，直接以一级标题开头；"
              "区分观察事实、旧主张、方法批注与原因推测。"
              "事件的 changed_fields 不说明变更原因或测量口径；分组标签不说明独立对象数。"
              "证据不足处写待核实，不得补造。\n\n证据包：\n"
              + json.dumps(dossier, ensure_ascii=False, sort_keys=True))
    guard = NativeBudgetGuard(max_model_requests=1,
                              max_observed_input_tokens=300_000)
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
            reasoning_effort="off", max_tokens=8000,
            cwd=str(out), runtime_cwd=str(out),
            dsh_bin=str(ROOT / "node_modules/.bin/dsh"), profile="sdk",
            patches=(str(PATCH),), dsh_home=str(ROOT / ".local/dsh"),
            request_timeout_seconds=600,
        ) as harness:
            result = harness.run(prompt, session_id=f"sss-script-{args.case}-{uuid4().hex}",
                                 on_notification=observe)
        answer = result.final_response.strip()
        heading = answer.find("\n# ")
        if heading >= 0 and not answer.startswith("# "):
            answer = answer[heading + 1:]
        if answer:
            (out / "agent-answer.md").write_text(answer + "\n", encoding="utf-8")
            (out / "agent-answer.md").chmod(0o600)
        report = {"status": "answered_unreviewed" if answer.startswith("# ") and
                  result.finish_reason == "completed" else "incomplete",
                  "finish_reason": result.finish_reason,
                  "answer_characters": len(answer)}
    except Exception as exc:
        report = {"status": "error", "error_type": type(exc).__name__,
                  "error": str(exc)[:300]}
    report.update({"case": args.case, "arm": "script_dossier",
                   "elapsed_seconds": round(time.monotonic() - started, 3),
                   "started_requests": guard.started_requests,
                   "budget_ledger": os.environ.get("SSS_BUDGET_LEDGER"),
                   **_usage(guard.events)})
    write_private(out / "agent-metrics.json", report)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "answered_unreviewed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
