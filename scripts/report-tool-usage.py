#!/usr/bin/env python3
"""Summarize exposed and called DSH tools without printing arguments or results."""

import argparse
from collections import Counter, defaultdict
import glob
import json
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from src.adapters.dsh_event_projection import is_original_tool_result  # noqa: E402

ROOT = PROJECT_ROOT / ".local" / "dsh" / "sessions"


def group(name: str) -> str:
    parts = name.split("__", 2)
    return parts[1] if len(parts) == 3 and parts[0] == "mcp" else "native"


def result_succeeded(event: dict) -> bool:
    data = event.get("data", {})
    if not isinstance(data, dict) or data.get("error"):
        return False
    message = data.get("message")
    blocks = message.get("content") if isinstance(message, dict) else None
    if not isinstance(blocks, list) or not blocks:
        return False
    for block in blocks:
        if not isinstance(block, dict) or block.get("isError") is True:
            return False
        parts = block.get("content")
        if not isinstance(parts, list) or not parts:
            return False
        for part in parts:
            value = part.get("text") if isinstance(part, dict) else None
            if not isinstance(value, str) or value.startswith("Error:"):
                return False
            try:
                payload = json.loads(value)
            except ValueError:
                continue
            if isinstance(payload, dict) and payload.get("status") in {
                    "unavailable", "error", "failed"}:
                return False
    return True


def summarize(events):
    exposed = set()
    calls = {}
    results = {}
    for event in events:
        kind = event.get("type")
        data = event.get("data", {})
        if kind == "request/header":
            for tool in data.get("header", {}).get("tools", []):
                if isinstance(tool, dict):
                    name = tool.get("name") or tool.get("function", {}).get("name")
                    if isinstance(name, str):
                        exposed.add(name)
        elif kind == "tool/call":
            call_id, name = data.get("callId"), data.get("name")
            if isinstance(call_id, str) and isinstance(name, str):
                calls[call_id] = name
        elif kind == "tool/result" and is_original_tool_result(event):
            message = data.get("message")
            source = message.get("source") if isinstance(message, dict) else None
            call_id = source.get("callId") if isinstance(source, dict) else None
            if isinstance(call_id, str):
                results.setdefault(call_id, result_succeeded(event))

    rows = defaultdict(lambda: {"exposed_tools": 0, "calls": 0, "reported_success": 0,
                                "reported_failure": 0, "no_result": 0, "called_tools": set()})
    for name in exposed:
        rows[group(name)]["exposed_tools"] += 1
    for call_id, name in calls.items():
        row = rows[group(name)]
        row["calls"] += 1
        row["called_tools"].add(name)
        if call_id not in results:
            row["no_result"] += 1
        elif results[call_id]:
            row["reported_success"] += 1
        else:
            row["reported_failure"] += 1
    for row in rows.values():
        row["distinct_called_tools"] = len(row.pop("called_tools"))
    return {
        "exposed_tools": len(exposed),
        "tool_calls": len(calls),
        "by_group": dict(sorted(rows.items())),
        "scope": "Call/result flags only; scientific contribution and whether an uncalled tool was needed require the task's tool-opportunity review.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize DSH tool exposure and calls")
    parser.add_argument("session", nargs="?", type=Path, help="session.v3.jsonl.zstd; defaults to newest local session")
    args = parser.parse_args()
    if args.session:
        path = args.session.expanduser().resolve(strict=True)
    else:
        candidates = [Path(p) for p in glob.glob(str(ROOT / "**" / "session.v3.jsonl.zstd"), recursive=True)]
        if not candidates:
            parser.error("no Harness session files found")
        path = max(candidates, key=lambda item: item.stat().st_mtime)
    result = subprocess.run(["zstdcat", str(path)], capture_output=True, text=True, check=True)
    report = summarize(json.loads(line) for line in result.stdout.splitlines())
    report["session_file"] = str(path)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
