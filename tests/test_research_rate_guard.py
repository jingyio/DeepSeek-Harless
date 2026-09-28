from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.adapters.research_rate_guard import (direction_issues,
                                               paired_rate_facts, repair_prompt,
                                               repair_result_once)


def trace(rows, *, read_version="version-1", total=None):
    dataset = "dataset-1"
    source = "source-1"
    table = {"source_id": source, "version_sha256": "version-1",
             "value": {"dataset_id": dataset, "row_count": len(rows),
                       "metric": {"allowed_groups": ["arm"],
                                  "numerator": "accepted", "denominator": "reviewed"}}}
    data = {"dataset_id": dataset, "source_id": source,
            "version_sha256": read_version, "offset": 0,
            "total": len(rows) if total is None else total, "rows": rows}
    events = []
    for index, (name, value) in enumerate((("read_pinned", table),
                                           ("read_rows", data))):
        call_id = f"call-{index}"
        events.append({"type": "tool/call", "data": {"callId": call_id,
                          "name": f"mcp__research_portfolio_fixture__{name}"}})
        events.append({"type": "tool/result", "data": {"message": {
            "source": {"callId": call_id}, "content": [{"type": "tool-result",
            "content": [{"type": "text", "text": json.dumps(value)}]}]}}})
    return events


SAME = [
    {"seed": 1, "arm": "retrieval", "accepted": 36, "reviewed": 50},
    {"seed": 2, "arm": "retrieval", "accepted": 37, "reviewed": 50},
    {"seed": 1, "arm": "state", "accepted": 35, "reviewed": 50},
    {"seed": 2, "arm": "state", "accepted": 36, "reviewed": 50},
]
MIXED = [
    {"seed": 1, "arm": "baseline", "accepted": 40, "reviewed": 50},
    {"seed": 2, "arm": "baseline", "accepted": 37, "reviewed": 50},
    {"seed": 1, "arm": "candidate", "accepted": 44, "reviewed": 50},
    {"seed": 2, "arm": "candidate", "accepted": 36, "reviewed": 50},
]


class PairedRateGuardTest(unittest.TestCase):
    def test_flags_historical_same_direction_error(self):
        facts = paired_rate_facts(trace(SAME))
        self.assertEqual(len(facts), 1)
        self.assertTrue(facts[0]["same_direction"])
        self.assertEqual(facts[0]["higher_group"], "retrieval")
        issues = direction_issues(
            "两个 seed 的方向本身不一致（retrieval 36→37 升、state 35→36 升）", facts)
        self.assertEqual(len(issues), 1)
        self.assertIn("36/50", repair_prompt(issues))
        self.assertEqual(direction_issues("两个 seed 均为 retrieval 高于 state", facts), [])

    def test_mixed_sign_is_not_falsely_flagged(self):
        facts = paired_rate_facts(trace(MIXED))
        self.assertFalse(facts[0]["same_direction"])
        self.assertEqual(direction_issues("两种子差值方向不一致（一正一负）", facts), [])
        self.assertEqual(len(direction_issues("两个 seed 的方向一致", facts)), 1)

    def test_stale_or_incomplete_rows_do_not_authorize_repair(self):
        self.assertEqual(paired_rate_facts(trace(SAME, read_version="version-2")), [])
        self.assertEqual(paired_rate_facts(trace(SAME, total=5)), [])
        self.assertEqual(paired_rate_facts(trace(SAME[:-1])), [])

    def test_duplicate_pair_or_tie_does_not_authorize_direction(self):
        duplicate = SAME + [SAME[0]]
        self.assertEqual(paired_rate_facts(trace(duplicate)), [])
        tied = [dict(row) for row in SAME]
        tied[-1]["accepted"] = 37
        self.assertEqual(paired_rate_facts(trace(tied)), [])

    def test_runtime_repairs_once_and_rechecks(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_text("\n".join(json.dumps(row) for row in trace(SAME)))
            bad = SimpleNamespace(final_response="两个 seed 的方向不一致",
                                  finish_reason="completed")
            calls = []

            def corrected(prompt):
                calls.append(prompt)
                return SimpleNamespace(final_response="两个 seed 均为 retrieval 较高",
                                       finish_reason="completed")

            result, audit = repair_result_once(bad, path, corrected)
            self.assertEqual(len(calls), 1)
            self.assertEqual(audit["repair_requests"], 1)
            self.assertEqual(audit["remaining_issues"], [])
            self.assertIn("retrieval", result.final_response)

            calls.clear()
            result, audit = repair_result_once(bad, path,
                lambda prompt: calls.append(prompt) or bad)
            self.assertEqual(len(calls), 1)
            self.assertEqual(len(audit["remaining_issues"]), 1)
            self.assertEqual(result, bad)

    def test_runtime_skips_repair_when_answer_is_consistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_text("\n".join(json.dumps(row) for row in trace(SAME)))
            good = SimpleNamespace(final_response="两个 seed 均为 retrieval 较高",
                                   finish_reason="completed")
            result, audit = repair_result_once(
                good, path, lambda _: self.fail("unexpected model repair"))
            self.assertIs(result, good)
            self.assertEqual(audit["repair_requests"], 0)


if __name__ == "__main__":
    unittest.main()
