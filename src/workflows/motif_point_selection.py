"""Persist validated point choices as Motif decisions with candidate dependencies."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.adapters.point_research_semantic import parse_point_selection
from src.motif_core import MotifContextManager
from src.motif_core.context_manager import DecisionState, VALIDATED
from src.workflows.point_candidate_pool import candidate_fingerprint


MOTIF_ID = "research_point_selection"


def _point_digest(point: dict[str, Any]) -> str:
    raw = json.dumps(point, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _restore(previous: dict[str, Any]) -> MotifContextManager:
    if previous.get("schema_version") != 1 or previous.get("motif_id") != MOTIF_ID:
        raise ValueError("unsupported Motif point selection state")
    manager = MotifContextManager()
    frame = manager.suspend_motif(
        motif_id=MOTIF_ID, execution_plan=["choose_evidence", "verify_evidence"],
        plan_step=1, motif_tools={"choose_evidence", "verify_evidence"},
        completed_tools={"choose_evidence"}, revision=int(previous["revision"]),
    )
    frame.decisions = {
        key: DecisionState(**{**row, "member_slots": tuple(row["member_slots"]),
                              "dependency_signatures": tuple(row["dependency_signatures"])})
        for key, row in previous["decisions"].items()
    }
    frame.resume_count = int(previous["resume_count"])
    return manager


def resolve_selection(source_dir: Path, points: list[dict[str, Any]],
                      candidates: dict[str, dict[str, Any]],
                      selected_ids: dict[str, list[str]] | None = None,
                      previous: dict[str, Any] | None = None,
                      signature_scope: str = "per_point"
                      ) -> tuple[dict[str, list[str]] | None, dict[str, Any], list[dict[str, str]]]:
    if signature_scope not in {"global", "per_point"}:
        raise ValueError("unsupported selection signature scope")
    root = str(source_dir.resolve(strict=True))
    if previous and previous.get("source_dir") != root:
        raise ValueError("previous selection belongs to a different source directory")
    fingerprint = candidate_fingerprint(candidates)
    manager = _restore(previous) if previous else MotifContextManager()
    revision = int(previous["revision"]) + 1 if previous else 1
    frame = (manager.mark_resumed(MOTIF_ID, revision) if previous else
             manager.activate_motif(MOTIF_ID, execution_plan=["choose_evidence", "verify_evidence"],
                                    plan_step=0, motif_tools={"choose_evidence", "verify_evidence"}))
    if frame is None:
        raise RuntimeError("Motif point selection frame did not resume")
    signatures = {
        f"select_{point['id']}": (
            (fingerprint if signature_scope == "global" else
             candidate_fingerprint({key: row for key, row in candidates.items()
                                    if row["point_id"] == point["id"]})),
            _point_digest(point),
        )
        for point in points
    }
    stale = frame.stale_changed_dependencies(signatures)
    events = [{"event": "selection_invalidated", "point_id": name.removeprefix("select_")}
              for kind, name, _ in stale if kind == "decision"]
    supplied_selection = selected_ids is not None
    if not supplied_selection:
        candidate_choice = {
            point["id"]: frame.decisions[f"select_{point['id']}.choice"].values["evidence_ids"]
            for point in points
            if (f"select_{point['id']}.choice" in frame.decisions
                and frame.decisions[f"select_{point['id']}.choice"].resolution_status == VALIDATED)
        }
        if candidate_choice:
            raw = json.dumps({"selections": [{"point_id": point_id, "evidence_ids": keys}
                                             for point_id, keys in candidate_choice.items()]},
                             ensure_ascii=False)
            try:
                selected_ids = parse_point_selection(
                    raw, [point for point in points if point["id"] in candidate_choice], candidates)
            except ValueError:
                selected_ids = None
            else:
                events.extend({"event": "selection_reused", "point_id": point_id}
                              for point_id in selected_ids)
    if supplied_selection:
        raw = json.dumps({"selections": [{"point_id": point_id, "evidence_ids": keys}
                                         for point_id, keys in selected_ids.items()]}, ensure_ascii=False)
        selected_ids = parse_point_selection(raw, points, candidates)
        for point in points:
            point_id = point["id"]
            changed = frame.validate_decision(
                f"select_{point_id}.choice", values={"evidence_ids": selected_ids[point_id]},
                member_slots=("evidence_ids",), dependency_signatures=signatures[f"select_{point_id}"],
            )
            if changed:
                events.append({"event": "selection_validated", "point_id": point_id})
    manager.suspend_motif(
        motif_id=MOTIF_ID, execution_plan=["choose_evidence", "verify_evidence"],
        plan_step=1, motif_tools={"choose_evidence", "verify_evidence"},
        completed_tools={"choose_evidence"} if selected_ids and len(selected_ids) == len(points)
        else set(), revision=revision,
    )
    state = {"schema_version": 1, "motif_id": MOTIF_ID, "source_dir": root,
             "revision": revision, "resume_count": frame.resume_count,
             "signature_scope": signature_scope,
             "candidate_sha256": fingerprint,
             "decisions": {key: asdict(value) for key, value in frame.decisions.items()
                           if value.resolution_status == VALIDATED}}
    return selected_ids, state, events
