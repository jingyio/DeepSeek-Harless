"""Discover exact application-object ID flow without promoting it to execution.

Opaque source handles and application IDs have different version semantics.
This miner records the latter from real tool results, but never treats a
repeated ID as permission to execute a successor or bypass the model.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from typing import Any

from src.adapters.dsh_event_projection import is_original_tool_result


OBJECT_ID = re.compile(r"^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*:[A-Za-z0-9_]+$")


def _fields(value: Any, path: str = ""):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _fields(child, f"{path}.{key}" if path else key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _fields(child, f"{path}.{index}" if path else str(index))
    elif isinstance(value, str) and OBJECT_ID.fullmatch(value):
        yield path, value


def _result(event: dict) -> dict | None:
    if not is_original_tool_result(event):
        return None
    blocks = event.get("data", {}).get("message", {}).get("content", [])
    if (len(blocks) != 1 or blocks[0].get("isError") or
            len(blocks[0].get("content", [])) != 1):
        return None
    item = blocks[0]["content"][0]
    if item.get("type") != "text":
        return None
    try:
        parsed = json.loads(item["text"])
    except (KeyError, TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def object_reference_witnesses(events: list[dict], approved_tools: set[str]
                               ) -> list[dict[str, str]]:
    """Require one earlier successful producer and one successful consumer."""
    calls: dict[str, tuple[str, dict]] = {}
    producers: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    pending: dict[str, list[dict[str, str]]] = {}
    witnesses = []
    for event in events:
        data = event.get("data", {})
        if event.get("type") == "tool/call":
            call_id, name = data.get("callId"), data.get("name")
            if not isinstance(call_id, str) or name not in approved_tools:
                continue
            try:
                args = json.loads(data.get("arguments", ""))
            except (TypeError, ValueError):
                continue
            if not isinstance(args, dict):
                continue
            calls[call_id] = (name, args)
            for param, value in args.items():
                if not isinstance(value, str) or not OBJECT_ID.fullmatch(value):
                    continue
                source = producers.get(value, [])
                if len(source) != 1:
                    continue
                _, from_tool, from_field = source[0]
                if from_tool == name:
                    continue
                pending.setdefault(call_id, []).append({
                    "from_tool": from_tool, "from_field": from_field,
                    "to_tool": name, "to_param": param})
        elif is_original_tool_result(event):
            call_id = data.get("message", {}).get("source", {}).get("callId")
            call = calls.get(call_id)
            value = _result(event)
            if call is None or value is None:
                continue
            name, args = call
            if (value.get("object_id") is not None and
                    args.get("object_id") is not None and
                    value["object_id"] != args["object_id"]):
                continue
            witnesses.extend(pending.pop(call_id, []))
            for field, object_id in _fields(value):
                producers[object_id].append((call_id, name, field))
    return witnesses


def repeated_object_edge_candidates(traces: list[dict], approved_tools: set[str]
                                    ) -> list[dict]:
    """Require two independent source tasks and one distinct validation task."""
    if (len(traces) != 3 or len({row.get("trace_id") for row in traces}) != 3 or
            len({row.get("decision_id") for row in traces}) != 3 or
            any(not row.get("decision_id") or not isinstance(row.get("events"), list)
                for row in traces)):
        raise ValueError("two training tasks and one distinct validation task are required")
    counts = [Counter(tuple(witness[key] for key in
                      ("from_tool", "from_field", "to_tool", "to_param"))
                      for witness in object_reference_witnesses(row["events"], approved_tools))
              for row in traces]
    shared = sorted(set(counts[0]) & set(counts[1]) & set(counts[2]))
    return [{"status": "witnessed_not_executable",
             "from_tool": edge[0], "from_field": edge[1],
             "to_tool": edge[2], "to_param": edge[3],
             "supporting_trace_ids": [row["trace_id"] for row in traces[:2]],
             "validation_trace_id": traces[2]["trace_id"],
             "witness_counts": {row["trace_id"]: count[edge]
                                for row, count in zip(traces, counts)},
             "missing_guard": "cross-object version and authorization relation"}
            for edge in shared]
