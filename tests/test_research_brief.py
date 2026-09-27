"""The brief must expose accepted claims, sources, and unresolved obligations."""

from __future__ import annotations

import unittest

from src.workflows.research_brief import render_brief


class ResearchBriefTests(unittest.TestCase):
    def test_renders_two_source_comparison_and_gap(self) -> None:
        points = [{"id": "methods", "requirement": "Compare Alpha and Beta", "min_sources": 2},
                  {"id": "limits", "requirement": "State known limits"}]
        citations = {
            "E1": {"source": "alpha.pdf", "page": 2, "source_sha256": "a" * 64},
            "E2": {"source": "beta.pdf", "page": 4, "source_sha256": "b" * 64},
        }
        claims = [{"point_id": "methods", "text": "Alpha retrieves and Beta refines poses.",
                   "supports": [{"evidence_id": "E1", "quote": "Alpha retrieves poses"},
                                {"evidence_id": "E2", "quote": "Beta refines poses"}]}]
        gaps = [{"point_id": "limits", "text": "Outdoor evidence is missing",
                 "blocks_requirement": True}]
        brief = render_brief("How do they work?", points, claims, gaps, citations)
        for expected in ("Alpha retrieves and Beta refines poses", "alpha.pdf", "beta.pdf",
                         "Outdoor evidence is missing", "尚无可引用的结论"):
            self.assertIn(expected, brief)


if __name__ == "__main__":
    unittest.main()
