"""A trace-derived read Motif executes, mediates gaps, and blocks failures."""

from __future__ import annotations

import hashlib
import json
import unittest
from dataclasses import replace

from src.adapters.dsh_trajectory import (
    DshTrace, ToolContract, ToolRecord, extract_dsh_trace, mine_dsh_traces,
)
from src.motif_core.handoff import SemanticResolution
from src.motif_core.offline.trace_compiler import (
    certify_read_motif, compile_read_motif,
)
from src.motif_core.offline.failure_evolution import (
    guard_matches, propose_exact_failure_guard, validate_failure_guard_replays,
    promote_failure_guard, new_guard_registry, activate_guard_version,
    rollback_guard_version, current_active_guards,
)
from src.motif_core.read_executor import resume_read_motif, run_read_motif


def event_pair(index: int, tool: str, args: dict, observation: dict) -> list[dict]:
    call_id = f"c{index}"
    return [
        {"seq": index * 2, "type": "tool/call",
         "data": {"callId": call_id, "name": tool,
                  "arguments": json.dumps(args)}},
        {"seq": index * 2 + 1, "type": "tool/result",
         "data": {"message": {"source": {"callId": call_id},
                              "content": [{"type": "tool-result", "isError": False,
                                           "content": [{"type": "text",
                                                        "text": json.dumps(observation)}]}]}}},
    ]


CONTRACTS = {
    "search": ToolContract(("query",), True, ("id",)),
    "read": ToolContract(("doc_id",), True),
}


def trace(label: str, doc_id: str, *, read_id: str | None = None,
          contracts: dict | None = None, causal: bool = True):
    events = (event_pair(1, "search", {"query": label}, {"id": doc_id})
              + event_pair(2, "read", {"doc_id": read_id or doc_id},
                           {"text": f"Document {doc_id}"}))
    extracted = extract_dsh_trace(events, contracts or CONTRACTS,
                                  trace_id=f"run-{label}", task_fingerprint=f"task-{label}")
    if not causal:
        return extracted
    records = list(extracted.records)
    records[1] = replace(records[1], parameter_sources={
        "doc_id": {"from_tool": "search", "from_field": "id"}})
    return replace(extracted, records=tuple(records))


def certified_artifact():
    first, second, holdout = trace("alpha", "A"), trace("beta", "B"), trace("gamma", "C")
    candidate = mine_dsh_traces([first, second])[0]
    compiled = compile_read_motif(candidate, [first, second], CONTRACTS)
    return certify_read_motif(compiled, holdout, CONTRACTS)


