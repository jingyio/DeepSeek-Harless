"""Rebind already quote-checked evidence for one missing research obligation.

This carries source evidence across answer points without carrying an old
conclusion as authority. The caller must first verify the source snapshot.
"""

from __future__ import annotations

from typing import Any


def _canonical(value: str) -> str:
    return "".join(char for char in value.casefold() if char.isalnum())


def rebind_accepted_evidence(
    claims: list[dict[str, Any]], citations: dict[str, dict[str, Any]],
    missing_ids: set[str], *, max_claims: int = 10, max_citations: int = 16,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], list[dict[str, str]]]:
    accepted = [claim for claim in claims if claim.get("point_id") not in missing_ids]
    if not accepted or len(accepted) > max_claims:
        raise ValueError("accepted-claim count is outside the bounded reuse scope")
    source_keys = list(dict.fromkeys(
        support["evidence_id"] for claim in accepted for support in claim.get("supports", [])
    ))
    if not source_keys or len(source_keys) > max_citations:
        raise ValueError("accepted evidence exceeds the bounded reuse scope")
    if any(key not in citations for key in source_keys):
        raise ValueError("accepted claim references missing source evidence")
    aliases = {key: f"R{index}" for index, key in enumerate(source_keys, 1)}
    rebound = {aliases[key]: citations[key] for key in source_keys}
    context: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    for claim in accepted:
        supports = claim.get("supports", [])
        if not supports:
            raise ValueError("accepted claim has no source support")
        rebound_supports = []
        for support in supports:
            key = support["evidence_id"]
            quote = support.get("quote")
            if (not isinstance(quote, str) or len(_canonical(quote)) < 12
                    or not any(_canonical(quote) in _canonical(passage) for passage in
                               (citations[key].get("passages") or [citations[key]["snippet"]]))):
                raise ValueError("accepted claim quote no longer matches its source excerpt")
            rebound_supports.append({"evidence_id": aliases[key], "quote": support["quote"]})
            for target in sorted(missing_ids):
                edges.append({"from_point": claim["point_id"], "to_point": target,
                              "original_evidence_id": key, "repair_evidence_id": aliases[key]})
        context.append({"point_id": claim["point_id"], "text": claim["text"],
                        "supports": rebound_supports})
    return rebound, context, edges
