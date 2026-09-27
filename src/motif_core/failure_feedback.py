"""Privacy-minimal failure evidence for later Motif guard revisions.

A failed execution is evidence that a particular binding was unsafe. It is not
permission to change a reusable Motif. Promotion requires a separate replay
and task-quality gate.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from .dependencies import DependencyResult


def _signature(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def dependency_failure_witness(*, motif_id: str, result: DependencyResult,
                               metadata: dict[str, Any], binding: dict[str, Any],
                               input_version: str) -> dict[str, Any]:
    """Record the failed operator and hashes, without copying task material."""
    if result.status != "BLOCKED" or not motif_id or not result.tool or not input_version:
        raise ValueError("a blocked, identified Motif execution is required")
    return {
        "schema_version": 1,
        "execution_id": uuid.uuid4().hex,
        "motif_id": motif_id,
        "operator": result.tool,
        "reason": result.reason,
        "error_class": result.error_class,
        "missing_params": list(result.missing),
        "motif_signature": _signature(metadata),
        "binding_signature": result.binding_signature or _signature(binding),
        "input_version": input_version,
        "disposition": "quarantined_candidate_evidence",
    }
