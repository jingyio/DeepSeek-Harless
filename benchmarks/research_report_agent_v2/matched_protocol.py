"""Opt-in controlled comparison, never a substitute for a semantic decision.

The frozen specification is visible input supplied identically to both arms.
Real LLM calls must still submit it through the normal approval tools, whose
scientific/provenance checks remain active. No model response is manufactured.
Natural-request runs without this metadata are unaffected.
"""
from __future__ import annotations

import copy
import hashlib
import json


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def fixed_decisions(study: dict) -> dict | None:
    value = study.get("benchmark_frozen_decisions")
    if value is None:
        return None
    if not isinstance(value, dict) or value.get("protocol_version") != 1:
        raise ValueError("Invalid explicitly supplied controlled-comparison protocol")
    if not isinstance(value.get("plan"), dict):
        raise ValueError("Controlled comparison requires a frozen plan")
    if value["plan"].get("interpretation_mode") == "custom" and not isinstance(value.get("commentary"), dict):
        raise ValueError("Controlled custom comparison requires frozen commentary")
    expected = hashlib.sha256(_canonical({k: value[k] for k in ("plan", "commentary") if k in value}).encode()).hexdigest()
    if value.get("decision_sha256") != expected:
        raise ValueError("Frozen comparison decisions changed")
    return copy.deepcopy(value)


def validate_fixed_decision(study: dict, field: str, actual: dict) -> None:
    if field not in {"plan", "commentary"}:
        raise ValueError("Unsupported comparison decision field")
    fixed = fixed_decisions(study)
    if fixed is None:
        return
    if field not in fixed or _canonical(actual) != _canonical(fixed[field]):
        raise ValueError("Controlled-comparison decision differs from the supplied frozen " + field +
                         ". Submit the visible specification exactly, or report its conflict with the actual evidence. "
                         "This check does not authorize an invalid analysis or bypass normal validation.")

