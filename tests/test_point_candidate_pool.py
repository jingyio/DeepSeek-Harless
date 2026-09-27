"""Retrieval must preserve enough independent choices for a comparison."""

from __future__ import annotations

import unittest
import json

from src.adapters.point_research_semantic import parse_point_selection
from src.workflows.point_candidate_pool import candidate_fingerprint, candidate_pool


class PointCandidatePoolTests(unittest.TestCase):
    def test_reserves_a_second_source_within_four_candidate_budget(self) -> None:
        evidence = [{"source": "alpha.pdf", "page": page} for page in range(1, 6)]
        evidence.append({"source": "beta.pdf", "page": 1})
        chosen = candidate_pool(evidence, min_sources=2)
        self.assertEqual(len(chosen), 4)
        self.assertEqual(chosen[:2], [evidence[0], evidence[-1]])

    def test_stops_if_comparison_has_one_source(self) -> None:
        evidence = [{"source": "alpha.pdf", "page": 1}]
        with self.assertRaisesRegex(ValueError, "independent sources"):
            candidate_pool(evidence, min_sources=2)

    def test_reserves_three_independent_sources(self) -> None:
        evidence = [{"source": "a.json", "page": 1}, {"source": "a.json", "page": 2},
                    {"source": "b.json", "page": 1}, {"source": "c.json", "page": 1}]
        chosen = candidate_pool(evidence, min_sources=3)
        self.assertEqual([row["source"] for row in chosen[:3]], ["a.json", "b.json", "c.json"])

    def test_selection_requires_all_three_named_sources(self) -> None:
        points = [{"id": "totals", "requirement": "Compare three groups", "min_sources": 3}]
        candidates = {f"totals-C{i}": {"point_id": "totals", "evidence": {"source": name}}
                      for i, name in enumerate(("a.json", "b.json", "c.json"), 1)}
        insufficient = {"selections": [{"point_id": "totals",
                                         "evidence_ids": ["totals-C1", "totals-C2"]}]}
        with self.assertRaisesRegex(ValueError, "independent sources"):
            parse_point_selection(json.dumps(insufficient), points, candidates)
        complete = {"selections": [{"point_id": "totals",
                                     "evidence_ids": list(candidates)}]}
        self.assertEqual(parse_point_selection(json.dumps(complete), points, candidates)
                         ["totals"], list(candidates))

    def test_fingerprint_changes_with_source_content(self) -> None:
        before = {"C1": {"point_id": "p", "evidence": {"source": "a.pdf", "page": 1,
                                                        "source_sha256": "a" * 64, "snippet": "old"}}}
        after = {"C1": {"point_id": "p", "evidence": {"source": "a.pdf", "page": 1,
                                                       "source_sha256": "b" * 64, "snippet": "new"}}}
        self.assertNotEqual(candidate_fingerprint(before), candidate_fingerprint(after))


if __name__ == "__main__":
    unittest.main()
