"""A structural skill revision must be sourced, gated, and used later."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.workflows.motif_point_selection import resolve_selection
from src.workflows.motif_skill_evolution import (
    assess, load_registry, new_registry, promote, propose_local_dependency,
    record_use, save_registry,
)


def case(case_id: str, changed_point: str = "b") -> dict:
    points = [{"id": "a", "requirement": "Summarize A"},
              {"id": "b", "requirement": "Summarize B"}]
    before = {f"{key}-C1": {"point_id": key, "evidence": {
        "source": f"{key}.pdf", "page": 1, "source_sha256": key * 64,
        "snippet": key.upper()}} for key in ("a", "b")}
    after = {**before, f"{changed_point}-C1": {
        "point_id": changed_point,
        "evidence": {**before[f"{changed_point}-C1"]["evidence"],
                     "source_sha256": "c" * 64}}}
    return {"id": case_id, "points": points, "before_candidates": before,
            "after_candidates": after,
            "selected_ids": {"a": ["a-C1"], "b": ["b-C1"]}}


class MotifSkillEvolutionTests(unittest.TestCase):
    def test_sourced_revision_assessment_promotion_and_later_use(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            registry = new_registry()
            training = case("train-1")
            _, state, _ = resolve_selection(root, training["points"],
                                            training["before_candidates"],
                                            selected_ids=training["selected_ids"],
                                            signature_scope="global")
            _, _, events = resolve_selection(root, training["points"],
                                             training["after_candidates"], previous=state,
                                             signature_scope="global")
            child = propose_local_dependency(
                registry, source_run_id="source-run-1", points=training["points"],
                before_candidates=training["before_candidates"],
                after_candidates=training["after_candidates"],
                invalidated_point_ids=[row["point_id"] for row in events
                                       if row["event"] == "selection_invalidated"])
            self.assertEqual(child["witness"]["redundantly_invalidated_points"], ["a"])
            with self.assertRaisesRegex(ValueError, "train and frozen validation"):
                promote(registry, child["id"])
            train_result = assess(registry, version_id=child["id"], split="train",
                                  cases=[training], source_dir=root)
            validation_result = assess(registry, version_id=child["id"], split="validation",
                                       cases=[case("heldout-1", "a")], source_dir=root)
            self.assertEqual(train_result["parent"]["safe_reused_points"], 0)
            self.assertEqual(train_result["candidate"]["safe_reused_points"], 1)
            self.assertEqual(validation_result["candidate"]["unsafe_reused_points"], 0)
            promote(registry, child["id"])
            self.assertEqual(registry["active_version_id"], child["id"])
            with self.assertRaisesRegex(ValueError, "distinct executed run"):
                record_use(registry, run_id="source-run-1", version_id=child["id"],
                           executed_point_ids=["a"])
            use = record_use(registry, run_id="later-run-1", version_id=child["id"],
                             executed_point_ids=["a", "b"])
            self.assertEqual(use["executed_point_ids"], ["a", "b"])
            path = root / "registry.json"
            save_registry(path, registry)
            self.assertEqual(load_registry(path)["uses"], [use])

    def test_no_proposal_without_observed_redundant_invalidation(self) -> None:
        item = case("train-1")
        with self.assertRaisesRegex(ValueError, "trace does not show"):
            propose_local_dependency(new_registry(), source_run_id="r", points=item["points"],
                                     before_candidates=item["before_candidates"],
                                     after_candidates=item["after_candidates"],
                                     invalidated_point_ids=["b"])

    def test_requirement_change_cannot_reuse_its_point(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            registry = new_registry()
            item = case("train-1")
            child = propose_local_dependency(
                registry, source_run_id="source-run", points=item["points"],
                before_candidates=item["before_candidates"],
                after_candidates=item["after_candidates"],
                invalidated_point_ids=["a", "b"])
            changed_requirement = {**item, "id": "req-change",
                                   "after_candidates": item["before_candidates"],
                                   "after_points": [{**item["points"][0],
                                                     "requirement": "Compare A with another method"},
                                                    item["points"][1]]}
            result = assess(registry, version_id=child["id"], split="validation",
                            cases=[changed_requirement], source_dir=Path(temporary))
            self.assertEqual(result["candidate"]["unsafe_reused_points"], 0)
            self.assertEqual(result["candidate"]["safe_reused_points"], 1)


if __name__ == "__main__":
    unittest.main()
