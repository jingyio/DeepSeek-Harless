"""Application IDs need witnessed provenance before any online promotion."""

from __future__ import annotations

import json
import unittest

from src.motif_core.offline.object_reference_candidates import (
    object_reference_witnesses, repeated_object_edge_candidates,
)


SOURCE = "mcp__fixture__read_change"
TARGET = "mcp__fixture__pin_object"
APPROVED = {SOURCE, TARGET}


def call(call_id: str, name: str, arguments: dict) -> dict:
    return {"type": "tool/call", "data": {"callId": call_id, "name": name,
                                          "arguments": json.dumps(arguments)}}


def result(call_id: str, value: dict, *, error: bool = False) -> dict:
    return {"type": "tool/result", "data": {"message": {
        "source": {"callId": call_id},
        "content": [{"type": "tool-result", "toolCallId": call_id,
                     "isError": error,
                     "content": [{"type": "text", "text": json.dumps(value)}]}]}}}


def trace(case: str) -> list[dict]:
    object_id = f"wps:{case}:run_2026w39"
    return [call("event", SOURCE, {"event_id": f"event:{case}:w39"}),
            result("event", {"experiment_id": object_id, "event_version": "v1"}),
            call("pin", TARGET, {"object_id": object_id}),
            result("pin", {"object_id": object_id, "version_sha256": "v2"})]


class ObjectReferenceCandidateTest(unittest.TestCase):
    def test_distinct_source_and_target_versions_are_witnessed_not_executed(self):
        rows = repeated_object_edge_candidates([
            {"trace_id": case, "decision_id": f"decision:{case}",
             "events": trace(case)} for case in ("alpha", "beta", "gamma")], APPROVED)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["from_field"], "experiment_id")
        self.assertEqual(rows[0]["status"], "witnessed_not_executable")

    def test_ambiguous_or_failed_observation_is_not_a_witness(self):
        rows = trace("alpha")
        extra = [call("duplicate", SOURCE, {"event_id": "event:alpha:w39"}),
                 result("duplicate", {"experiment_id": "wps:alpha:run_2026w39"})]
        ambiguous = rows[:2] + extra + rows[2:]
        self.assertEqual(object_reference_witnesses(ambiguous, APPROVED), [])
        failed = rows[:-1] + [result("pin", {"object_id": "wps:alpha:run_2026w39"},
                                    error=True)]
        self.assertEqual(object_reference_witnesses(failed, APPROVED), [])

    def test_nested_object_id_is_found_from_result(self):
        discover = "mcp__fixture__find_dependent_claims"
        note = "obsidian:alpha:claim"
        rows = [call("find", discover, {"object_id": "wps:alpha:run_2026w39"}),
                result("find", {"claims": [{"note_id": note}]}),
                call("pin", TARGET, {"object_id": note}),
                result("pin", {"object_id": note, "version_sha256": "v3"})]
        witness = object_reference_witnesses(rows, APPROVED | {discover})
        self.assertEqual(witness[0]["from_field"], "claims.0.note_id")


if __name__ == "__main__":
    unittest.main()
