"""Motif point choices may be reused only for the same candidate evidence."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.workflows.motif_point_selection import resolve_selection


class MotifPointSelectionTests(unittest.TestCase):
    def test_reuses_exact_candidates_then_invalidates_changed_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            points = [{"id": "methods", "requirement": "Compare two methods", "min_sources": 2}]
            candidates = {
                "methods-C1": {"point_id": "methods", "evidence": {
                    "source": "alpha.pdf", "page": 1, "source_sha256": "a" * 64, "snippet": "Alpha"}},
                "methods-C2": {"point_id": "methods", "evidence": {
                    "source": "beta.pdf", "page": 1, "source_sha256": "b" * 64, "snippet": "Beta"}},
            }
            chosen = {"methods": ["methods-C1", "methods-C2"]}
            first, state, events = resolve_selection(root, points, candidates, chosen)
            self.assertEqual(first, chosen)
            self.assertEqual([row["event"] for row in events], ["selection_validated"])
            second, state2, events2 = resolve_selection(root, points, candidates, previous=state)
            self.assertEqual(second, chosen)
            self.assertEqual(state2["resume_count"], 1)
            self.assertEqual([row["event"] for row in events2], ["selection_reused"])
            changed = {**candidates, "methods-C2": {
                **candidates["methods-C2"],
                "evidence": {**candidates["methods-C2"]["evidence"], "source_sha256": "c" * 64},
            }}
            third, state3, events3 = resolve_selection(root, points, changed, previous=state2)
            self.assertIsNone(third)
            self.assertEqual(state3["decisions"], {})
            self.assertEqual([row["point_id"] for row in events3 if row["event"] == "selection_invalidated"],
                             ["methods"])

    def test_changed_requirement_invalidates_choice(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            points = [{"id": "p", "requirement": "Summarize a paper"}]
            candidates = {"p-C1": {"point_id": "p", "evidence": {
                "source": "paper.pdf", "page": 1, "source_sha256": "a" * 64, "snippet": "text"}}}
            _, state, _ = resolve_selection(root, points, candidates, {"p": ["p-C1"]})
            changed_points = [{"id": "p", "requirement": "Compare the paper against a baseline"}]
            selected, _, events = resolve_selection(root, changed_points, candidates, previous=state)
            self.assertIsNone(selected)
            self.assertTrue(any(row["event"] == "selection_invalidated" for row in events))

    def test_changed_candidate_invalidates_only_its_answer_point(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            points = [{"id": "a", "requirement": "Summarize A"},
                      {"id": "b", "requirement": "Summarize B"}]
            candidates = {
                "a-C1": {"point_id": "a", "evidence": {"source": "a.pdf", "page": 1,
                         "source_sha256": "a" * 64, "snippet": "A"}},
                "b-C1": {"point_id": "b", "evidence": {"source": "b.pdf", "page": 1,
                         "source_sha256": "b" * 64, "snippet": "B"}},
            }
            _, state, _ = resolve_selection(root, points, candidates,
                                            {"a": ["a-C1"], "b": ["b-C1"]})
            changed = {**candidates, "b-C1": {"point_id": "b", "evidence": {
                **candidates["b-C1"]["evidence"], "source_sha256": "c" * 64}}}
            reused, state2, events = resolve_selection(root, points, changed, previous=state)
            self.assertEqual(reused, {"a": ["a-C1"]})
            self.assertEqual({row["point_id"] for row in events if row["event"] == "selection_invalidated"},
                             {"b"})
            self.assertEqual({row["point_id"] for row in events if row["event"] == "selection_reused"},
                             {"a"})
            self.assertEqual(set(state2["decisions"]), {"select_a.choice"})
            completed, _, events2 = resolve_selection(root, points, changed,
                                                       {"a": ["a-C1"], "b": ["b-C1"]},
                                                       previous=state2)
            self.assertEqual(completed["b"], ["b-C1"])
            self.assertEqual({row["point_id"] for row in events2
                              if row["event"] == "selection_validated"}, {"b"})


if __name__ == "__main__":
    unittest.main()
