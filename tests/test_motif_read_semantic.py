"""The semantic port can choose a bounded slot but never bypass Motif guards."""

from __future__ import annotations

import json
import unittest

from src.adapters.dsh_client import SemanticValidationError
from src.adapters.motif_read_semantic import resolve_and_resume_read_motif
from src.motif_core.read_executor import run_read_motif
from src.motif_core.offline.chain_compiler import (
    certify_witnessed_chain_motif, compile_witnessed_chain_motif,
)
from src.semantic_inputs import SemanticInputRequired
from tests.test_trace_compiled_read_motif import CONTRACTS, certified_artifact
from tests.test_witnessed_chain_motif import (
    CONTRACTS as CHAIN_CONTRACTS, FIRST, SECOND, trace,
)


class MotifReadSemanticTests(unittest.TestCase):
    def test_model_can_choose_one_record_array_then_resume_chain(self) -> None:
        artifact = certify_witnessed_chain_motif(
            compile_witnessed_chain_motif(FIRST, SECOND,
                                          [trace("A"), trace("B")], CHAIN_CONTRACTS),
            trace("C"), CHAIN_CONTRACTS)
        calls = []

        def execute(tool, params):
            calls.append(tool)
            if tool == "pin":
                return {"source_id": "source-D"}
            if tool == "inspect":
                if not params["records_path"]:
                    raise SemanticInputRequired("records_path", ("rows", "groups"),
                                                {"rows": {"record_count": 27,
                                                          "fields": ["fraction", "policy", "seed"]},
                                                 "groups": {"record_count": 9,
                                                            "fields": ["fraction", "policy"]}})
                return {"dataset_id": "dataset-D"}
            return {"result_id": "result-D"}

        common = {"contracts": CHAIN_CONTRACTS, "execute_tool": execute,
                  "verify_current": lambda: None, "is_read_only": lambda _: True}
        prior = run_read_motif(
            artifact, bindings={"pin": {"path": "D.json"},
                                "aggregate": {"group_by": [],
                                              "measures": [{"name": "n", "op": "count"}]}},
            input_version="frozen-D", **common)
        prompts = []

        def semantic(prompt):
            prompts.append(json.loads(prompt))
            return '{"slot_values":{"inspect":{"records_path":"rows"}}}', {
                "model_requests": 1}

        resumed, metrics, _ = resolve_and_resume_read_motif(
            artifact, prior, choices={"inspect": {"records_path": ["rows", "groups"]}},
            call_semantic=semantic, intent="Compare individual experiment runs by seed.",
            **common)
        self.assertEqual(resumed.status, "completed")
        self.assertEqual(metrics["model_requests"], 1)
        self.assertNotIn("subset_slots", prompts[0])
        self.assertIn("never a list", prompts[0]["instruction"])
        self.assertEqual(prompts[0]["intent"],
                         "Compare individual experiment runs by seed.")
        self.assertEqual(prompts[0]["choice_details"]["inspect"]["records_path"]
                         ["rows"]["record_count"], 27)
        self.assertEqual(calls, ["pin", "inspect", "inspect", "aggregate"])

    def setUp(self) -> None:
        self.artifact = certified_artifact()
        self.calls: list[tuple[str, dict]] = []
        self.changed = False

        def execute(tool: str, params: dict) -> dict:
            self.calls.append((tool, dict(params)))
            return {"id": "D"} if tool == "search" else {"text": "Document D"}

        self.execute = execute
        self.common = {"contracts": CONTRACTS, "execute_tool": self.execute,
                       "verify_current": self.verify_current,
                       "is_read_only": lambda _tool: True}
        self.blocked = run_read_motif(
            self.artifact, bindings={}, input_version="snapshot-delta", **self.common)
        self.assertEqual(self.blocked.status, "needs_mediation")

    def verify_current(self) -> None:
        if self.changed:
            raise ValueError("source snapshot changed")

    def test_semantic_choice_resumes_same_compiled_motif(self) -> None:
        seen_prompts = []

        def semantic(prompt: str):
            seen_prompts.append(json.loads(prompt))
            return '{"slot_values":{"search":{"query":"delta"}}}', {"model_requests": 1}

        resumed, metrics, resolution = resolve_and_resume_read_motif(
            self.artifact, self.blocked, choices={"search": {"query": ["delta", "other"]}},
            call_semantic=semantic, **self.common)
        self.assertEqual(resumed.status, "completed")
        self.assertEqual(self.calls, [("search", {"query": "delta"}),
                                      ("read", {"doc_id": "D"})])
        self.assertEqual(metrics["model_requests"], 1)
        self.assertEqual(resolution.slot_values["search"]["query"], "delta")
        self.assertEqual(seen_prompts[0]["choices"], {"search": {"query": ["delta", "other"]}})

    def test_unlisted_value_stops_without_tool_execution_and_retains_usage(self) -> None:
        with self.assertRaisesRegex(SemanticValidationError, "unauthorized") as raised:
            resolve_and_resume_read_motif(
                self.artifact, self.blocked, choices={"search": {"query": ["delta"]}},
                call_semantic=lambda _prompt: (
                    '{"slot_values":{"search":{"query":"invented"}}}',
                    {"model_requests": 1, "inputTokens": 20}), **self.common)
        self.assertEqual(self.calls, [])
        self.assertEqual(raised.exception.metrics["inputTokens"], 20)

    def test_single_choice_list_is_rejected_before_reentry(self) -> None:
        with self.assertRaisesRegex(SemanticValidationError, "unauthorized"):
            resolve_and_resume_read_motif(
                self.artifact, self.blocked,
                choices={"search": {"query": ["delta", "other"]}},
                call_semantic=lambda _prompt: (
                    '{"slot_values":{"search":{"query":["delta"]}}}',
                    {"model_requests": 1}), **self.common)
        self.assertEqual(self.calls, [])

    def test_source_change_during_semantic_call_prevents_reentry(self) -> None:
        def semantic(_prompt: str):
            self.changed = True
            return '{"slot_values":{"search":{"query":"delta"}}}', {"model_requests": 1}

        with self.assertRaisesRegex(SemanticValidationError, "source snapshot changed"):
            resolve_and_resume_read_motif(
                self.artifact, self.blocked, choices={"search": {"query": ["delta"]}},
                call_semantic=semantic, **self.common)
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
