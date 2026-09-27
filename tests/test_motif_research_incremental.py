"""Incremental drafts recheck prior quotes and reopen changed obligations."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.workflows.motif_research_incremental import (
    plan_incremental, remap_new_claims, render_change_log,
)
from src.workflows.research_review_gate import build_review_record


QUOTE = "The method aligns local camera poses before global refinement"


def save(root: Path, name: str, value) -> None:
    (root / name).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


class MotifResearchIncrementalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.points = [{"id": "coarse", "requirement": "Explain coarse alignment"},
                       {"id": "fine", "requirement": "Explain fine refinement"}]
        self.citations = {
            "E1": {"source": "alpha.pdf", "page": 2, "source_sha256": "a" * 64,
                   "snippet": QUOTE + " in each frame."},
            "E2": {"source": "beta.pdf", "page": 3, "source_sha256": "b" * 64,
                   "snippet": "Fine optimization uses a separate geometric constraint for pose refinement."},
        }
        self.old_state = {"source_dir": str(self.root), "decisions": {
            "select_coarse.choice": {"resolution_status": "VALIDATED",
                                     "dependency_signatures": ["alpha", "coarse"]},
            "select_fine.choice": {"resolution_status": "VALIDATED",
                                   "dependency_signatures": ["beta", "fine"]},
        }}
        save(self.root, "status.json", {"status": "point_links_present"})
        (self.root / "question.txt").write_text("Compare alignment methods\n", encoding="utf-8")
        save(self.root, "answer-points.json", self.points)
        save(self.root, "motif-selection-state.json", self.old_state)
        self.source_state = {"source_dir": str(self.root), "evidence": [
            {"binding": {"source": "alpha.pdf", "sha256": "a" * 64}},
            {"binding": {"source": "beta.pdf", "sha256": "b" * 64}},
        ]}
        save(self.root, "motif-source-state.json", self.source_state)
        save(self.root, "selected-evidence.json", self.citations)
        save(self.root, "claims.json", [
            {"point_id": "coarse", "text": "The method aligns local poses first.",
             "supports": [{"evidence_id": "E1", "quote": QUOTE}]},
            {"point_id": "fine", "text": "Fine refinement uses a geometric constraint.",
             "supports": [{"evidence_id": "E2",
                           "quote": "Fine optimization uses a separate geometric constraint"}]},
        ])
        save(self.root, "uncertainties.json", [])
        save(self.root, "question-coverage.json", [
            {"id": "coarse", "status": "cited_claim"},
            {"id": "fine", "status": "cited_claim"},
        ])

    def plan(self, *, state=None, citations=None, points=None, source_state=None):
        current = citations or {"E3": self.citations["E1"], "E4": self.citations["E2"]}
        return plan_incremental(
            self.root, question="Compare alignment methods", points=points or self.points,
            current_selection_state=state or self.old_state,
            current_source_state=source_state or self.source_state,
            current_citations=current,
            point_citations={"coarse": {"E3"}, "fine": {"E4"}})

    def test_reuses_quote_checked_claims_with_new_citation_ids(self) -> None:
        state = json.loads(json.dumps(self.old_state))
        for decision in state["decisions"].values():
            decision["dependency_signatures"] = tuple(decision["dependency_signatures"])
        result = self.plan(state=state)
        self.assertEqual(result["carried_points"], ["coarse", "fine"])
        self.assertEqual(result["dirty_points"], [])
        self.assertEqual(result["carried_claims"][0]["supports"][0]["evidence_id"], "E3")
        self.assertTrue(result["review_required"])

    def test_dependency_change_reopens_only_affected_point(self) -> None:
        state = json.loads(json.dumps(self.old_state))
        state["decisions"]["select_fine.choice"]["dependency_signatures"] = ["new-beta", "fine"]
        result = self.plan(state=state)
        self.assertEqual(result["carried_points"], ["coarse"])
        self.assertEqual(result["dirty_points"], ["fine"])

    def test_changed_source_hash_reopens_even_with_stale_decision_signature(self) -> None:
        citations = {"E3": {**self.citations["E1"], "source_sha256": "c" * 64},
                     "E4": self.citations["E2"]}
        result = self.plan(citations=citations)
        self.assertEqual(result["dirty_points"], ["coarse"])
        self.assertEqual(result["carried_points"], ["fine"])

    def test_prior_uncertainty_reopens_point(self) -> None:
        save(self.root, "uncertainties.json", [
            {"point_id": "fine", "text": "Need another source", "blocks_requirement": False}])
        result = self.plan()
        self.assertEqual(result["dirty_points"], ["fine"])

    def test_source_delta_is_recorded_even_when_selection_is_reused(self) -> None:
        current = json.loads(json.dumps(self.source_state))
        current["evidence"].append({"binding": {"source": "new.pdf", "sha256": "n" * 64}})
        result = self.plan(source_state=current)
        self.assertEqual(result["source_changes"],
                         {"added": ["new.pdf"], "removed": [], "modified": []})
        self.assertEqual(result["carried_points"], ["coarse", "fine"])
        self.assertIn("新增：`new.pdf`", render_change_log(result))

    def test_reduced_prompt_claims_map_into_full_evidence_ledger(self) -> None:
        claims = [{"point_id": "coarse", "text": "Local poses are aligned first.",
                   "supports": [{"evidence_id": "E1", "quote": QUOTE}]}]
        result = remap_new_claims(claims, {"E1": self.citations["E1"]},
                                  {"E3": self.citations["E1"]}, {"coarse": {"E3"}})
        self.assertEqual(result[0]["supports"][0]["evidence_id"], "E3")

    def test_incremental_draft_needs_human_review_before_next_round(self) -> None:
        save(self.root, "status.json", {"status": "incremental_draft"})
        (self.root / "answer.md").write_text("Draft for review\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "requires human review"):
            self.plan()
        assessment = {
            "reviewer": "researcher-1", "reviewed_at": "2026-09-26T15:00:00+08:00",
            "verdict": "approved", "serious_error": False,
            "review_minutes": 12, "notes": "Checked both claims against the sources.",
            "point_scores": {point["id"]: {"support": 2, "coverage": 2}
                             for point in self.points},
        }
        save(self.root, "human-review.json", build_review_record(self.root, assessment))
        accepted = self.plan()
        self.assertEqual(accepted["carried_points"], ["coarse", "fine"])
        self.assertEqual(accepted["prior_review"]["status"], "verified")
        self.assertEqual(len(accepted["prior_review"]["record_sha256"]), 64)
        (self.root / "answer.md").write_text("Changed after review\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "current files"):
            self.plan()

    def test_review_cannot_approve_partial_quality(self) -> None:
        (self.root / "answer.md").write_text("Draft for review\n", encoding="utf-8")
        assessment = {
            "reviewer": "researcher-1", "reviewed_at": "2026-09-26T15:00:00+08:00",
            "verdict": "approved", "serious_error": False,
            "review_minutes": 12, "notes": "One point needs correction.",
            "point_scores": {"coarse": {"support": 2, "coverage": 2},
                             "fine": {"support": 1, "coverage": 2}},
        }
        with self.assertRaisesRegex(ValueError, "every quality point"):
            build_review_record(self.root, assessment)

    def test_unreviewed_draft_can_recompute_every_point_without_carrying_claims(self) -> None:
        save(self.root, "status.json", {"status": "incremental_draft"})
        changed = json.loads(json.dumps(self.old_state))
        for decision in changed["decisions"].values():
            decision["dependency_signatures"] = ["new-source"]
        result = self.plan(state=changed)
        self.assertEqual(result["carried_claims"], [])
        self.assertEqual(result["dirty_points"], ["coarse", "fine"])
        self.assertFalse(result["review_required"])
        self.assertEqual(result["prior_review"], {"required": False,
                                                   "status": "not_required"})


if __name__ == "__main__":
    unittest.main()
