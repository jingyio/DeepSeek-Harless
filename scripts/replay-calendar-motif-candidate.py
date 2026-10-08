#!/usr/bin/env python3
"""Shadow-replay a mined Calendar continuation through live read-only MCP."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path

from mcp import Client, StdioServerParameters

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / ".local/benchmarks/mcp-app-internal-v2/calendar/availability-v1"
SPEC = importlib.util.spec_from_file_location("sss_doctor_mcp", ROOT / "scripts/doctor-mcp.py")
assert SPEC and SPEC.loader
DOCTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DOCTOR)


def field(value: dict, path: str):
    for part in path.split("."):
        value = value[part]
    return value


def proposed_arguments(candidate: dict, root_arguments: dict, result: dict) -> dict:
    if (candidate.get("status") != "candidate_only_requires_independent_heldout"
            or candidate.get("online_execution_allowed") is not False
            or result.get("status") != "available"
            or not isinstance(result.get("sourceSha256"), str)
            or len(result["sourceSha256"]) != 64):
        raise ValueError("Candidate or fresh Calendar result cannot be shadow-replayed")
    args = {edge["to_param"]: field(result, edge["from_field"])
            for edge in candidate["output_edges"]}
    args.update({edge["to_param"]: root_arguments[edge["from_param"]]
                 for edge in candidate["argument_carryover"]})
    return args


def check_result(found: dict, checked: dict) -> bool:
    return (found.get("sourceSha256") == checked.get("sourceSha256")
            and checked.get("valid") is True
            and checked.get("isEarliest") is True)


async def main() -> None:
    candidate = json.loads((BASE / "calendar-find-validate-candidate.json").read_text())
    calendar = json.loads((ROOT / ".local/google-calendar/test-calendar.json").read_text())
    env = DOCTOR._google_proxy_env()
    env.update(SSS_BENCH_CALENDAR_ID=calendar["id"],
               GOOGLE_OAUTH_CREDENTIALS=str(ROOT / ".local/google-calendar/oauth-client.json"),
               GOOGLE_CALENDAR_MCP_TOKEN_PATH=str(ROOT / ".local/google-calendar/tokens.json"))
    parameters = StdioServerParameters(command="node",
        args=["scripts/calendar-scoped-benchmark-mcp.cjs"], cwd=ROOT, env=env)
    async with Client(parameters, read_timeout_seconds=45) as client:
        async def call(name: str, args: dict) -> dict:
            response = await client.call_tool(name, args)
            if response.is_error:
                raise RuntimeError(f"Read-only Calendar tool failed: {name}")
            return json.loads(response.content[0].text)

        rows = []
        for case in "bc":
            path = BASE / f"agent-{case}" / "agent-events.jsonl"
            events = [json.loads(line) for line in path.read_text().splitlines()]
            find = next(event["data"] for event in events
                if event.get("type") == "tool/call" and
                event["data"]["name"] == candidate["tools"][0])
            original_validate = next(event["data"] for event in events
                if event.get("type") == "tool/call" and
                event["data"]["name"] == candidate["tools"][1])
            root_args = json.loads(find["arguments"])
            found = await call("find-available-slots", root_args)
            predicted = proposed_arguments(candidate, root_args, found)
            exact_match = predicted == json.loads(original_validate["arguments"])
            checked = await call("validate-slot", predicted)
            if not exact_match or not check_result(found, checked):
                raise RuntimeError(f"Case {case} failed shadow replay")
            rows.append({"case": case.upper(), "predicted_arguments_match_trace": True,
                         "same_source_and_valid": True,
                         "source_sha256": found["sourceSha256"],
                         "trace_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    report = {"status": "shadow_passed_not_certified", "model_requests": 0,
              "calendar_writes": 0, "cases": rows}
    target = BASE / "calendar-motif-shadow-replay.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    target.chmod(0o600)
    print(json.dumps({"status": report["status"], "model_requests": 0,
                      "cases": [row["case"] for row in rows]}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
