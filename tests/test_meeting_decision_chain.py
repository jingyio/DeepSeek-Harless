"""Meaningful fixture checks: three distinct decisions, metrics and stale handles."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mcp import Client, StdioServerParameters

from benchmarks.meeting_decision_chain_v1 import mock_apps_server as apps
from benchmarks.meeting_decision_chain_v1.script_baseline import run


PROJECT = Path(__file__).resolve().parents[1]


def grouped(result: dict) -> dict:
    fields = result["group_by"]
    return {tuple(row[field] for field in fields): row["value"]
            for row in result["groups"]}


class MeetingFixtureTest(unittest.TestCase):
    def test_three_independent_updates_and_script_handoff(self):
        expected = {
            "family_shift": ((0.55, 0.675), (0.65, 0.7125)),
            "label_audit": ((0.825, 0.9), (0.7375, 0.775)),
            "hardware_latency": ((105.0, 95.0), (130.0, 120.0)),
        }
        for case, ((current_slice, previous_slice),
                   (current_total, previous_total)) in expected.items():
            with self.subTest(case=case):
                result = run(case)
                self.assertEqual(result["decision"], "semantic_review_required")
                self.assertFalse(result["complete_research_decision"])
                self.assertEqual(result["model_requests"], 0)
                current = grouped(result["metric"])
                previous = grouped(result["prior_metric"])
                group = "unseen" if case == "family_shift" else (
                    "verified" if case == "label_audit" else "fast")
                self.assertAlmostEqual(current[("candidate", group)], current_slice)
                self.assertAlmostEqual(previous[("candidate", group)], previous_slice)
                source_id = apps.pin_object(result["metric"]["object_id"])["source_id"]
                dataset_id = apps.read_pinned_object(source_id)["value"]["dataset_id"]
                all_current = apps.aggregate_pinned_experiment(dataset_id, ["variant"])
                self.assertAlmostEqual(grouped(all_current)[("candidate",)], current_total)
                prior_id = apps.pin_object(result["prior_metric"]["object_id"])["source_id"]
                prior_dataset_id = apps.read_pinned_object(prior_id)["value"]["dataset_id"]
                all_previous = apps.aggregate_pinned_experiment(prior_dataset_id, ["variant"])
                self.assertAlmostEqual(grouped(all_previous)[("candidate",)], previous_total)

    def test_changed_source_invalidates_existing_handle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "sources" / "family_shift"
            shutil.copytree(apps.ROOT / "sources" / "family_shift", target)
            with patch.object(apps, "ROOT", root), patch.dict(
                os.environ, {"SSS_MEETING_CASE": "family_shift"}):
                source_id = apps.pin_object("obsidian:family_shift:claim")["source_id"]
                path = target / "note.json"
                note = json.loads(path.read_text(encoding="utf-8"))
                note["text"] += " 本周新增疑点。"
                path.write_text(json.dumps(note, ensure_ascii=False), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "source changed"):
                    apps.read_pinned_object(source_id)

    def test_other_case_is_outside_scope(self):
        with patch.dict(os.environ, {"SSS_MEETING_CASE": "family_shift"}):
            with self.assertRaisesRegex(ValueError, "outside this case"):
                apps.pin_object("wps:label_audit:run_2026w39")
            with self.assertRaisesRegex(ValueError, "outside this case"):
                apps.read_change("event:label_audit:w39")


class MeetingMcpTest(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_parameter_flow(self):
        params = StdioServerParameters(
            command=str(PROJECT / ".venv312/bin/python"),
            args=["-m", "benchmarks.meeting_decision_chain_v1.mock_apps_server"],
            cwd=PROJECT,
            env={"SSS_MEETING_CASE": "hardware_latency", "PYTHONPATH": str(PROJECT)},
        )
        async with Client(params, read_timeout_seconds=20) as client:
            names = {tool.name for tool in (await client.list_tools()).tools}
            self.assertEqual(names, {"read_change", "pin_object", "read_pinned_object",
                                     "read_dataset_rows", "aggregate_pinned_experiment",
                                     "find_dependent_claims"})
            event = await client.call_tool("read_change",
                                           {"event_id": "event:hardware_latency:w39"})
            self.assertFalse(event.is_error)
            experiment_id = json.loads(event.content[0].text)["experiment_id"]
            pinned = await client.call_tool("pin_object", {"object_id": experiment_id})
            self.assertFalse(pinned.is_error)
            source_id = json.loads(pinned.content[0].text)["source_id"]
            inspected = await client.call_tool("read_pinned_object", {"source_id": source_id})
            self.assertFalse(inspected.is_error)
            dataset_id = json.loads(inspected.content[0].text)["value"]["dataset_id"]
            metric = await client.call_tool("aggregate_pinned_experiment",
                                            {"dataset_id": dataset_id,
                                             "group_by": ["variant", "hardware"]})
            self.assertFalse(metric.is_error)
            values = grouped(json.loads(metric.content[0].text))
            self.assertEqual(values[("candidate", "fast")], 105.0)
            self.assertEqual(values[("baseline", "fast")], 100.0)


if __name__ == "__main__":
    unittest.main()
