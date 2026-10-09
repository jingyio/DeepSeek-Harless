"""Verify the added families are frozen and accessible only through scoped MCP."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import unittest
from collections import deque
from pathlib import Path
from unittest.mock import patch

from mcp import Client, StdioServerParameters

from benchmarks.research_decision_portfolio_v2 import build_fixtures as fixtures
from benchmarks.research_decision_portfolio_v2 import mock_apps_server as apps

ROOT = Path(fixtures.__file__).resolve().parent


class PortfolioV2Test(unittest.TestCase):
    def setUp(self):
        apps._handles.clear()
        apps._datasets.clear()
        apps._discovered.clear()

    def test_nine_frozen_independent_decisions_across_three_new_families(self):
        lock = json.loads((ROOT / "fixtures.lock.json").read_text())
        self.assertEqual({family: len(cases) for family, cases in
                          lock["families"].items()}, {
            "artifact_lineage_release": 3,
            "replication_readiness": 3,
            "evidence_gap_experiment_choice": 3})
        self.assertEqual(len(set(fixtures.CASES)), 9)
        for filename, expected in lock["sha256"].items():
            self.assertEqual(hashlib.sha256((ROOT / filename).read_bytes()).hexdigest(),
                             expected)

    def test_each_case_requires_linked_discovery_and_keeps_review_separate(self):
        for case in fixtures.CASES:
            with self.subTest(case=case), patch.dict(os.environ,
                                                     {"SSS_PORTFOLIO_CASE": case}):
                self.setUp()
                sources = json.loads((ROOT / "cases" / case / "sources.json").read_text())
                task = (ROOT / "cases" / case / "task.md").read_text()
                self.assertNotIn("fatal", task)
                event = apps.read_event(f"event:{case}:01")
                queue = deque(event["root_objects"])
                seen = set()
                while queue:
                    object_id = queue.popleft()
                    if object_id in seen:
                        continue
                    seen.add(object_id)
                    handle = apps.pin_resource(object_id)
                    value = apps.read_pinned(handle["source_id"])
                    self.assertEqual(handle["version_sha256"],
                                     value["version_sha256"])
                    queue.extend(value["value"].get("links", []))
                    found = apps.find_dependents(object_id)
                    queue.extend(row["object_id"] for row in found["claims"])
                self.assertEqual(seen, set(sources["objects"]))
                with self.assertRaisesRegex(ValueError, "outside"):
                    apps.pin_resource("quarto:outside:q01")


class PortfolioV2McpTest(unittest.IsolatedAsyncioTestCase):
    async def test_quarto_case_is_a_read_only_stdio_mcp(self):
        project = ROOT.parent.parent
        case = "a_model_rsi_figure"
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(ROOT / "mock_apps_server.py")], cwd=project,
            env={"SSS_PORTFOLIO_CASE": case, "PYTHONPATH": str(project)})
        async with Client(params, read_timeout_seconds=20) as client:
            tools = {tool.name for tool in (await client.list_tools()).tools}
            self.assertIn("pin_resource", tools)
            self.assertIn("aggregate_rate", tools)
            event = await client.call_tool("read_event",
                                           {"event_id": f"event:{case}:01"})
            self.assertFalse(event.is_error)
            root = json.loads(event.content[0].text)["root_object_id"]
            self.assertEqual(root, f"quarto:{case}:q01")
            pinned = await client.call_tool("pin_resource", {"object_id": root})
            self.assertFalse(pinned.is_error)


if __name__ == "__main__":
    unittest.main()
