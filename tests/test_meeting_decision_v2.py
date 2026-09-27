"""Three new scientific decisions retain independent data and versioned app links."""

from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from benchmarks.meeting_decision_chain_v1 import mock_apps_server as apps
from benchmarks.meeting_decision_chain_v2.build_fixtures import CASES, ROOT, build


SPEC = importlib.util.spec_from_file_location(
    "prepare_meeting_object_task", ROOT.parents[1] / "scripts/prepare-meeting-object-task.py")
TASKS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TASKS)


class MeetingDecisionV2Tests(unittest.TestCase):
    def test_build_is_stable_and_cases_have_distinct_decisions(self):
        cases = sorted(CASES)
        files = [ROOT / "sources" / case / "experiment.xlsx" for case in cases]
        before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in files]
        build()
        after = [hashlib.sha256(path.read_bytes()).hexdigest() for path in files]
        self.assertEqual(before, after)
        self.assertEqual(len(set(after)), 3)
        self.assertEqual(len({CASES[case]["note"]["claim_id"] for case in cases}), 3)

    def test_event_to_index_to_claims_has_independent_versions(self):
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
                task_text = (ROOT / "tasks" / f"{case}.md").read_text()
                task = TASKS.prepare(case, {"schema_version": 1,
                                      "task_id": f"meeting-decision-{case}",
                                      "intent": task_text, "bindings": {}})
                self.assertEqual(task["object_versions"][event["experiment_id"]],
                                 current["version_sha256"])
                self.assertEqual(task["lookup_versions"]["mcp__meeting_decision_fixture__"
                                  "find_dependent_claims"][event["experiment_id"]],
                                 index["index_version_sha256"])
                self.assertIn(note["version_sha256"], task["source_versions"][
                    "mcp__meeting_decision_fixture__pin_object"])
                self.assertIn(annotation["version_sha256"], task["source_versions"][
                    "mcp__meeting_decision_fixture__pin_object"])


if __name__ == "__main__":
    unittest.main()
