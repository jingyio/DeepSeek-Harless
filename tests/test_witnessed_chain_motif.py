"""Three-node Motifs require a connected invocation, not just two edges."""

from __future__ import annotations

import unittest
import hashlib
import json

from src.adapters.dsh_trajectory import DshTrace, ToolContract, ToolRecord
from src.adapters.motif_read_semantic import resolve_and_resume_controller_slots
from src.motif_core.controller import MotifController
from src.motif_core.offline.chain_compiler import (
    certify_witnessed_chain_motif, compile_witnessed_chain_motif,
)
from src.motif_core.offline.library_builder import library_from_certified
from src.motif_core.handoff import SemanticResolution
from src.motif_core.read_executor import resume_read_motif, run_read_motif
from src.semantic_inputs import SemanticInputRequired


CONTRACTS = {
    "pin": ToolContract(("path",), True, ("source_id",)),
    "inspect": ToolContract(("source_id",), True, ("dataset_id",),
                            default_params=(("records_path", ""),)),
    "aggregate": ToolContract(("dataset_id", "group_by", "measures"), True,
                              ("result_id",), parameter_shapes=(
                                  ("group_by", "string_list_allow_empty"),
                                  ("measures", "measure_list"))),
    "other": ToolContract(("query",), True),
}
FIRST = {"status": "candidate_only", "from_tool": "pin", "from_field": "source_id",
         "to_tool": "inspect", "to_param": "source_id", "source_trace_ids": ["A", "B"]}
SECOND = {"status": "candidate_only", "from_tool": "inspect", "from_field": "dataset_id",
          "to_tool": "aggregate", "to_param": "dataset_id",
          "source_trace_ids": ["A", "B"]}


def trace(label: str, *, disconnected: bool = False) -> DshTrace:
    source_id, dataset_id = f"source-{label}", f"dataset-{label}"
    common = (
        ToolRecord("pin", {"path": f"{label}.json"}, "digest", True,
                   "eligible_read", 1, {"source_id": source_id}),
        ToolRecord("other", {"query": label}, "digest", True,
                   "eligible_read", 2, {}),
        ToolRecord("inspect", {"source_id": source_id, "records_path": "rows"},
                   "digest", True, "eligible_read", 3, {"dataset_id": dataset_id},
                   {"source_id": {"from_tool": "pin", "from_field": "source_id"}}),
    )
    if disconnected:
        extra = (ToolRecord("inspect", {"source_id": "unrelated"}, "digest", True,
                            "eligible_read", 4, {"dataset_id": f"other-{label}"}),)
        aggregate_dataset = f"other-{label}"
    else:
        extra = (ToolRecord("other", {"query": "other"}, "digest", True,
                            "eligible_read", 4, {}),)
        aggregate_dataset = dataset_id
    last = (ToolRecord("aggregate", {"dataset_id": aggregate_dataset,
                                     "group_by": [],
                                     "measures": [{"name": "n", "op": "count"}]},
                       "digest", True, "eligible_read", 5,
                       {"result_id": f"result-{label}"},
                       {"dataset_id": {"from_tool": "inspect",
                                       "from_field": "dataset_id"}}),)
    return DshTrace(label, common + extra + last, (), f"task-{label}")


