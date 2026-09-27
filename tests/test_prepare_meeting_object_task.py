"""A version-scoped fixture task must bind only approved current objects."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/prepare-meeting-object-task.py"
SPEC = importlib.util.spec_from_file_location("prepare_meeting_object_task", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PrepareMeetingObjectTaskTests(unittest.TestCase):
    def test_scopes_event_and_each_object_to_its_own_hash(self):
        template = {"schema_version": 1, "task_id": "meeting-decision-site_transfer",
                    "intent": "Compare old and new site results", "bindings": {}}
        task = MODULE.prepare("site_transfer", template)
        self.assertEqual(len(task["object_versions"]), 4)
        self.assertEqual(task["source_versions"][MODULE.PREFIX + "read_change"],
                         MODULE.sha(MODULE.SOURCES / "site_transfer/event.json"))
        self.assertEqual(task["object_versions"]["wps:site_transfer:run_2026w38"],
                         MODULE.sha(MODULE.SOURCES /
                                    "site_transfer/previous_experiment.xlsx"))
        self.assertNotEqual(task["source_versions"][MODULE.PREFIX + "read_change"],
                            task["object_versions"]["wps:site_transfer:run_2026w38"])
        self.assertEqual(task["bindings"], {})

    def test_rejects_a_prewritten_tool_binding(self):
        with self.assertRaisesRegex(ValueError, "template"):
            MODULE.prepare("site_transfer", {
                "schema_version": 1, "task_id": "meeting-decision-site_transfer",
                "intent": "Check results", "bindings": {
                    MODULE.PREFIX + "pin_object": {"object_id": "invented"}}})


if __name__ == "__main__":
    unittest.main()
