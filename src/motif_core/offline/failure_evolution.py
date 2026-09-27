"""Failure-derived Motif guard proposals; never enables a guard on its own.

An exact failed binding can suggest a negative guard, but a failure witness is
only a candidate. Separate replays must reproduce it and show a contrasting
successful input. Task-quality review is still required before deployment.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Iterable

from .trace_compiler import artifact_signature


_KEYS = ("motif_id", "operator", "reason", "error_class",
         "motif_signature", "binding_signature", "input_version")


def _fingerprint(witness: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(witness.get(key) for key in _KEYS)


def _signature(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _checked_witness(artifact: dict[str, Any], witness: dict[str, Any]) -> None:
    if (witness.get("schema_version") != 1
            or witness.get("disposition") != "quarantined_candidate_evidence"
            or not witness.get("execution_id")
            or witness.get("motif_id") != artifact.get("motif_id")
            or witness.get("operator") not in artifact.get("tools", [])
            or witness.get("motif_signature") != _signature(artifact.get("dependencies"))
            or witness.get("reason") != "dependency_tool_error"
            or not all(witness.get(key) for key in _KEYS)):
        raise ValueError("failure witness is not an identified tool failure")


def propose_exact_failure_guard(
    artifact: dict[str, Any], witnesses: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Propose a narrow negative guard after two separate failed executions."""
    if (artifact.get("status") != "trace_validated_read_only"
            or artifact.get("certified_digest") != artifact_signature(artifact)):
        raise ValueError("failure guard needs a current certified Motif")
    rows = list(witnesses)
    if len(rows) < 2:
        raise ValueError("failure guard needs repeated execution evidence")
    for row in rows:
        _checked_witness(artifact, row)
    if (len({row["execution_id"] for row in rows}) != len(rows)
            or len({_fingerprint(row) for row in rows}) != 1):
        raise ValueError("failure witnesses do not independently reproduce one binding")
    first = rows[0]
    return {
        "schema_version": 1,
        "status": "quarantined_guard_proposal",
        "motif_id": first["motif_id"],
        "artifact_digest": artifact["certified_digest"],
        "operator": first["operator"],
        "failure_reason": first["reason"],
        "error_class": first["error_class"],
        "motif_signature": first["motif_signature"],
        "binding_signature": first["binding_signature"],
        "input_version": first["input_version"],
        "source_execution_ids": [row["execution_id"] for row in rows],
    }


def guard_matches(proposal: dict[str, Any], artifact: dict[str, Any], *,
                  operator: str, binding_signature: str,
                  input_version: str) -> bool:
    """Inspect the proposal's exact scope; this does not authorize execution."""
    return bool(
        proposal.get("schema_version") == 1
        and proposal.get("status") in {
            "quarantined_guard_proposal", "replay_validated_candidate"}
        and artifact.get("certified_digest") == artifact_signature(artifact)
        and proposal.get("artifact_digest") == artifact["certified_digest"]
        and proposal.get("motif_id") == artifact.get("motif_id")
        and proposal.get("operator") == operator
        and proposal.get("binding_signature") == binding_signature
        and proposal.get("input_version") == input_version
    )


def validate_failure_guard_replays(
    proposal: dict[str, Any], artifact: dict[str, Any], *,
    failed_replay_witnesses: Iterable[dict[str, Any]],
    successful_contrasts: Iterable[Any],
) -> dict[str, Any]:
    """Check reproduction and nonmatching success; keep candidate disabled."""
    if (proposal.get("status") != "quarantined_guard_proposal"
            or proposal.get("artifact_digest") != artifact.get("certified_digest")):
        raise ValueError("failure guard proposal is stale")
    failures = list(failed_replay_witnesses)
    if len(failures) < 2:
        raise ValueError("independent failure replays are required")
    seen = set(proposal.get("source_execution_ids", []))
    expected = (proposal["motif_id"], proposal["operator"],
                proposal["failure_reason"], proposal["error_class"],
                proposal["motif_signature"], proposal["binding_signature"],
                proposal["input_version"])
    for row in failures:
        _checked_witness(artifact, row)
        if row["execution_id"] in seen or _fingerprint(row) != expected:
            raise ValueError("failure replay does not reproduce the proposal")
        seen.add(row["execution_id"])
    contrasts = list(successful_contrasts)
    if not contrasts:
        raise ValueError("a successful contrast run is required")
    for run in contrasts:
        if (run.status != "completed" or run.motif_id != proposal["motif_id"]
                or not isinstance(run.bindings, dict)
                or not run.input_version):
            raise ValueError("contrast is not a successful Motif run")
        records = [record for record in run.manager.evidence.records.values()
                   if record["type"] == proposal["operator"]]
        if len(records) != 1:
            raise ValueError("contrast needs one identified successful operator binding")
        if guard_matches(
            proposal, artifact, operator=proposal["operator"],
            binding_signature=_signature(records[0]["binding"]),
            input_version=run.input_version,
        ):
            raise ValueError("proposed guard would block a successful contrast")
    return {
        **proposal, "status": "replay_validated_candidate",
        "replay_execution_ids": [row["execution_id"] for row in failures],
        "contrast_count": len(contrasts),
    }