class WitnessedChainMotifTests(unittest.TestCase):
    def test_controller_owns_record_array_handoff_and_reentry(self):
        artifact = certify_witnessed_chain_motif(
            compile_witnessed_chain_motif(FIRST, SECOND,
                                          [trace("A"), trace("B")], CONTRACTS),
            trace("C"), CONTRACTS)
        calls = []

        def execute(name, arguments):
            calls.append(name)
            if name == "pin":
                return {"source_id": "source-D"}
            if name == "inspect":
                if not arguments["records_path"]:
                    raise SemanticInputRequired("records_path", ("rows", "groups"))
                return {"dataset_id": "dataset-D"}
            return {"result_id": "result-D"}

        controller = MotifController(
            library_from_certified([artifact]), contracts=CONTRACTS,
            execute_tool=execute, verify_current=lambda: None,
            is_read_only=lambda _: True)
        gap = controller.execute_goal(
            required_output="aggregate",
            bindings={"pin": {"path": "D.json"},
                      "aggregate": {"group_by": [],
                                    "measures": [{"name": "n", "op": "count"}]}},
            input_version="frozen-D")
        self.assertEqual(gap.status, "needs_mediation")
        done, metrics, _ = resolve_and_resume_controller_slots(
            controller, intent="Count per-run records.",
            call_semantic=lambda _prompt: (
                '{"slot_values":{"inspect":{"records_path":"rows"}}}',
                {"model_requests": 1}))
        self.assertEqual(done.status, "completed")
        self.assertEqual(metrics["model_requests"], 1)
        self.assertEqual(calls, ["pin", "inspect", "inspect", "aggregate"])
        followup = controller.execute_goal(
            required_output="aggregate",
            bindings={"pin": {"path": "D.json"},
                      "inspect": {"records_path": "rows"},
                      "aggregate": {"group_by": [],
                                    "measures": [{"name": "other_count", "op": "count"}]}},
            input_version="frozen-D")
        self.assertEqual(followup.status, "completed")
        self.assertEqual(calls, ["pin", "inspect", "inspect", "aggregate",
                                 "aggregate"])
        with self.assertRaisesRegex(ValueError, "no current parameter gap"):
            resolve_and_resume_controller_slots(
                controller, call_semantic=lambda _prompt: ("{}", {}))

    def test_ambiguous_record_array_handoff_resumes_same_chain(self):
        artifact = certify_witnessed_chain_motif(
            compile_witnessed_chain_motif(FIRST, SECOND,
                                          [trace("A"), trace("B")], CONTRACTS),
            trace("C"), CONTRACTS)
        calls = []

        def execute(name, arguments):
            calls.append((name, dict(arguments)))
            if name == "pin":
                return {"source_id": "source-D"}
            if name == "inspect":
                if not arguments["records_path"]:
                    raise SemanticInputRequired("records_path", ("rows", "groups"))
                return {"dataset_id": "dataset-D"}
            return {"result_id": "result-D"}

        bindings = {"pin": {"path": "D.json"},
                    "aggregate": {"group_by": [],
                                  "measures": [{"name": "n", "op": "count"}]}}
        prior = run_read_motif(
            artifact, contracts=CONTRACTS, bindings=bindings,
            input_version="frozen-D", execute_tool=execute,
            verify_current=lambda: None, is_read_only=lambda _: True)
        self.assertEqual(prior.status, "needs_mediation")
        self.assertEqual(prior.handoff.missing_params, {"inspect": ["records_path"]})
        self.assertEqual(prior.handoff.available_state["candidate_values"],
                         {"inspect": {"records_path": ["rows", "groups"]}})
        self.assertEqual(prior.handoff.available_state["candidate_value_modes"],
                         {"inspect": {"records_path": "one_of"}})
        handoff_signature = hashlib.sha256(json.dumps(
            prior.handoff.to_dict(), sort_keys=True, ensure_ascii=False,
            separators=(",", ":")).encode()).hexdigest()
        metadata = {"handoff_signature": handoff_signature}
        with self.assertRaisesRegex(ValueError, "unauthorized slots"):
            resume_read_motif(
                artifact, prior,
                SemanticResolution("slot_fill", {"inspect": {"records_path": "other"}},
                                   metadata=metadata),
                contracts=CONTRACTS, execute_tool=execute,
                verify_current=lambda: None, is_read_only=lambda _: True)
        with self.assertRaisesRegex(ValueError, "source version changed"):
            resume_read_motif(
                artifact, prior,
                SemanticResolution("slot_fill", {"inspect": {"records_path": "rows"}},
                                   metadata=metadata),
                contracts=CONTRACTS, execute_tool=execute,
                verify_current=lambda: (_ for _ in ()).throw(
                    ValueError("source version changed")),
                is_read_only=lambda _: True)
        self.assertEqual([name for name, _ in calls], ["pin", "inspect"])
        result = resume_read_motif(
            artifact, prior,
            SemanticResolution("slot_fill", {"inspect": {"records_path": "rows"}},
                               metadata=metadata),
            contracts=CONTRACTS, execute_tool=execute,
            verify_current=lambda: None, is_read_only=lambda _: True)
        self.assertEqual(result.status, "completed")
        self.assertEqual([name for name, _ in calls],
                         ["pin", "inspect", "inspect", "aggregate"])
        self.assertEqual(calls[-2][1]["records_path"], "rows")

    def test_connected_interleaved_chain_executes_with_semantic_slots(self):
        compiled = compile_witnessed_chain_motif(FIRST, SECOND,
                                                 [trace("A"), trace("B")], CONTRACTS)
        artifact = certify_witnessed_chain_motif(compiled, trace("C"), CONTRACTS)
        calls = []

        def execute(name, arguments):
            calls.append((name, dict(arguments)))
            return ({"source_id": "source-D"} if name == "pin" else
                    {"dataset_id": "dataset-D"} if name == "inspect" else
                    {"result_id": "result-D"})

        result = run_read_motif(
            artifact, contracts=CONTRACTS,
            bindings={"pin": {"path": "D.json"},
                      "inspect": {"records_path": "rows"},
                      "aggregate": {"group_by": [],
                                    "measures": [{"name": "n", "op": "count"}]}},
            input_version="frozen-D", execute_tool=execute,
            verify_current=lambda: None, is_read_only=lambda _: True)
        self.assertEqual(result.status, "completed")
        self.assertEqual([name for name, _ in calls], ["pin", "inspect", "aggregate"])
        self.assertEqual(calls[1][1], {"records_path": "rows", "source_id": "source-D"})
        self.assertEqual(calls[2][1]["dataset_id"], "dataset-D")

    def test_disconnected_middle_call_cannot_be_composed(self):
        with self.assertRaisesRegex(ValueError, "share one safe middle"):
            compile_witnessed_chain_motif(FIRST, SECOND,
                                         [trace("A"), trace("B", disconnected=True)],
                                         CONTRACTS)

    def test_source_version_change_stops_before_next_node(self):
        artifact = certify_witnessed_chain_motif(
            compile_witnessed_chain_motif(FIRST, SECOND,
                                          [trace("A"), trace("B")], CONTRACTS),
            trace("C"), CONTRACTS)
        calls = []
        changed = False

        def execute(name, _arguments):
            nonlocal changed
            calls.append(name)
            if name == "pin":
                changed = True
                return {"source_id": "source-D"}
            return {"dataset_id": "dataset-D"}

        def verify():
            if changed:
                raise ValueError("source version changed")

        result = run_read_motif(
            artifact, contracts=CONTRACTS,
            bindings={"pin": {"path": "D.json"},
                      "aggregate": {"group_by": [],
                                    "measures": [{"name": "n", "op": "count"}]}},
            input_version="frozen-D", execute_tool=execute,
            verify_current=verify, is_read_only=lambda _: True)
        self.assertEqual(result.status, "blocked")
        self.assertEqual(calls, ["pin"])


if __name__ == "__main__":
    unittest.main()
