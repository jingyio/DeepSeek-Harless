#!/usr/bin/env python3
"""Find witnessed, non-semantic Calendar continuations in ordinary Agent traces.

This audits candidate parameter flow; it does not certify or execute a Motif.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / ".local/benchmarks/mcp-app-internal-v2/calendar/availability-v1"
PARAMS = ("calendarId", "timeZone", "timeWindows", "durationMinutes")


def read_events(path: Path) -> tuple[list[dict], dict[str, dict]]:
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    calls = [event["data"] for event in events if event.get("type") == "tool/call"]
    results = {}
    for event in events:
        if event.get("type") != "tool/result":
            continue
        message = event["data"]["message"]
        call_id = message.get("source", {}).get("callId")
        blocks = message.get("content", [])
        if (not call_id or len(blocks) != 1 or blocks[0].get("isError")
                or len(blocks[0].get("content", [])) != 1):
            continue
        item = blocks[0]["content"][0]
        if item.get("type") == "text":
            try:
                results[call_id] = json.loads(item["text"])
            except (TypeError, ValueError):
                pass
    return calls, results


def witnessed_continuation(calls: list[dict], results: dict[str, dict]) -> dict:
    find = [(i, call) for i, call in enumerate(calls)
            if call["name"].endswith("__find-available-slots")]
    validate = [(i, call) for i, call in enumerate(calls)
                if call["name"].endswith("__validate-slot")]
    if len(find) != 1 or len(validate) != 1:
        return {"witnessed": False, "reason": "missing_or_repeated_tools"}
    find_index, find_call = find[0]
    validate_index, validate_call = validate[0]
    try:
        fargs = json.loads(find_call["arguments"])
        vargs = json.loads(validate_call["arguments"])
        found = results[find_call["callId"]]
        checked = results[validate_call["callId"]]
    except (KeyError, TypeError, ValueError):
        return {"witnessed": False, "reason": "missing_arguments_or_result"}
    checks = {
        "find_before_validate": find_index < validate_index
            and find_call["step"] < validate_call["step"],
        "unchanged_task_arguments": all(fargs.get(key) == vargs.get(key) for key in PARAMS),
        "candidate_from_result": isinstance(found.get("earliest"), dict)
            and vargs.get("candidateStart") == found["earliest"].get("start")
            and vargs.get("candidateEnd") == found["earliest"].get("end"),
        "same_fresh_source": isinstance(found.get("sourceSha256"), str)
            and len(found["sourceSha256"]) == 64
            and found["sourceSha256"] == checked.get("sourceSha256"),
        "validated_earliest": checked.get("valid") is True
            and checked.get("isEarliest") is True,
    }
    return {"witnessed": all(checks.values()), "checks": checks,
            "find_step": find_call["step"], "validate_step": validate_call["step"]}


def main() -> None:
    rows = []
    for case in "abc":
        folder = BASE / f"agent-{case}"
        calls, results = read_events(folder / "agent-events.jsonl")
        rows.append({"case": case.upper(), "event_sha256": hashlib.sha256(
            (folder / "agent-events.jsonl").read_bytes()).hexdigest(),
                     **witnessed_continuation(calls, results)})
    report = {"kind": "calendar_model_bypass_candidate_audit",
              "status": "candidate_only_not_certified",
              "ordinary_agent_cases": rows,
              "witness_count": sum(row["witnessed"] for row in rows),
              "heldout_positive_trace_available": False}
    target = BASE / "motif-opportunity-audit.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    target.chmod(0o600)
    print(json.dumps({"status": report["status"], "witness_count": report["witness_count"],
                      "cases": [{"case": row["case"], "witnessed": row["witnessed"],
                                 "checks": row.get("checks")} for row in rows]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
