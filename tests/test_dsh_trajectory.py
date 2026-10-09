"""DSH tool events may propose motifs; they never authorize execution alone."""

from __future__ import annotations

import json
import inspect
import hashlib
import importlib.util
import unittest
from copy import deepcopy
from pathlib import Path

from src.adapters.dsh_trajectory import (
    ToolContract, extract_dsh_trace, infer_dsh_provenance, mine_dsh_traces,
    mine_witnessed_parameter_edges,
)
from tests.test_trace_compiled_read_motif import event_pair
from src.adapters.tool_contract_loader import parse_tool_contracts
from src.motif_core.offline.trace_compiler import compile_read_motif, certify_read_motif
from src.motif_core.offline.library_builder import build_read_motif_library
from src.motif_core.read_executor import run_read_motif


def call(index: int, name: str, *, arguments: dict | str | None = None,
         failed: bool = False) -> list[dict]:
    call_id = f"c{index}"
    raw = json.dumps(arguments if arguments is not None else {"item": str(index)})
    if isinstance(arguments, str):
        raw = arguments
    return [
        {"seq": 2 * index, "type": "tool/call",
         "data": {"callId": call_id, "name": name, "arguments": raw}},
        {"seq": 2 * index + 1, "type": "tool/result",
         "data": {"message": {"source": {"callId": call_id},
                              "content": [{"type": "tool-result", "isError": failed,
                                           "content": [{"type": "text", "text": "result"}]}]}}},
    ]


CONTRACTS = {
    "search": ToolContract(("item",), True),
    "read": ToolContract(("item",), True),
    "write": ToolContract(("item",), False),
}