class TraceCompiledReadMotifTests(unittest.TestCase):
    def test_witnessed_list_parameter_compiles_and_executes_as_a_collection(self) -> None:
        contracts = {
            "list_sources": ToolContract(("project",), True, ("sources",)),
            "inspect_sources": ToolContract(("sources",), True,
                                            collection_params=("sources",),
                                            provenance_params=("sources",)),
        }
        def witnessed(label: str, names: list[str]):
            events = (event_pair(1, "list_sources", {"project": label},
                                 {"sources": names})
                      + event_pair(2, "inspect_sources", {"sources": names},
                                   {"count": len(names)}))
            return extract_dsh_trace(
                events, contracts, trace_id=label, task_fingerprint=label,
                provenance_by_call_id={"c2": {"sources": {
                    "from_call_id": "c1", "from_field": "sources"}}})
        train = [witnessed("alpha", ["a.md", "b.md"]),
                 witnessed("beta", ["c.md", "d.md"])]
        heldout = witnessed("gamma", ["e.md", "f.md"])
        candidate = next(row for row in mine_dsh_traces(train)
                         if row["tools"] == ["list_sources", "inspect_sources"])
        with self.assertRaisesRegex(ValueError, "replay-stable"):
            compile_read_motif(candidate, train, {
                **contracts,
                "list_sources": replace(contracts["list_sources"], replay_stable=False),
            })
        compiled = compile_read_motif(candidate, train, contracts)
        artifact = certify_read_motif(compiled, heldout, contracts)
        self.assertEqual(artifact["dependencies"]["operators"]["inspect_sources"]["bindings"],
                         [{"from_tool": "list_sources", "from_field": "sources",
                           "to_param": "sources"}])
        calls = []
        def execute(tool: str, params: dict) -> dict:
            calls.append((tool, params))
            return ({"sources": ["new.md", "other.md"]} if tool == "list_sources"
                    else {"count": len(params["sources"])})
        run = run_read_motif(
            artifact, contracts=contracts,
            bindings={"list_sources": {"project": "delta"}},
            input_version="delta-v1", execute_tool=execute,
            verify_current=lambda: None, is_read_only=lambda _tool: True)
        self.assertEqual(run.status, "completed")
        self.assertEqual(calls[-1],
                         ("inspect_sources", {"sources": ["new.md", "other.md"]}))

    def test_independent_traces_compile_and_new_task_executes(self) -> None:
        artifact = certified_artifact()
        self.assertEqual(artifact["status"], "trace_validated_read_only")
        self.assertEqual(artifact["transfer_evidence"][0]["from_field"], "id")
        calls = []

        def execute(tool: str, params: dict) -> dict:
            calls.append((tool, dict(params)))
            return {"id": "D"} if tool == "search" else {"text": "Document D"}

        result = run_read_motif(
            artifact, contracts=CONTRACTS,
            bindings={"search": {"query": "delta"}}, input_version="snapshot-delta",
            execute_tool=execute, verify_current=lambda: None,
            is_read_only=lambda _tool: True)
        self.assertEqual(result.status, "completed")
        self.assertEqual(calls, [("search", {"query": "delta"}),
                                 ("read", {"doc_id": "D"})])
        self.assertEqual(result.outputs["read"], {"text": "Document D"})

    def test_missing_entry_slot_handoffs_then_resumes_without_model_in_core(self) -> None:
        artifact = certified_artifact()
        calls = []

        def execute(tool: str, params: dict) -> dict:
            calls.append(tool)
            return {"id": "D"} if tool == "search" else {"text": "Document D"}

        common = {"contracts": CONTRACTS, "execute_tool": execute,
                  "verify_current": lambda: None, "is_read_only": lambda _tool: True}
        blocked = run_read_motif(
            artifact, bindings={}, input_version="snapshot-delta", **common)
        self.assertEqual(blocked.status, "needs_mediation")
        self.assertEqual(calls, [])
        request = blocked.handoff
        handoff_signature = hashlib.sha256(json.dumps(
            request.to_dict(), sort_keys=True, ensure_ascii=False,
            separators=(",", ":")).encode()).hexdigest()
        resolution = SemanticResolution(
            resolution_type="slot_fill", slot_values={"search": {"query": "delta"}},
            metadata={"handoff_signature": handoff_signature})
        resumed = resume_read_motif(artifact, blocked, resolution, **common)
        self.assertEqual(resumed.status, "completed")
        self.assertEqual(resumed.manager.completed_motifs[-1]["motif_id"], artifact["motif_id"])
        self.assertEqual(calls, ["search", "read"])

    def test_failure_quarantines_evidence_without_auto_revision(self) -> None:
        artifact = certified_artifact()
        def execute(tool: str, _params: dict) -> dict:
            if tool == "read":
                raise RuntimeError("private diagnostic")
            return {"id": "D"}
        result = run_read_motif(
            artifact, contracts=CONTRACTS,
            bindings={"search": {"query": "delta"}}, input_version="snapshot-delta",
            execute_tool=execute, verify_current=lambda: None,
            is_read_only=lambda _tool: True)
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.failure_witness["operator"], "read")
        self.assertEqual(result.failure_witness["error_class"], "RuntimeError")
        self.assertNotIn("private diagnostic", str(result.failure_witness))
        self.assertEqual(result.handoff.allowed_reentry["mode"], "none")

    def test_heldout_mismatch_and_duplicate_values_need_declared_source(self) -> None:
        first, second = trace("alpha", "A"), trace("beta", "B")
        candidate = mine_dsh_traces([first, second])[0]
        compiled = compile_read_motif(candidate, [first, second], CONTRACTS)
        with self.assertRaisesRegex(ValueError, "contradicts"):
            certify_read_motif(compiled, trace("gamma", "C", read_id="other"), CONTRACTS)
        ambiguous = {**CONTRACTS, "search": ToolContract(("query",), True, ("id", "alias"))}
        def amb(label: str, doc_id: str):
            events = (event_pair(1, "search", {"query": label},
                                 {"id": doc_id, "alias": doc_id})
                      + event_pair(2, "read", {"doc_id": doc_id}, {"text": doc_id}))
            extracted = extract_dsh_trace(events, ambiguous, trace_id=label,
                                          task_fingerprint=f"task-{label}")
            records = list(extracted.records)
            records[1] = replace(records[1], parameter_sources={
                "doc_id": {"from_tool": "search", "from_field": "id"}})
            return replace(extracted, records=tuple(records))
        a, b = amb("a", "A"), amb("b", "B")
        candidate = mine_dsh_traces([a, b])[0]
        compiled = compile_read_motif(candidate, [a, b], ambiguous)
        self.assertEqual(compiled["dependencies"]["operators"]["read"]["bindings"], [
            {"from_tool": "search", "from_field": "id", "to_param": "doc_id"}])

    def test_equal_values_without_causal_source_do_not_compile_transfer(self) -> None:
        first, second = trace("alpha", "A", causal=False), trace("beta", "B", causal=False)
        candidate = mine_dsh_traces([first, second])[0]
        compiled = compile_read_motif(candidate, [first, second], CONTRACTS)
        self.assertEqual(compiled["transfer_evidence"], [])

    def test_declared_collection_entry_passes_without_becoming_a_repeat(self) -> None:
        contracts = {
            "snapshot": ToolContract(("source",), True, ("sha256",)),
            "search": ToolContract(("source", "sha256", "terms"), True,
                                   collection_params=("terms",)),
        }
        def make(label: str, digest: str):
            first = ToolRecord("snapshot", {"source": label}, digest, True,
                               "eligible_read", 1, {"sha256": digest})
            second = ToolRecord("search", {"source": label, "sha256": digest,
                                            "terms": [label, "graph"]}, digest,
                                True, "eligible_read", 2, {"matches": 2},
                                {"sha256": {"from_tool": "snapshot",
                                             "from_field": "sha256"}})
            return DshTrace(label, (first, second), (("snapshot", "search"),),
                            f"task-{label}")
        a, b, c = make("a", "A"), make("b", "B"), make("c", "C")
        candidate = mine_dsh_traces([a, b])[0]
        artifact = certify_read_motif(
            compile_read_motif(candidate, [a, b], contracts), c, contracts)
        self.assertEqual(artifact["dependencies"]["operators"]["search"]["collection_params"],
                         ["terms"])
        calls = []
        result = run_read_motif(
            artifact, contracts=contracts,
            bindings={"snapshot": {"source": "d"},
                      "search": {"source": "d", "terms": ["d", "graph"]}},
            input_version="D", execute_tool=lambda tool, params: (
                calls.append((tool, params)) or
                ({"sha256": "D"} if tool == "snapshot" else {"matches": 2})),
            verify_current=lambda: None, is_read_only=lambda _tool: True)
        self.assertEqual(result.status, "completed")
        self.assertEqual(calls[-1][1]["terms"], ["d", "graph"])
        self.assertEqual(len(calls), 2)

    def test_artifact_or_contract_change_prevents_execution(self) -> None:
        artifact = certified_artifact()
        changed = {**artifact, "dependencies": {**artifact["dependencies"],
                   "required_evidence": ["read"]}}
        with self.assertRaisesRegex(ValueError, "trace-validated"):
            run_read_motif(changed, contracts=CONTRACTS,
                           bindings={"search": {"query": "delta"}},
                           input_version="v", execute_tool=lambda *_: {},
                           verify_current=lambda: None,
                           is_read_only=lambda _: True)

    def test_failed_execution_proposes_scoped_guard_but_does_not_enable_it(self) -> None:
        artifact = certified_artifact()
        common = {"contracts": CONTRACTS, "bindings": {"search": {"query": "delta"}},
                  "input_version": "snapshot-delta", "verify_current": lambda: None,
                  "is_read_only": lambda _tool: True}

        def broken(tool: str, _params: dict) -> dict:
            if tool == "read":
                raise RuntimeError("private diagnostic")
            return {"id": "D"}

        def failed_run():
            return run_read_motif(artifact, execute_tool=broken, **common)

        a, b = failed_run(), failed_run()
        with self.assertRaisesRegex(ValueError, "repeated"):
            propose_exact_failure_guard(artifact, [a.failure_witness])
        with self.assertRaisesRegex(ValueError, "independently"):
            propose_exact_failure_guard(artifact, [a.failure_witness, a.failure_witness])
        proposal = propose_exact_failure_guard(
            artifact, [a.failure_witness, b.failure_witness])
        self.assertEqual(proposal["status"], "quarantined_guard_proposal")
        self.assertNotIn("private diagnostic", str(proposal))
        c, d = failed_run(), failed_run()
        success = run_read_motif(
            artifact, contracts=CONTRACTS, bindings=common["bindings"],
            input_version="different-snapshot", execute_tool=lambda tool, _params: (
                {"id": "D"} if tool == "search" else {"text": "Document D"}),
            verify_current=lambda: None, is_read_only=lambda _tool: True)
        same_input_success = run_read_motif(
            artifact, contracts=CONTRACTS, bindings=common["bindings"],
            input_version="snapshot-delta", execute_tool=lambda tool, _params: (
                {"id": "D"} if tool == "search" else {"text": "Recovered document"}),
            verify_current=lambda: None, is_read_only=lambda _tool: True)
        with self.assertRaisesRegex(ValueError, "block a successful contrast"):
            validate_failure_guard_replays(
                proposal, artifact, failed_replay_witnesses=[c.failure_witness,
                                                             d.failure_witness],
                successful_contrasts=[same_input_success])
        validated = validate_failure_guard_replays(
            proposal, artifact, failed_replay_witnesses=[c.failure_witness,
                                                         d.failure_witness],
            successful_contrasts=[success])
        self.assertEqual(validated["status"], "replay_validated_candidate")
        self.assertFalse(guard_matches(
            validated, artifact, operator="read", binding_signature=
            a.failure_witness["binding_signature"], input_version="different-snapshot"))
        self.assertTrue(guard_matches(
            validated, artifact, operator="read", binding_signature=
            a.failure_witness["binding_signature"], input_version="snapshot-delta"))
        # The candidate is deliberately not an execution-time guard: even a
        # reproduced failure must pass a task-level quality gate first.
        self.assertEqual(failed_run().status, "blocked")
        active = promote_failure_guard(
            validated, artifact, quality_review={
                "review_id": "review-1", "reviewer_id": "researcher",
                "task_ids": ["later-quality-check"], "result": "pass"})
        seen = []
        guarded = run_read_motif(
            artifact, contracts=CONTRACTS,
            bindings=common["bindings"], input_version="snapshot-delta",
            execute_tool=lambda tool, params: (
                seen.append(tool) or ({"id": "D"} if tool == "search" else {"text": "D"})),
            verify_current=lambda: None, is_read_only=lambda _tool: True,
            active_guards=(active,))
        self.assertEqual(guarded.status, "blocked")
        self.assertEqual(guarded.handoff.reason, "active_negative_guard")
        self.assertEqual(seen, ["search"])
        changed_input = run_read_motif(
            artifact, contracts=CONTRACTS, bindings=common["bindings"],
            input_version="other-snapshot", execute_tool=lambda tool, _params: (
                {"id": "D"} if tool == "search" else {"text": "D"}),
            verify_current=lambda: None, is_read_only=lambda _tool: True,
            active_guards=(active,))
        self.assertEqual(changed_input.status, "completed")
        registry = activate_guard_version(new_guard_registry(artifact), artifact, active)
        self.assertEqual(len(current_active_guards(registry, artifact)), 1)
        rolled_back = rollback_guard_version(
            registry, artifact, guard_id=active["guard_id"],
            reviewer_id="researcher", reason="task quality regressed")
        self.assertEqual(current_active_guards(rolled_back, artifact), ())
        self.assertEqual(rolled_back["revision"], 2)


if __name__ == "__main__":
    unittest.main()
