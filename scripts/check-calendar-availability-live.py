#!/usr/bin/env python3
"""Read-only smoke test of the availability tools against the SSS test calendar."""

from __future__ import annotations

import asyncio
import argparse
import importlib.util
import json
from pathlib import Path

from mcp import Client, StdioServerParameters

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("sss_doctor_mcp", ROOT / "scripts/doctor-mcp.py")
assert SPEC and SPEC.loader
DOCTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DOCTOR)

CASES = (
    ("A", "2026-10-12", 60, (("10:00", "12:00"), ("14:00", "17:00")), "10:15", "11:15"),
    ("B", "2026-10-13", 45, (("15:00", "17:30"),), "15:30", "16:15"),
    ("C-after-change", "2026-10-14", 90, (("09:00", "13:00"), ("14:00", "17:00")),
     "15:00", "16:30"),
)


async def main(production: bool = False) -> None:
    record = json.loads((ROOT / ".local/google-calendar/test-calendar.json").read_text())
    assert record["summary"] == "SSS MCP Test" and record["createdBySSS"]
    env = DOCTOR._google_proxy_env()
    env.update(SSS_BENCH_CALENDAR_ID=record["id"],
               GOOGLE_OAUTH_CREDENTIALS=str(ROOT / ".local/google-calendar/oauth-client.json"),
               GOOGLE_CALENDAR_MCP_TOKEN_PATH=str(ROOT / ".local/google-calendar/tokens.json"))
    parameters = (DOCTOR._stdio_parameters("google_calendar") if production else
                  StdioServerParameters(command="node", args=["scripts/calendar-scoped-benchmark-mcp.cjs"],
                                        cwd=ROOT, env=env))
    async with Client(parameters, read_timeout_seconds=45) as client:
        names = {tool.name for tool in (await client.list_tools()).tools}
        assert {"find-available-slots", "validate-slot"} <= names

        async def call(name: str, args: dict) -> dict:
            response = await client.call_tool(name, args)
            if response.is_error:
                raise RuntimeError(f"{name} failed: {response.content[0].text[:200]}")
            return json.loads(response.content[0].text)

        results = []
        for case, day, minutes, spans, start, end in CASES:
            prefix = lambda time: f"{day}T{time}:00+08:00"
            args = {"calendarId": record["id"], "timeZone": "Asia/Shanghai",
                    "durationMinutes": minutes,
                    "timeWindows": [{"start": prefix(a), "end": prefix(b)} for a, b in spans]}
            found = await call("find-available-slots", args)
            expected = {"start": prefix(start), "end": prefix(end)}
            assert found["earliest"] == expected, (case, found["earliest"])
            checked = await call("validate-slot", {**args, "candidateStart": expected["start"],
                                                    "candidateEnd": expected["end"]})
            assert checked["valid"] and checked["isEarliest"], case
            results.append({"case": case, "earliest": found["earliest"],
                            "sourceSha256": found["sourceSha256"]})
        args = {"calendarId": record["id"], "timeZone": "Asia/Shanghai", "durationMinutes": 90,
                "timeWindows": [{"start": "2026-10-14T09:00:00+08:00",
                                 "end": "2026-10-14T13:00:00+08:00"},
                                {"start": "2026-10-14T14:00:00+08:00",
                                 "end": "2026-10-14T17:00:00+08:00"}],
                "candidateStart": "2026-10-14T11:00:00+08:00",
                "candidateEnd": "2026-10-14T12:30:00+08:00"}
        stale = await call("validate-slot", args)
        assert stale["valid"] is False and stale["noConflict"] is False
        report = {"status": "passed", "bridge": "production" if production else "scoped",
                  "cases": results, "stale_c_rejected": True,
                  "model_requests": 0, "calendar_writes": 0}
        target = (ROOT / ".local/benchmarks/mcp-app-internal-v2/calendar/availability-v1" /
                  f"live-{report['bridge']}-smoke.json")
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        target.chmod(0o600)
        print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production", action="store_true", help="Check the production Calendar bridge")
    args = parser.parse_args()
    asyncio.run(main(production=args.production))
