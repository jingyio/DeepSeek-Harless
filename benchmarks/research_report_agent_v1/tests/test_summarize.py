"""Artificial temporary unit-test fixtures; these are NOT experimental evidence."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import summarize as summary


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def write_lines(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(value) for value in values) + "\n", encoding="utf-8")


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.schemas = {"mcp__research_report__verify_report": {"type": "object"}}
        self.library = {"training_cases": ["train_materials", "train_ml"],
                        "certification_case": "cert_environment", "library_digest": "fixture-only",
                        "tool_schemas": self.schemas, "artifacts": [{
                            "training_evidence": [{"run_id": "training", "case_id": "train_materials"}],
                            "certification_evidence": {"run_id": "certification", "case_id": "cert_environment"}}]}

    def tearDown(self):
        self.temp.cleanup()

    def fixture(self, name, case="eval_biology", mode="baseline", quality=True, usage=True):
        directory = self.root / name
        report = directory / "workspace" / "artifacts" / "test-only" / "report.pdf"
        report.parent.mkdir(parents=True)
        report.write_bytes(b"UNIT TEST FIXTURE ONLY; NOT A REAL REPORT")
        body = {"kind": "report", "source_version": "fixture", "workspace_id": "fixture",
                "authorized_tools": [], "payload": {"path": str(report), "target_pages": 4,
                  "sha256": summary.hashlib.sha256(report.read_bytes()).hexdigest(), "metadata": {}}}
        rid = "rra-report-" + summary.digest(body)[:32]
        write(directory / "workspace" / "records" / f"{rid}.json", {"id": rid, **body})
        manifest = {"run_id": name, "case_id": case, "mode": mode, "real_upstream": True,
                    "prompt_sha256": "fixed", "source_files": [{"path": "/fixture/data.csv", "sha256": "same"}],
                    "benchmark_code_sha256": {key: "same" for key in summary.CRITICAL_CODE},
                    "library_digest": "fixture-only" if mode == "execute" else None,
                    "model": "deepseek-flash", "tool_order": list(self.schemas)}
        write(directory / "manifest.json", manifest)
        metrics = {"status": "done", "report_quality_passed": quality, "upstream_requests": 1,
                   "tool_calls": 1, "verified_motif_bypasses": 0, "elapsed_seconds": 2.0}
        write(directory / "metrics.json", metrics)
        output = {"ok": True, "quality_passed": quality, "report_id": rid, "checks": {"fixture": quality}}
        write_lines(directory / "agent-events.jsonl", [
            {"type": "tool/call", "data": {"name": "mcp__research_report__verify_report", "callId": "t1"}},
            {"type": "tool/result", "data": {"message": {"source": {"callId": "t1"}, "content": [
                {"type": "tool-result", "content": [{"type": "text", "text": json.dumps(output)}]}]}}}])
        write(directory / "model-requests" / "fixture.request.json", {"tools": [
            {"function": {"name": name, "parameters": schema}} for name, schema in self.schemas.items()]})
        write_lines(directory / "cost-ledger.jsonl", [{"request_id": name, "status": 200 if usage else 502,
                    "peak_estimate_cny": 0.1 if usage else None, "offpeak_estimate_cny": 0.05 if usage else None,
                    "reserved_upper_cny": 0.3, "usage": {"prompt_tokens": 10, "prompt_cache_hit_tokens": 6,
                        "prompt_cache_miss_tokens": 4, "completion_tokens": 2, "total_tokens": 12} if usage else {}}])
        return directory

    def test_matches_real_files_and_separates_training_failures_and_unknown_costs(self):
        self.fixture("base")
        self.fixture("motif", mode="execute")
        self.fixture("training", case="train_materials")
        self.fixture("failed", case="eval_energy", quality=False, usage=False)
        result = summary.summarize(self.root, self.library)
        self.assertEqual(len(result["runs"]), 4)
        self.assertEqual(len(result["paired_comparisons"]), 1)
        self.assertTrue(result["paired_comparisons"][0]["eligible_for_automatic_paired_comparison"])
        failed = next(row for row in result["runs"] if row["run_id"] == "failed")
        self.assertFalse(failed["automated_quality_eligible"])
        self.assertEqual(failed["unknown_reserved_upper_cny"], 0.3)
        self.assertEqual(failed["confirmed_peak_estimate_cny"], 0)
        with tempfile.TemporaryDirectory() as rendered:
            paths = summary.plot_results(result, Path(rendered))
            self.assertEqual(len(paths), 4)
            self.assertTrue(all(Path(path).stat().st_size > 1000 for path in paths))

    def test_earlier_same_case_is_pilot_not_selected_training(self):
        self.fixture("training", case="train_materials")
        self.fixture("old-training", case="train_materials")
        result = summary.summarize(self.root, self.library)
        phases = {row["run_id"]: row["phase"] for row in result["runs"]}
        self.assertEqual(phases["training"], "training")
        self.assertEqual(phases["old-training"], "development_pilot")

    def test_does_not_select_best_repeat(self):
        self.fixture("base1")
        self.fixture("base2")
        self.fixture("motif", mode="execute")
        result = summary.summarize(self.root, self.library)
        self.assertEqual(result["paired_comparisons"], [])
        self.assertEqual(result["unpaired_or_ambiguous_cases"][0]["qualified_run_counts"]["baseline"], 2)

    def test_code_change_blocks_savings_claim_even_when_both_reports_pass(self):
        self.fixture("base")
        directory = self.fixture("motif", mode="execute")
        manifest = summary.read(directory / "manifest.json")
        manifest["benchmark_code_sha256"]["data_tools.py"] = "changed"
        write(directory / "manifest.json", manifest)
        pair = summary.summarize(self.root, self.library)["paired_comparisons"][0]
        self.assertFalse(pair["eligible_for_automatic_paired_comparison"])
        self.assertNotIn("request_reduction_fraction", pair)

    def test_no_experiments_means_no_invented_zero_saving_or_figures(self):
        result = summary.summarize(self.root, self.library)
        self.assertEqual(result["runs"], [])
        self.assertEqual(result["phase_totals_including_failed_attempts"], [])
        self.assertEqual(summary.plot_results(result, self.root / "empty-plots"), [])


if __name__ == "__main__":
    unittest.main()
