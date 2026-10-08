#!/usr/bin/env python3
"""Check frozen synthetic Calendar Agent answers against independently read busy intervals."""

from __future__ import annotations

import importlib.util
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / ".local/benchmarks/mcp-app-internal-v2/calendar"
SPEC = importlib.util.spec_from_file_location(
    "calendar_script", ROOT / "scripts/run-calendar-internal-script-baseline.py")
assert SPEC and SPEC.loader
SCRIPT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCRIPT)

HEADER = re.compile(r"^#{1,3}\s+.*?(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})[–-](\d{2}:\d{2})", re.M)
START = re.compile(r"(?m)^\s*[-*]?\s*\*{0,2}开始[：:]\s*(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})")
END = re.compile(r"(?m)^\s*[-*]?\s*\*{0,2}结束[：:]\s*(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})")


def interval(date: str, start: str, end: str) -> tuple[datetime, datetime]:
    return (datetime.fromisoformat(f"{date}T{start}:00+08:00"),
            datetime.fromisoformat(f"{date}T{end}:00+08:00"))


def candidates(answer: str) -> dict[str, tuple[datetime, datetime]]:
    found = {}
    if match := HEADER.search(answer):
        found["headline"] = interval(*match.groups())
    starts, ends = START.findall(answer), END.findall(answer)
    if starts and ends:
        start_day, start_time = starts[-1]
        end_day, end_time = ends[-1]
        found["final"] = (interval(start_day, start_time, start_time)[0],
                          interval(end_day, end_time, end_time)[0])
    return found


def validate(task: dict, busy: list[tuple[datetime, datetime]],
             proposed: tuple[datetime, datetime], expected: datetime) -> dict:
    start, end = proposed
    windows = [(SCRIPT.instant(task["date"], a), SCRIPT.instant(task["date"], b))
               for a, b in task["windows"]]
    return {
        "start": start.isoformat(), "end": end.isoformat(),
        "correct_duration": end - start == timedelta(minutes=task["minutes"]),
        "inside_one_window": any(a <= start < end <= b for a, b in windows),
        "no_busy_overlap": all(not (a < end and b > start) for a, b in busy),
        "earliest": start == expected,
    }


def main() -> None:
    baseline = json.loads((BASE / "script-baseline.json").read_text())
    tasks = {row["id"]: row for row in SCRIPT.TASKS}
    rows = []
    for case in "ABC":
        task = tasks[case]
        truth = next(row for row in baseline["results"] if row["case"] == case)
        busy = [(datetime.fromisoformat(v["start"]), datetime.fromisoformat(v["end"]))
                for v in truth["busy"]]
        expected = datetime.fromisoformat(truth["recommended_start"])
        answer = (BASE / f"agent-{case.lower()}" / "answer.md").read_text()
        parsed = candidates(answer)
        checks = {name: validate(task, busy, value, expected)
                  for name, value in parsed.items()}
        final = checks.get("final")
        qualified = bool(final and all(final[key] for key in
                                       ("correct_duration", "inside_one_window",
                                        "no_busy_overlap", "earliest")))
        if "headline" in checks:
            qualified = qualified and checks["headline"] == final
        rows.append({"case": case, "expected_start": expected.isoformat(),
                     "candidates": checks, "qualified": qualified})
    result = {"kind": "synthetic_calendar_answer_constraint_audit",
              "method": "regex_extract_headline_and_final_times_then_check_window_duration_busy_and_earliest",
              "cases": rows, "qualified_count": sum(row["qualified"] for row in rows)}
    target = BASE / "agent-quality-audit.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    target.chmod(0o600)
    print(json.dumps({"qualified_count": result["qualified_count"],
                      "cases": [{"case": row["case"], "qualified": row["qualified"],
                                 "checks": row["candidates"]} for row in rows]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
