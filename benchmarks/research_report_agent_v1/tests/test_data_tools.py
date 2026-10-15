"""Offline correctness and provenance guards; never contacts a model endpoint."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import get_case_dir, get_record, sha256_file
from data_tools import inspect_study, plan_analysis, run_analysis, verify_analysis
from generate_data import CASES, generate


def plan_for(case: dict, allow: bool = True) -> dict:
    result = {"design": case["design"], "outcome_column": "value",
              "missing_policy": "complete_case", "confidence": 0.95,
              "hypothesis": "Two-sided comparison or nonzero linear slope",
              "allow_deterministic_continuation": allow}
    if case["design"] == "regression":
        result["predictor_column"] = "predictor"
    else:
        paired = case["design"] == "paired"
        result.update(group_column="condition" if paired else "group",
                      reference_group="before" if paired else "control",
                      comparison_group="after" if paired else "treatment")
        if paired:
            result["subject_column"] = "subject"
    return result


class DataToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        generate(self.data)
        self.env = patch.dict(os.environ, {"RRA_DATA_ROOT": str(self.data),
                              "RRA_RUN_ROOT": str(self.root / "runs" / "test"),
                              "RRA_CASE": CASES[0]["id"]})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_six_cases_independently_recompute_and_mark_missing(self):
        for case in CASES:
            with self.subTest(case=case["id"]):
                os.environ["RRA_CASE"] = case["id"]
                os.environ["RRA_RUN_ROOT"] = str(self.root / "runs" / case["id"])
                inspected = inspect_study(case["id"])
                self.assertTrue(inspected["study"]["synthetic"])
                self.assertEqual(inspected["missing_by_column"]["value"], 2)
                selected = plan_analysis(case["id"], plan_for(case))
                result = run_analysis(selected["plan_id"])
                checked = verify_analysis(result["analysis_id"])
                self.assertTrue(checked["passed"])
                self.assertGreaterEqual(result["diagnostics"]["excluded_rows"], 2)
                self.assertLess(result["statistics"]["ci_low"], result["statistics"]["estimate"])
                self.assertLess(result["statistics"]["estimate"], result["statistics"]["ci_high"])
                self.assertEqual(checked["_provenance"]["authorized_tools"], [])

    def test_continuation_is_explicitly_authorized_not_default(self):
        proposed = plan_for(CASES[0])
        del proposed["allow_deterministic_continuation"]
        denied = plan_analysis(CASES[0]["id"], proposed)
        self.assertEqual(denied["_provenance"]["authorized_tools"], [])
        result = run_analysis(denied["plan_id"])
        self.assertEqual(result["_provenance"]["authorized_tools"], [])
        approved = plan_analysis(CASES[0]["id"], plan_for(CASES[0]))
        self.assertEqual(approved["_provenance"]["authorized_tools"], ["run_analysis"])
        result = run_analysis(approved["plan_id"])
        self.assertEqual(result["_provenance"]["authorized_tools"], ["verify_analysis"])

    def test_source_change_invalidates_prior_plan(self):
        selected = plan_analysis(CASES[0]["id"], plan_for(CASES[0]))
        path = get_case_dir() / "data.csv"
        path.write_bytes(path.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "source data changed"):
            run_analysis(selected["plan_id"])

    def test_record_tamper_is_detected_and_hash_is_actual_file_hash(self):
        selected = plan_analysis(CASES[0]["id"], plan_for(CASES[0]))
        path = Path(selected["_provenance"]["record_path"])
        self.assertEqual(selected["_provenance"]["record_sha256"], sha256_file(path))
        content = json.loads(path.read_text(encoding="utf-8"))
        content["payload"]["plan"]["confidence"] = 0.9
        path.write_text(json.dumps(content), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "record content changed"):
            get_record(selected["plan_id"])

    def test_study_scope_and_record_paths_are_contained(self):
        with self.assertRaisesRegex(ValueError, "outside this task"):
            inspect_study(CASES[-1]["id"])
        with self.assertRaisesRegex(ValueError, "invalid record"):
            get_record("../../oracles/eval_energy.json")
        selected = plan_analysis(CASES[0]["id"], plan_for(CASES[0]))
        os.environ["RRA_RUN_ROOT"] = str(self.root / "runs" / "another")
        with self.assertRaisesRegex(ValueError, "unavailable"):
            get_record(selected["plan_id"])

    def test_missing_values_require_explicit_policy(self):
        proposed = plan_for(CASES[0])
        proposed["missing_policy"] = "zero_impute"
        with self.assertRaisesRegex(ValueError, "complete_case"):
            plan_analysis(CASES[0]["id"], proposed)

    def test_repeated_units_cannot_be_treated_as_independent(self):
        case = CASES[1]
        os.environ["RRA_CASE"] = case["id"]
        proposed = plan_for(case)
        proposed["design"] = "independent_groups"
        with self.assertRaisesRegex(ValueError, "paired analysis"):
            plan_analysis(case["id"], proposed)


if __name__ == "__main__":
    unittest.main()
