"""Meaningful execution checks for the local analysis MCP boundary."""

from __future__ import annotations

import unittest
from pathlib import Path

from mcp import Client

from src.mcp.local_research_tools_server import (
    ROOT, list_workspace_files, preview_quarto, render_quarto,
    run_python, server, write_workspace_text,
)


class WorkflowTest(unittest.TestCase):
    def test_python_executes_and_cannot_write_outside_workspace(self) -> None:
        result = run_python("print(sum([2, 3]))")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["stdout"], "5\n")

        forbidden = ROOT / ".local" / "python-escape-test.txt"
        self.assertFalse(forbidden.exists())

        private = ROOT / ".local" / "google-calendar" / "python-private-test.txt"
        private.parent.mkdir(exist_ok=True)
        private.write_text("private", encoding="utf-8")
        try:
            result = run_python(f"from pathlib import Path\nprint(Path({str(private)!r}).read_text())")
            self.assertFalse(result["ok"])
            self.assertNotIn("private\n", result["stdout"])
        finally:
            private.unlink(missing_ok=True)
        result = run_python(f"from pathlib import Path\nPath({str(forbidden)!r}).write_text('bad')")
        self.assertFalse(result["ok"])
        self.assertFalse(forbidden.exists())

    def test_quarto_render_stays_in_private_workspace(self) -> None:
        write_workspace_text("tests/report.qmd", "---\ntitle: MCP smoke\n---\n\nResult: 5.\n")
        preview = preview_quarto("tests/report.qmd")
        self.assertTrue(preview["quarto_available"])
        result = render_quarto("tests/report.qmd")
        self.assertTrue(result["ok"], result)
        self.assertTrue(any(f["path"] == "rendered/report.html" for f in list_workspace_files()))

    def test_rejects_workspace_escape(self) -> None:
        with self.assertRaisesRegex(ValueError, "leaves"):
            write_workspace_text("../escape.py", "print(1)")


class WorkflowMCPTest(unittest.IsolatedAsyncioTestCase):
    async def test_tools_are_available_to_mcp_client(self) -> None:
        async with Client(server) as client:
            names = {tool.name for tool in (await client.list_tools()).tools}
            self.assertIn("run_python", names)
            self.assertIn("render_quarto", names)
            result = await client.call_tool("python_environment", {})
            self.assertFalse(result.is_error)


if __name__ == "__main__":
    unittest.main()
