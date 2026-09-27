"""Cross-point reuse retains source-version and quote provenance."""

from __future__ import annotations

import unittest

from src.workflows.research_cross_point import cross_point_dependencies


class CrossPointTests(unittest.TestCase):
    def test_records_verified_origin_and_target(self) -> None:
        citations = {"E1": {"source": "data.json", "source_sha256": "a" * 64,
                            "snippet": "reward: count=30, sum=26, mean=0.8667"}}
        claims = [{"point_id": "label", "text": "Run A measured 26 successes.",
                   "supports": [{"evidence_id": "E1", "quote": "reward: count=30, sum=26"}]}]
        edges = cross_point_dependencies(
            claims, citations, {"numeric": {"E1"}, "label": set()})
        self.assertEqual(edges, [{"claim_index": 1, "target_point_id": "label",
                                  "source_point_ids": ["numeric"], "evidence_id": "E1",
                                  "source": "data.json", "source_sha256": "a" * 64,
                                  "quote": "reward: count=30, sum=26"}])

    def test_unowned_cross_point_reference_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "no verified owner"):
            cross_point_dependencies(
                [{"point_id": "label", "supports": [{"evidence_id": "E1", "quote": "value"}]}],
                {"E1": {"source": "data.json", "source_sha256": "a" * 64,
                        "snippet": "value is measured"}},
                {"label": set()})

    def test_changed_quote_blocks_reuse(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not match current source"):
            cross_point_dependencies(
                [{"point_id": "label", "supports": [{"evidence_id": "E1",
                                                     "quote": "reward: count=30, sum=26"}]}],
                {"E1": {"source": "data.json", "source_sha256": "a" * 64,
                        "snippet": "reward: count=30, sum=25"}},
                {"numeric": {"E1"}, "label": set()})


if __name__ == "__main__":
    unittest.main()
