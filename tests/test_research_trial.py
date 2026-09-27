"""Equal-input review scoring must not turn failed or unpriced runs into savings."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.workflows.research_trial import review_template, score_trial, validate_review


def write(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


class ResearchTrialTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.points = [{"id": "method", "requirement": "Compare methods", "min_sources": 2}]
        self.points_path = self.root / "points.json"
        write(self.points_path, self.points)
        self.runs = []
        for label, method in (("A", "simple"), ("B", "motif")):
            run = self.root / label
            run.mkdir()
            (run / "answer.md").write_text("A sourced research answer", encoding="utf-8")
            (run / "question.txt").write_text("Compare two methods\n", encoding="utf-8")
            write(run / "answer-points.json", self.points)
            write(run / "sources.json", [{"filename": "paper.pdf", "sha256": "a" * 64}])
            write(run / "status.json", {"status": "point_links_present"})
            write(run / "metrics.json", {"model_requests": 1, "inputTokens": 1000,
                                         "cacheReadTokens": 0, "outputTokens": 200})
            review = review_template(label, self.points)
            review.update(reviewer_id="reviewer-1", overall_usable=True,
                          practical_usable=True, comparison_accuracy="yes",
                          correction_minutes=6, notes="")
            review["points"][0].update(support=2, coverage=2, critical_error=False)
            review_path = self.root / f"review-{label}.json"
            write(review_path, review)
            self.runs.append({"label": label, "method": method, "run_dir": str(run),
                              "review_file": str(review_path), "model": "deepseek-flash",
                              "api_cost_usd": 0.02, "api_cost_evidence": "provider invoice",
                              "local_cost_usd": 0.001, "setup_minutes": 2})

    def manifest(self):
        return {"schema_version": 1, "task_id": "fixture-task",
                "answer_points": str(self.points_path), "human_rate_usd_per_hour": 12,
                "runs": self.runs}

    def test_qualified_total_cost_includes_setup_and_correction(self) -> None:
        report = score_trial(self.manifest())
        self.assertTrue(report["qualified_cost_comparison_ready"])
        self.assertTrue(all(row["qualified"] for row in report["runs"]))
        self.assertEqual(report["runs"][0]["human_minutes"], 8)
        self.assertAlmostEqual(report["runs"][0]["total_cost_usd"], 1.621)

    def test_failed_quality_has_no_qualified_cost(self) -> None:
        review_path = Path(self.runs[1]["review_file"])
        review = json.loads(review_path.read_text())
        review["points"][0]["coverage"] = 1
        write(review_path, review)
        report = score_trial(self.manifest())
        self.assertFalse(report["qualified_cost_comparison_ready"])
        self.assertIsNone(report["runs"][1]["qualified_total_cost_usd"])
        self.assertTrue(report["practical_cost_comparison_ready"])
        self.assertAlmostEqual(report["runs"][1]["practical_total_cost_usd"], 1.621)

    def test_minor_quality_tolerance_keeps_factual_floor(self) -> None:
        review_path = Path(self.runs[1]["review_file"])
        review = json.loads(review_path.read_text())
        review["points"][0]["coverage"] = 1
        review["points"][0]["support"] = 1
        write(review_path, review)
        report = score_trial(self.manifest())
        self.assertFalse(report["runs"][1]["practical_qualified"])
        self.assertIsNone(report["runs"][1]["practical_total_cost_usd"])

    def test_minor_quality_tolerance_requires_explicit_reviewer_acceptance(self) -> None:
        review_path = Path(self.runs[1]["review_file"])
        review = json.loads(review_path.read_text())
        review["points"][0]["coverage"] = 1
        review["practical_usable"] = False
        write(review_path, review)
        report = score_trial(self.manifest())
        self.assertFalse(report["runs"][1]["practical_qualified"])

    def test_minor_quality_tolerance_allows_at_most_one_partial_point(self) -> None:
        points = [{"id": "first"}, {"id": "second"}]
        review = review_template("A", points)
        review.update(reviewer_id="reviewer-1", overall_usable=False,
                      practical_usable=True, comparison_accuracy="not_applicable",
                      correction_minutes=3)
        for row in review["points"]:
            row.update(support=2, coverage=1, critical_error=False)
        self.assertFalse(validate_review(review, label="A", points=points)["practical_qualified"])

    def test_mismatched_source_inventory_fails_trial(self) -> None:
        write(Path(self.runs[1]["run_dir"]) / "sources.json",
              [{"filename": "paper.pdf", "sha256": "b" * 64}])
        with self.assertRaisesRegex(ValueError, "source inventory differs"):
            score_trial(self.manifest())

    def test_estimated_api_price_does_not_make_total_cost_complete(self) -> None:
        self.runs[1].pop("api_cost_usd")
        self.runs[1].pop("api_cost_evidence")
        report = score_trial(self.manifest())
        self.assertEqual(report["runs"][1]["api_cost"]["kind"], "pinned_price_estimate")
        self.assertIsNone(report["runs"][1]["total_cost_usd"])
        self.assertFalse(report["cost_comparison_ready"])

    def test_synthetic_fixture_cannot_be_scored_as_real(self) -> None:
        write(Path(self.runs[0]["run_dir"]) / "status.json",
              {"status": "point_links_present", "fixture_only": True})
        with self.assertRaisesRegex(ValueError, "synthetic fixture"):
            score_trial(self.manifest())


if __name__ == "__main__":
    unittest.main()
