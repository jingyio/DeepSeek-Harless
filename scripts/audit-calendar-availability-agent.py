#!/usr/bin/env python3
"""Audit the frozen availability-tool Agent answers against independently read slots."""

from __future__ import annotations

import importlib.util
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".local/benchmarks/mcp-app-internal-v2/calendar"
OUT = SOURCE / "availability-v1"
SPEC = importlib.util.spec_from_file_location(
    "calendar_answer_audit", ROOT / "scripts/audit-calendar-internal-agent-answers.py")
assert SPEC and SPEC.loader
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)
TASKS = {row["id"]: row for row in AUDIT.SCRIPT.TASKS}
RECOMMENDATION = re.compile(
    r"推荐时段[：:]?\s*(\d{4}-\d{2}-\d{2})(?:（[^）]*）)?\s*"
    r"(\d{2}:\d{2})\s*[–—-]\s*(\d{2}:\d{2})")
ISO_FINAL = re.compile(
    r"推荐[：:]\s*开始\s*(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2})"
    r"，结束\s*(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2})")


def recommendations(answer: str) -> list[tuple[datetime, datetime]]:
    found = []
    for day, start, end in RECOMMENDATION.findall(answer):
        found.append(AUDIT.interval(day, start, end))
    for start, end in ISO_FINAL.findall(answer):
        found.append((datetime.fromisoformat(start), datetime.fromisoformat(end)))
    return found


def main() -> None:
    truth = json.loads((SOURCE / "script-current-scoped.json").read_text())
    if truth["status"] != "passed" or truth["case_count"] != 3:
        raise RuntimeError("Current independent Calendar read is missing")
    rows = []
    for case in "ABC":
        row = next(item for item in truth["results"] if item["case"] == case)
        folder = OUT / f"agent-{case.lower()}"
        answer = (folder / "answer.md").read_text(encoding="utf-8")
        metrics = json.loads((folder / "metrics.json").read_text())
        ledger = [json.loads(line) for line in (folder / "budget-ledger.jsonl").read_text().splitlines()]
        if len(ledger) != metrics["model_requests"]:
            raise RuntimeError(f"Case {case} ledger/request count mismatch")
        busy = [(datetime.fromisoformat(v["start"]), datetime.fromisoformat(v["end"]))
                for v in row["busy"]]
        expected = datetime.fromisoformat(row["recommended_start"])
        parsed = recommendations(answer)
        checks = [AUDIT.validate(TASKS[case], busy, value, expected) for value in parsed]
        qualified = bool(checks) and all(all(check[key] for key in
            ("correct_duration", "inside_one_window", "no_busy_overlap", "earliest"))
            for check in checks)
        source_event_ids_present = all(v["id"] in answer for v in row["event_versions"])
        events = [json.loads(line) for line in (folder / "agent-events.jsonl").read_text().splitlines()]
        calls = [event["data"] for event in events if event.get("type") == "tool/call"]
        tool_results = [event["data"]["message"] for event in events
                        if event.get("type") == "tool/result"]
        tool_errors = sum(bool(content.get("isError")) for message in tool_results
                          for content in message["content"])
        tool_names = [call.get("name", call.get("toolName", "unknown")) for call in calls]
        rows.append({"case": case, "expected_start": row["recommended_start"],
                     "recommendations": checks, "time_constraints_qualified": qualified,
                     "source_event_ids_present": source_event_ids_present,
                     "used_find": any(name.endswith("__find-available-slots") for name in tool_names),
                     "used_validate": any(name.endswith("__validate-slot") for name in tool_names),
                     "model_requests": metrics["model_requests"], "tool_calls": tool_names,
                     "tool_errors": tool_errors, "elapsed_seconds": metrics["elapsed_seconds"],
                     "estimated_api_usd": round(sum(item["observed_peak_usd"] for item in ledger), 8),
                     "http_statuses": [item["response_status"] for item in ledger]})
    payload = {"kind": "synthetic_calendar_availability_agent_audit",
               "source": "script-current-scoped.json", "cases": rows,
               "time_constraints_qualified_count": sum(row["time_constraints_qualified"] for row in rows),
               "model_requests": sum(row["model_requests"] for row in rows),
               "mcp_calls": sum(len(row["tool_calls"]) for row in rows),
               "estimated_api_usd": round(sum(row["estimated_api_usd"] for row in rows), 8),
               "elapsed_seconds": round(sum(row["elapsed_seconds"] for row in rows), 3)}
    target = OUT / "agent-quality-audit.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    target.chmod(0o600)
    print(json.dumps({key: payload[key] for key in
                      ("time_constraints_qualified_count", "model_requests", "mcp_calls",
                       "estimated_api_usd", "elapsed_seconds")}, ensure_ascii=False))
    print(json.dumps({"cases": [{"case": row["case"],
                                 "time_constraints_qualified": row["time_constraints_qualified"],
                                 "source_event_ids_present": row["source_event_ids_present"],
                                 "tool_errors": row["tool_errors"],
                                 "estimated_api_usd": row["estimated_api_usd"],
                                 "tool_calls": row["tool_calls"]} for row in rows]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
