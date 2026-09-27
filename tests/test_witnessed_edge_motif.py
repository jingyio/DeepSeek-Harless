"""A real dependency can survive interleaving but not a failed barrier."""

from __future__ import annotations

import unittest
import hashlib
import json

from src.adapters.dsh_trajectory import DshTrace, ToolContract, ToolRecord
from src.motif_core.offline.edge_compiler import (
    certify_witnessed_edge_motif, compile_witnessed_edge_motif,
    count_safe_edge_witnesses,
)
from src.motif_core.handoff import SemanticResolution
from src.motif_core.read_executor import resume_read_motif, run_read_motif


CONTRACTS = {
    "pin": ToolContract(("path",), True, ("source_id",)),
    "inspect": ToolContract(("source_id",), True, ("dataset_id",)),
    "other": ToolContract(("query",), True),
}
CANDIDATE = {"status": "candidate_only", "from_tool": "pin",
             "from_field": "source_id", "to_tool": "inspect",
             "to_param": "source_id", "source_trace_ids": ["A", "B"]}


def trace(label: str, *, blocked: bool = False, unrelated_failure: bool = False,
          optional: bool = False) -> DshTrace:
    source_id = f"source-{label}"
    rows = (
        ToolRecord("pin", {"path": f"{label}.csv"}, "digest", True,
                   "eligible_read", 1, {"source_id": source_id}),
        ToolRecord("other", {"query": source_id if blocked else label}, "digest",
                   not (blocked or unrelated_failure),
                   "eligible_read" if not (blocked or unrelated_failure)
                   else "missing_or_failed_result", 2, {}),
        ToolRecord("inspect", {"source_id": source_id, **({"records_path": "rows"}
                                                      if optional else {})},
                   "digest", True, "eligible_read", 3,
                   {"dataset_id": f"dataset-{label}"},
                   {"source_id": {"from_tool": "pin", "from_field": "source_id"}}),
    )
    return DshTrace(label, rows, (), f"task-{label}")


