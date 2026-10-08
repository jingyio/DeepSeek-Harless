#!/usr/bin/env python3
"""Replay certified parameter transfers against fresh scoped Calendar MCP."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path

from mcp import Client, StdioServerParameters

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".local/benchmarks/mcp-app-internal-v2/calendar/motif-continuation-v1"
SPEC = importlib.util.spec_from_file_location("doctor", ROOT / "scripts/doctor-mcp.py")
assert SPEC and SPEC.loader
DOCTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DOCTOR)


async def main() -> None:
    artifact = json.loads((OUT / "calendar-certified-motif.json").read_text())
    calendar = json.loads((ROOT / ".local/google-calendar/test-calendar.json").read_text())
    env = DOCTOR._google_proxy_env()
    env.update(SSS_BENCH_CALENDAR_ID=calendar["id"],
               GOOGLE_OAUTH_CREDENTIALS=str(ROOT / ".local/google-calendar/oauth-client.json"),
               GOOGLE_CALENDAR_MCP_TOKEN_PATH=str(ROOT / ".local/google-calendar/tokens.json"))
    params = StdioServerParameters(command="node",
        args=["scripts/calendar-scoped-benchmark-mcp.cjs"], cwd=ROOT, env=env)
    rows = []
    async with Client(params, read_timeout_seconds=45) as client:
        async def call(name: str, args: dict) -> dict:
            result = await client.call_tool(name, args)
            if result.is_error:
                raise RuntimeError(f"read-only Calendar tool failed: {name}")
            return json.loads(result.content[0].text)

        for case in "de":
            path = OUT / f"agent-{case}/agent-events.jsonl"
            events = [json.loads(line) for line in path.read_text().splitlines()]
            find = next(row["data"] for row in events if row.get("type") == "tool/call"
                        and row["data"]["name"] == artifact["tools"][0])
            original = next(row["data"] for row in events if row.get("type") == "tool/call"
                            and row["data"]["name"] == artifact["tools"][1])
            root_args = json.loads(find["arguments"])
            found = await call("find-available-slots", root_args)
            derived = {edge["to_param"]: root_args[edge["from_param"]]
                       for edge in artifact["argument_carryover"]}
            for edge in artifact["transfer_evidence"]:
                value = found
                for part in edge["from_field"].split("."):
                    value = value[part]
                derived[edge["to_param"]] = value
            checked = await call("validate-slot", derived)
            if (derived != json.loads(original["arguments"]) or
                    found.get("sourceSha256") != checked.get("sourceSha256") or
                    checked.get("valid") is not True or
                    checked.get("isEarliest") is not True):
                raise RuntimeError(f"Case {case} failed certified shadow replay")
            rows.append({"case": case.upper(), "parameters_match_agent": True,
                         "same_source_and_valid": True,
                         "candidate": found["earliest"],
                         "source_sha256": found["sourceSha256"]})
    report = {"status": "live_shadow_passed", "synthetic_fixture": True,
              "model_requests": 0, "calendar_writes": 0,
              "certified_digest": artifact["certified_digest"], "cases": rows}
    target = OUT / "calendar-certified-shadow-replay.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    target.chmod(0o600)
    print(json.dumps({"status": report["status"], "cases": [r["case"] for r in rows],
                      "model_requests": 0}))


if __name__ == "__main__":
    asyncio.run(main())
