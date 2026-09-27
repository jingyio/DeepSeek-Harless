"""Typed reentry for a Motif research gap served by DeepSeek Harness.

The adapter accepts a replayed response or a Harness caller. The core owns the
handoff and verifies its current source/point scope before and after mediation.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

from src.adapters.dsh_client import SemanticValidationError
from src.adapters.harness_semantic import _parse_response
from src.adapters.point_research_semantic import (
    parse_point_selection, repair_same_page_selection_aliases,
)
from src.adapters.research_repair_semantic import parse_repair_queries
from src.motif_core.handoff import SemanticResolution, StructureHandoffRequest
from src.workflows.point_candidate_pool import candidate_fingerprint


def _signature(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _scope(request: StructureHandoffRequest, prompt: str,
           point_ids: list[str], sources: list[dict[str, str]]) -> str:
    if (request.handoff_type != "need_semantic_resolution"
            or request.source != "point_query_planning"
            or request.missing_slots != ["queries_by_point"]
            or request.allowed_reentry != {"mode": "same_motif", "candidates": point_ids}
            or request.available_state.get("point_ids") != point_ids
            or request.available_state.get("sources") != sources
            or request.metadata.get("prompt_sha256") != hashlib.sha256(prompt.encode()).hexdigest()):
        raise ValueError("Motif handoff no longer matches current research state")
    return _signature(request.to_dict())


def _normalize_repeated_query_points(raw: str, point_ids: list[str]
                                     ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep the first valid query per point and record discarded repetitions."""
    value = raw.strip()
    if value.startswith("```"):
        import re
        value = re.sub(r"^```(?:json)?\s*|\s*```$", "", value, flags=re.IGNORECASE).strip()
    payload = json.loads(value)
    if not isinstance(payload, dict) or set(payload) != {"queries"} or not isinstance(payload["queries"], list):
        raise ValueError("invalid repair query schema")
    chosen: dict[str, dict[str, Any]] = {}
    dropped = []
    for index, row in enumerate(payload["queries"], 1):
        if not isinstance(row, dict) or set(row) != {"point_id", "terms"}:
            raise ValueError("invalid repair query entry")
        point_id = row["point_id"]
        if point_id not in point_ids:
            raise ValueError("unknown repair point")
        terms = row["terms"]
        if (not isinstance(terms, list) or not 2 <= len(terms) <= 8 or
                any(not isinstance(term, str) or not 3 <= len(term.strip()) <= 60
                    for term in terms)):
            raise ValueError("invalid repair search terms")
        if len(terms) > 4:
            dropped.append({"entry_index": index, "point_id": point_id,
                            "reason": "more than four terms; first four retained",
                            "dropped_terms": terms[4:]})
            row = {"point_id": point_id, "terms": terms[:4]}
        # Validate each retained row independently, including duplicates.
        validated = parse_repair_queries(
            json.dumps({"queries": [row]}, ensure_ascii=False), {point_id})[0]
        if point_id in chosen:
            dropped.append({"entry_index": index, "point_id": point_id,
                            "reason": "repeated point; first valid entry retained"})
        else:
            chosen[point_id] = validated
    if set(chosen) != set(point_ids):
        raise ValueError("each missing point needs one repair query")
    return [chosen[point_id] for point_id in point_ids], dropped


