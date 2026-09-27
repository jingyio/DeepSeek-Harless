#!/usr/bin/env python3
"""Summarize model and tool cost by DSH step without persisting source text."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.dsh_event_projection import is_original_tool_result  # noqa: E402

LOCAL = (ROOT / ".local").resolve()
TOKEN_KEYS = ("inputTokens", "cacheReadTokens", "outputTokens",
              "totalTokens", "reasoningTokens")


def _failed_result(event: Mapping[str, Any]) -> bool:
    data = event.get("data")
    if not isinstance(data, dict) or data.get("error"):
        return True
    message = data.get("message")
    blocks = message.get("content") if isinstance(message, dict) else None
    if not isinstance(blocks, list) or len(blocks) != 1:
        return True
    block = blocks[0]
    if not isinstance(block, dict) or block.get("isError") is True:
        return True
    content = block.get("content")
    if not isinstance(content, list) or len(content) != 1:
        return True
    message_text = content[0].get("text") if isinstance(content[0], dict) else None
    if not isinstance(message_text, str) or message_text.startswith("Error:"):
        return True
    try:
        payload = json.loads(message_text)
    except ValueError:
        return False
    return isinstance(payload, dict) and payload.get("status") in {
        "unavailable", "error", "failed"}


def summarize_events(events: Iterable[Mapping[str, Any]], *, run: str) -> dict[str, Any]:
    steps: dict[int, dict[str, Any]] = {}
    call_steps: dict[str, int] = {}
    call_names: dict[str, str] = {}
    unassigned_results = 0

    def row(number: int) -> dict[str, Any]:
        if number not in steps:
            steps[number] = {"step": number, "model_messages": 0,
                             "tools": Counter(), "failed_tools": Counter(),
                             **{key: 0 for key in TOKEN_KEYS}}
        return steps[number]

    for event in events:
        kind = event.get("type")
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        step = data.get("step")
        if kind == "assistant/message" and type(step) is int:
            usage = data.get("usage")
            if not isinstance(usage, dict):
                continue
            target = row(step)
            target["model_messages"] += 1
            for key in TOKEN_KEYS:
                target[key] += int(usage.get(key) or 0)
        elif kind == "tool/call" and type(step) is int:
            name, call_id = data.get("name"), data.get("callId")
            if not isinstance(name, str) or not name:
                continue
            row(step)["tools"][name] += 1
            if isinstance(call_id, str) and call_id:
                call_steps[call_id] = step
                call_names[call_id] = name
        elif kind == "tool/result" and is_original_tool_result(event):
            message = data.get("message")
            source = message.get("source") if isinstance(message, dict) else None
            call_id = source.get("callId") if isinstance(source, dict) else None
            assigned = call_steps.get(call_id)
            if assigned is None:
                unassigned_results += 1
                continue
            if _failed_result(event):
                target = row(assigned)
                target["failed_tools"][call_names[call_id]] += 1

    ordered = []
    for number in sorted(steps):
        current = steps[number]
        prompt = current["inputTokens"] + current["cacheReadTokens"]
        ordered.append({**current, "tools": dict(current["tools"]),
                        "failed_tools": dict(current["failed_tools"]),
                        "tool_calls": sum(current["tools"].values()),
                        "failed_tool_calls": sum(current["failed_tools"].values()),
                        "prompt_tokens": prompt,
                        "cache_hit_fraction": (round(current["cacheReadTokens"] / prompt, 4)
                                               if prompt else None)})
    totals = {key: sum(step[key] for step in ordered) for key in TOKEN_KEYS}
    return {"run": run, "steps": ordered,
            "model_messages": sum(step["model_messages"] for step in ordered),
            "tool_calls": sum(step["tool_calls"] for step in ordered),
            "failed_tool_calls": sum(step["failed_tool_calls"] for step in ordered),
            "unassigned_results": unassigned_results, "tokens": totals}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    output = args.out.resolve()
    if not output.is_relative_to(LOCAL):
        parser.error("output must be under .local")
    reports = []
    for path in args.events:
        source = path.resolve(strict=True)
        if not source.is_relative_to(LOCAL):
            parser.error("event logs must be under .local")
        events = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()
                  if line.strip()]
        reports.append(summarize_events(events, run=source.parent.name))
    result = {"runs": reports,
              "total_model_messages": sum(row["model_messages"] for row in reports),
              "total_tool_calls": sum(row["tool_calls"] for row in reports),
              "tokens": {key: sum(row["tokens"][key] for row in reports)
                         for key in TOKEN_KEYS},
              "note": "Step costs are SDK usage, not supplier billing; all steps remain in source logs."}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    output.chmod(0o600)
    print(json.dumps({"runs": len(reports),
                      "model_messages": result["total_model_messages"],
                      "tool_calls": result["total_tool_calls"],
                      "total_tokens": result["tokens"]["totalTokens"]},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
