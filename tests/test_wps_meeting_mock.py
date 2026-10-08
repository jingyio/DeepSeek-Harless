"""Guard checks for the synthetic WPS meeting fixture."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "benchmarks" / "wps_meeting_mock_v1" / "run_mock.py"
SPEC = importlib.util.spec_from_file_location("run_wps_meeting_mock", MODULE_PATH)
assert SPEC and SPEC.loader
mock = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mock)


class WpsMeetingMockTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = mock.read_rows(mock.DEFAULT_BOOK)
        cls.contract = json.loads((mock.HERE / "mock_contract.json").read_text(encoding="utf-8"))

    def test_duration_update_preserves_claim_dependency(self):
        changed = mock.apply_event(self.rows, self.contract["scenarios"]["duration_update"])
        approved = sorted(self.contract["approved_dependency"], key=lambda item: item[0])
        self.assertEqual(mock.claim_dependency(changed), approved)
        self.assertEqual(mock.metrics(changed)["candidate"]["duration_s"], 305.0)

    def test_result_update_invalidates_claim(self):
        changed = mock.apply_event(self.rows, self.contract["scenarios"]["result_update"])
        approved = sorted(self.contract["approved_dependency"], key=lambda item: item[0])
        self.assertNotEqual(mock.claim_dependency(changed), approved)
        with tempfile.TemporaryDirectory() as directory:
            log = mock.run(mock.DEFAULT_BOOK, Path(directory), "result_update", render=False)
            report = Path(log["report"]).read_text(encoding="utf-8")
        self.assertEqual(log["decision"], "semantic_handoff_required")
        self.assertNotIn(self.contract["approved_claim"], report)

    def test_stale_event_and_bad_denominator_stop(self):
        stale = [{"run_id": "cand_s3", "field": "correct", "old": 79, "new": 63}]
        with self.assertRaisesRegex(ValueError, "precondition"):
            mock.apply_event(self.rows, stale)
        invalid = [dict(row) for row in self.rows]
        invalid[0]["test_cases"] = 0
        with self.assertRaisesRegex(ValueError, "denominator"):
            mock.validate(invalid)


if __name__ == "__main__":
    unittest.main()
