#!/usr/bin/env python3
"""Freeze/run a paid Calendar Agent retest with the new read-only slot tools."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "calendar_agent_baseline", ROOT / "scripts/run-calendar-internal-agent-baseline.py")
assert SPEC and SPEC.loader
BASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASE)

SOURCE = ROOT / ".local/benchmarks/mcp-app-internal-v2/calendar"
OUT = SOURCE / "availability-v1"
BASE.OUT = OUT


def preview(case: str) -> dict:
    calendar = json.loads((ROOT / ".local/google-calendar/test-calendar.json").read_text())
    if calendar.get("summary") != "SSS MCP Test" or not calendar.get("createdBySSS"):
        raise ValueError("Dedicated test calendar record is missing")
    current_path = SOURCE / "script-current-scoped.json"
    original_path = SOURCE / "script-baseline-scoped.json"
    current = json.loads(current_path.read_text())
    original = json.loads(original_path.read_text())
    if current.get("status") != "passed" or current.get("case_count") != 3:
        raise ValueError("Current fixture state has not passed read-only verification")
    if original.get("status") != "passed":
        raise ValueError("Original read-only baseline is missing")
    for selected in "AB":
        old = next(row for row in original["results"] if row["case"] == selected)
        now = next(row for row in current["results"] if row["case"] == selected)
        if old["event_versions"] != now["event_versions"]:
            raise ValueError(f"Case {selected} source versions changed")
    row = next(row for row in current["results"] if row["case"] == case)
    return {
        "task_id": f"synthetic-calendar-availability-{case.lower()}-development",
        "comparison": "same prompt and A/B source versions; C is an incremental changed-source case",
        "synthetic_fixture": True, "real_calendar_mcp": True,
        "case": case, "model": "deepseek-flash", "reasoning_effort": "off",
        "budget_cap_usd": BASE.CAP_USD, "max_model_requests": BASE.MAX_REQUESTS,
        "max_output_tokens_per_request": BASE.MAX_OUTPUT,
        "read_only": True, "no_attendees_or_invitations": True,
        "test_calendar_id_sha256": hashlib.sha256(calendar["id"].encode()).hexdigest(),
        "current_source_sha256": BASE.sha(current_path),
        "source_event_versions": [dict(id_sha256=hashlib.sha256(v["id"].encode()).hexdigest(),
                                       updated=v["updated"]) for v in row["event_versions"]],
        "bridge_sha256": BASE.sha(BASE.BRIDGE),
        "availability_tool_sha256": BASE.sha(ROOT / "scripts/calendar-availability.cjs"),
        "prompt_sha256": hashlib.sha256(BASE.prompt(case).encode()).hexdigest(),
        "patch_sha256": hashlib.sha256(BASE.patch_text().encode()).hexdigest(),
    }


BASE.preview = preview


if __name__ == "__main__":
    raise SystemExit(BASE.main())
