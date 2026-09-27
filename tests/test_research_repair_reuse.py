"""Reuse of accepted evidence must preserve a checkable cross-point dependency."""

import unittest

from src.workflows.research_repair_reuse import rebind_accepted_evidence


class ResearchRepairReuseTests(unittest.TestCase):
    def test_rebinds_only_accepted_point_evidence_and_records_edges(self):
        citations = {"E1": {"source": "run.json", "snippet": "reward count 30 sum 24"},
                     "E2": {"source": "review.md", "snippet": "Figure 7 maps to ACT run"}}
        claims = [
            {"point_id": "numbers", "text": "24 successes",
             "supports": [{"evidence_id": "E1", "quote": "reward count 30 sum 24"}]},
            {"point_id": "mapping", "text": "maps to ACT",
             "supports": [{"evidence_id": "E2", "quote": "Figure 7 maps to ACT run"}]},
            {"point_id": "decision", "text": "old incomplete claim",
             "supports": [{"evidence_id": "E2", "quote": "Figure 7 maps to ACT run"}]},
        ]
        rebound, context, edges = rebind_accepted_evidence(claims, citations, {"decision"})
        self.assertEqual(set(rebound), {"R1", "R2"})
        self.assertEqual([row["point_id"] for row in context], ["numbers", "mapping"])
        self.assertEqual(context[0]["supports"][0]["evidence_id"], "R1")
        self.assertEqual({row["from_point"] for row in edges}, {"numbers", "mapping"})
        self.assertEqual({row["to_point"] for row in edges}, {"decision"})

    def test_missing_or_unbounded_evidence_fails_closed(self):
        claim = {"point_id": "numbers", "text": "24",
                 "supports": [{"evidence_id": "E1", "quote": "24"}]}
        with self.assertRaisesRegex(ValueError, "missing source evidence"):
            rebind_accepted_evidence([claim], {}, {"decision"})
        with self.assertRaisesRegex(ValueError, "bounded reuse scope"):
            rebind_accepted_evidence([claim], {"E1": {}}, {"decision"}, max_citations=0)
        with self.assertRaisesRegex(ValueError, "no longer matches"):
            rebind_accepted_evidence([claim], {"E1": {"snippet": "A different value entirely"}},
                                     {"decision"})


if __name__ == "__main__":
    unittest.main()
