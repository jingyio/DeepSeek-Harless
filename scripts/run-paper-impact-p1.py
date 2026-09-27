#!/usr/bin/env python3
"""Preview or run the scoped AIDD paper-impact development trial."""

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

PARENT = ROOT / ".local/benchmarks/research-weekly-loop/aidd-next-preflight"
SOURCE = PARENT / "baseline-scope-approved.json"
SOURCE_APPROVAL = PARENT / "baseline-approval.json"
OUT = ROOT / ".local/benchmarks/research-weekly-loop/paper-impact-p1-20260927"
SCOPE = OUT / "source-scope.json"
PREVIEW = OUT / "PREVIEW.json"
APPROVAL = OUT / "APPROVAL.json"
PROMPT = ROOT / "benchmarks/research_weekly_loop_v1/mcp_paper_impact_p1_prompt.md"
PATCH = ROOT / "config/aidd-scoped-baseline.patch.yml"
ALLOWED_SOURCES = {"current_state", "open_questions", "antibody_pdf"}
ALLOWED_ZOTERO = {"antibody_item", *(f"antibody_annotation_{n}" for n in range(1, 7))}
BUDGET_USD = 2.0


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_private(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def narrowed_scope() -> dict:
    original = json.loads(SOURCE.read_text(encoding="utf-8"))
    prior = json.loads(SOURCE_APPROVAL.read_text(encoding="utf-8"))
    if (original.get("status") != "approved_for_model"
            or prior.get("approved") is not True
            or prior.get("approved_scope_sha256") != digest(SOURCE)):
        raise ValueError("previous AIDD source approval is no longer valid")
    sources = [row for row in original["sources"] if row.get("role") in ALLOWED_SOURCES]
    zotero = [row for row in original["zotero_sources"]
              if row.get("role") in ALLOWED_ZOTERO]
    if ({row["role"] for row in sources} != ALLOWED_SOURCES
            or {row["role"] for row in zotero} != ALLOWED_ZOTERO
            or len(sources) != 3 or len(zotero) != 7
            or any(row.get("external_model_excerpt_allowed") is not True
                   for row in sources + zotero)):
        raise ValueError("P1 source range is incomplete or unapproved")
    for row in sources:
        if digest(Path(row["path"]).resolve(strict=True)) != row["sha256"]:
            raise ValueError(f"P1 source changed: {row['role']}")
    for row in zotero:
        verify_zotero(row)
    return {**original, "sources": sources, "zotero_sources": zotero,
            "parent_scope_sha256": digest(SOURCE), "trial": "paper_impact_p1"}


def preview(scope: dict) -> dict:
    raw = (json.dumps(scope, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return {"task": "AIDD antibody paper impact card; development trial",
            "model": "deepseek-flash", "reasoning_effort": "high",
            "budget_cap_usd": BUDGET_USD, "max_model_requests": None,
            "max_output_tokens_per_request": 8000,
            "source_roles": sorted(ALLOWED_SOURCES),
            "zotero_roles": sorted(ALLOWED_ZOTERO),
            "parent_scope_sha256": digest(SOURCE),
            "narrowed_scope_sha256": hashlib.sha256(raw).hexdigest(),
            "prompt_sha256": digest(PROMPT), "patch_sha256": digest(PATCH),
            "output": str(OUT)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--call-model", action="store_true")
    args = parser.parse_args()
    scope = narrowed_scope()
    details = preview(scope)
    print(json.dumps({**details, "paid_api_requested": args.call_model},
                     ensure_ascii=False), flush=True)
    if not args.call_model:
        for path, value in ((SCOPE, scope), (PREVIEW, details)):
            if path.exists() and json.loads(path.read_text(encoding="utf-8")) != value:
                parser.error(f"existing P1 preview changed: {path.name}")
            if not path.exists():
                write_private(path, value)
        return 0
    if not PREVIEW.is_file() or not SCOPE.is_file() or not APPROVAL.is_file():
        parser.error("P1 needs a frozen preview, narrowed scope and approval record")
    approved = json.loads(APPROVAL.read_text(encoding="utf-8"))
    frozen = json.loads(PREVIEW.read_text(encoding="utf-8"))
    if (approved.get("approved") is not True or frozen != details
            or approved.get("preview_sha256") != digest(PREVIEW)
            or approved.get("scope_sha256") != digest(SCOPE)
            or json.loads(SCOPE.read_text(encoding="utf-8")) != scope):
        parser.error("P1 source, prompt, patch or budget differs from approved preview")
    require_budget_gate()
    if float(os.environ["SSS_BUDGET_CAP_USD"]) > BUDGET_USD:
        parser.error("P1 cost gate exceeds US$2")
    if (OUT / "agent-events.jsonl").exists() or (OUT / "agent-answer.md").exists():
        parser.error("P1 attempt exists; do not overwrite it")
    from deepseek_harness import DeepSeekHarness

    marker = OUT / "paid-attempt.marker"
    fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write("one P1 paid attempt reserved\n")
    session_id = "sss-paper-impact-p1-" + uuid4().hex
    prompt = PROMPT.read_text(encoding="utf-8")
    (OUT / "agent-prompt.txt").write_text(prompt, encoding="utf-8")
    (OUT / "agent-prompt.txt").chmod(0o600)
    (OUT / "session-id.txt").write_text(session_id + "\n", encoding="utf-8")
    (OUT / "session-id.txt").chmod(0o600)
    os.environ.update({"SSS_MCP_PYTHON": str(ROOT / ".venv312/bin/python"),
                       "SSS_PROJECT_ROOT": str(ROOT),
                       "SSS_RESEARCH_SCOPE_FILE": str(SCOPE)})
    guard = NativeBudgetGuard(max_model_requests=None, max_observed_input_tokens=None)
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
        with DeepSeekHarness(
            provider="deepseek-official", model="deepseek-flash",
            reasoning_effort="high", max_tokens=8000,
            cwd=str(OUT), runtime_cwd=str(OUT),
            dsh_bin=str(ROOT / "node_modules/.bin/dsh"), profile="sdk",
            patches=(str(PATCH),), dsh_home=str(ROOT / ".local/dsh"),
            request_timeout_seconds=900,
        ) as harness:
            result = harness.run(prompt, session_id=session_id,
                                 on_notification=observe)
        answer = OUT / "agent-answer.md"
        answer.write_text(result.final_response, encoding="utf-8")
        answer.chmod(0o600)
        status = "done" if result.finish_reason == "completed" and result.final_response.strip() else "incomplete"
        metrics = {"status": status, "finish_reason": result.finish_reason}
    except Exception as exc:
        metrics = {"status": "error", "error_type": type(exc).__name__,
                   "error": str(exc)[:300]}
    metrics.update({"session_id": session_id,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "started_requests": guard.started_requests,
                    **_usage(guard.events)})
    write_private(OUT / "agent-metrics.json", metrics)
    print(json.dumps({"output": str(OUT), **metrics}, ensure_ascii=False), flush=True)
    return 0 if metrics["status"] == "done" else 2


if __name__ == "__main__":
    raise SystemExit(main())