def promote_failure_guard(
    candidate: dict[str, Any], artifact: dict[str, Any], *,
    quality_review: dict[str, Any],
) -> dict[str, Any]:
    """Create an exact active guard only after an external task-quality review.

    This records the review; it cannot independently establish that a human
    performed it. The runtime also checks the guard's exact artifact, input
    version and effective operator binding before suppressing a retry.
    """
    if (candidate.get("status") != "replay_validated_candidate"
            or candidate.get("artifact_digest") != artifact.get("certified_digest")
            or artifact.get("certified_digest") != artifact_signature(artifact)
            or candidate.get("operator") not in artifact.get("tools", [])
            or str(candidate["operator"]).endswith("+")):
        raise ValueError("only a replay-validated scalar Motif guard can be promoted")
    if not isinstance(quality_review, dict):
        raise ValueError("task-quality review must be a record")
    review_ids = quality_review.get("task_ids")
    if (quality_review.get("result") != "pass"
            or not isinstance(quality_review.get("review_id"), str)
            or not quality_review["review_id"]
            or not isinstance(quality_review.get("reviewer_id"), str)
            or not quality_review["reviewer_id"]
            or not isinstance(review_ids, list) or not review_ids
            or any(not isinstance(item, str) or not item for item in review_ids)
            or len(set(review_ids)) != len(review_ids)
            or set(review_ids) & set(candidate.get("source_execution_ids", []))
            or set(review_ids) & set(candidate.get("replay_execution_ids", []))):
        raise ValueError("an independent passing task-quality review is required")
    review = {"review_id": quality_review["review_id"],
              "reviewer_id": quality_review["reviewer_id"],
              "task_ids": list(review_ids), "result": "pass"}
    active = {**candidate, "status": "active_guard", "quality_review": review}
    active["guard_id"] = "guard_" + _signature(active)[:16]
    return active


def active_guard_matches(guard: dict[str, Any], artifact: dict[str, Any], *,
                         operator: str, binding_signature: str,
                         input_version: str) -> bool:
    """Check an installed guard; proposal/candidate statuses never execute."""
    review = guard.get("quality_review")
    return bool(
        guard.get("status") == "active_guard"
        and guard.get("guard_id") == "guard_" + _signature({
            key: value for key, value in guard.items() if key != "guard_id"})[:16]
        and isinstance(review, dict) and review.get("result") == "pass"
        and artifact.get("certified_digest") == artifact_signature(artifact)
        and guard.get("artifact_digest") == artifact["certified_digest"]
        and guard.get("motif_id") == artifact.get("motif_id")
        and guard.get("operator") == operator
        and guard.get("binding_signature") == binding_signature
        and guard.get("input_version") == input_version
    )


def validate_active_guard(guard: dict[str, Any], artifact: dict[str, Any]) -> None:
    if not isinstance(guard, dict) or not active_guard_matches(
        guard, artifact, operator=str(guard.get("operator") or ""),
        binding_signature=str(guard.get("binding_signature") or ""),
        input_version=str(guard.get("input_version") or ""),
    ) or not all(guard.get(key) for key in (
        "operator", "binding_signature", "input_version", "failure_reason",
        "error_class", "source_execution_ids", "replay_execution_ids"
    )):
        raise ValueError("active Motif guard is stale or invalid")


def _seal_registry(registry: dict[str, Any]) -> dict[str, Any]:
    registry["registry_digest"] = _signature({
        key: value for key, value in registry.items() if key != "registry_digest"})
    return registry


