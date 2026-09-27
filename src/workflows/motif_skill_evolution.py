"""Auditable evolution of one Motif decision-dependency contract.

This first slice evolves *structure*: whether a point choice depends on every
candidate or only on that point's candidates. It never stores source passages,
answers, or model-generated instructions as a reusable skill.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from src.workflows.motif_point_selection import resolve_selection
from src.workflows.point_candidate_pool import candidate_fingerprint


SKILL_ID = "research_point_selection_dependency"


def new_registry() -> dict[str, Any]:
    return {"schema_version": 1, "skill_id": SKILL_ID, "active_version_id": "global-v0",
            "versions": [{"id": "global-v0", "parent_id": None, "signature_scope": "global",
                          "source_run_id": None, "change": "seed", "status": "active",
                          "assessments": []}], "uses": []}


def load_registry(path: Path) -> dict[str, Any]:
    registry = json.loads(path.read_text(encoding="utf-8"))
    if registry.get("schema_version") != 1 or registry.get("skill_id") != SKILL_ID:
        raise ValueError("unsupported Motif skill registry")
    ids = [version["id"] for version in registry["versions"]]
    if len(ids) != len(set(ids)) or registry["active_version_id"] not in ids:
        raise ValueError("invalid Motif skill version lineage")
    return registry


def save_registry(path: Path, registry: dict[str, Any]) -> None:
    if path.exists():
        load_registry(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def version(registry: dict[str, Any], version_id: str | None = None) -> dict[str, Any]:
    target = version_id or registry["active_version_id"]
    found = next((item for item in registry["versions"] if item["id"] == target), None)
    if found is None:
        raise ValueError("unknown Motif skill version")
    return found


def _per_point_hashes(candidates: dict[str, dict[str, Any]],
                      points: list[dict[str, Any]]) -> dict[str, str]:
    return {point["id"]: candidate_fingerprint({key: row for key, row in candidates.items()
                                                if row["point_id"] == point["id"]})
            for point in points}


def propose_local_dependency(registry: dict[str, Any], *, source_run_id: str,
                             points: list[dict[str, Any]],
                             before_candidates: dict[str, dict[str, Any]],
                             after_candidates: dict[str, dict[str, Any]],
                             invalidated_point_ids: list[str]) -> dict[str, Any]:
    """Propose a child only after a trace shows unrelated global invalidation."""
    parent = version(registry)
    if parent["signature_scope"] != "global" or not source_run_id:
        raise ValueError("local dependency patch needs a sourced global parent")
    before = _per_point_hashes(before_candidates, points)
    after = _per_point_hashes(after_candidates, points)
    unchanged = {point_id for point_id in before if before[point_id] == after[point_id]}
    changed = set(before) - unchanged
    redundant = unchanged & set(invalidated_point_ids)
    if not changed or not redundant or set(invalidated_point_ids) != set(before):
        raise ValueError("trace does not show unrelated candidate invalidation")
    payload = {"parent": parent["id"], "source_run": source_run_id,
               "change": "global_to_per_point_candidate_dependency"}
    child_id = "local-" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]
    if any(item["id"] == child_id for item in registry["versions"]):
        raise ValueError("this trace already proposed a version")
    child = {"id": child_id, "parent_id": parent["id"], "signature_scope": "per_point",
             "source_run_id": source_run_id, "change": payload["change"],
             "status": "candidate", "assessments": [],
             "witness": {"changed_points": sorted(changed),
                         "redundantly_invalidated_points": sorted(redundant)}}
    registry["versions"].append(child)
    return child


def assess(registry: dict[str, Any], *, version_id: str, split: str,
           cases: list[dict[str, Any]], source_dir: Path) -> dict[str, Any]:
    """Replay frozen candidate changes; report safe reuse, not answer quality."""
    if split not in {"train", "validation"} or not cases:
        raise ValueError("assessment needs nonempty train or validation cases")
    case_ids = [case["id"] for case in cases]
    if len(case_ids) != len(set(case_ids)) or any(not isinstance(key, str) or not key for key in case_ids):
        raise ValueError("assessment cases need distinct nonempty IDs")
    candidate = version(registry, version_id)
    if candidate["status"] != "candidate":
        raise ValueError("only a candidate version can be assessed")
    parent = version(registry, candidate["parent_id"])
    results = {}
    for item in (parent, candidate):
        reused_total = 0
        unsafe_total = 0
        for case in cases:
            points = case["points"]
            after_points = case.get("after_points", points)
            if [point["id"] for point in points] != [point["id"] for point in after_points]:
                raise ValueError("case must retain the same point IDs and order")
            chosen = case["selected_ids"]
            before = case["before_candidates"]
            after = case["after_candidates"]
            _, state, _ = resolve_selection(source_dir, points, before, selected_ids=chosen,
                                            signature_scope=item["signature_scope"])
            reused, _, _ = resolve_selection(source_dir, after_points, after, previous=state,
                                             signature_scope=item["signature_scope"])
            before_hashes = _per_point_hashes(before, points)
            after_hashes = _per_point_hashes(after, after_points)
            reused = reused or {}
            unsafe_total += sum(
                before_hashes[point_id] != after_hashes[point_id]
                or points[index] != after_points[index]
                for index, point_id in enumerate(before_hashes) if point_id in reused
            )
            reused_total += len(reused)
        results[item["id"]] = {"safe_reused_points": reused_total,
                               "unsafe_reused_points": unsafe_total}
    assessment = {"split": split, "case_count": len(cases),
                  "parent": results[parent["id"]], "candidate": results[candidate["id"]],
                  "case_ids": case_ids}
    if any(old["split"] == split for old in candidate["assessments"]):
        raise ValueError("split has already been assessed")
    candidate["assessments"].append(assessment)
    return assessment


def promote(registry: dict[str, Any], version_id: str) -> None:
    child = version(registry, version_id)
    if child["status"] != "candidate" or child["parent_id"] != registry["active_version_id"]:
        raise ValueError("only the active parent's candidate can be promoted")
    assessments = {item["split"]: item for item in child["assessments"]}
    if set(assessments) != {"train", "validation"}:
        raise ValueError("train and frozen validation assessments are required")
    if set(assessments["train"]["case_ids"]) & set(assessments["validation"]["case_ids"]):
        raise ValueError("train and validation cases must be disjoint")
    if any(item["candidate"]["unsafe_reused_points"] != 0 or
           item["candidate"]["safe_reused_points"] < item["parent"]["safe_reused_points"]
           for item in assessments.values()):
        raise ValueError("candidate failed safety or reuse regression gate")
    if not any(item["candidate"]["safe_reused_points"] > item["parent"]["safe_reused_points"]
               for item in assessments.values()):
        raise ValueError("candidate has no measured structural benefit")
    version(registry)["status"] = "superseded"
    child["status"] = "active"
    registry["active_version_id"] = child["id"]


def record_use(registry: dict[str, Any], *, run_id: str, version_id: str,
               executed_point_ids: list[str]) -> dict[str, Any]:
    selected = version(registry, version_id)
    if (selected["status"] != "active" or not run_id or
            run_id == selected["source_run_id"] or not executed_point_ids):
        raise ValueError("later use needs an active version and a distinct executed run")
    if any(item["run_id"] == run_id for item in registry["uses"]):
        raise ValueError("run already recorded")
    use = {"run_id": run_id, "version_id": version_id,
           "executed_point_ids": sorted(set(executed_point_ids))}
    registry["uses"].append(use)
    return use
