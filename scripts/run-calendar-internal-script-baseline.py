#!/usr/bin/env python3
"""Evaluate three synthetic scheduling requests through the real read-only Calendar MCP."""

from __future__ import annotations

import asyncio
import argparse
import hashlib
import importlib.util
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from mcp import Client, StdioServerParameters


ROOT = Path(__file__).resolve().parents[1]
DOCTOR_PATH = ROOT / "scripts/doctor-mcp.py"
SPEC = importlib.util.spec_from_file_location("sss_doctor_mcp", DOCTOR_PATH)
assert SPEC and SPEC.loader
DOCTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DOCTOR)
OUT = ROOT / ".local/benchmarks/mcp-app-internal-v2/calendar"
CALENDAR = "SSS MCP Test"
TASKS = (
    {"id": "A", "date": "2026-10-12", "minutes": 60,
     "windows": (("10:00", "12:00"), ("14:00", "17:00")),
     "expected_start": "2026-10-12T10:15:00+08:00"},
    {"id": "B", "date": "2026-10-13", "minutes": 45,
     "windows": (("15:00", "17:30"),),
     "expected_start": "2026-10-13T15:30:00+08:00"},
    {"id": "C", "date": "2026-10-14", "minutes": 90,
     "windows": (("09:00", "13:00"), ("14:00", "17:00")),
     "expected_start": "2026-10-14T11:00:00+08:00"},
)


def instant(date: str, hhmm: str) -> datetime:
    return datetime.fromisoformat(f"{date}T{hhmm}:00+08:00")


def earliest_slot(task: dict, busy: list[tuple[datetime, datetime]]) -> tuple[datetime, datetime] | None:
    duration = timedelta(minutes=task["minutes"])
    for left, right in task["windows"]:
        candidate = instant(task["date"], left)
        limit = instant(task["date"], right)
        while candidate + duration <= limit:
            overlaps = [(a, b) for a, b in busy if a < candidate + duration and b > candidate]
            if not overlaps:
                return candidate, candidate + duration
            candidate = max(b for _, b in overlaps)
    return None


