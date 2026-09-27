"""Identify durable DSH tool observations across context replacements."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def is_original_tool_result(event: Mapping[str, Any]) -> bool:
    """Exclude result events appended only to replace model-visible context.

    DSH compaction can append a replacement with the same callId as an earlier
    result. That replacement changes the model's context, not the tool's
    original observation. Older event streams have no surfaceOp marker.
    """
    if event.get("type") != "tool/result":
        return False
    operation = event.get("surfaceOp")
    return operation is None or operation == "append" or (
        isinstance(operation, Mapping) and operation.get("op") == "append")