class WitnessedEdgeMotifTests(unittest.TestCase):
    def test_independent_object_reference_compiles_with_distinct_version_relation(self):
        contracts = {
            "change": ToolContract(("event_id",), True,
                                   ("previous_experiment_id", "event_version")),
            "pin": ToolContract(("object_id",), True,
                                ("source_id", "version_sha256")),
        }
        candidate = {"status": "candidate_only", "from_tool": "change",
                     "from_field": "previous_experiment_id", "to_tool": "pin",
                     "to_param": "object_id", "version_relation": "object_lookup",
                     "source_trace_ids": ["A", "B"]}

        def make(label):
            object_id = f"wps:case_{label.lower()}:previous"
            return DshTrace(label, (
                ToolRecord("change", {"event_id": f"event:case_{label.lower()}:w39"},
                           "digest", True, "eligible_read", 1,
                           {"previous_experiment_id": object_id,
                            "event_version": f"event-version-{label}"}),
                ToolRecord("pin", {"object_id": object_id}, "digest", True,
                           "eligible_read", 2,
                           {"source_id": f"source-{label}",
                            "version_sha256": f"object-version-{label}"},
                           {"object_id": {"from_tool": "change",
                                          "from_field": "previous_experiment_id"}}),
            ), (), f"decision-{label}")

        artifact = certify_witnessed_edge_motif(
            compile_witnessed_edge_motif(candidate, [make("A"), make("B")], contracts),
            make("C"), contracts)
        self.assertEqual(artifact["transfer_evidence"][0]["version_relation"],
                         "object_lookup")
        calls = []

        def execute(name, arguments):
            calls.append((name, dict(arguments)))
            return ({"previous_experiment_id": "wps:case_d:previous",
                     "event_version": "event-version-D"} if name == "change"
                    else {"source_id": "source-D", "version_sha256": "object-version-D"})

        result = run_read_motif(artifact, contracts=contracts,
                                bindings={"change": {"event_id": "event:case_d:w39"}},
                                input_version="task-D", execute_tool=execute,
                                verify_current=lambda: None, is_read_only=lambda _: True,
                                node_versions={"change": "event-version-D",
                                               "pin": "object-version-D"})
        self.assertEqual(result.status, "completed")
        self.assertEqual(calls[1], ("pin", {"object_id": "wps:case_d:previous"}))

    def test_interleaved_real_edge_compiles_certifies_and_executes(self):
        self.assertEqual(count_safe_edge_witnesses(CANDIDATE, trace("A"), CONTRACTS), 1)
        compiled = compile_witnessed_edge_motif(CANDIDATE, [trace("A"), trace("B")], CONTRACTS)
        self.assertEqual(compiled["mining_basis"], "witnessed_parameter_edge")
        artifact = certify_witnessed_edge_motif(compiled, trace("C"), CONTRACTS)
        calls = []

        def execute(name, arguments):
            calls.append((name, dict(arguments)))
            return ({"source_id": "source-D"} if name == "pin"
                    else {"dataset_id": "dataset-D"})

        result = run_read_motif(
            artifact, contracts=CONTRACTS, bindings={"pin": {"path": "D.csv"}},
            input_version="frozen-D", execute_tool=execute,
            verify_current=lambda: None, is_read_only=lambda _: True)
        self.assertEqual(result.status, "completed")
        self.assertEqual(calls, [("pin", {"path": "D.csv"}),
                                 ("inspect", {"source_id": "source-D"})])

    def test_unrelated_failed_read_does_not_erase_exact_handle_flow(self):
        self.assertEqual(count_safe_edge_witnesses(
            CANDIDATE, trace("A", unrelated_failure=True), CONTRACTS), 1)

    def test_barrier_or_optional_argument_blocks_transfer(self):
        self.assertEqual(count_safe_edge_witnesses(
            CANDIDATE, trace("B", blocked=True), CONTRACTS), 0)
        with self.assertRaisesRegex(ValueError, "safe exact-argument"):
            compile_witnessed_edge_motif(CANDIDATE, [trace("A"), trace("B", blocked=True)],
                                         CONTRACTS)
        compiled = compile_witnessed_edge_motif(CANDIDATE, [trace("A"), trace("B")], CONTRACTS)
        with self.assertRaisesRegex(ValueError, "safe exact-argument"):
            certify_witnessed_edge_motif(compiled, trace("C", optional=True), CONTRACTS)

    def test_declared_record_path_default_and_semantic_override(self):
        contracts = {**CONTRACTS,
                     "inspect": ToolContract(("source_id",), True, ("dataset_id",),
                                             default_params=(("records_path", ""),))}
        self.assertEqual(count_safe_edge_witnesses(
            CANDIDATE, trace("B", optional=True), contracts), 1)
        restricted = {**contracts,
                      "inspect": ToolContract(("source_id",), True, ("dataset_id",),
                                              default_params=(("records_path", ""),),
                                              witness_default_only=("records_path",))}
        self.assertEqual(count_safe_edge_witnesses(
            CANDIDATE, trace("B", optional=True), restricted), 0)
        compiled = compile_witnessed_edge_motif(
            CANDIDATE, [trace("A"), trace("B", optional=True)], contracts)
        artifact = certify_witnessed_edge_motif(compiled, trace("C"), contracts)
        calls = []

        def execute(name, arguments):
            calls.append((name, dict(arguments)))
            return ({"source_id": "source-D"} if name == "pin"
                    else {"dataset_id": "dataset-D"})

        common = dict(artifact=artifact, contracts=contracts, input_version="D",
                      execute_tool=execute, verify_current=lambda: None,
                      is_read_only=lambda _: True)
        root = run_read_motif(bindings={"pin": {"path": "D.json"}}, **common)
        self.assertEqual(root.status, "completed")
        self.assertEqual(calls[-1][1]["records_path"], "")
        calls.clear()
        nested = run_read_motif(bindings={"pin": {"path": "D.json"},
                                          "inspect": {"records_path": "rows"}}, **common)
        self.assertEqual(nested.status, "completed")
        self.assertEqual(calls[-1][1]["records_path"], "rows")
        invalid = run_read_motif(bindings={"pin": {"path": "D.json"},
                                           "inspect": {"records_path": []}}, **common)
        self.assertEqual(invalid.status, "blocked")

    def test_structured_statistic_slots_allow_empty_group_but_reject_empty_measures(self):
        contracts = {
            "inspect": ToolContract(("source_id",), True, ("dataset_id",)),
            "aggregate": ToolContract(("dataset_id", "group_by", "measures"), True,
                                      ("result_id",), parameter_shapes=(
                                          ("group_by", "string_list_allow_empty"),
                                          ("measures", "measure_list"))),
        }
        candidate = {"status": "candidate_only", "from_tool": "inspect",
                     "from_field": "dataset_id", "to_tool": "aggregate",
                     "to_param": "dataset_id", "source_trace_ids": ["A", "B"]}

        def make(label):
            data_id = f"dataset-{label}"
            rows = (
                ToolRecord("inspect", {"source_id": f"source-{label}"}, "digest", True,
                           "eligible_read", 1, {"dataset_id": data_id}),
                ToolRecord("aggregate", {"dataset_id": data_id, "group_by": [],
                                         "measures": [{"name": "n", "op": "count"}]},
                           "digest", True, "eligible_read", 2, {"result_id": f"result-{label}"},
                           {"dataset_id": {"from_tool": "inspect", "from_field": "dataset_id"}}),
            )
            return DshTrace(label, rows, (), f"task-{label}")

        artifact = certify_witnessed_edge_motif(
            compile_witnessed_edge_motif(candidate, [make("A"), make("B")], contracts),
            make("C"), contracts)
        calls = []

        def execute(name, arguments):
            calls.append((name, arguments))
            return ({"dataset_id": "dataset-D"} if name == "inspect"
                    else {"result_id": "result-D"})

        common = dict(artifact=artifact, contracts=contracts, input_version="D",
                      execute_tool=execute, verify_current=lambda: None,
                      is_read_only=lambda _: True)
        good = run_read_motif(bindings={"inspect": {"source_id": "source-D"},
                                       "aggregate": {"group_by": [],
                                                     "measures": [{"name": "n", "op": "count"}]}},
                              **common)
        self.assertEqual(good.status, "completed")
        self.assertEqual(calls[-1][1]["group_by"], [])
        calls.clear()
        paused = run_read_motif(bindings={"inspect": {"source_id": "source-D"}}, **common)
        self.assertEqual(paused.status, "needs_mediation")
        signature = hashlib.sha256(json.dumps(paused.handoff.to_dict(), sort_keys=True,
                                              ensure_ascii=False,
                                              separators=(",", ":")).encode()).hexdigest()
        resumed = resume_read_motif(
            artifact, paused, SemanticResolution(
                resolution_type="slot_fill", slot_values={"aggregate": {
                    "group_by": [], "measures": [{"name": "n", "op": "count"}]}},
                metadata={"handoff_signature": signature}),
            contracts=contracts, execute_tool=execute, verify_current=lambda: None,
            is_read_only=lambda _: True)
        self.assertEqual(resumed.status, "completed")
        calls.clear()
        bad = run_read_motif(bindings={"inspect": {"source_id": "source-E"},
                                      "aggregate": {"group_by": [], "measures": []}}, **common)
        self.assertEqual(bad.status, "blocked")
        self.assertEqual([name for name, _ in calls], ["inspect"])


if __name__ == "__main__":
    unittest.main()
