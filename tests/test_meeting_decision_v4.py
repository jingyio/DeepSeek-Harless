"""Fresh decisions preserve source locks and cross-application version guards."""

from __future__ import annotations

import hashlib
import json
import os
import unittest
from unittest.mock import patch

from benchmarks.meeting_decision_chain_v1 import mock_apps_server as apps
from benchmarks.meeting_decision_chain_v4.build_fixtures import CASES, ROOT, build


class MeetingDecisionV4Tests(unittest.TestCase):
    def test_lock_survives_rebuild_and_decisions_are_distinct(self):
        lock = json.loads((ROOT / "fixtures.lock.json").read_text())["input_sha256"]
        build()
        actual = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in [*ROOT.glob("sources/**/*"), *ROOT.glob("tasks/*.md")]
                  if path.is_file()}
        self.assertEqual(lock, actual)
        self.assertEqual(len(CASES), 3)
        self.assertEqual(len({spec["note"]["claim_id"] for spec in CASES.values()}), 3)

    def test_current_previous_and_claim_index_are_versioned(self):
        for case in CASES:
            with self.subTest(case=case), patch.dict(os.environ,
                                                       {"SSS_MEETING_CASE": case}):
                event = apps.read_change(f"event:{case}:w39")
                current = apps.pin_object(event["experiment_id"])
                previous = apps.pin_object(event["previous_experiment_id"])
                self.assertEqual(previous["version_sha256"],
                                 event["previous_version_sha256"])
                index = apps.find_dependent_claims(event["experiment_id"])
                note = apps.pin_object(index["claims"][0]["note_id"])
                annotation = apps.pin_object(index["claims"][0]["annotation_id"])
                self.assertEqual(apps.read_pinned_object(note["source_id"])["value"]
                                 ["depends_on"], event["experiment_id"])
                self.assertTrue(apps.read_pinned_object(annotation["source_id"])
                                ["value"]["text"])
                for source in (current, previous):
                    inspected = apps.read_pinned_object(source["source_id"])
                    rows = apps.read_dataset_rows(inspected["value"]["dataset_id"])
                    self.assertEqual(rows["total"], 12)
                    self.assertEqual(rows["version_sha256"], source["version_sha256"])
                    metric = inspected["value"]["metric_contract"]
                    self.assertTrue(all(0 <= row[metric["numerator"]] <=
                                        row[metric["denominator"]] for row in rows["rows"]))


if __name__ == "__main__":
    unittest.main()
