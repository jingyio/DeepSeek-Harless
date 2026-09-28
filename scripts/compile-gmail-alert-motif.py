#!/usr/bin/env python3
"""Certify one Gmail search-to-read Motif from independent private alert traces."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.dsh_trajectory import (  # noqa: E402
    extract_dsh_trace, infer_dsh_provenance,
)
from src.adapters.tool_contract_loader import parse_tool_contracts  # noqa: E402
from src.motif_core.offline.library_builder import build_read_motif_library  # noqa: E402

BASE = ROOT / ".local/benchmarks/research-weekly-loop/gmail-alert-motif-20260928"
CONTRACTS = ROOT / "config/scoped-gmail-request-contracts.json"
EXPORT = ROOT / "scripts/export-online-motif-manifest.py"
SEARCH = "mcp__scoped_gmail_request__search_emails"
READ = "mcp__scoped_gmail_request__read_email"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    path.chmod(0o600)


def read_result_evidence(events: list[dict], tool: str) -> dict[str, str]:
    ids = {row.get("data", {}).get("callId") for row in events
           if row.get("type") == "tool/call"
           and row.get("data", {}).get("name") == tool}
    if len(ids) != 1:
        raise ValueError("output evidence needs one witnessed read call")
    matches = [row["data"]["message"]["content"]
               for row in events if row.get("type") == "tool/result"
               and row.get("data", {}).get("message", {}).get("source", {}).get("callId")
               in ids]
    if (len(matches) != 1 or len(matches[0]) != 1
            or matches[0][0].get("isError") is True
            or len(matches[0][0].get("content", [])) != 1
            or matches[0][0]["content"][0].get("type") != "text"):
        raise ValueError("output evidence needs one successful text result")
    payload = json.dumps(matches[0], sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"))
    return {"text": matches[0][0]["content"][0]["text"],
            "observation_sha256": sha(payload.encode())}


def main() -> None:
    case_file = BASE / "cases.json"
    cases = json.loads(case_file.read_text(encoding="utf-8"))["cases"]
    rows = json.loads(CONTRACTS.read_text(encoding="utf-8"))
    contracts = parse_tool_contracts(rows)
    traces = {"train": [], "validation": []}
    evidence = {}
    output_samples = {}
    for case_id, case in cases.items():
        if case["role"] not in traces:
            continue
        event_file = BASE / case_id / "baseline/agent-events.jsonl"
        prompt_file = BASE / case_id / "prompt.md"
        events = [json.loads(line) for line in event_file.read_text().splitlines()]
        trace_id = "gmail-alert-" + case_id
        fingerprint = sha((case_id + "\n" + case["query"]).encode())
        provenance = infer_dsh_provenance(events, contracts)
        trace = extract_dsh_trace(events, contracts, trace_id=trace_id,
                                  task_fingerprint=fingerprint,
                                  provenance_by_call_id=provenance)
        if (len(trace.records) != 2 or [row.name for row in trace.records]
                != [SEARCH, READ] or not all(row.eligible for row in trace.records)
                or trace.records[0].observation.get("count") != 1
                or trace.records[1].parameter_sources.get("messageId") != {
                    "from_tool": SEARCH, "from_field": "selected_message_id"}):
            raise ValueError(f"{case_id} lacks a witnessed unique search-to-read edge")
        traces[case["role"]].append(trace)
        output_samples[trace_id] = {READ: read_result_evidence(events, READ)}
        evidence[trace_id] = {
            "research_decision_id": fingerprint,
            "manifest_sha256": sha(json.dumps(case, ensure_ascii=False,
                                              sort_keys=True).encode()),
            "events_sha256": sha(event_file.read_bytes()),
            "identity_sha256": sha((case_id + ":independent-alert").encode()),
            "question_sha256": sha(prompt_file.read_bytes()),
        }
    if len(traces["train"]) != 2 or len(traces["validation"]) != 1:
        raise ValueError("need two independent training alerts and one held-out alert")
    library = build_read_motif_library(traces["train"], traces["validation"],
                                       contracts, task_identity_evidence=evidence,
                                       output_projection_codecs={
                                           READ: "marked_html_visible_text_v1"},
                                       output_projection_samples=output_samples)
    if len(library["artifacts"]) != 1:
        raise ValueError(f"expected one certified Motif: {library['rejected']}")
    slot_rules = {SEARCH: {"query":
                  r'subject:"[A-Za-z ]+ - new related research" '
                  r'after:2026/09/[0-9]{2} before:2026/09/[0-9]{2}'}}
    versions = {SEARCH: "selected_message_id", READ: "source_version"}
    spec = importlib.util.spec_from_file_location("online_export", EXPORT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest = module.export_manifest(library, rows, slot_rules, versions)
    save(BASE / "certified-library.json", library)
    save(BASE / "online-manifest.json", manifest)
    print(json.dumps({"training_tasks": len(traces["train"]),
                      "validation_tasks": len(traces["validation"]),
                      "certified_motifs": len(library["artifacts"]),
                      "manifest_digest": manifest["manifest_digest"],
                      "library_digest": library["library_digest"]}))


if __name__ == "__main__":
    main()
