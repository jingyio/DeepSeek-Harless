"""Detect a completed DSH turn whose saved final message is only a supplement."""

from __future__ import annotations


def supplemental_final(events: list[dict], final_response: str) -> bool:
    """Flag a short last message following a much longer answer plus a tool call.

    This is a delivery guard, not a scientific-quality judge. It conservatively
    flags the observed pattern and leaves ambiguous answers for human review.
    """
    if not isinstance(final_response, str) or len(final_response.strip()) >= 700:
        return False
    calls = {(row.get("data") or {}).get("step")
             for row in events if row.get("type") == "tool/call"}
    for row in events:
        if row.get("type") != "assistant/message":
            continue
        data = row.get("data") or {}
        if data.get("step") not in calls:
            continue
        content = (data.get("message") or {}).get("content") or []
        text = "".join(part.get("text", "") for part in content
                       if isinstance(part, dict) and part.get("type") == "text")
        if len(text) >= 800 and len(text) >= 3 * max(1, len(final_response.strip())):
            return True
    return False
