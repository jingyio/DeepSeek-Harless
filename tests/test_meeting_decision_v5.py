"""Four-seed held-out fixtures retain distinct decisions and versioned sources."""

from __future__ import annotations

import hashlib
import json
import os
import unittest
from unittest.mock import patch

from benchmarks.meeting_decision_chain_v1 import mock_apps_server as apps
from benchmarks.meeting_decision_chain_v5.build_fixtures import CASES, ROOT, build


class MeetingDecisionV5Tests(unittest.TestCase):
    def test_rebuild_matches_frozen_inputs(self):
        lock = json.loads((ROOT / "fixtures.lock.json").read_text())["input_sha256"]
        build()
        observed = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in [*ROOT.glob("sources/**/*"), *ROOT.glob("tasks/*.md")]
                    if path.is_file()}
        self.assertEqual(lock, observed)
        self.assertEqual(len({spec["note"]["claim_id"] for spec in CASES.values()}), 3)

    def test_cross_app_links_and_full_row_versions(self):
        for case in CASES:
            with self.subTest(case=case), patch.dict(os.environ,
                                                       {"SSS_MEETING_CASE": case}):
                event = apps.read_change(f"event:{case}:w39")
                index = apps.find_dependent_claims(event["experiment_id"])
                for object_id in (event["experiment_id"],
                                  event["previous_experiment_id"],
                                  index["claims"][0]["note_id"],
                                  index["claims"][0]["annotation_id"]):
                    pinned = apps.pin_object(object_id)
                    inspected = apps.read_pinned_object(pinned["source_id"])
                    self.assertEqual(pinned["version_sha256"],
                                     inspected["version_sha256"])
                    if object_id.startswith("wps:"):
                        rows = apps.read_dataset_rows(inspected["value"]["dataset_id"])
                        self.assertEqual(rows["total"], 16)
                        self.assertEqual(len(rows["rows"]), 16)
                previous = apps.pin_object(event["previous_experiment_id"])
                self.assertEqual(previous["version_sha256"],
                                 event["previous_version_sha256"])


if __name__ == "__main__":
    unittest.main()
