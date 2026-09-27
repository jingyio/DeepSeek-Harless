"""An event log cannot gain independent-task status from a CLI string."""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.adapters.dsh_trajectory import DshTrace
from src.adapters.task_identity import load_trace_identity, require_distinct_decisions
from src.motif_core.offline.library_builder import (
    build_read_motif_library, validate_read_motif_library,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/freeze-dsh-task-identity.py"
SPEC = importlib.util.spec_from_file_location("freeze_dsh_task_identity", SCRIPT)
assert SPEC and SPEC.loader
FREEZE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FREEZE)


class DshTaskIdentityTests(unittest.TestCase):
    def task(self, folder: Path, name: str, question: str, decision: str):
        path = folder / name
        path.mkdir()
        manifest = path / "manifest.json"
        events = path / "events.jsonl"
        manifest.write_text(json.dumps({"task_id": name, "question": question}),
                            encoding="utf-8")
        events.write_text('{"type":"assistant/message"}\n', encoding="utf-8")
        identity = FREEZE.freeze(path, decision)
        return identity, events

    def test_lock_is_immutable_and_detects_changed_events(self):
        with TemporaryDirectory(dir=ROOT / ".local") as temporary:
            local = ROOT / ".local"
            identity, events = self.task(Path(temporary), "run-a", "Can A support B?",
                                         "decision-a")
            first = load_trace_identity(identity, events, local)
            self.assertEqual(first["research_decision_id"], "decision-a")
            self.assertEqual(FREEZE.freeze(identity.parent, "decision-a"), identity)
            with self.assertRaisesRegex(ValueError, "immutable"):
                FREEZE.freeze(identity.parent, "decision-b")
            events.write_text('{"type":"tool/call"}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match"):
                load_trace_identity(identity, events, local)

    def test_same_decision_or_same_question_cannot_be_independent(self):
        with TemporaryDirectory(dir=ROOT / ".local") as temporary:
            local = ROOT / ".local"
            root = Path(temporary)
            a, a_events = self.task(root, "run-a", "Does the graph support the claim?",
                                    "research-decision-a")
            b, b_events = self.task(root, "run-b", "A different question",
                                    "research-decision-a")
            c, c_events = self.task(root, "run-c", "  Does the graph support the claim? ",
                                    "research-decision-c")
            first = load_trace_identity(a, a_events, local)
            second = load_trace_identity(b, b_events, local)
            third = load_trace_identity(c, c_events, local)
            with self.assertRaisesRegex(ValueError, "repeat one research decision"):
                require_distinct_decisions([first, second])
            with self.assertRaisesRegex(ValueError, "identical research questions"):
                require_distinct_decisions([first, third])
            with self.assertRaisesRegex(ValueError, "share one task directory"):
                load_trace_identity(a, b_events, local)

    def test_compiled_library_keeps_identity_evidence_in_digest(self):
        with TemporaryDirectory(dir=ROOT / ".local") as temporary:
            local = ROOT / ".local"
            root = Path(temporary)
            data = [self.task(root, f"run-{name}", f"Question {name}?",
                              f"decision-{name}") for name in ("a", "b", "c")]
            identities = [load_trace_identity(lock, events, local)
                          for lock, events in data]
            traces = [DshTrace(f"trace-{name}", (), (), f"decision-{name}")
                      for name in ("a", "b", "c")]
            evidence = {trace.trace_id: identity
                        for trace, identity in zip(traces, identities)}
            library = build_read_motif_library(
                traces[:2], traces[2:], {}, task_identity_evidence=evidence)
            validate_read_motif_library(library)
            self.assertEqual(library["task_identity_evidence"], evidence)
            library["task_identity_evidence"]["trace-a"]["events_sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "stale or invalid"):
                validate_read_motif_library(library)
            evidence["trace-b"] = {**evidence["trace-b"],
                                   "research_decision_id": "forged-decision"}
            with self.assertRaisesRegex(ValueError, "must match every frozen trace"):
                build_read_motif_library(
                    traces[:2], traces[2:], {}, task_identity_evidence=evidence)
            evidence["trace-b"] = {**identities[1],
                                   "question_sha256": identities[0]["question_sha256"]}
            with self.assertRaisesRegex(ValueError, "must match every frozen trace"):
                build_read_motif_library(
                    traces[:2], traces[2:], {}, task_identity_evidence=evidence)

    def test_invalid_manifest_does_not_leave_identity_lock(self):
        with TemporaryDirectory(dir=ROOT / ".local") as temporary:
            root = Path(temporary)
            (root / "manifest.json").write_text(json.dumps({"task_id": "x"}),
                                                encoding="utf-8")
            (root / "events.jsonl").write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "research question"):
                FREEZE.freeze(root, "decision-x")
            self.assertFalse((root / "task-identity.json").exists())

    def test_manifest_symlink_cannot_define_task_identity(self):
        with TemporaryDirectory(dir=ROOT / ".local") as temporary:
            root = Path(temporary)
            inner = root / "task"
            inner.mkdir()
            (root / "outside-manifest.json").write_text(json.dumps({
                "task_id": "x", "question": "A question?"}), encoding="utf-8")
            (inner / "manifest.json").symlink_to(root / "outside-manifest.json")
            (inner / "events.jsonl").write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "regular task files"):
                FREEZE.freeze(inner, "decision-x")
            self.assertFalse((inner / "task-identity.json").exists())


if __name__ == "__main__":
    unittest.main()
