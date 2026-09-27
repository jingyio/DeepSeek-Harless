"""Guard against reversing version-bound raw evidence at delivery."""

from __future__ import annotations

import json
import unittest

from src.adapters.versioned_evidence_guard import (
    _formal_simpson_reversal, audit_versioned_seed_claims,
)


def observation(call_id: str, name: str, value: dict) -> list[dict]:
    return [
        {"type": "tool/call", "data": {"callId": call_id, "name":
          f"mcp__fixture__{name}"}},
        {"type": "tool/result", "data": {"message": {"content": [{
          "type": "tool-result", "toolCallId": call_id, "isError": False,
          "content": [{"type": "text", "text": json.dumps(value)}]}]}}},
    ]


def evidence() -> list[dict]:
    current = "wps:study:run_2026w39"
    previous = "wps:study:run_2026w38"
    events = observation("event", "read_change", {
        "experiment_id": current, "previous_experiment_id": previous,
        "changed_fields": ["correct"], "previous_version_sha256": "old-version"})
    for label, object_id, values in (("new", current, (22, 21, 20)),
                                      ("old", previous, (26, 25, 24))):
        source = f"source-{label}"
        events += observation(f"pinned-{label}", "read_pinned_object", {
            "source_id": source, "object_id": object_id,
            "version_sha256": f"{label}-version",
            "value": {"metric_contract": {
                "allowed_groups": ["variant", "frequency_band"]}}})
        events += observation(f"rows-{label}", "read_dataset_rows", {
            "source_id": source, "version_sha256": f"{label}-version",
            "offset": 0, "total": 3,
            "rows": [{"variant": "candidate", "frequency_band": "tail",
                      "seed": index + 1, "cases": 40, "correct": value}
                     for index, value in enumerate(values)]})
    return events


class VersionedEvidenceGuardTest(unittest.TestCase):
    def test_reversed_seed_series_is_blocked(self):
        draft = "原始行核验（w39，candidate/tail，三 seed 分别为 26、25、24；w38 为 22、21、20）。"
        result = audit_versioned_seed_claims(evidence(), draft)
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(len(result["conflicts"]), 2)

    def test_correct_series_is_not_blocked(self):
        draft = "原始行核验（w39，candidate/tail，三 seed 分别为 22、21、20；w38 为 26、25、24）。"
        result = audit_versioned_seed_claims(evidence(), draft)
        self.assertEqual(result["status"], "checked")
        self.assertEqual(result["checked_versioned_series"], 2)

    def test_no_false_match_across_paragraphs(self):
        draft = "w39 候选的总体数值有变化。\n三个种子由 26、25、24 降为 22、21、20。"
        result = audit_versioned_seed_claims(evidence(), draft)
        self.assertEqual(result["status"], "checked")
        self.assertEqual(result["checked_versioned_series"], 0)

    def test_missing_raw_pair_never_claims_clearance(self):
        events = [event for event in evidence()
                  if event.get("data", {}).get("callId") != "rows-old" and
                  not any(block.get("toolCallId") == "rows-old" for block in
                          event.get("data", {}).get("message", {}).get("content", []))]
        result = audit_versioned_seed_claims(events, "w39 三 seed 为 22、21、20。")
        self.assertEqual(result["status"], "insufficient_evidence")

    def test_unchanged_row_count_blocks_claim_of_new_rows(self):
        result = audit_versioned_seed_claims(evidence(), "w39 新增 tail 行，需复核。")
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["conflicts"][0]["kind"], "row_count")
        allowed = audit_versioned_seed_claims(evidence(), "w39 没有新增 tail 行。")
        self.assertEqual(allowed["status"], "checked")

    def test_simpson_label_requires_reversal_in_every_stratum(self):
        contract = {"numerator": "correct", "denominator": "cases"}
        groups = ["variant", "site"]
        mixed = [{"variant": "baseline", "site": "a", "correct": 70, "cases": 100},
                 {"variant": "candidate", "site": "a", "correct": 80, "cases": 100},
                 {"variant": "baseline", "site": "b", "correct": 60, "cases": 100},
                 {"variant": "candidate", "site": "b", "correct": 50, "cases": 100}]
        self.assertFalse(_formal_simpson_reversal(mixed, contract, groups))
        reversed_groups = [
            {"variant": "baseline", "site": "a", "correct": 80, "cases": 100},
            {"variant": "candidate", "site": "a", "correct": 9, "cases": 10},
            {"variant": "baseline", "site": "b", "correct": 0, "cases": 10},
            {"variant": "candidate", "site": "b", "correct": 1, "cases": 100},
        ]
        self.assertTrue(_formal_simpson_reversal(reversed_groups, contract, groups))
        negated = audit_versioned_seed_claims(evidence(), "这并非辛普森悖论。")
        self.assertEqual(negated["status"], "checked")


if __name__ == "__main__":
    unittest.main()
