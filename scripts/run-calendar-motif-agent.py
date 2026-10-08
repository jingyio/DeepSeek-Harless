#!/usr/bin/env python3
"""Freeze/run independent Calendar D/E ordinary Agent traces for Motif evaluation."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "calendar_agent_baseline", ROOT / "scripts/run-calendar-internal-agent-baseline.py")
assert SPEC and SPEC.loader
BASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASE)

OUT = ROOT / ".local/benchmarks/mcp-app-internal-v2/calendar/motif-continuation-v1"
FIXTURE = ROOT / "scripts/setup-calendar-motif-fixture.cjs"
BASE.OUT = OUT
BASE.TASKS = {
    "D": ("2026-10-15", "50 分钟", "09:00–12:00 或 14:00–16:00"),
    "E": ("2026-10-16", "55 分钟", "09:00–12:00 或 14:00–16:00"),
}


def preview(case: str) -> dict:
    calendar = json.loads((ROOT / ".local/google-calendar/test-calendar.json").read_text())
    if calendar.get("summary") != "SSS MCP Test" or not calendar.get("createdBySSS"):
        raise ValueError("Dedicated test calendar record is missing")
    return {
        "task_id": f"synthetic-calendar-motif-{case.lower()}-ordinary",
        "role": "D held-out certification" if case == "D" else "E same-source ordinary baseline",
        "synthetic_fixture": True, "real_calendar_mcp": True,
        "case": case, "model": "deepseek-flash", "reasoning_effort": "off",
        "budget_cap_usd": BASE.CAP_USD, "max_model_requests": BASE.MAX_REQUESTS,
        "max_output_tokens_per_request": BASE.MAX_OUTPUT,
        "read_only": True, "no_attendees_or_invitations": True,
        "test_calendar_id_sha256": hashlib.sha256(calendar["id"].encode()).hexdigest(),
        "fixture_plan_sha256": BASE.sha(FIXTURE),
        "bridge_sha256": BASE.sha(BASE.BRIDGE),
        "availability_tool_sha256": BASE.sha(ROOT / "scripts/calendar-availability.cjs"),
        "prompt_sha256": hashlib.sha256(BASE.prompt(case).encode()).hexdigest(),
        "patch_sha256": hashlib.sha256(BASE.patch_text().encode()).hexdigest(),
    }


BASE.preview = preview


if __name__ == "__main__":
    if "--call-model" in sys.argv:
        manifest = json.loads((OUT / "fixture-manifest.json").read_text())
        if (manifest.get("mode") != "--apply" or
                {row["id"] for row in manifest.get("events", [])} !=
                {f"sss20260929cal{suffix}" for suffix in ("d1", "d2", "e1", "e2")} or
                any(row["action"] not in {"created", "already_present"}
                    for row in manifest.get("operations", []))):
            raise ValueError("Dedicated D/E fixture was not verified")
    raise SystemExit(BASE.main())
