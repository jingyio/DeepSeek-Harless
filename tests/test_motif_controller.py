"""Exercise the trace-derived library through Motif-owned match and reentry."""

import hashlib
import json
import unittest

from src.adapters.dsh_trajectory import DshTrace, ToolContract, ToolRecord
from src.adapters.dsh_client import SemanticValidationError
from src.adapters.motif_read_semantic import (
    resolve_and_resume_controller_slots, resolve_and_resume_motif_choice,
)
from src.motif_core.controller import MotifController
from src.motif_core.handoff import SemanticResolution
from src.motif_core.offline.library_builder import build_read_motif_library


CONTRACTS = {
    "search": ToolContract(("query",), True, ("id",)),
    "lookup": ToolContract(("query",), True, ("id",)),
    "read": ToolContract(("doc_id",), True, ("text",)),
}


def sig(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":")).encode()).hexdigest()


def trace(kind, label, identifier):
    return DshTrace(
        f"{kind}-{label}",
        (ToolRecord(kind, {"query": label}, "first", True, "eligible_read", 1,
                    {"id": identifier}),
         ToolRecord("read", {"doc_id": identifier}, "second", True,
                    "eligible_read", 2, {"text": identifier},
                    {"doc_id": {"from_tool": kind, "from_field": "id"}})),
        ((kind, "read"),), f"task-{kind}-{label}")


def library(two_paths=False):
    train = [trace("search", "alpha", "A"), trace("search", "beta", "B")]
    heldout = [trace("search", "gamma", "C")]
    if two_paths:
        train += [trace("lookup", "delta", "D"), trace("lookup", "epsilon", "E")]
        heldout += [trace("lookup", "zeta", "F")]
    return build_read_motif_library(train, heldout, CONTRACTS)


