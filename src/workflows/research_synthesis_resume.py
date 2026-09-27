"""Resume a failed semantic synthesis from validated Motif state.

The source snapshot, question, obligations, plan and selected candidate IDs
must still match. A failed model response is never replayed as evidence.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from src.workflows.motif_research_sources import verify_source_snapshot


def prepare_synthesis_resume(parent: Path, *, local_root: Path,
                             output: Path, question: str,
                             answer_points: list[dict[str, Any]]) -> dict[str, Any]:
    parent = parent.resolve(strict=True)
    local_root = local_root.resolve(strict=True)
    if not parent.is_dir() or not parent.is_relative_to(local_root / "point-research-runs"):
        raise ValueError("resume parent must be a private point research run")
    status = json.loads((parent / "status.json").read_text(encoding="utf-8"))
    if status.get("status") != "stopped" or status.get("stage") != "synthesis":
        raise ValueError("only a stopped synthesis handoff may resume")
    if (parent / "question.txt").read_text(encoding="utf-8").strip() != question.strip():
        raise ValueError("resume question differs from the failed run")
    if json.loads((parent / "answer-points.json").read_text(encoding="utf-8")) != answer_points:
        raise ValueError("resume answer points differ from the failed run")
    state_path = parent / "motif-source-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    source_dir = Path(state["source_dir"])
    verify_source_snapshot(source_dir, state)
    plan = parent / "plan.json"
    chosen = json.loads((parent / "selection.json").read_text(encoding="utf-8"))
    template = json.loads((parent / "selection-bundle-template.json").read_text(encoding="utf-8"))
    selection_state_path = parent / "motif-selection-state.json"
    selection_state = json.loads(selection_state_path.read_text(encoding="utf-8"))
    if (not isinstance(chosen, dict) or not isinstance(template, dict)
            or set(template) != {"candidate_sha256", "selections"}
            or not isinstance(template["candidate_sha256"], str)
            or len(template["candidate_sha256"]) != 64):
        raise ValueError("failed run lacks a validated selection bundle")
    if (selection_state.get("motif_id") != "research_point_selection"
            or selection_state.get("source_dir") != str(source_dir.resolve())
            or selection_state.get("candidate_sha256") != template["candidate_sha256"]):
        raise ValueError("selection state is not bound to the source and candidates")
    decisions = selection_state.get("decisions")
    if not isinstance(decisions, dict) or set(chosen) != {key.removeprefix("select_").removesuffix(".choice")
                                                      for key in decisions}:
        raise ValueError("selection state does not cover the saved choices")
    for point_id, ids in chosen.items():
        decision = decisions.get(f"select_{point_id}.choice")
        if (not isinstance(decision, dict) or decision.get("resolution_status") != "VALIDATED"
                or decision.get("values", {}).get("evidence_ids") != ids):
            raise ValueError("saved choice differs from the validated Motif decision")
    selection = {"candidate_sha256": template["candidate_sha256"],
                 "selections": [{"point_id": point_id, "evidence_ids": ids}
                                for point_id, ids in chosen.items()]}
    bundle = output / "resume-selection.json"
    bundle.write_text(json.dumps(selection, ensure_ascii=False, indent=2), encoding="utf-8")
    retrieval = parent / "motif-retrieval-state.json"
    lineage = {
        "parent_run": str(parent), "parent_status": status,
        "source_state_sha256": hashlib.sha256(state_path.read_bytes()).hexdigest(),
        "plan_sha256": hashlib.sha256(plan.read_bytes()).hexdigest(),
        "validated_selection_sha256": hashlib.sha256(
            (parent / "selection.json").read_bytes()).hexdigest(),
        "motif_selection_state_sha256": hashlib.sha256(selection_state_path.read_bytes()).hexdigest(),
        "discarded_synthesis_sha256": (hashlib.sha256(
            (parent / "synthesis-response.txt").read_bytes()).hexdigest()
            if (parent / "synthesis-response.txt").is_file() else None),
    }
    (output / "resume-lineage.json").write_text(
        json.dumps(lineage, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"source_dir": source_dir, "previous_source_state": state_path,
            "previous_retrieval_state": retrieval if retrieval.is_file() else None,
            "plan_file": plan, "selection_file": bundle, "lineage": lineage}
