"""A cached Motif node still needs current guards; failures stay reviewable."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.motif_core.dependencies import resolve_dependencies
from src.motif_core.evidence import BoundEvidence
from src.workflows.motif_research_sources import SourceReadBlocked, collect


class MotifFailureFeedbackTests(unittest.TestCase):
    def test_cached_child_cannot_bypass_failed_precondition(self) -> None:
        metadata = {
            "required_evidence": ["child"],
            "operators": {
                "guard": {"read_only": True, "required_params": ["version"]},
                "child": {"read_only": True, "required_params": ["id"],
                          "requires": [{"output": "guard", "kind": "precondition"}]},
            },
        }
        evidence = BoundEvidence()
        evidence.record("child", {"id": "answer"}, {"value": "cached"})
        calls = []

        def execute(tool: str, params: dict) -> dict:
            calls.append(tool)
            return {"error": "current guard failed"}

        result = resolve_dependencies(
            metadata, evidence,
            {"guard": {"version": "new"}, "child": {"id": "answer"}},
            execute, lambda _tool: True, lambda *_args, **_kwargs: None,
        )
        self.assertEqual((result.status, result.reason, result.tool),
                         ("BLOCKED", "dependency_tool_error", "guard"))
        self.assertEqual(calls, ["guard"])

    def test_cached_child_recomputes_after_changed_precondition(self) -> None:
        metadata = {
            "required_evidence": ["child"],
            "operators": {
                "guard": {"read_only": True, "required_params": ["version"]},
                "child": {"read_only": True, "required_params": ["id"],
                          "requires": [{"output": "guard", "kind": "precondition"}]},
            },
        }
        evidence = BoundEvidence()
        evidence.record("child", {"id": "answer"}, {"value": "old"})
        calls = []

        def execute(tool: str, params: dict) -> dict:
            calls.append(tool)
            return {"value": "new"}

        result = resolve_dependencies(
            metadata, evidence,
            {"guard": {"version": "new"}, "child": {"id": "answer"}},
            execute, lambda _tool: True, lambda *_args, **_kwargs: None,
        )
        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(calls, ["guard", "child"])
        self.assertEqual(evidence.lookup("child", {"id": "answer"})["value"],
                         {"value": "new"})

    def test_source_failure_retains_hashes_without_source_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "damaged.txt").write_bytes(b"private\xffpayload")
            with self.assertRaises(SourceReadBlocked) as caught:
                collect(root)
            witness = caught.exception.witness
            self.assertEqual(witness["motif_id"], "research_sources")
            self.assertEqual(witness["operator"], "read_source")
            self.assertEqual(witness["reason"], "dependency_tool_error")
            self.assertEqual(witness["error_class"], "UnicodeDecodeError")
            self.assertEqual(witness["disposition"], "quarantined_candidate_evidence")
            self.assertNotIn("private", str(witness))
            self.assertEqual(len(witness["input_version"]), 64)


if __name__ == "__main__":
    unittest.main()
