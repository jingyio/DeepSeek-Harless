"""Tool-use reports reflect upstream results, not context projections."""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/report-tool-usage.py"
SPEC = importlib.util.spec_from_file_location("report_tool_usage", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class ToolUsageTests(unittest.TestCase):
    def test_replacement_cannot_reverse_original_success(self) -> None:
        call = {"type": "tool/call", "data": {"callId": "a", "name": "mcp__source__read"}}
        original = {"type": "tool/result", "data": {"message": {
            "source": {"callId": "a"}, "content": [{"isError": False,
                "content": [{"text": json.dumps({"rows": 3})}]}]}}}
        replacement = {"type": "tool/result", "surfaceOp": {"op": "replace"},
                       "data": {"message": {"source": {"callId": "a"},
                                            "content": [{"isError": True}]}}}
        report = module.summarize([call, original, replacement])
        self.assertEqual(report["tool_calls"], 1)
        self.assertEqual(report["by_group"]["source"]["reported_success"], 1)
        self.assertEqual(report["by_group"]["source"]["reported_failure"], 0)

    def test_provider_unavailable_counts_as_failure(self) -> None:
        call = {"type": "tool/call", "data": {"callId": "a", "name": "mcp__source__read"}}
        result = {"type": "tool/result", "data": {"message": {
            "source": {"callId": "a"}, "content": [{"isError": False,
                "content": [{"text": json.dumps({"status": "unavailable"})}]}]}}}
        report = module.summarize([call, result])
        self.assertEqual(report["by_group"]["source"]["reported_failure"], 1)


if __name__ == "__main__":
    unittest.main()
