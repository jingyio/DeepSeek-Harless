"""Bound observed model turns without mistaking tool pairs for savings."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

from src.adapters.dsh_trajectory import ToolContract
from tests.test_trace_compiled_read_motif import event_pair


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/audit-motif-turn-opportunities.py"
SPEC = importlib.util.spec_from_file_location("motif_turn_opportunities", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MotifTurnOpportunityTests(unittest.TestCase):
    def test_only_isolated_cross_step_reads_are_turn_candidates(self):
        contracts = {
            "pin": ToolContract(("role",), True, ("source_id",)),
            "read": ToolContract(("source_id",), True,
                                 provenance_params=("source_id",)),
            "other": ToolContract(("query",), True),
        }
        events = []

        def add_call(index, step, name, args, observation):
            pair = event_pair(index, name, args, observation)
            for event in pair:
                event["data"]["step"] = step
            events.extend(pair)

        def add_message(step):
            events.append({"type": "assistant/message", "data": {
                "step": step, "usage": {"inputTokens": step * 100,
                                          "cacheReadTokens": step * 10}}})

        def source(letter):
            return "source-" + letter * 32

        add_call(1, 1, "pin", {"role": "A"}, {"source_id": source("a")})
        add_message(1)
        add_call(2, 2, "read", {"source_id": source("a")}, {"text": "A"})
        add_message(2)
        add_call(3, 3, "pin", {"role": "B"}, {"source_id": source("b")})
        add_call(4, 3, "read", {"source_id": source("b")}, {"text": "B"})
        add_message(3)
        add_call(5, 4, "pin", {"role": "C"}, {"source_id": source("c")})
        add_message(4)
        add_call(6, 5, "read", {"source_id": source("c")}, {"text": "C"})
        add_call(7, 5, "other", {"query": "follow up"}, {"text": "X"})
        add_message(5)

        result = MODULE.audit(events, contracts, trace_id="fixture")
        self.assertEqual(result["cross_step_target_steps"], [2, 5])
        self.assertEqual(result["isolated_safe_target_steps"], [2])
        self.assertEqual(result["isolated_target_model_turn_upper_bound"], 1)
        self.assertEqual(result["isolated_target_prompt_token_exposure"], 220)
        self.assertEqual(result["isolated_target_usage_upper_bound"],
                         {"miss": 200, "hit": 20, "output": 0})
        self.assertEqual(result["isolated_target_direct_offpeak_usd_upper_bound"],
                         round((200 * 0.15 + 20 * 0.003) / 1_000_000, 8))
        self.assertEqual(result["safe_edges"][0]["safe_pairs"], 3)
        self.assertEqual(result["safe_edges"][0]["cross_step_pairs"], 2)
        self.assertEqual(result["safe_edges"][0]["same_step_pairs"], 1)

    def test_data_handle_does_not_fill_semantic_statistic_slots(self):
        contracts = {
            "inspect": ToolContract(("source_id",), True, ("dataset_id",)),
            "aggregate": ToolContract(("dataset_id", "group_by", "measures"), True,
                                      provenance_params=("dataset_id",)),
        }
        dataset = "dataset-" + "d" * 32
        first = event_pair(1, "inspect", {"source_id": "source-" + "s" * 32},
                           {"dataset_id": dataset})
        second = event_pair(2, "aggregate", {
            "dataset_id": dataset, "group_by": ["study"],
            "measures": [{"name": "n", "op": "count"}]}, {"rows": 3})
        for event in first:
            event["data"]["step"] = 1
        for event in second:
            event["data"]["step"] = 2
        events = first + second + [{"type": "assistant/message", "data": {
            "step": 2, "usage": {"inputTokens": 900}}}]

        result = MODULE.audit(events, contracts, trace_id="semantic-slot-fixture")
        self.assertEqual(result["cross_step_target_steps"], [2])
        self.assertEqual(result["fully_bound_cross_step_targets"], 0)
        self.assertEqual(result["isolated_safe_target_steps"], [])
        self.assertEqual(result["isolated_target_model_turn_upper_bound"], 0)
        self.assertEqual(result["unresolved_target_slots"], [
            {"tool": "aggregate", "parameter": "group_by", "calls": 1},
            {"tool": "aggregate", "parameter": "measures", "calls": 1},
        ])


if __name__ == "__main__":
    unittest.main()