async def main(scoped: bool = False, after_change: bool = False, current: bool = False) -> None:
    start = time.monotonic()
    calls: list[dict] = []
    if scoped:
        calendar = json.loads((ROOT / ".local/google-calendar/test-calendar.json").read_text())
        env = DOCTOR._google_proxy_env()
        env.update(SSS_BENCH_CALENDAR_ID=calendar["id"],
                   GOOGLE_OAUTH_CREDENTIALS=str(ROOT / ".local/google-calendar/oauth-client.json"),
                   GOOGLE_CALENDAR_MCP_TOKEN_PATH=str(ROOT / ".local/google-calendar/tokens.json"))
        parameters = StdioServerParameters(command="node",
            args=["scripts/calendar-scoped-benchmark-mcp.cjs"], cwd=ROOT, env=env)
    else:
        parameters = DOCTOR._stdio_parameters("google_calendar")

    async with Client(parameters, read_timeout_seconds=35) as client:
        async def call(name: str, args: dict) -> dict:
            response = await client.call_tool(name, args)
            if response.is_error:
                detail = " ".join(item.text[:240] for item in response.content if item.type == "text")
                raise RuntimeError(f"{name} returned MCP error: {detail}")
            blocks = [item.text for item in response.content if item.type == "text"]
            if len(blocks) != 1:
                raise RuntimeError(f"{name} did not return one JSON text block")
            data = json.loads(blocks[0])
            calls.append({"tool": name,
                          "args_sha256": hashlib.sha256(json.dumps(args, sort_keys=True).encode()).hexdigest(),
                          "result_sha256": hashlib.sha256(blocks[0].encode()).hexdigest(),
                          "result_bytes": len(blocks[0].encode())})
            return data

        listing = await call("list-calendars", {})
        matched = [c for c in listing.get("calendars", []) if c.get("summary") == CALENDAR]
        if len(matched) != 1:
            raise RuntimeError("Expected exactly one dedicated SSS test calendar")
        calendar_id = matched[0]["id"]
        frozen = json.loads((ROOT / ".local/google-calendar/test-calendar.json").read_text())
        if calendar_id != frozen["id"]:
            raise RuntimeError("Listed calendar differs from the SSS-owned test calendar")

        results = []
        selected = ([{**row, "expected_start": "2026-10-14T15:00:00+08:00"}
                     if row["id"] == "C" else row for row in TASKS]
                    if current else
                    [{**next(row for row in TASKS if row["id"] == "C"),
                      "expected_start": "2026-10-14T15:00:00+08:00"}]
                    if after_change else TASKS)
        for task in selected:
            day_start = instant(task["date"], "00:00")
            day_end = day_start + timedelta(days=1)
            common = {"calendarId": calendar_id, "timeMin": day_start.isoformat(),
                      "timeMax": day_end.isoformat(), "timeZone": "Asia/Shanghai"}
            events_data = await call("list-events", common)
            events = events_data.get("events", [])
            expected_count = 3 if task["id"] == "C" and (after_change or current) else 2
            if len(events) != expected_count or events_data.get("totalCount") != expected_count:
                raise RuntimeError(f"Case {task['id']} fixture changed: expected {expected_count} events")
            pinned = []
            for event in events:
                if not event.get("id", "").startswith("sss20260929cal") or not event.get("summary", "").startswith("SSS 测试｜"):
                    raise RuntimeError("Non-fixture event appears in the dedicated case window")
                detail = (await call("get-event", {"calendarId": calendar_id,
                                                    "eventId": event["id"], "fields": ["updated"]}))["event"]
                if any(detail.get(key) != event.get(key) for key in ("id", "start", "end", "updated")):
                    raise RuntimeError("Event version or timing changed between list and get")
                pinned.append({"id": detail["id"], "updated": detail.get("updated"),
                               "start": detail["start"]["dateTime"],
                               "end": detail["end"]["dateTime"]})
            freebusy = await call("get-freebusy", {"calendars": [{"id": calendar_id}],
                                                    "timeMin": day_start.isoformat(),
                                                    "timeMax": day_end.isoformat(),
                                                    "timeZone": "Asia/Shanghai"})
            calendar_busy = freebusy.get("calendars", {}).get(calendar_id, {}).get("busy", [])
            busy = sorted((datetime.fromisoformat(v["start"]), datetime.fromisoformat(v["end"]))
                          for v in calendar_busy)
            event_intervals = sorted((datetime.fromisoformat(v["start"]),
                                      datetime.fromisoformat(v["end"])) for v in pinned)
            if busy != event_intervals:
                raise RuntimeError("Free/busy disagrees with pinned event intervals")
            slot = earliest_slot(task, busy)
            if not slot or slot[0].isoformat() != task["expected_start"]:
                raise RuntimeError(f"Case {task['id']} output differs from frozen expected slot")
            results.append({"case": task["id"], "date": task["date"],
                            "duration_minutes": task["minutes"], "windows": task["windows"],
                            "busy": [{"start": a.isoformat(), "end": b.isoformat()} for a, b in busy],
                            "event_versions": pinned,
                            "recommended_start": slot[0].isoformat(),
                            "recommended_end": slot[1].isoformat()})
    OUT.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = {"kind": "synthetic_calendar_fixture_real_mcp", "status": "passed",
               "scoped_field_view": scoped,
               "after_change": after_change or current,
               "case_count": len(results), "mcp_calls": len(calls),
               "model_requests": 0, "elapsed_seconds": round(time.monotonic() - start, 3),
               "results": results, "calls": calls}
    if current:
        target = OUT / ("script-current-scoped.json" if scoped else "script-current.json")
    elif after_change:
        target = OUT / ("script-incremental-scoped.json" if scoped else "script-incremental.json")
    else:
        target = OUT / ("script-baseline-scoped.json" if scoped else "script-baseline.json")
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    target.chmod(0o600)
    print(json.dumps({key: payload[key] for key in
                      ("status", "case_count", "mcp_calls", "model_requests", "elapsed_seconds")},
                     ensure_ascii=False))
    for row in results:
        print(row["case"], row["recommended_start"], row["recommended_end"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scoped", action="store_true", help="Use the Agent's scoped field view")
    parser.add_argument("--after-change", action="store_true", help="Recheck C after the additional test event")
    parser.add_argument("--current", action="store_true", help="Recheck A/B and changed C together")
    args = parser.parse_args()
    if args.after_change and args.current:
        parser.error("Choose only one source-state mode")
    asyncio.run(main(scoped=args.scoped, after_change=args.after_change, current=args.current))
