"""Keep evidence choices diverse enough for multi-source research obligations."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def candidate_fingerprint(candidates: dict[str, dict[str, Any]]) -> str:
    payload = json.dumps(candidates, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def candidate_pool(evidence: list[dict[str, Any]], *, min_sources: int,
                   limit: int = 4) -> list[dict[str, Any]]:
    if type(min_sources) is not int or not 1 <= min_sources <= 4 or limit < min_sources:
        raise ValueError("invalid candidate diversity requirement")
    distinct = []
    seen_sources: set[str] = set()
    for row in evidence:
        source = row["source"]
        if source not in seen_sources:
            distinct.append(row)
            seen_sources.add(source)
    if len(distinct) < min_sources:
        raise ValueError("fewer independent sources than the answer point requires")
    # Reserve the required number of independent sources before filling the
    # remaining budget in the original retrieval rank order.
    selected = distinct[:min_sources]
    for row in evidence:
        if len(selected) >= limit:
            break
        if row not in selected:
            selected.append(row)
    return selected
