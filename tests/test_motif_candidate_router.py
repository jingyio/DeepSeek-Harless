"""Candidate advice must stop at the MotifController's signed frontier."""

import math
import unittest
from unittest.mock import patch
from io import BytesIO

from src.adapters.jev_decision import JevDecisionPort
from src.adapters.laya_decision import ChoiceDecision
from src.adapters.dsh_trajectory import ToolContract
from src.adapters.local_embedding import LocalEmbeddingPort
from src.adapters.motif_candidate_router import (
    advise_current_with_embeddings, advise_with_embeddings,
    advise_with_choice, advise_with_local_choice,
    descriptions_from_contracts, resume_approved_advice,
)
from src.motif_core.controller import MotifController
from tests.test_motif_controller import CONTRACTS, library


class FakeEmbedding:
    def __init__(self, vectors):
        self.vectors = vectors
        self.received = None

    def embed(self, texts):
        self.received = texts
        return self.vectors


class FakeChoice:
    def __init__(self, probabilities, choice):
        self.probabilities = probabilities
        self.choice = choice
        self.received = None

    def choose(self, **kwargs):
        self.received = kwargs
        return ChoiceDecision(
            "next_motif", self.choice, self.probabilities[self.choice], None,
            "local-laya", {"answers": {"next_motif": {
                "probabilities": self.probabilities}}})


class CandidateRouterTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.controller = MotifController(
            library(two_paths=True), contracts=CONTRACTS,
            execute_tool=lambda tool, params: (
                self.calls.append((tool, dict(params))) or
                ({"id": "G"} if tool != "read" else {"text": "G"})),
            verify_current=lambda: None, is_read_only=lambda _: True)
        self.handoff = self.controller.execute_goal(
            required_output="read", bindings={}, input_version="v1",
            intent="Read the cited paper through the appropriate source").handoff
        self.ids = self.handoff.allowed_reentry["candidates"]
        self.descriptions = {
            motif_id: "Certified " + " → ".join(self.controller.artifacts[motif_id]["tools"])
            for motif_id in self.ids}

    def test_embedding_suggestion_needs_acceptance_and_then_stops_at_slot_gap(self):
        port = FakeEmbedding([[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
        advice = advise_with_embeddings(
            self.handoff, self.descriptions, context="source lookup", port=port,
            min_similarity=.8, min_margin=.3)
        self.assertEqual(advice.status, "suggested")
        self.assertEqual(advice.motif_id, self.ids[0])
        self.assertEqual(len(port.received), 3)
        self.assertEqual(self.calls, [])
        with self.assertRaisesRegex(ValueError, "not approved"):
            resume_approved_advice(self.controller, advice, approved=False)
        self.assertEqual(self.calls, [])
        result = resume_approved_advice(self.controller, advice, approved=True)
        self.assertEqual(result.status, "needs_mediation")
        self.assertEqual(self.calls, [])

    def test_embedding_uncertainty_and_bad_vector_defer_or_fail_closed(self):
        port = FakeEmbedding([[1.0, 0.0], [1.0, 0.0], [1.0, 0.0]])
        advice = advise_with_embeddings(
            self.handoff, self.descriptions, context="", port=port,
            min_similarity=.8, min_margin=.2)
        self.assertEqual(advice.status, "defer")
        self.assertIsNone(advice.motif_id)
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            advise_with_embeddings(
                self.handoff, self.descriptions, context="", 
                port=FakeEmbedding([[math.nan, 0], [1, 0], [0, 1]]),
                min_similarity=.8, min_margin=.2)
        self.assertEqual(self.calls, [])

    def test_embedding_overlength_state_defers_without_truncation(self):
        port = FakeEmbedding([])
        handoff = self.controller.execute_goal(
            required_output="read", bindings={}, input_version="v1",
            intent="研究" * 500).handoff
        advice = advise_with_embeddings(
            handoff, self.descriptions, context="资料" * 500,
            port=port, min_similarity=.8, min_margin=.2)
        self.assertEqual(advice.reason, "input_too_long")
        self.assertIsNone(port.received)

    def test_local_choice_offers_defer_and_rejects_uncertain_answer(self):
        probabilities = {self.ids[0]: .7, self.ids[1]: .2, "__defer__": .1}
        port = FakeChoice(probabilities, self.ids[0])
        advice = advise_with_local_choice(
            self.handoff, self.descriptions, context="source lookup", port=port,
            min_probability=.8, min_margin=.3)
        self.assertEqual(advice.status, "defer")
        self.assertIn("__defer__", port.received["criteria"])
        self.assertEqual(self.calls, [])
        accepted = advise_with_local_choice(
            self.handoff, self.descriptions, context="source lookup", port=port,
            min_probability=.6, min_margin=.3)
        self.assertEqual(accepted.motif_id, self.ids[0])
        self.assertEqual(accepted.model, "local-laya")

    def test_old_advice_cannot_reenter_changed_snapshot(self):
        advice = advise_with_embeddings(
            self.handoff, self.descriptions, context="source lookup",
            port=FakeEmbedding([[1, 0], [1, 0], [0, 1]]),
            min_similarity=.8, min_margin=.3)
        self.controller.execute_goal(
            required_output="read", bindings={}, input_version="v2",
            intent="Read the cited paper through the appropriate source")
        with self.assertRaisesRegex(ValueError, "not approved"):
            resume_approved_advice(self.controller, advice, approved=True)
        self.assertEqual(self.calls, [])

    def test_descriptions_must_match_exact_handoff_candidates(self):
        with self.assertRaisesRegex(ValueError, "candidate descriptions"):
            advise_with_embeddings(
                self.handoff, {self.ids[0]: "Only one"}, context="", 
                port=FakeEmbedding([[1, 0], [1, 0]]),
                min_similarity=.8, min_margin=.2)

    def test_undocumented_tool_cannot_enter_local_model(self):
        port = FakeEmbedding([[1, 0], [1, 0], [0, 1]])
        with self.assertRaisesRegex(ValueError, "tool documentation"):
            advise_current_with_embeddings(
                self.controller, context="topic search", port=port,
                min_similarity=.8, min_margin=.2)
        self.assertIsNone(port.received)

    def test_match_descriptions_derive_from_tool_contracts_not_past_tasks(self):
        documented = {
            "search": ToolContract(("query",), True, ("id",), (),
                                   "Search a corpus by research topic or title"),
            "lookup": ToolContract(("query",), True, ("id",), (),
                                   "Look up one exact catalog identifier"),
            "read": ToolContract(("doc_id",), True, ("text",), (),
                                 "Read the identified source document"),
        }
        controller = MotifController(
            library(two_paths=True), contracts=documented,
            execute_tool=lambda *args: self.calls.append(args),
            verify_current=lambda: None, is_read_only=lambda _: True)
        handoff = controller.execute_goal(
            required_output="read", bindings={}, input_version="v1",
            intent="Find a paper about the topic").handoff
        descriptions = descriptions_from_contracts(controller, handoff)
        self.assertEqual(set(descriptions), set(handoff.allowed_reentry["candidates"]))
        search_id = next(key for key in descriptions
                         if controller.artifacts[key]["tools"][0] == "search")
        self.assertIn("Search a corpus", descriptions[search_id])
        self.assertIn("search.id → read.doc_id", descriptions[search_id])
        self.assertNotIn("alpha", str(descriptions))
        port = FakeEmbedding([[1, 0], [1, 0], [0, 1]])
        advice = advise_current_with_embeddings(
            controller, context="topic search", port=port,
            min_similarity=.8, min_margin=.2)
        self.assertEqual(advice.status, "suggested")
        self.assertEqual(self.calls, [])
        controller.execute_goal(required_output="read", bindings={},
                                input_version="v2", intent="New task")
        with self.assertRaisesRegex(ValueError, "current certified handoff"):
            descriptions_from_contracts(controller, handoff)

    def test_local_embedding_rejects_external_destination(self):
        with self.assertRaisesRegex(ValueError, "loopback"):
            LocalEmbeddingPort("https://remote.example/v1/embeddings", "model")

    def test_jev_is_opt_in_and_matches_official_choice_shape(self):
        port = JevDecisionPort(api_key="test-only")
        with self.assertRaisesRegex(PermissionError, "explicit"):
            advise_with_choice(
                self.handoff, self.descriptions, context="source lookup",
                port=port, min_probability=.7, min_margin=.2)
        probabilities = {self.ids[0]: .9, self.ids[1]: .05, "__defer__": .05}
        response = {"model": "jev-1.13.0", "usage": {"input_tokens": 100,
                    "output_tokens": 3}, "answers": {"next_motif": {
                        "type": "choice", "choice": self.ids[0],
                        "confidence": .85, "probabilities": probabilities}}}
        import json
        with patch("src.adapters.jev_decision.urlopen",
                   return_value=BytesIO(json.dumps(response).encode())) as mock_call:
            advice = advise_with_choice(
                self.handoff, self.descriptions, context="source lookup",
                port=JevDecisionPort(api_key="test-only", allow_paid_requests=True),
                min_probability=.7, min_margin=.2)
        self.assertEqual(advice.backend, "jev_api")
        self.assertEqual(advice.motif_id, self.ids[0])
        self.assertEqual(advice.usage["input_tokens"], 100)
        request = mock_call.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.typesafe.ai/v1/systemone")
        self.assertEqual(json.loads(request.data)["questions"]["next_motif"]["type"],
                         "choice")
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
