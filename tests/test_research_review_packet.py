"""Blind review packets must present comparable claims without run provenance."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "scripts" / "prepare-research-review.py"
SPEC = importlib.util.spec_from_file_location("prepare_research_review", MODULE)
assert SPEC and SPEC.loader
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


class ResearchReviewPacketTests(unittest.TestCase):
    def test_packet_has_sources_and_same_quality_rubric_without_method_name(self) -> None:
        points = [{"id": "methods", "requirement": "Compare methods", "min_sources": 2}]
        claims = [{"point_id": "methods", "text": "Alpha retrieves, Beta refines.", "supports": [
            {"evidence_id": "E1", "quote": "Alpha retrieves"},
            {"evidence_id": "E2", "quote": "Beta refines"}]}]
        citations = {
            "E1": {"source": "alpha.txt", "page": 1, "source_sha256": "a" * 64,
                   "snippet": "Alpha retrieves candidate poses."},
            "E2": {"source": "beta.txt", "page": 2, "source_sha256": "b" * 64,
                   "snippet": "Beta refines candidate poses."},
        }
        packet = review.build_packet("A", "How?", points, claims, [], citations)
        for expected in ("alpha.txt", "beta.txt", "支持 __/2", "覆盖 __/2",
                         "人工修订", "两种方法"):
            self.assertIn(expected, packet)
        self.assertNotIn("SSS", packet)
        self.assertNotIn("model_requests", packet)

    def test_common_packet_accepts_native_freeform_answer(self) -> None:
        points = [{"id": "methods", "requirement": "Compare methods", "min_sources": 2}]
        packet = review.build_brief_only_packet(
            "B", "How do they compare?", "Alpha retrieves. Beta refines. [alpha.txt, beta.txt]", points)
        self.assertIn("Alpha retrieves. Beta refines.", packet)
        self.assertIn("支持 __/2", packet)
        self.assertNotIn("model_requests", packet)


if __name__ == "__main__":
    unittest.main()