class DshTrajectoryTests(unittest.TestCase):
    def test_observed_gmail_anchor_can_certify_without_replaying_search(self):
        root = Path(__file__).resolve().parents[1]
        contracts = parse_tool_contracts(json.loads((
            root / "tests/fixtures/contracts/scoped-gmail-request-contracts.json").read_text(encoding="utf-8")))
        search_name = "mcp__scoped_gmail_request__search_emails"
        read_name = "mcp__scoped_gmail_request__read_email"

        def make_trace(label: str):
            message_id = label * 16
            query = f"subject:research-{label}"
            metadata = {"message_ids": [message_id], "count": 1,
                        "selected_message_id": message_id,
                        "result_digest": hashlib.sha256(json.dumps(
                            [message_id], separators=(",", ":")).encode()).hexdigest()}
            events = (event_pair(1, search_name, {"query": query}, metadata)
                      + event_pair(2, read_name, {"messageId": message_id},
                                   {"message_id": message_id,
                                    "source_version": message_id}))
            return extract_dsh_trace(
                events, contracts, trace_id=f"gmail-{label}",
                task_fingerprint=f"independent-mail-{label}",
                provenance_by_call_id=infer_dsh_provenance(events, contracts))

        training = [make_trace("a"), make_trace("b")]
        heldout = make_trace("c")
        library = build_read_motif_library(training, [heldout], contracts)
        self.assertEqual(len(library["artifacts"]), 1, library["rejected"])
        artifact = library["artifacts"][0]
        self.assertEqual(artifact["transfer_evidence"][0]["from_field"],
                         "selected_message_id")
        spec = importlib.util.spec_from_file_location(
            "online_export_test", root / "scripts/export-online-motif-manifest.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        manifest = module.export_manifest(
            library, json.loads((root / "tests/fixtures/contracts/scoped-gmail-request-contracts.json").read_text(encoding="utf-8")),
            {search_name: {"query": "subject:research-[abc]"}},
            {search_name: "selected_message_id", read_name: "source_version"})
        self.assertTrue(manifest["contracts"][search_name]["observed_anchor"])
        with self.assertRaisesRegex(ValueError, "live online tool result"):
            run_read_motif(artifact, contracts=contracts,
                           bindings={search_name: {"query": "subject:research-a"}},
                           input_version="snapshot-a",
                           execute_tool=lambda *_: self.fail("must not replay search"),
                           verify_current=lambda: None,
                           is_read_only=lambda _: True)

    def test_scoped_gmail_search_to_read_has_witnessed_message_id(self):
        contracts = parse_tool_contracts(json.loads((
            Path(__file__).resolve().parents[1] /
            "tests/fixtures/contracts/scoped-gmail-request-contracts.json").read_text(encoding="utf-8")))
        message_id = "a" * 16
        search = event_pair(1, "mcp__scoped_gmail_request__search_emails",
                            {"query": "subject:SSS"}, {"ignored": True})
        read = event_pair(2, "mcp__scoped_gmail_request__read_email",
                          {"messageId": message_id}, {"ignored": True})
        for pair, metadata in ((search, {"message_ids": [message_id],
                                        "selected_message_id": message_id,
                                        "count": 1, "result_digest": "b" * 64}),
                               (read, {"message_id": message_id,
                                       "thread_id": "c" * 16,
                                       "source_version": message_id})):
            pair[1]["data"]["message"]["content"][0]["content"][0]["text"] = (
                "SSS_STRUCTURED_METADATA_V1 " + json.dumps(metadata) + "\n"
                "<untrusted-tool-output>\nsource text\n</untrusted-tool-output>")
        events = search + read
        provenance = infer_dsh_provenance(events, contracts)
        self.assertEqual(provenance["c2"]["messageId"],
                         {"from_call_id": "c1", "from_field": "selected_message_id"})
        trace = extract_dsh_trace(events, contracts, trace_id="gmail-diagnostic",
                                  provenance_by_call_id=provenance)
        self.assertEqual(trace.segments, (("mcp__scoped_gmail_request__search_emails",
                                           "mcp__scoped_gmail_request__read_email"),))
        self.assertTrue(all(row.eligible for row in trace.records))
        two_results = deepcopy(events)
        two_results[1]["data"]["message"]["content"][0]["content"][0]["text"] = (
            "SSS_STRUCTURED_METADATA_V1 " + json.dumps({
                "message_ids": [message_id, "d" * 16], "count": 2,
                "result_digest": "e" * 64}) + "\n"
            "<untrusted-tool-output>\nsource text\n</untrusted-tool-output>")
        self.assertNotIn("c2", infer_dsh_provenance(two_results, contracts))

    def test_native_sss_frontier_provenance_can_be_compiled_only_when_witnessed(self):
        contracts = parse_tool_contracts(json.loads((
            Path(__file__).resolve().parents[1] /
            "tests/fixtures/contracts/sss-runtime-tool-contracts.json").read_text(encoding="utf-8")))
        prefix = "mcp__sss_runtime__"
        run_id, frontier_id = "a" * 32, "b" * 32
        question = "Which evidence supports this claim?"
        collected = {"run_id": run_id}
        opened = {"run_id": run_id, "frontier_id": frontier_id,
                  "point_id": "P1", "question": question,
                  "allowed_sources": ["paper.md"],
                  "handoff_signature": "c" * 64}
        open_args = {"run_id": run_id, "point_id": "P1", "question": question,
                     "source_allowlist": ["paper.md"]}
        resolve_args = {**open_args, "frontier_id": frontier_id,
                        "handoff_signature": opened["handoff_signature"],
                        "terms": ["evidence"]}
        events = (event_pair(1, prefix + "collect_sources", {}, collected)
                  + event_pair(2, prefix + "open_point", open_args, opened)
                  + event_pair(3, prefix + "resolve_point", resolve_args,
                               {"run_id": run_id, "frontier_id": frontier_id,
                                "point_id": "P1", "evidence": []}))
        sidecar = {
            "c2": {"run_id": {"from_call_id": "c1", "from_field": "run_id"}},
            "c3": {"run_id": {"from_call_id": "c1", "from_field": "run_id"},
                   **{param: {"from_call_id": "c2", "from_field": field}
                      for param, field in {
                          "frontier_id": "frontier_id", "point_id": "point_id",
                          "question": "question", "source_allowlist": "allowed_sources",
                          "handoff_signature": "handoff_signature",
                      }.items()}},
        }
        accepted = extract_dsh_trace(events, contracts, trace_id="native-sss",
                                     provenance_by_call_id=sidecar)
        self.assertEqual(accepted.segments, ((prefix + "collect_sources",
                                              prefix + "open_point",
                                              prefix + "resolve_point"),),
                         [row.reason for row in accepted.records])
        self.assertEqual(set(accepted.records[2].parameter_sources),
                         set(contracts[prefix + "resolve_point"].provenance_params))
        missing = deepcopy(sidecar)
        del missing["c3"]["frontier_id"]
        rejected = extract_dsh_trace(events, contracts, trace_id="missing-frontier",
                                     provenance_by_call_id=missing)
        self.assertEqual(rejected.records[2].reason, "missing_parameter_provenance")
        forged = deepcopy(sidecar)
        forged["c3"]["source_allowlist"]["from_field"] = "question"
        rejected = extract_dsh_trace(events, contracts, trace_id="forged-scope",
                                     provenance_by_call_id=forged)
        self.assertEqual(rejected.records[2].reason, "invalid_parameter_provenance")

        def independent(label: str):
            run = label * 32
            frontier = label.upper() * 32
            point, query = f"P-{label}", f"Question for {label}?"
            scope = [f"paper-{label}.md"]
            opened = {"run_id": run, "frontier_id": frontier,
                      "point_id": point, "question": query,
                      "allowed_sources": scope,
                      "handoff_signature": label * 64}
            events = (event_pair(1, prefix + "collect_sources", {}, {"run_id": run})
                      + event_pair(2, prefix + "open_point", {
                          "run_id": run, "point_id": point, "question": query,
                          "source_allowlist": scope}, opened)
                      + event_pair(3, prefix + "resolve_point", {
                          "run_id": run, "frontier_id": frontier,
                          "point_id": point, "question": query,
                          "source_allowlist": scope,
                          "handoff_signature": label * 64,
                          "terms": [f"term-{label}"]},
                          {"run_id": run, "frontier_id": frontier,
                           "point_id": point, "evidence": []}))
            return extract_dsh_trace(
                events, contracts, trace_id=f"sample-{label}",
                task_fingerprint=f"decision-{label}",
                provenance_by_call_id=sidecar)
        training = [independent("a"), independent("b")]
        heldout = independent("c")
        candidate = next(row for row in mine_dsh_traces(training)
                         if row["tools"] == [prefix + "collect_sources",
                                             prefix + "open_point",
                                             prefix + "resolve_point"])
        certified = certify_read_motif(
            compile_read_motif(candidate, training, contracts), heldout, contracts)
        self.assertEqual({row["to_param"] for row in certified["dependencies"][
            "operators"][prefix + "resolve_point"]["bindings"]},
            set(contracts[prefix + "resolve_point"].provenance_params))

    def test_compaction_replacement_cannot_change_tool_observation_or_provenance(self):
        source_id = "source-" + "a" * 32
        forged_id = "source-" + "b" * 32
        contracts = {
            "pin": ToolContract(("role",), True, ("source_id",)),
            "read": ToolContract(("source_id",), True,
                                 provenance_params=("source_id",)),
        }
        pin = event_pair(1, "pin", {"role": "paper"}, {"source_id": source_id})
        read = event_pair(2, "read", {"source_id": source_id}, {"text": "full paper"})
        original = pin + read

        # DSH's pruner logs a later result for the same callId and replaces
        # only the model-visible surface. A forged JSON body tests that this
        # surface event cannot become a new source-handle producer.
        replacement = deepcopy(pin[1])
        replacement["seq"] = 20
        replacement["surfaceOp"] = {"op": "replace", "startSeq": pin[1]["seq"],
                                    "endSeq": pin[1]["seq"]}
        replacement["sourceEventSeqs"] = [pin[1]["seq"]]
        replacement["data"]["message"]["content"][0]["content"][0]["text"] = json.dumps(
            {"source_id": forged_id})
        events = pin + [replacement] + read

        self.assertEqual(infer_dsh_provenance(events, contracts),
                         infer_dsh_provenance(original, contracts))
        baseline = extract_dsh_trace(
            original, contracts, trace_id="original",
            provenance_by_call_id=infer_dsh_provenance(original, contracts))
        compressed = extract_dsh_trace(
            events, contracts, trace_id="compressed",
            provenance_by_call_id=infer_dsh_provenance(events, contracts))
        self.assertEqual(compressed.segments, baseline.segments)
        self.assertEqual([row.observation_sha256 for row in compressed.records],
                         [row.observation_sha256 for row in baseline.records])
        self.assertEqual(compressed.records[1].reason, "eligible_read")

    def test_pruned_read_result_keeps_original_digest(self):
        contracts = {"read": ToolContract(("item",), True)}
        original = call(1, "read")
        replacement = deepcopy(original[1])
        replacement["seq"] = 30
        replacement["surfaceOp"] = {"op": "replace", "startSeq": original[1]["seq"],
                                    "endSeq": original[1]["seq"]}
        replacement["sourceEventSeqs"] = [original[1]["seq"]]
        replacement["data"]["message"]["content"][0]["content"][0]["text"] = (
            "truncated head [... tool result middle pruned ...] tail")
        before = extract_dsh_trace(original, contracts, trace_id="before")
        after = extract_dsh_trace(original + [replacement], contracts, trace_id="after")
        self.assertEqual(after.records[0].observation_sha256,
                         before.records[0].observation_sha256)

    def test_two_scoped_apps_only_prove_their_own_returned_handle_edges(self):
        obsidian = "source-" + "a" * 32
        zotero = "source-" + "b" * 32
        contracts = {
            "mcp__scoped_research_read__pin_scoped_source":
                ToolContract(("role",), True, ("source_id",)),
            "mcp__scoped_research_read__read_pinned_note":
                ToolContract(("source_id",), True, provenance_params=("source_id",)),
            "mcp__scoped_zotero_read__pin_scoped_zotero_source":
                ToolContract(("role",), True, ("source_id",)),
            "mcp__scoped_zotero_read__read_pinned_zotero_annotation":
                ToolContract(("source_id",), True, provenance_params=("source_id",)),
        }
        events = (
            event_pair(1, "mcp__scoped_research_read__pin_scoped_source",
                       {"role": "state"}, {"source_id": obsidian})
            + event_pair(2, "mcp__scoped_research_read__read_pinned_note",
                         {"source_id": obsidian}, {"text": "note"})
            + event_pair(3, "mcp__scoped_zotero_read__pin_scoped_zotero_source",
                         {"role": "annotation"}, {"source_id": zotero})
            + event_pair(4, "mcp__scoped_zotero_read__read_pinned_zotero_annotation",
                         {"source_id": zotero}, {"text": "annotation"})
        )
        inferred = infer_dsh_provenance(events, contracts)
        self.assertEqual(inferred["c2"]["source_id"]["from_call_id"], "c1")
        self.assertEqual(inferred["c4"]["source_id"]["from_call_id"], "c3")
        trace = extract_dsh_trace(events, contracts, trace_id="fixture",
                                  provenance_by_call_id=inferred)
        self.assertEqual(len(trace.records), 4)
        self.assertTrue(all(row.eligible for row in trace.records))

    def test_pdf_quote_match_handle_witnesses_locator_to_read_edge(self):
        root = Path(__file__).resolve().parents[1]
        contracts = parse_tool_contracts(json.loads((
            root / "tests/fixtures/contracts/scoped-research-handle-contracts.json").read_text(encoding="utf-8")))
        prefix = "mcp__scoped_research_read__"
        source_id, match_id = "source-" + "a" * 32, "match-" + "b" * 32
        events = (event_pair(1, prefix + "pin_scoped_source", {"role": "paper"},
                             {"source_id": source_id})
                  + event_pair(2, prefix + "locate_pinned_pdf_quote",
                               {"source_id": source_id,
                                "quote": "A uniquely matching quotation"},
                               {"status": "unique", "match_id": match_id})
                  + event_pair(3, prefix + "read_pinned_pdf_match",
                               {"match_id": match_id}, {"pdf_page": 2}))
        provenance = infer_dsh_provenance(events, contracts)
        self.assertEqual(provenance["c2"]["source_id"]["from_call_id"], "c1")
        self.assertEqual(provenance["c3"]["match_id"],
                         {"from_call_id": "c2", "from_field": "match_id"})
        trace = extract_dsh_trace(events, contracts, trace_id="pdf-quote",
                                  provenance_by_call_id=provenance)
        self.assertEqual(len(trace.records), 3)
        self.assertTrue(all(row.eligible for row in trace.records))

    def test_approved_obsidian_excerpt_has_pinned_source_provenance(self):
        root = Path(__file__).resolve().parents[1]
        contracts = parse_tool_contracts(json.loads((
            root / "tests/fixtures/contracts/scoped-research-handle-contracts.json").read_text(encoding="utf-8")))
        prefix = "mcp__scoped_research_read__"
        source_id = "source-" + "c" * 32
        events = (event_pair(1, prefix + "pin_scoped_note", {"role": "current_state"},
                             {"source_id": source_id, "sha256": "a" * 64})
                  + event_pair(2, prefix + "read_pinned_approved_note_excerpt",
                               {"source_id": source_id}, {"sha256": "a" * 64}))
        provenance = infer_dsh_provenance(events, contracts)
        self.assertEqual(provenance["c2"]["source_id"],
                         {"from_call_id": "c1", "from_field": "source_id"})
        trace = extract_dsh_trace(events, contracts, trace_id="obsidian-excerpt",
                                  provenance_by_call_id=provenance)
        self.assertTrue(all(row.eligible for row in trace.records))

    def test_two_independent_traces_propose_but_do_not_authorize_motif(self):
        first = extract_dsh_trace(call(1, "search") + call(2, "read"),
                                  CONTRACTS, trace_id="task-a")
        second = extract_dsh_trace(call(3, "search") + call(4, "read"),
                                   CONTRACTS, trace_id="task-b")
        motifs = mine_dsh_traces([first, second])
        self.assertEqual(len(motifs), 1)
        self.assertEqual(motifs[0]["tools"], ["search", "read"])
        self.assertEqual(motifs[0]["source_trace_ids"], ["task-a", "task-b"])
        self.assertEqual(motifs[0]["status"], "candidate_only")

    def test_unknown_failed_and_effectful_calls_split_segments(self):
        events = (call(1, "search") + call(2, "bash") + call(3, "read")
                  + call(4, "search", failed=True) + call(5, "read")
                  + call(6, "write") + call(7, "search"))
        trace = extract_dsh_trace(events, CONTRACTS, trace_id="task-a")
        self.assertEqual(trace.segments, (("search",), ("read",), ("read",), ("search",)))
        self.assertEqual([row.reason for row in trace.records if not row.eligible],
                         ["unapproved_tool", "missing_or_failed_result", "effectful_tool"])
        self.assertEqual(mine_dsh_traces([trace]), [])

    def test_parameter_and_result_failures_block_mining(self):
        trace = extract_dsh_trace(call(1, "search", arguments={})
                                  + call(2, "read", arguments="not-json")
                                  + [{"type": "tool/call", "data": {
                                      "callId": "no-result", "name": "search",
                                      "arguments": '{"item":"x"}'}}],
                                  CONTRACTS, trace_id="task-a")
        self.assertEqual([row.reason for row in trace.records],
                         ["missing_required_parameter", "invalid_arguments",
                          "missing_or_failed_result"])

    def test_duplicate_trace_identity_is_rejected(self):
        trace = extract_dsh_trace(call(1, "search") + call(2, "read"),
                                  CONTRACTS, trace_id="task-a")
        with self.assertRaisesRegex(ValueError, "unique"):
            mine_dsh_traces([trace, trace])

    def test_explicit_call_provenance_is_checked_against_prior_result(self):
        contracts = {"search": ToolContract(("query",), True, ("id",)),
                     "read": ToolContract(("doc_id",), True)}
        events = (event_pair(1, "search", {"query": "paper"}, {"id": "D"})
                  + event_pair(2, "read", {"doc_id": "D"}, {"text": "paper"}))
        ref = {"c2": {"doc_id": {"from_call_id": "c1", "from_field": "id"}}}
        traced = extract_dsh_trace(
            events, contracts, trace_id="run", task_fingerprint="task",
            provenance_by_call_id=ref)
        self.assertEqual(traced.records[1].parameter_sources,
                         {"doc_id": {"from_tool": "search", "from_field": "id"}})
        wrong = extract_dsh_trace(
            events, contracts, trace_id="run", task_fingerprint="task",
            provenance_by_call_id={"c2": {"doc_id": {
                "from_call_id": "c1", "from_field": "invented"}}})
        self.assertEqual(wrong.records[1].reason, "invalid_parameter_provenance")
        self.assertEqual(wrong.segments, (("search",),))

    def test_opaque_handles_prove_a_prior_result_to_parameter_edge(self):
        source_id = "source-" + "a" * 32
        dataset_id = "dataset-" + "b" * 32
        contracts = {
            "pin": ToolContract(("path",), True, ("source_id",)),
            "inspect": ToolContract(("source_id",), True, ("dataset_id",),
                                    provenance_params=("source_id",)),
            "aggregate": ToolContract(("dataset_id",), True, ("result_id",),
                                      provenance_params=("dataset_id",)),
        }
        events = (event_pair(1, "pin", {"path": "a.csv"}, {"source_id": source_id})
                  + event_pair(2, "inspect", {"source_id": source_id},
                               {"dataset_id": dataset_id})
                  + event_pair(3, "aggregate", {"dataset_id": dataset_id},
                               {"result_id": "result-" + "c" * 32}))
        inferred = infer_dsh_provenance(events, contracts)
        self.assertEqual(inferred["c2"]["source_id"],
                         {"from_call_id": "c1", "from_field": "source_id"})
        self.assertEqual(inferred["c3"]["dataset_id"],
                         {"from_call_id": "c2", "from_field": "dataset_id"})
        trace = extract_dsh_trace(events, contracts, trace_id="real-chain",
                                  provenance_by_call_id=inferred)
        self.assertEqual(trace.segments, (("pin", "inspect", "aggregate"),))
        missing = extract_dsh_trace(events, contracts, trace_id="no-witness")
        self.assertEqual(missing.records[1].reason, "missing_parameter_provenance")
        self.assertEqual(missing.records[2].reason, "missing_parameter_provenance")

    def test_parameter_edges_survive_batched_calls_without_claiming_execution(self):
        contracts = {
            "pin": ToolContract(("path",), True, ("source_id",)),
            "inspect": ToolContract(("source_id",), True, ("dataset_id",),
                                    provenance_params=("source_id",)),
            "aggregate": ToolContract(("dataset_id",), True, ("result_id",),
                                      provenance_params=("dataset_id",)),
        }
        def make_trace(label: str, batched: bool):
            sources = ["source-" + ch * 32 for ch in ("a", "b")]
            datasets = ["dataset-" + ch * 32 for ch in ("c", "d")]
            calls = [event_pair(1, "pin", {"path": f"{label}-1.csv"},
                                {"source_id": sources[0]})]
            if batched:
                calls.append(event_pair(2, "pin", {"path": f"{label}-2.csv"},
                                        {"source_id": sources[1]}))
            calls.append(event_pair(3, "inspect", {"source_id": sources[0]},
                                    {"dataset_id": datasets[0]}))
            if batched:
                calls.append(event_pair(4, "inspect", {"source_id": sources[1]},
                                        {"dataset_id": datasets[1]}))
            calls.append(event_pair(5, "aggregate", {"dataset_id": datasets[0]},
                                    {"result_id": "result-" + "e" * 32}))
            events = [item for pair in calls for item in pair]
            return extract_dsh_trace(events, contracts, trace_id=label,
                                     task_fingerprint=label,
                                     provenance_by_call_id=infer_dsh_provenance(events, contracts))
        first, second = make_trace("task-a", True), make_trace("task-b", False)
        self.assertEqual(mine_dsh_traces([first, second]), [])
        edges = mine_witnessed_parameter_edges([first, second])
        self.assertEqual([(row["from_tool"], row["to_tool"]) for row in edges],
                         [("pin", "inspect"), ("inspect", "aggregate")])
        self.assertTrue(all(row["status"] == "candidate_only" for row in edges))


if __name__ == "__main__":
    unittest.main()
