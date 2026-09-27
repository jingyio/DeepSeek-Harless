"""Step-level audit keeps costs and failures attached to the right call."""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/summarize-dsh-step-cost.py"
SPEC = importlib.util.spec_from_file_location("dsh_step_cost", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def result(call_id: str, payload: dict, *, error: bool = False) -> dict:
    return {"type": "tool/result", "data": {"message": {
        "source": {"callId": call_id}, "content": [{
            "isError": error, "content": [{"text": json.dumps(payload)}]}]}}}


class StepCostTests(unittest.TestCase):
    def test_multiple_tools_one_step_and_provider_unavailable(self) -> None:
        events = [
            {"type": "assistant/message", "data": {"step": 1, "usage": {
                "inputTokens": 100, "cacheReadTokens": 200,
                "outputTokens": 10, "totalTokens": 310}}},
            {"type": "tool/call", "data": {"step": 1, "callId": "a", "name": "read"}},
            {"type": "tool/call", "data": {"step": 1, "callId": "b", "name": "search"}},
            result("a", {"rows": 3}),
            result("b", {"status": "unavailable"}),
            {"type": "assistant/message", "data": {"step": 2, "usage": {
                "inputTokens": 50, "cacheReadTokens": 300,
                "outputTokens": 20, "totalTokens": 370}}},
        ]
        report = module.summarize_events(events, run="sample")
        self.assertEqual(report["model_messages"], 2)
        self.assertEqual(report["tool_calls"], 2)
        self.assertEqual(report["failed_tool_calls"], 1)
        self.assertEqual(report["steps"][0]["failed_tools"], {"search": 1})
        self.assertEqual(report["steps"][0]["prompt_tokens"], 300)
        self.assertEqual(report["tokens"]["totalTokens"], 680)

    def test_context_replacement_is_not_a_new_tool_failure(self) -> None:
        original = result("a", {"rows": 3})
        replacement = result("a", {"status": "unavailable"})
        replacement["surfaceOp"] = {"op": "replace", "startSeq": 2, "endSeq": 2}
        events = [
            {"type": "tool/call", "data": {"step": 1, "callId": "a", "name": "read"}},
            original, replacement,
        ]
        report = module.summarize_events(events, run="compacted")
        self.assertEqual(report["tool_calls"], 1)
        self.assertEqual(report["failed_tool_calls"], 0)
        self.assertEqual(report["unassigned_results"], 0)


if __name__ == "__main__":
    unittest.main()
