"""Record quote-checked evidence reused across answer points."""

from __future__ import annotations

from typing import Any


def cross_point_dependencies(
    claims: list[dict[str, Any]], citations: dict[str, dict[str, Any]],
    point_citations: dict[str, set[str]],
) -> list[dict[str, Any]]:
    edges = []
    for claim_index, claim in enumerate(claims, 1):
        target = claim["point_id"]
        if target not in point_citations:
            raise ValueError(f"unknown target point: {target}")
        for support in claim["supports"]:
            key = support["evidence_id"]
            if key in point_citations[target]:
                continue
            if key not in citations:
                raise ValueError(f"unknown cross-point citation: {key}")
            owners = sorted(point_id for point_id, allowed in point_citations.items()
                            if point_id != target and key in allowed)
            if not owners:
                raise ValueError(f"cross-point citation has no verified owner: {key}")
            row = citations[key]
            quote = "".join(char for char in support["quote"].casefold() if char.isalnum())
            passages = row.get("passages") or [row.get("snippet", "")]
            if (len(quote) < 12 or not any(
                    quote in "".join(char for char in passage.casefold() if char.isalnum())
                    for passage in passages)):
                raise ValueError(f"cross-point quote does not match current source: {key}")
            edges.append({
                "claim_index": claim_index, "target_point_id": target,
                "source_point_ids": owners, "evidence_id": key,
                "source": row["source"], "source_sha256": row["source_sha256"],
                "quote": support["quote"],
            })
    return edges