class MotifControllerTests(unittest.TestCase):
    def test_completed_evidence_restores_only_for_same_current_snapshot(self):
        compiled = library()
        current = ["v1"]
        calls = []
        def verify_current():
            if current[0] != "v1":
                raise ValueError("source changed")
        def new_controller():
            def execute(tool, params):
                calls.append((tool, dict(params)))
                return {"id": "G"} if tool == "search" else {"text": "G"}
            return MotifController(
                compiled, contracts=CONTRACTS, execute_tool=execute,
                verify_current=verify_current,
                is_read_only=lambda _: True)
        first = new_controller()
        kwargs = {"required_output": "read", "bindings": {"search": {"query": "new"}},
                  "input_version": "v1"}
        self.assertEqual(first.execute_goal(**kwargs).status, "completed")
        self.assertEqual(len(calls), 2)
        saved = json.loads(json.dumps(first.export_evidence_snapshot()))
        restored = new_controller()
        self.assertEqual(restored.restore_evidence_snapshot(
            saved, current_input_version="v1"), 2)
        self.assertEqual(restored.execute_goal(**kwargs).status, "completed")
        self.assertEqual(len(calls), 2)
        changed = json.loads(json.dumps(saved))
        changed["records"][0]["value"] = {"id": "forged"}
        with self.assertRaisesRegex(ValueError, "stale or invalid"):
            new_controller().restore_evidence_snapshot(
                changed, current_input_version="v1")
        with self.assertRaisesRegex(ValueError, "stale or invalid"):
            new_controller().restore_evidence_snapshot(
                saved, current_input_version="v2")
        current[0] = "v2"
        with self.assertRaisesRegex(ValueError, "source changed"):
            new_controller().restore_evidence_snapshot(
                saved, current_input_version="v1")

    def test_direct_gap_and_ambiguous_choice_replay_after_restart(self):
        def new_controller(compiled):
            return MotifController(
                compiled, contracts=CONTRACTS,
                execute_tool=lambda tool, _params: ({"id": "G"} if tool != "read"
                                                   else {"text": "G"}),
                verify_current=lambda: None, is_read_only=lambda _: True)

        one = library()
        gap_owner = new_controller(one)
        gap = gap_owner.execute_goal(required_output="read", bindings={}, input_version="v")
        self.assertEqual(gap.status, "needs_mediation")
        saved_gap = json.loads(json.dumps(gap_owner.export_replay_checkpoint()))
        recovered = new_controller(one)
        repeated = recovered.replay_checkpoint(
            saved_gap, current_input_version="v")
        self.assertEqual(repeated.handoff.to_dict(), gap.handoff.to_dict())
        finished = recovered.resume_slots(SemanticResolution(
            resolution_type="slot_fill", slot_values={"search": {"query": "new"}},
            metadata={"handoff_signature": sig(repeated.handoff.to_dict())}))
        self.assertEqual(finished.status, "completed")

        two = library(two_paths=True)
        choice_owner = new_controller(two)
        choice = choice_owner.execute_goal(required_output="read", bindings={}, input_version="v")
        self.assertEqual(choice.status, "needs_motif_choice")
        saved_choice = json.loads(json.dumps(choice_owner.export_replay_checkpoint()))
        recovered_choice = new_controller(two)
        repeated_choice = recovered_choice.replay_checkpoint(
            saved_choice, current_input_version="v")
        self.assertEqual(repeated_choice.handoff.to_dict(), choice.handoff.to_dict())
        chosen = next(row for row in two["artifacts"] if row["tools"][0] == "search")
        next_gap = recovered_choice.resume_selection(SemanticResolution(
            resolution_type="motif_choice", action={"motif_id": chosen["motif_id"]},
            metadata={"handoff_signature": sig(repeated_choice.handoff.to_dict())}))
        self.assertEqual(next_gap.status, "needs_mediation")

    def test_training_to_match_to_execution_without_semantic_call(self):
        compiled = library()
        self.assertEqual(len(compiled["artifacts"]), 1)
        self.assertEqual(compiled["artifacts"][0]["dag"]["parameter_edges"],
                         [["search", "read"]])
        calls = []
        controller = MotifController(
            compiled, contracts=CONTRACTS,
            execute_tool=lambda tool, params: (
                calls.append((tool, dict(params))) or
                ({"id": "G"} if tool == "search" else {"text": "G"})),
            verify_current=lambda: None, is_read_only=lambda _: True)
        result = controller.execute_goal(
            required_output="read", bindings={"search": {"query": "new"}},
            input_version="snapshot-1")
        self.assertEqual(result.status, "completed")
        self.assertEqual(calls, [("search", {"query": "new"}),
                                 ("read", {"doc_id": "G"})])
        controller.execute_goal(required_output="read",
                                bindings={"search": {"query": "new"}},
                                input_version="snapshot-1")
        self.assertEqual(len(calls), 2)
        controller.execute_goal(required_output="read",
                                bindings={"search": {"query": "new"}},
                                input_version="snapshot-2")
        self.assertEqual(len(calls), 4)

    def test_node_versions_reuse_only_unaffected_dependencies(self):
        calls = []
        controller = MotifController(
            library(), contracts=CONTRACTS,
            execute_tool=lambda tool, params: (
                calls.append(tool) or ({"id": "G"} if tool == "search"
                                       else {"text": "G"})),
            verify_current=lambda: None, is_read_only=lambda _: True)
        common = {"required_output": "read",
                  "bindings": {"search": {"query": "same"}}}
        controller.execute_goal(input_version="snapshot-1",
                                node_versions={"search": "source-1",
                                               "read": "reader-1"}, **common)
        controller.execute_goal(input_version="snapshot-2",
                                node_versions={"search": "source-1",
                                               "read": "reader-2"}, **common)
        self.assertEqual(calls, ["search", "read", "read"])
        controller.execute_goal(input_version="snapshot-3",
                                node_versions={"search": "source-2",
                                               "read": "reader-2"}, **common)
        self.assertEqual(calls, ["search", "read", "read", "search", "read"])

    def test_ambiguous_match_and_missing_slot_resume_are_bounded(self):
        compiled = library(two_paths=True)
        self.assertEqual(len(compiled["artifacts"]), 2)
        calls = []
        controller = MotifController(
            compiled, contracts=CONTRACTS,
            execute_tool=lambda tool, params: (
                calls.append(tool) or ({"id": "G"} if tool != "read" else {"text": "G"})),
            verify_current=lambda: None, is_read_only=lambda _: True)
        match = controller.execute_goal(required_output="read", bindings={},
                                        input_version="snapshot-1")
        self.assertEqual(match.status, "needs_motif_choice")
        self.assertEqual(calls, [])
        chosen = next(row for row in compiled["artifacts"] if row["tools"][0] == "search")
        with self.assertRaisesRegex(ValueError, "outside"):
            controller.resume_selection(SemanticResolution(
                resolution_type="motif_choice", action={"motif_id": "invented"},
                metadata={"handoff_signature": sig(match.handoff.to_dict())}))
        gap = controller.resume_selection(SemanticResolution(
            resolution_type="motif_choice", action={"motif_id": chosen["motif_id"]},
            metadata={"handoff_signature": sig(match.handoff.to_dict())}))
        self.assertEqual(gap.status, "needs_mediation")
        self.assertEqual(calls, [])
        done = controller.resume_slots(SemanticResolution(
            resolution_type="slot_fill", slot_values={"search": {"query": "new"}},
            metadata={"handoff_signature": sig(gap.handoff.to_dict())}))
        self.assertEqual(done.status, "completed")
        self.assertEqual(calls, ["search", "read"])

    def test_unknown_goal_handoffs_without_running_tools(self):
        calls = []
        controller = MotifController(
            library(), contracts=CONTRACTS,
            execute_tool=lambda *args: calls.append(args),
            verify_current=lambda: None, is_read_only=lambda _: True)
        result = controller.execute_goal(required_output="publish",
                                         bindings={}, input_version="v")
        self.assertEqual(result.status, "no_motif")
        self.assertEqual(result.handoff.allowed_reentry["mode"], "none")
        self.assertFalse(calls)

    def test_repeated_failure_only_proposes_a_guard(self):
        controller = MotifController(
            library(), contracts=CONTRACTS,
            execute_tool=lambda tool, _params: (
                {"id": "G"} if tool == "search" else
                (_ for _ in ()).throw(RuntimeError("private failure"))),
            verify_current=lambda: None, is_read_only=lambda _: True)
        motif_id = next(iter(controller.artifacts))
        for _ in range(2):
            result = controller.execute_goal(
                required_output="read",
                bindings={"search": {"query": "same"}}, input_version="v")
            self.assertEqual(result.status, "blocked")
        proposals = controller.failure_guard_proposals(motif_id)
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["status"], "quarantined_guard_proposal")
        self.assertNotIn("private failure", str(proposals))

    def test_semantic_port_chooses_motif_then_only_missing_slot(self):
        calls = []
        controller = MotifController(
            library(two_paths=True), contracts=CONTRACTS,
            execute_tool=lambda tool, params: (
                calls.append((tool, dict(params))) or
                ({"id": "G"} if tool != "read" else {"text": "G"})),
            verify_current=lambda: None, is_read_only=lambda _: True)
        choice = controller.execute_goal(required_output="read", bindings={},
                                         input_version="v")
        chosen = next(row for row in controller.artifacts.values()
                      if row["tools"][0] == "search")
        gap, usage, _ = resolve_and_resume_motif_choice(
            controller, choice, call_semantic=lambda _prompt: (
                json.dumps({"motif_id": chosen["motif_id"]}), {"model_requests": 1}))
        self.assertEqual(gap.status, "needs_mediation")
        done, slot_usage, _ = resolve_and_resume_controller_slots(
            controller, choices={"search": {"query": ["new"]}},
            call_semantic=lambda _prompt: (
                '{"slot_values":{"search":{"query":"new"}}}',
                {"model_requests": 1}))
        self.assertEqual(done.status, "completed")
        self.assertEqual((usage["model_requests"], slot_usage["model_requests"]), (1, 1))
        self.assertEqual(calls, [("search", {"query": "new"}),
                                 ("read", {"doc_id": "G"})])

    def test_verified_repeat_expands_only_source_candidates(self):
        contracts = {"search": ToolContract(("query",), True, ("ids",)),
                     "read": ToolContract(("doc_id",), True)}

        def repeated(label, ids, selected=None):
            selected = ids if selected is None else selected
            rows = [ToolRecord("search", {"query": label}, "source", True,
                               "eligible_read", 1, {"ids": ids})]
            rows.extend(ToolRecord(
                "read", {"doc_id": identifier}, f"read-{index}", True,
                "eligible_read", index + 2, {"text": identifier},
                {"doc_id": {"from_tool": "search", "from_field": "ids"}})
                for index, identifier in enumerate(selected))
            return DshTrace(label, tuple(rows),
                            (tuple(["search"] + ["read"] * len(selected)),),
                            f"task-{label}")

        compiled = build_read_motif_library(
            [repeated("a", ["A", "B"]), repeated("b", ["C", "D"])],
            [repeated("c", ["E", "F", "G"])], contracts)
        self.assertEqual(len(compiled["artifacts"]), 1)
        self.assertEqual(compiled["artifacts"][0]["tools"], ["search", "read+"])
        calls = []
        controller = MotifController(
            compiled, contracts=contracts,
            execute_tool=lambda tool, params: (
                calls.append((tool, dict(params))) or
                ({"ids": ["X", "Y"]} if tool == "search" else {"text": params["doc_id"]})),
            verify_current=lambda: None, is_read_only=lambda _: True)
        done = controller.execute_goal(
            required_output="read", bindings={"search": {"query": "new"}},
            input_version="v")
        self.assertEqual(done.status, "completed")
        self.assertEqual(calls, [("search", {"query": "new"}),
                                 ("read", {"doc_id": "X"}),
                                 ("read", {"doc_id": "Y"})])
        self.assertEqual(done.run.outputs["read+"],
                         [{"text": "X"}, {"text": "Y"}])

        calls.clear()
        blocked = controller.execute_goal(
            required_output="read",
            bindings={"search": {"query": "new"},
                      "read+": {"doc_id": ["X", "invented"]}},
            input_version="v")
        self.assertEqual(blocked.status, "blocked")
        self.assertEqual(calls, [])

    def test_verified_subset_handoffs_then_rechecks_source_candidates(self):
        contracts = {"search": ToolContract(("query",), True, ("ids",)),
                     "read": ToolContract(("doc_id",), True)}

        def repeated(label, ids, selected):
            rows = [ToolRecord("search", {"query": label}, "source", True,
                               "eligible_read", 1, {"ids": ids})]
            rows.extend(ToolRecord(
                "read", {"doc_id": identifier}, f"read-{index}", True,
                "eligible_read", index + 2, {"text": identifier},
                {"doc_id": {"from_tool": "search", "from_field": "ids"}})
                for index, identifier in enumerate(selected))
            return DshTrace(label, tuple(rows),
                            (tuple(["search"] + ["read"] * len(selected)),),
                            f"task-{label}")

        compiled = build_read_motif_library(
            [repeated("a", ["A", "B", "C"], ["A", "C"]),
             repeated("b", ["D", "E", "F"], ["D", "F"])],
            [repeated("c", ["G", "H", "I"], ["G", "I"])], contracts)
        self.assertEqual(compiled["artifacts"][0]["selection_evidence"][0]["policy"],
                         "bounded_subset")
        calls = []
        controller = MotifController(
            compiled, contracts=contracts,
            execute_tool=lambda tool, params: (
                calls.append((tool, dict(params))) or
                ({"ids": ["X", "Y", "Z"]} if tool == "search"
                 else {"text": params["doc_id"]})),
            verify_current=lambda: None, is_read_only=lambda _: True)
        gap = controller.execute_goal(
            required_output="read", bindings={"search": {"query": "new"}},
            input_version="v")
        self.assertEqual(gap.status, "needs_mediation")
        self.assertEqual(gap.handoff.available_state["candidate_values"],
                         {"read+": {"doc_id": ["X", "Y", "Z"]}})
        self.assertEqual(calls, [("search", {"query": "new"})])
        with self.assertRaisesRegex(SemanticValidationError, "unauthorized subset"):
            resolve_and_resume_controller_slots(
                controller, call_semantic=lambda _prompt: (
                    '{"slot_values":{"read+":{"doc_id":["X","invented"]}}}',
                    {"model_requests": 1}))
        self.assertEqual(calls, [("search", {"query": "new"})])
        done, _, _ = resolve_and_resume_controller_slots(
            controller, call_semantic=lambda _prompt: (
                '{"slot_values":{"read+":{"doc_id":["X","Z"]}}}',
                {"model_requests": 1}))
        self.assertEqual(done.status, "completed")
        self.assertEqual(calls[1:], [("read", {"doc_id": "X"}),
                                     ("read", {"doc_id": "Z"})])


if __name__ == "__main__":
    unittest.main()