def new_guard_registry(artifact: dict[str, Any]) -> dict[str, Any]:
    if (artifact.get("status") != "trace_validated_read_only"
            or artifact.get("certified_digest") != artifact_signature(artifact)):
        raise ValueError("guard registry needs a current certified Motif")
    return _seal_registry({"schema_version": 1, "motif_id": artifact["motif_id"],
                           "artifact_digest": artifact["certified_digest"],
                           "revision": 0, "guards": {}, "events": []})


def _check_registry(registry: dict[str, Any], artifact: dict[str, Any]) -> None:
    if (not isinstance(registry, dict) or registry.get("schema_version") != 1
            or registry.get("motif_id") != artifact.get("motif_id")
            or registry.get("artifact_digest") != artifact.get("certified_digest")
            or registry.get("registry_digest") != _signature({
                key: value for key, value in registry.items() if key != "registry_digest"})
            or not isinstance(registry.get("guards"), dict)
            or not isinstance(registry.get("events"), list)
            or registry.get("revision") != len(registry["events"])):
        raise ValueError("Motif guard registry is stale or malformed")
    active_from_history: set[str] = set()
    seen_from_history: set[str] = set()
    for index, event in enumerate(registry["events"], 1):
        if (not isinstance(event, dict) or event.get("revision") != index
                or event.get("parent_revision") != index - 1):
            raise ValueError("Motif guard history has a broken version chain")
        guard_id = event.get("guard_id")
        if event.get("action") == "activate":
            if guard_id in seen_from_history or guard_id not in registry["guards"]:
                raise ValueError("Motif guard activation history is inconsistent")
            seen_from_history.add(guard_id)
            active_from_history.add(guard_id)
        elif event.get("action") == "rollback":
            if guard_id not in active_from_history:
                raise ValueError("Motif guard rollback history is inconsistent")
            active_from_history.remove(guard_id)
        else:
            raise ValueError("Motif guard history has an unknown transition")
    if seen_from_history != set(registry["guards"]):
        raise ValueError("Motif guard records differ from their history")
    for guard_id, row in registry["guards"].items():
        if (not isinstance(row, dict) or not isinstance(row.get("guard"), dict)
                or guard_id != row["guard"].get("guard_id")
                or row.get("status") not in {"active", "rolled_back"}):
            raise ValueError("Motif guard record is malformed")
        if (row["status"] == "active") != (guard_id in active_from_history):
            raise ValueError("Motif guard status differs from its history")
        validate_active_guard(row["guard"], artifact)


def activate_guard_version(
    registry: dict[str, Any], artifact: dict[str, Any], guard: dict[str, Any],
) -> dict[str, Any]:
    _check_registry(registry, artifact)
    validate_active_guard(guard, artifact)
    if guard["guard_id"] in registry["guards"]:
        raise ValueError("Motif guard was already registered")
    result = deepcopy(registry)
    result["guards"][guard["guard_id"]] = {"status": "active", "guard": guard}
    result["revision"] += 1
    result["events"].append({
        "revision": result["revision"], "parent_revision": registry["revision"],
        "action": "activate", "guard_id": guard["guard_id"],
        "review_id": guard["quality_review"]["review_id"],
    })
    return _seal_registry(result)


def rollback_guard_version(
    registry: dict[str, Any], artifact: dict[str, Any], *,
    guard_id: str, reviewer_id: str, reason: str,
) -> dict[str, Any]:
    _check_registry(registry, artifact)
    if (not reviewer_id or not reason or guard_id not in registry["guards"]
            or registry["guards"][guard_id]["status"] != "active"):
        raise ValueError("rollback needs an active guard and a recorded reason")
    result = deepcopy(registry)
    result["guards"][guard_id]["status"] = "rolled_back"
    result["revision"] += 1
    result["events"].append({
        "revision": result["revision"], "parent_revision": registry["revision"],
        "action": "rollback", "guard_id": guard_id,
        "reviewer_id": reviewer_id, "reason": reason,
    })
    return _seal_registry(result)


def current_active_guards(registry: dict[str, Any], artifact: dict[str, Any]
                          ) -> tuple[dict[str, Any], ...]:
    _check_registry(registry, artifact)
    return tuple(row["guard"] for row in registry["guards"].values()
                 if row["status"] == "active")
