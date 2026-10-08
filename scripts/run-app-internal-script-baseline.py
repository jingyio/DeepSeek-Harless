#!/usr/bin/env python3
"""Read the two approved app scopes with a deterministic, no-model MCP script.

This measures only the structural retrieval segment. It does not produce the
research judgment required of the Agent and is not a full-quality comparator.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path

from mcp import Client, StdioServerParameters


ROOT = Path(__file__).resolve().parents[1]
SCOPE = ROOT / ".local/benchmarks/research-weekly-loop/paper-impact-p1-20260927/source-scope.json"
APPROVAL = SCOPE.parent / "APPROVAL.json"
BASE = ROOT / ".local/benchmarks/mcp-app-internal-v2"
TASKS = {
    "zotero": {
        "module": "src.mcp.scoped_zotero_read_server",
        "roles": ["antibody_item", *(f"antibody_annotation_{n}" for n in range(1, 7))],
        "list": "list_scoped_zotero_sources", "pin": "pin_scoped_zotero_source",
    },
    "obsidian": {
        "module": "src.mcp.scoped_obsidian_read_server",
        "roles": ["current_state", "open_questions"],
        "list": "list_scoped_notes", "pin": "pin_scoped_note",
    },
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_approval(category: str) -> dict[str, dict]:
    scope = json.loads(SCOPE.read_text(encoding="utf-8"))
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    if (scope.get("status") != "approved_for_model" or approval.get("approved") is not True
            or approval.get("scope_sha256") != sha(SCOPE)):
        raise ValueError("Approved source scope changed")
    source_list = scope["zotero_sources"] if category == "zotero" else scope["sources"]
    selected = {row["role"]: row for row in source_list
                if row.get("role") in TASKS[category]["roles"]}
    if (set(selected) != set(TASKS[category]["roles"])
            or any(row.get("external_model_excerpt_allowed") is not True
                   for row in selected.values())):
        raise ValueError("Required source roles are no longer approved")
    return selected


async def run(category: str) -> dict:
    task = TASKS[category]
    selected = check_approval(category)
    env = os.environ.copy()
    env["SSS_RESEARCH_SCOPE_FILE"] = str(SCOPE)
    env["SSS_SCOPED_HANDLE_MODE"] = "1"
    if category == "obsidian":
        env["SSS_SCOPED_NOTES_ONLY"] = "1"
    params = StdioServerParameters(command=sys.executable,
                                   args=["-m", task["module"]], cwd=ROOT, env=env)
    calls = []
    started = time.monotonic()

    async with Client(params, read_timeout_seconds=60) as client:
        async def call(name: str, arguments: dict) -> dict:
            began = time.monotonic()
            reply = await client.call_tool(name, arguments)
            payload = getattr(reply, "structured_content", None)
            calls.append({"tool": name, "elapsed_seconds": round(time.monotonic() - began, 4),
                          "is_error": bool(getattr(reply, "is_error", False))})
            if getattr(reply, "is_error", False) or not isinstance(payload, dict):
                raise RuntimeError(f"{name} failed")
            return payload

        listed = await call(task["list"], {})
        listed_roles = {row["role"] for row in listed.get("sources" if category == "zotero"
                                                               else "notes", [])}
        if not set(task["roles"]) <= listed_roles:
            raise ValueError("MCP source list differs from approved scope")
        for role in task["roles"]:
            pinned = await call(task["pin"], {"role": role})
            if category == "zotero":
                read_tool = ("read_pinned_zotero_item" if selected[role]["kind"] == "item"
                             else "read_pinned_zotero_annotation")
                expected_hash_field = "data_sha256"
            else:
                read_tool = "read_pinned_approved_note_excerpt"
                expected_hash_field = "sha256"
            read = await call(read_tool, {"source_id": pinned["source_id"]})
            if (read.get("source_id") != pinned["source_id"]
                    or read.get(expected_hash_field) != selected[role][expected_hash_field]):
                raise ValueError("MCP read source or version differs from approval")

    result = {"category": category, "source_scope_sha256": sha(SCOPE),
              "read_roles": task["roles"], "tool_calls": calls,
              "tool_call_count": len(calls), "model_requests": 0, "model_cost_usd": 0,
              "elapsed_seconds": round(time.monotonic() - started, 3),
              "quality_scope": "structural retrieval only; no scientific answer"}
    out = BASE / category / "script-baseline.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    out.chmod(0o600)
    return result


async def main() -> None:
    for category in TASKS:
        result = await run(category)
        print(json.dumps({"category": category, "status": "completed",
                          "tool_calls": result["tool_call_count"],
                          "model_requests": 0,
                          "elapsed_seconds": result["elapsed_seconds"]}))


if __name__ == "__main__":
    asyncio.run(main())