def resolve_point_query_handoff(
    request: StructureHandoffRequest, *, prompt: str,
    point_ids: list[str], sources: list[dict[str, str]],
    replay_response: str | None = None,
    call_harness: Callable[[str], tuple[str, dict[str, Any]]] | None = None,
) -> tuple[str, dict[str, Any], SemanticResolution]:
    """Call the semantic port once, or replay it, and validate a bounded result."""
    handoff_signature = _scope(request, prompt, point_ids, sources)
    if (replay_response is None) == (call_harness is None):
        raise ValueError("provide exactly one semantic response source")
    if replay_response is not None:
        raw, metrics = replay_response, {}
    else:
        raw, metrics = call_harness(prompt)
    try:
        queries, dropped = _normalize_repeated_query_points(raw, point_ids)
    except (ValueError, TypeError) as exc:
        # The Harness request has already happened. Preserve its usage and raw
        # response even when structural validation rejects the answer.
        raise SemanticValidationError(str(exc), metrics=metrics,
                                      raw_response=raw) from exc
    resolution = SemanticResolution(
        resolution_type="slot_fill",
        slot_values={"queries_by_point": queries},
        metadata={"handoff_signature": handoff_signature,
                  "slot_signature": _signature(queries),
                  "response_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                  "query_normalization": dropped},
    )
    return raw, metrics, resolution


def reenter_point_query_handoff(
    request: StructureHandoffRequest, resolution: SemanticResolution, *, prompt: str,
    point_ids: list[str], sources: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Reject a stale or out-of-scope semantic answer before structural progress."""
    expected = _scope(request, prompt, point_ids, sources)
    if (resolution.resolution_type != "slot_fill"
            or set(resolution.slot_values) != {"queries_by_point"}
            or resolution.metadata.get("handoff_signature") != expected):
        raise ValueError("semantic resolution cannot reenter this Motif state")
    queries = resolution.slot_values["queries_by_point"]
    if resolution.metadata.get("slot_signature") != _signature(queries):
        raise ValueError("semantic resolution changed after validation")
    # Recheck the content, not just the signature of its originating handoff.
    reparsed = parse_repair_queries(
        json.dumps({"queries": queries}, ensure_ascii=False), set(point_ids))
    return reparsed


def _selection_scope(
    request: StructureHandoffRequest, *, prompt: str,
    points: list[dict[str, Any]], candidates: dict[str, dict[str, Any]],
    sources: list[dict[str, str]],
) -> str:
    point_ids = [point["id"] for point in points]
    allowed_ids = sorted(key for key, row in candidates.items()
                         if row["point_id"] in set(point_ids))
    if (request.handoff_type != "need_semantic_resolution"
            or request.source != "point_evidence_selection"
            or request.missing_slots != ["selected_ids_by_point"]
            or request.allowed_reentry != {"mode": "same_motif", "candidates": allowed_ids}
            or request.available_state.get("point_ids") != point_ids
            or request.available_state.get("sources") != sources
            or request.available_state.get("candidate_sha256") != candidate_fingerprint(candidates)
            or request.metadata.get("prompt_sha256") != hashlib.sha256(prompt.encode()).hexdigest()):
        raise ValueError("Motif selection handoff no longer matches current evidence")
    return _signature(request.to_dict())


def resolve_point_selection_handoff(
    request: StructureHandoffRequest, *, prompt: str,
    points: list[dict[str, Any]], candidates: dict[str, dict[str, Any]],
    sources: list[dict[str, str]],
    replay_response: str | None = None,
    call_harness: Callable[[str], tuple[str, dict[str, Any]]] | None = None,
) -> tuple[str, dict[str, Any], SemanticResolution]:
    """Validate a bounded selection before it enters the Motif's evidence state."""
    handoff_signature = _selection_scope(
        request, prompt=prompt, points=points, candidates=candidates, sources=sources)
    if (replay_response is None) == (call_harness is None):
        raise ValueError("provide exactly one semantic response source")
    if replay_response is not None:
        raw, metrics = replay_response, {}
    else:
        raw, metrics = call_harness(prompt)
    changes: list[dict[str, str]] = []
    try:
        try:
            selected = parse_point_selection(raw, points, candidates)
        except ValueError:
            selected, changes = repair_same_page_selection_aliases(raw, points, candidates)
    except (ValueError, TypeError) as exc:
        raise SemanticValidationError(str(exc), metrics=metrics,
                                      raw_response=raw) from exc
    resolution = SemanticResolution(
        resolution_type="candidate_selection",
        slot_values={"selected_ids_by_point": selected},
        metadata={"handoff_signature": handoff_signature,
                  "slot_signature": _signature(selected),
                  "response_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                  "alias_normalization": changes},
    )
    return raw, metrics, resolution


def reenter_point_selection_handoff(
    request: StructureHandoffRequest, resolution: SemanticResolution, *, prompt: str,
    points: list[dict[str, Any]], candidates: dict[str, dict[str, Any]],
    sources: list[dict[str, str]],
) -> dict[str, list[str]]:
    expected = _selection_scope(
        request, prompt=prompt, points=points, candidates=candidates, sources=sources)
    if (resolution.resolution_type != "candidate_selection"
            or set(resolution.slot_values) != {"selected_ids_by_point"}
            or resolution.metadata.get("handoff_signature") != expected):
        raise ValueError("semantic selection cannot reenter this Motif state")
    selected = resolution.slot_values["selected_ids_by_point"]
    if resolution.metadata.get("slot_signature") != _signature(selected):
        raise ValueError("semantic selection changed after validation")
    raw = json.dumps({"selections": [
        {"point_id": point_id, "evidence_ids": keys}
        for point_id, keys in selected.items()
    ]}, ensure_ascii=False)
    return parse_point_selection(raw, points, candidates)


def _synthesis_scope(
    request: StructureHandoffRequest, *, prompt: str,
    point_ids: list[str], citations: dict[str, dict[str, Any]],
    point_citations: dict[str, set[str]], sources: list[dict[str, str]],
) -> str:
    citation_scope = {key: sorted(value) for key, value in point_citations.items()}
    if (request.handoff_type != "need_semantic_resolution"
            or request.source != "point_evidence_synthesis"
            or request.missing_slots != ["claims_by_point"]
            or request.allowed_reentry != {"mode": "same_motif", "candidates": point_ids}
            or request.available_state.get("point_ids") != point_ids
            or request.available_state.get("sources") != sources
            or request.available_state.get("citations_sha256") != _signature(citations)
            or request.available_state.get("point_citations_sha256") != _signature(citation_scope)
            or request.metadata.get("prompt_sha256") != hashlib.sha256(prompt.encode()).hexdigest()):
        raise ValueError("Motif synthesis handoff no longer matches current evidence")
    return _signature(request.to_dict())


def resolve_point_synthesis_handoff(
    request: StructureHandoffRequest, *, prompt: str,
    point_ids: list[str], citations: dict[str, dict[str, Any]],
    point_citations: dict[str, set[str]], sources: list[dict[str, str]],
    replay_response: str | None = None,
    call_harness: Callable[[str], tuple[str, dict[str, Any]]] | None = None,
) -> tuple[str, dict[str, Any], SemanticResolution]:
    handoff_signature = _synthesis_scope(
        request, prompt=prompt, point_ids=point_ids,
        citations=citations, point_citations=point_citations, sources=sources)
    if (replay_response is None) == (call_harness is None):
        raise ValueError("provide exactly one semantic response source")
    if replay_response is not None:
        raw, metrics = replay_response, {}
    else:
        raw, metrics = call_harness(prompt)
    try:
        claims, uncertainties, rejected = _parse_response(
            raw, citations, point_ids=set(point_ids), point_citations=point_citations,
            allow_cross_point_reuse=request.metadata.get("allow_cross_point_reuse") is True)
    except (ValueError, TypeError, KeyError) as exc:
        raise SemanticValidationError(str(exc), metrics=metrics,
                                      raw_response=raw) from exc
    slots = {"claims": claims, "uncertainties": uncertainties,
             "rejected_claims": rejected}
    resolution = SemanticResolution(
        resolution_type="evidence_synthesis", slot_values=slots,
        metadata={"handoff_signature": handoff_signature,
                  "slot_signature": _signature(slots),
                  "response_sha256": hashlib.sha256(raw.encode()).hexdigest()},
    )
    return raw, metrics, resolution


def reenter_point_synthesis_handoff(
    request: StructureHandoffRequest, resolution: SemanticResolution, *,
    raw_response: str, prompt: str, point_ids: list[str],
    citations: dict[str, dict[str, Any]],
    point_citations: dict[str, set[str]], sources: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], list[Any], list[dict[str, str]]]:
    expected = _synthesis_scope(
        request, prompt=prompt, point_ids=point_ids,
        citations=citations, point_citations=point_citations, sources=sources)
    if (resolution.resolution_type != "evidence_synthesis"
            or set(resolution.slot_values) != {"claims", "uncertainties", "rejected_claims"}
            or resolution.metadata.get("handoff_signature") != expected
            or resolution.metadata.get("response_sha256") != hashlib.sha256(raw_response.encode()).hexdigest()
            or resolution.metadata.get("slot_signature") != _signature(resolution.slot_values)):
        raise ValueError("semantic synthesis cannot reenter this Motif state")
    reparsed = _parse_response(
        raw_response, citations, point_ids=set(point_ids), point_citations=point_citations,
        allow_cross_point_reuse=request.metadata.get("allow_cross_point_reuse") is True)
    if list(reparsed) != [resolution.slot_values[key] for key in
                          ("claims", "uncertainties", "rejected_claims")]:
        raise ValueError("semantic synthesis changed after validation")
    return reparsed
