#!/usr/bin/env python3
"""Freeze and run one scoped, simulated-release annotation impact trial."""

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

OUT = ROOT / ".local/benchmarks/research-weekly-loop/independent-annotation-candidate-20260927"
METADATA = OUT / "metadata-preview.json"
SCOPE = OUT / "source-scope.json"
PREVIEW = OUT / "RUN-PREVIEW.json"
APPROVAL = OUT / "RUN-APPROVAL.json"
PROMPT = ROOT / "benchmarks/research_weekly_loop_v1/flexibility_annotation_event_prompt.md"
PATCH = ROOT / "config/aidd-scoped-baseline.patch.yml"
BUDGET_USD = 2.0


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def private_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def frozen_scope() -> dict:
    metadata = json.loads(METADATA.read_text(encoding="utf-8"))
    if (metadata.get("status") != "metadata_preflight_only"
            or metadata.get("paper_key") != "UJQFBX2M"
            or metadata.get("actual_new_annotation_event") is not False
            or len(metadata.get("annotations", [])) != 4):
        raise ValueError("unexpected metadata preflight")
    vault = Path("/Users/apple/Documents/Research/Model RSI/科研思路管理").resolve(strict=True)
    note = metadata["obsidian_note"]
    pdf = metadata["pdf"]
    note_path = Path(note["path"]).resolve(strict=True)
    pdf_path = Path(pdf["path"]).resolve(strict=True)
    if (note_path != vault / "00-System/当前状态.md"
            or not note_path.is_relative_to(vault)
            or digest(note_path) != note["sha256"]
            or digest(pdf_path) != pdf["sha256"]
            or pdf_path.stat().st_size > 10_000_000):
        raise ValueError("approved note or PDF changed")
    item = {"role": "flexibility_item", "kind": "item",
            "key": metadata["paper_key"], "version": metadata["paper_version"],
            "data_sha256": metadata["paper_data_sha256"],
            "external_model_excerpt_allowed": True}
    zotero = [item]
    for index, row in enumerate(metadata["annotations"], 1):
        if row.get("parent_item") != "CFMEEGW4":
            raise ValueError("annotation is not on the approved PDF")
        zotero.append({"role": f"flexibility_annotation_{index}",
                       "kind": "annotation", "key": row["key"],
                       "version": row["version"],
                       "data_sha256": row["data_sha256"],
                       "external_model_excerpt_allowed": True})
    for row in zotero:
        verify_zotero(row)
    return {
        "status": "approved_for_model",
        "trial": "flexibility_annotation_simulated_release",
        "simulated_release_of_real_historical_annotations": True,
        "obsidian_vault_root": str(vault),
        "metadata_sha256": digest(METADATA),
        "sources": [
            {"role": "current_state", "path": str(note_path),
             "vault_path": "00-System/当前状态.md",
             "sha256": note["sha256"],
             "allowed_line_ranges": [[120, 175]],
             "external_model_excerpt_allowed": True},
            {"role": "flexibility_pdf", "path": str(pdf_path),
             "sha256": pdf["sha256"], "allowed_page_ranges": [[1, 19]],
             "external_model_excerpt_allowed": True},
        ],
        "zotero_sources": zotero,
    }


def preview(scope: dict) -> dict:
    encoded = (json.dumps(scope, ensure_ascii=False, indent=2) + "\n").encode()
    return {"task": "Flexibility Trap highlighters versus structural-prior claim",
            "event_status": "simulated release of real historical annotations",
            "model": "deepseek-flash", "reasoning_effort": "off",
            "budget_cap_usd": BUDGET_USD, "max_model_requests": None,
            "max_output_tokens_per_request": 6000,
            "source_roles": [row["role"] for row in scope["sources"]],
            "zotero_roles": [row["role"] for row in scope["zotero_sources"]],
            "scope_sha256": hashlib.sha256(encoded).hexdigest(),
            "prompt_sha256": digest(PROMPT), "patch_sha256": digest(PATCH),
            "metadata_sha256": digest(METADATA), "output": str(OUT)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--call-model", action="store_true")
    args = parser.parse_args()
    scope = frozen_scope()
    details = preview(scope)
    print(json.dumps({**details, "paid_api_requested": args.call_model},
                     ensure_ascii=False), flush=True)
    if not args.call_model:
        for path, value in ((SCOPE, scope), (PREVIEW, details)):
            if path.exists() and json.loads(path.read_text(encoding="utf-8")) != value:
                parser.error(f"frozen preview changed: {path.name}")
            if not path.exists():
                private_json(path, value)
        return 0
    if not SCOPE.is_file() or not PREVIEW.is_file() or not APPROVAL.is_file():
        parser.error("frozen scope, preview and user approval are required")
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    if (approval.get("approved") is not True
            or approval.get("preview_sha256") != digest(PREVIEW)
            or approval.get("scope_sha256") != digest(SCOPE)
            or json.loads(SCOPE.read_text(encoding="utf-8")) != scope
            or json.loads(PREVIEW.read_text(encoding="utf-8")) != details):
        parser.error("source, prompt, patch or budget differs from approved preview")
    require_budget_gate()
    if float(os.environ["SSS_BUDGET_CAP_USD"]) > BUDGET_USD:
        parser.error("cost gate exceeds approved US$2 cap")
    with (OUT / "paid-attempt.marker").open("x", encoding="utf-8") as stream:
        stream.write("one approved paid trial reserved\n")
    session_id = "sss-flexibility-event-" + uuid4().hex
    os.environ.update({"SSS_MCP_PYTHON": str(ROOT / ".venv312/bin/python"),
                       "SSS_PROJECT_ROOT": str(ROOT),
                       "SSS_RESEARCH_SCOPE_FILE": str(SCOPE)})
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
