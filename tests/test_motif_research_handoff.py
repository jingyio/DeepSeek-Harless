"""A Harness answer can reenter only the Motif state that requested it."""

from __future__ import annotations

import hashlib
import json
import unittest

from src.adapters.dsh_client import SemanticValidationError
from src.adapters.motif_research_handoff import (
    reenter_point_query_handoff, reenter_point_selection_handoff,
    reenter_point_synthesis_handoff, resolve_point_query_handoff,
    resolve_point_selection_handoff, resolve_point_synthesis_handoff,
)
from src.motif_core.handoff import SemanticResolution, StructureHandoffRequest
from src.workflows.point_candidate_pool import candidate_fingerprint


class MotifResearchHandoffTests(unittest.TestCase):
    def fixture(self):
        prompt = "Plan bounded source queries for method."
        point_ids = ["method"]
        sources = [{"source": "paper.md", "sha256": "a" * 64}]
        request = StructureHandoffRequest(
            handoff_type="need_semantic_resolution", source="point_query_planning",
            motif_id="research_point_planning", missing_slots=["queries_by_point"],
            available_state={"point_ids": point_ids, "sources": sources},
            allowed_reentry={"mode": "same_motif", "candidates": point_ids},
            metadata={"prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()},
        )
        raw = json.dumps({"queries": [{"point_id": "method",
                                       "terms": ["verified evidence", "cached workflow"]}]})
        return request, prompt, point_ids, sources, raw

    def selection_fixture(self):
        prompt = "Choose bounded evidence for method."
        points = [{"id": "method", "requirement": "Explain the method"}]
        sources = [{"source": "paper.md", "sha256": "a" * 64}]
        candidates = {"method-C1": {"point_id": "method", "evidence": {
            "source": "paper.md", "page": 1, "source_sha256": "a" * 64,
            "snippet": "The method checks evidence."}}}
        request = StructureHandoffRequest(
            handoff_type="need_semantic_resolution", source="point_evidence_selection",
            motif_id="research_point_selection", missing_slots=["selected_ids_by_point"],
            available_state={"point_ids": ["method"], "sources": sources,
                             "candidate_sha256": candidate_fingerprint(candidates)},
            allowed_reentry={"mode": "same_motif", "candidates": ["method-C1"]},
            metadata={"prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()},
        )
        raw = json.dumps({"selections": [{"point_id": "method",
                                          "evidence_ids": ["method-C1"]}]})
        return request, prompt, points, sources, candidates, raw

    def synthesis_fixture(self):
        prompt = "Synthesize claims for the verified method evidence."
        point_ids = ["method"]
        sources = [{"source": "paper.md", "sha256": "a" * 64}]
        citations = {"E1": {"source": "paper.md", "page": 1,
                            "source_sha256": "a" * 64,
                            "snippet": "The method checks verified evidence before reuse."}}
        point_citations = {"method": {"E1"}}
        from src.adapters.motif_research_handoff import _signature
        request = StructureHandoffRequest(
            handoff_type="need_semantic_resolution", source="point_evidence_synthesis",
            motif_id="research_point_synthesis", missing_slots=["claims_by_point"],
            available_state={
                "point_ids": point_ids, "sources": sources,
                "citations_sha256": _signature(citations),
                "point_citations_sha256": _signature({"method": ["E1"]}),
            },
            allowed_reentry={"mode": "same_motif", "candidates": point_ids},
            metadata={"prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()},
        )
        raw = json.dumps({"claims": [{"point_id": "method",
                                      "text": "The method checks evidence before reuse.",
                                      "supports": [{"evidence_id": "E1",
                                                    "quote": "The method checks verified evidence before reuse."}]}],
                          "uncertainties": []})
        return request, prompt, point_ids, sources, citations, point_citations, raw

    def test_harness_result_reenters_current_motif(self) -> None:
        request, prompt, points, sources, raw = self.fixture()
        calls = []

        def harness(sent: str):
            calls.append(sent)
            return raw, {"model_requests": 1}

        _, metrics, resolution = resolve_point_query_handoff(
            request, prompt=prompt, point_ids=points, sources=sources,
            call_harness=harness)
        queries = reenter_point_query_handoff(
            request, resolution, prompt=prompt, point_ids=points, sources=sources)
        self.assertEqual(calls, [prompt])
        self.assertEqual(metrics["model_requests"], 1)
        self.assertEqual(queries[0]["point_id"], "method")

    def test_repeated_query_point_is_logged_and_first_entry_reused(self) -> None:
        request, prompt, points, sources, _ = self.fixture()
        raw = json.dumps({"queries": [
            {"point_id": "method", "terms": ["verified evidence", "cached workflow"]},
            {"point_id": "method", "terms": ["different passage", "other phrase"]},
        ]})
        _, _, resolution = resolve_point_query_handoff(
            request, prompt=prompt, point_ids=points, sources=sources,
            replay_response=raw)
        queries = reenter_point_query_handoff(
            request, resolution, prompt=prompt, point_ids=points, sources=sources)
        self.assertEqual(queries[0]["terms"], ["verified evidence", "cached workflow"])
        self.assertEqual(resolution.metadata["query_normalization"][0]["entry_index"], 2)

    def test_excess_query_terms_are_truncated_with_audit_record(self) -> None:
        request, prompt, points, sources, _ = self.fixture()
        raw = json.dumps({"queries": [{"point_id": "method", "terms": [
            "verified evidence", "cached workflow", "source version",
            "bounded claim", "discarded extra"]}]})
        _, _, resolution = resolve_point_query_handoff(
            request, prompt=prompt, point_ids=points, sources=sources,
            replay_response=raw)
        queries = reenter_point_query_handoff(
            request, resolution, prompt=prompt, point_ids=points, sources=sources)
        self.assertEqual(len(queries[0]["terms"]), 4)
        self.assertEqual(resolution.metadata["query_normalization"][0]["dropped_terms"],
                         ["discarded extra"])

    def test_stale_sources_block_before_harness_call(self) -> None:
        request, prompt, points, sources, raw = self.fixture()
        calls = []
        with self.assertRaisesRegex(ValueError, "no longer matches"):
            resolve_point_query_handoff(
                request, prompt=prompt, point_ids=points,
                sources=[{**sources[0], "sha256": "b" * 64}],
                call_harness=lambda sent: (calls.append(sent), (raw, {}))[1])
        self.assertEqual(calls, [])

    def test_invalid_harness_answer_keeps_paid_usage(self) -> None:
        request, prompt, points, sources, _ = self.fixture()
        with self.assertRaises(SemanticValidationError) as caught:
            resolve_point_query_handoff(
                request, prompt=prompt, point_ids=points, sources=sources,
                call_harness=lambda _prompt: ('{"queries": []}',
                                              {"model_requests": 1, "inputTokens": 42}))
        self.assertEqual(caught.exception.metrics["model_requests"], 1)
        self.assertEqual(caught.exception.raw_response, '{"queries": []}')

    def test_reentry_rejects_stale_or_changed_selection(self) -> None:
        request, prompt, points, sources, raw = self.fixture()
        _, _, resolution = resolve_point_query_handoff(
            request, prompt=prompt, point_ids=points, sources=sources,
            replay_response=raw)
        with self.assertRaisesRegex(ValueError, "no longer matches"):
            reenter_point_query_handoff(
                request, resolution, prompt=prompt, point_ids=points,
                sources=[{**sources[0], "sha256": "c" * 64}])
        altered = SemanticResolution(
            resolution_type="slot_fill",
            slot_values={"queries_by_point": [{"point_id": "other",
                                                "terms": ["verified evidence", "cached workflow"]}]},
            metadata=resolution.metadata)
        with self.assertRaises(ValueError):
            reenter_point_query_handoff(
                request, altered, prompt=prompt, point_ids=points, sources=sources)

    def test_selection_replay_reenters_current_candidates(self) -> None:
        request, prompt, points, sources, candidates, raw = self.selection_fixture()
        _, metrics, resolution = resolve_point_selection_handoff(
            request, prompt=prompt, points=points, candidates=candidates,
            sources=sources, replay_response=raw)
        selected = reenter_point_selection_handoff(
            request, resolution, prompt=prompt, points=points,
            candidates=candidates, sources=sources)
        self.assertEqual(metrics, {})
        self.assertEqual(selected, {"method": ["method-C1"]})

    def test_selection_stale_candidates_block_before_model(self) -> None:
        request, prompt, points, sources, candidates, raw = self.selection_fixture()
        changed = {**candidates, "method-C1": {
            **candidates["method-C1"],
            "evidence": {**candidates["method-C1"]["evidence"], "snippet": "Changed."}}}
        calls = []
        with self.assertRaisesRegex(ValueError, "no longer matches"):
            resolve_point_selection_handoff(
                request, prompt=prompt, points=points, candidates=changed,
                sources=sources,
                call_harness=lambda sent: (calls.append(sent), (raw, {}))[1])
        self.assertEqual(calls, [])

    def test_selection_invalid_answer_preserves_model_usage(self) -> None:
        request, prompt, points, sources, candidates, _ = self.selection_fixture()
        with self.assertRaises(SemanticValidationError) as caught:
            resolve_point_selection_handoff(
                request, prompt=prompt, points=points, candidates=candidates,
                sources=sources, call_harness=lambda _prompt: (
                    '{"selections": [{"point_id": "method", "evidence_ids": ["unknown"]}]}',
                    {"model_requests": 1, "outputTokens": 12}))
        self.assertEqual(caught.exception.metrics["outputTokens"], 12)

    def test_synthesis_replay_validates_quotes_and_reenters(self) -> None:
        request, prompt, points, sources, citations, scopes, raw = self.synthesis_fixture()
        _, metrics, resolution = resolve_point_synthesis_handoff(
            request, prompt=prompt, point_ids=points, citations=citations,
            point_citations=scopes, sources=sources, replay_response=raw)
        claims, uncertainties, rejected = reenter_point_synthesis_handoff(
            request, resolution, raw_response=raw, prompt=prompt, point_ids=points,
            citations=citations, point_citations=scopes, sources=sources)
        self.assertEqual(metrics, {})
        self.assertEqual(len(claims), 1)
        self.assertEqual(uncertainties, [])
        self.assertEqual(rejected, [])

    def test_synthesis_stale_citation_blocks_before_model(self) -> None:
        request, prompt, points, sources, citations, scopes, raw = self.synthesis_fixture()
        changed = {"E1": {**citations["E1"], "snippet": "Different evidence."}}
        calls = []
        with self.assertRaisesRegex(ValueError, "no longer matches"):
            resolve_point_synthesis_handoff(
                request, prompt=prompt, point_ids=points, citations=changed,
                point_citations=scopes, sources=sources,
                call_harness=lambda sent: (calls.append(sent), (raw, {}))[1])
        self.assertEqual(calls, [])

    def test_synthesis_invalid_json_preserves_model_usage(self) -> None:
        request, prompt, points, sources, citations, scopes, _ = self.synthesis_fixture()
        with self.assertRaises(SemanticValidationError) as caught:
            resolve_point_synthesis_handoff(
                request, prompt=prompt, point_ids=points, citations=citations,
                point_citations=scopes, sources=sources,
                call_harness=lambda _prompt: ('{"wrong": true}',
                                              {"model_requests": 1, "inputTokens": 55}))
        self.assertEqual(caught.exception.metrics["inputTokens"], 55)


if __name__ == "__main__":
    unittest.main()
