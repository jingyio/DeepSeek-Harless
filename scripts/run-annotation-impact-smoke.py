#!/usr/bin/env python3
"""Preview or run a read-only, retrospective Zotero annotation impact smoke."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.dsh_client import _usage, require_budget_gate  # noqa: E402
from src.adapters.native_budget import NativeBudgetGuard  # noqa: E402
from src.mcp.scoped_zotero_read_server import _verified as verify_zotero  # noqa: E402

PARENT = ROOT / ".local/benchmarks/research-weekly-loop/paper-impact-p1-20260927"
OUT = ROOT / ".local/benchmarks/research-weekly-loop/annotation-impact-smoke-20260927"
PROMPT = ROOT / "benchmarks/research_weekly_loop_v1/annotation_impact_smoke_prompt.md"
PATCH = ROOT / "config/aidd-scoped-baseline.patch.yml"
SOURCE_ROLES = {"current_state", "open_questions", "antibody_pdf"}
ZOTERO_ROLES = {"antibody_item", "antibody_annotation_2"}
BUDGET_USD = 2.0


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def private_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def frozen_scope() -> dict:
    parent = PARENT / "source-scope.json"
    original = json.loads(parent.read_text(encoding="utf-8"))
    approval = json.loads((PARENT / "APPROVAL.json").read_text(encoding="utf-8"))
    if (approval.get("approved") is not True
            or approval.get("scope_sha256") != digest(parent)):
        raise ValueError("parent source approval changed")
    sources = [row for row in original["sources"] if row.get("role") in SOURCE_ROLES]
    zotero = [row for row in original["zotero_sources"]
              if row.get("role") in ZOTERO_ROLES]
    if ({row["role"] for row in sources} != SOURCE_ROLES
            or {row["role"] for row in zotero} != ZOTERO_ROLES
            or any(row.get("external_model_excerpt_allowed") is not True
                   for row in sources + zotero)):
        raise ValueError("expected approved source roles are unavailable")
    for row in sources:
        if digest(Path(row["path"]).resolve(strict=True)) != row["sha256"]:
            raise ValueError("approved file source changed")
    for row in zotero:
        verify_zotero(row)
    return {**original, "sources": sources, "zotero_sources": zotero,
            "parent_scope_sha256": digest(parent),
            "trial": "retrospective_annotation_impact_smoke"}


def preview(scope: dict) -> dict:
    raw = (json.dumps(scope, ensure_ascii=False, indent=2) + "\n").encode()
    return {
        "task": "retrospective AIDD annotation impact technical smoke",
        "not_independent_task": True,
        "model": "deepseek-flash", "reasoning_effort": "off",
        "budget_cap_usd": BUDGET_USD, "max_model_requests": None,
        "max_output_tokens_per_request": 6000,
        "source_roles": sorted(SOURCE_ROLES),
        "zotero_roles": sorted(ZOTERO_ROLES),
        "parent_scope_sha256": digest(PARENT / "source-scope.json"),
        "scope_sha256": hashlib.sha256(raw).hexdigest(),
        "prompt_sha256": digest(PROMPT), "patch_sha256": digest(PATCH),
        "output": str(OUT),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--call-model", action="store_true")
    args = parser.parse_args()
    scope = frozen_scope()
    details = preview(scope)
    print(json.dumps({**details, "paid_api_requested": args.call_model},
                     ensure_ascii=False), flush=True)
    scope_file = OUT / "source-scope.json"
    preview_file = OUT / "PREVIEW.json"
    approval_file = OUT / "APPROVAL.json"
    if not args.call_model:
        for path, value in ((scope_file, scope), (preview_file, details)):
            if path.exists() and json.loads(path.read_text(encoding="utf-8")) != value:
                parser.error(f"frozen preview changed: {path.name}")
            if not path.exists():
                private_json(path, value)
        return 0
    if not scope_file.is_file() or not preview_file.is_file() or not approval_file.is_file():
        parser.error("frozen scope, preview and user approval are required")
    approval = json.loads(approval_file.read_text(encoding="utf-8"))
    if (approval.get("approved") is not True
            or approval.get("preview_sha256") != digest(preview_file)
            or approval.get("scope_sha256") != digest(scope_file)
            or json.loads(scope_file.read_text(encoding="utf-8")) != scope
            or json.loads(preview_file.read_text(encoding="utf-8")) != details):
        parser.error("scope, prompt, patch or budget differs from approved preview")
    require_budget_gate()
    if float(os.environ["SSS_BUDGET_CAP_USD"]) > BUDGET_USD:
        parser.error("cost gate exceeds approved US$2 cap")
    marker = OUT / "paid-attempt.marker"
    with marker.open("x", encoding="utf-8") as stream:
        stream.write(datetime.now(timezone.utc).isoformat() + "\n")
    marker.chmod(0o600)
    session_id = "sss-annotation-impact-" + uuid4().hex
    os.environ.update({"SSS_MCP_PYTHON": str(ROOT / ".venv312/bin/python"),
                       "SSS_PROJECT_ROOT": str(ROOT),
                       "SSS_RESEARCH_SCOPE_FILE": str(scope_file)})
    guard = NativeBudgetGuard(max_model_requests=None,
                              max_observed_input_tokens=None)
    events = OUT / "agent-events.jsonl"

    def observe(notification) -> None:
        if getattr(notification, "method", None) != "session.event":
            return
        event = getattr(notification, "payload", {}).get("event")
        if isinstance(event, dict):
            with events.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            events.chmod(0o600)
        guard.on_notification(notification)

    started = time.monotonic()
    try:
        from deepseek_harness import DeepSeekHarness

        with DeepSeekHarness(
            provider="deepseek-official", model="deepseek-flash",
            reasoning_effort="off", max_tokens=6000,
            cwd=str(OUT), runtime_cwd=str(OUT),
            dsh_bin=str(ROOT / "node_modules/.bin/dsh"), profile="sdk",
            patches=(str(PATCH),), dsh_home=str(ROOT / ".local/dsh"),
            request_timeout_seconds=900,
        ) as harness:
            result = harness.run(PROMPT.read_text(encoding="utf-8"),
                                 session_id=session_id, on_notification=observe)
        (OUT / "agent-answer.md").write_text(result.final_response,
                                              encoding="utf-8")
        (OUT / "agent-answer.md").chmod(0o600)
        status = ("done" if result.finish_reason == "completed"
                  and result.final_response.strip() else "incomplete")
        metrics = {"status": status, "finish_reason": result.finish_reason}
    except Exception as exc:
        metrics = {"status": "error", "error_type": type(exc).__name__,
                   "error": str(exc)[:300]}
    metrics.update({"session_id": session_id,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "started_requests": guard.started_requests,
                    **_usage(guard.events)})
    private_json(OUT / "agent-metrics.json", metrics)
    print(json.dumps({"output": str(OUT), **metrics}, ensure_ascii=False), flush=True)
    return 0 if metrics["status"] == "done" else 2


if __name__ == "__main__":
    raise SystemExit(main())
