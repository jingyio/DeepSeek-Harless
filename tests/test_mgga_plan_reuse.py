"""A prior query plan is reused only when it still reaches new evidence."""

import unittest
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run-sss-mgga-trial.py"
loader = SourceFileLoader("sss_mgga_plan_reuse", str(SCRIPT))
spec = spec_from_loader(loader.name, loader)
trial = module_from_spec(spec)
loader.exec_module(trial)


class PlanReuseTests(unittest.TestCase):
    def test_new_evidence_must_reach_every_unresolved_point(self) -> None:
        coverage = [{"id": "numeric", "status": "cited_claim"},
                    {"id": "identity", "status": "explicit_uncertainty"},
                    {"id": "label", "status": "missing_cited_claim"}]
        candidates = {
            "a": {"point_id": "identity", "evidence": {"source": "review.md"}},
            "b": {"point_id": "label", "evidence": {"source": "review.md"}},
        }
        self.assertTrue(trial.plan_reuse_decision(
            candidates, coverage, new_source="review.md")["reuse"])
        self.assertFalse(trial.plan_reuse_decision(
            {"a": candidates["a"]}, coverage, new_source="review.md")["reuse"])
        self.assertFalse(trial.plan_reuse_decision(
            candidates, coverage, new_source="different.md")["reuse"])

    def test_fallback_only_for_structural_stop(self) -> None:
        self.assertTrue(trial.should_fallback_plan_reuse(
            {"status": "stopped", "stage": "passage-packaging"}))
        self.assertFalse(trial.should_fallback_plan_reuse(
            {"status": "incomplete_answer", "stage": "coverage"}))


if __name__ == "__main__":
    unittest.main()
