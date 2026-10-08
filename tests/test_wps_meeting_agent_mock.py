"""Synthetic cross-app MCP access and version-guard smoke checks."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mcp import Client, StdioServerParameters

from benchmarks.wps_meeting_mock_v1 import mock_apps_server as mock


ROOT = Path(__file__).resolve().parents[1]


class MockSourceTest(unittest.TestCase):
    def test_metric_and_note_are_separate_sources(self):
        listed = mock.list_mock_sources()["sources"]
        self.assertEqual({row["app"] for row in listed}, {"wps", "obsidian", "zotero"})
        wps = mock.pin_mock_source("wps:experiment_log")
        note = mock.pin_mock_source("obsidian:idea_state")
        self.assertEqual(mock.calculate_pinned_wps_metrics(wps["source_id"])
                         ["metrics"]["delta_percentage_points"], 8.0)
        self.assertIn("未见过的目标家族", mock.read_pinned_mock_source(note["source_id"])["content"])

    def test_note_change_invalidates_old_handle(self):
        original = json.loads(mock.APP_DATA.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "sources.json"
            fixture.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
            with patch.object(mock, "APP_DATA", fixture):
                pinned = mock.pin_mock_source("obsidian:idea_state")
                changed = json.loads(fixture.read_text(encoding="utf-8"))
                changed["obsidian:idea_state"]["content"] += " 新增疑点。"
                fixture.write_text(json.dumps(changed, ensure_ascii=False), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "source changed"):
                    mock.read_pinned_mock_source(pinned["source_id"])


class MockMcpTest(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_server_lists_and_reads(self):
        params = StdioServerParameters(
            command=str(ROOT / ".venv312/bin/python"),
            args=["-m", "benchmarks.wps_meeting_mock_v1.mock_apps_server"],
            cwd=ROOT,
        )
        async with Client(params, read_timeout_seconds=20) as client:
            tools = (await client.list_tools()).tools
            self.assertEqual({tool.name for tool in tools}, {
                "list_mock_sources", "pin_mock_source", "read_pinned_mock_source",
                "calculate_pinned_wps_metrics",
            })
            reply = await client.call_tool("pin_mock_source", {"object_id": "wps:experiment_log"})
            self.assertFalse(reply.is_error)
            payload = json.loads(reply.content[0].text)
            result = await client.call_tool("calculate_pinned_wps_metrics",
                                            {"source_id": payload["source_id"]})
            self.assertFalse(result.is_error)
            self.assertEqual(json.loads(result.content[0].text)["metrics"]
                             ["delta_percentage_points"], 8.0)
            for object_id in ("obsidian:idea_state", "zotero:split_study",
                              "zotero:replication_study"):
                pinned = await client.call_tool("pin_mock_source", {"object_id": object_id})
                self.assertFalse(pinned.is_error)
                source_id = json.loads(pinned.content[0].text)["source_id"]
                read = await client.call_tool("read_pinned_mock_source", {"source_id": source_id})
                self.assertFalse(read.is_error)
                self.assertEqual(json.loads(read.content[0].text)["object_id"], object_id)


if __name__ == "__main__":
    unittest.main()
