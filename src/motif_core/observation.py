from __future__ import annotations

import ast
import json
import re
from typing import Any


def is_error_observation(observation: Any) -> bool:
    """Classify the error shapes emitted by TauBench and normalized runtime calls."""
    if isinstance(observation, dict):
        raw = observation.get("raw")
        if isinstance(raw, str) and raw.strip().lower().startswith("error"):
            return True
        if observation.get("error") not in (None, "", False):
            return True
        status = str(observation.get("status") or "").strip().lower()
        return status in {"error", "failed", "failure"}
    if isinstance(observation, str):
        return observation.strip().lower().startswith("error")
    return False


def normalize_observation_payload(observation: Any) -> dict[str, Any]:
    """Normalize tool observations without losing the compiler's scalar root."""
    if isinstance(observation, dict):
        if set(observation) == {"raw"} and observation.get("raw") is not None:
            return {"output": observation["raw"], "raw": observation["raw"]}
        return observation

    parsed: Any = observation
    if isinstance(observation, str):
        try:
            parsed = json.loads(observation)
        except Exception:
            match = re.search(r"\{.*\}", observation, re.DOTALL)
            if match:
                try:
                    parsed = ast.literal_eval(match.group())
                except Exception:
                    parsed = observation
        if isinstance(parsed, dict):
            return parsed

    raw = observation if isinstance(observation, str) else str(observation)
    return {"output": parsed, "raw": raw}
