"""Two optional semantic backends for a certified Motif-choice handoff.

The router only recommends an ID from the controller's exact candidate set.
Execution remains owned by MotifController and needs explicit acceptance of
the advice. No TF-IDF path or silent fallback is provided.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from src.motif_core.controller import MotifController, MotifDecision
from src.motif_core.handoff import SemanticResolution, StructureHandoffRequest


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")).hexdigest()


class EmbeddingPort(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class ChoicePort(Protocol):
    def choose(self, *, state: str, question_id: str, instructions: str,
               criteria: dict[str, str], model: str = "multilingual") -> Any: ...


@dataclass(frozen=True)
class MotifAdvice:
    backend: str
    status: str
    motif_id: str | None
    handoff_signature: str
    scores: dict[str, float]
    reason: str
    model: str | None = None
    usage: dict[str, int] | None = None


def descriptions_from_contracts(
    controller: MotifController, request: StructureHandoffRequest,
) -> dict[str, str]:
    """Derive bounded match text from the current certified tool contracts.

    This uses tool documentation and compiled parameter flow, not old task
    contents or a hand-authored scenario path. Missing docs stop matching.
    """
    if (controller.last is None or controller.last.handoff is None
            or _digest(controller.last.handoff.to_dict()) != _digest(request.to_dict())
            or request.source != "motif_match"
            or request.allowed_reentry.get("mode") != "motif_choice"
            or request.available_state.get("library_digest") != controller.library_digest):
        raise ValueError("Motif descriptions need the current certified handoff")
    result = {}
    for motif_id in request.allowed_reentry["candidates"]:
        artifact = controller.artifacts.get(motif_id)
        if artifact is None or artifact.get("status") != "trace_validated_read_only":
            raise ValueError("Motif candidate is not certified")
        steps = []
        for tool_name in artifact["tools"]:
            base_name = tool_name.rstrip("+")
            contract = controller.contracts.get(base_name)
            description = getattr(contract, "description", "")
            if (not isinstance(description, str) or not description.strip()
                    or len(description) > 160):
                raise ValueError("tool documentation is missing or exceeds match scope")
            steps.append(f"{base_name}: {description.strip()}")
        transfers = [
            f"{row['from_tool']}.{row['from_field']} → "
            f"{row['to_tool']}.{row['to_param']}"
            for row in artifact.get("transfer_evidence", [])
        ]
        text = " ; ".join(steps)
        if transfers:
            text += " ; parameter flow: " + ", ".join(transfers)
        if len(text) > 500:
            raise ValueError("Motif description exceeds match scope")
        result[motif_id] = text
    _scope(request, result, "")
    return result


def advise_current_with_embeddings(
    controller: MotifController, *, context: str, port: EmbeddingPort,
    min_similarity: float, min_margin: float,
) -> MotifAdvice:
    """Match the suspended controller frontier using current tool documentation."""
    if controller.last is None or controller.last.handoff is None:
        raise ValueError("no current Motif choice frontier")
    handoff = controller.last.handoff
    descriptions = descriptions_from_contracts(controller, handoff)
    return advise_with_embeddings(
        handoff, descriptions, context=context, port=port,
        min_similarity=min_similarity, min_margin=min_margin)


def advise_current_with_choice(
    controller: MotifController, *, context: str, port: ChoicePort,
    min_probability: float, min_margin: float, model: str | None = None,
) -> MotifAdvice:
    """Use Laya or Jev over the same certified, documented candidates."""
    if controller.last is None or controller.last.handoff is None:
        raise ValueError("no current Motif choice frontier")
    handoff = controller.last.handoff
    descriptions = descriptions_from_contracts(controller, handoff)
    return advise_with_choice(
        handoff, descriptions, context=context, port=port,
        model=model, min_probability=min_probability, min_margin=min_margin)


def _scope(request: StructureHandoffRequest,
           descriptions: Mapping[str, str], context: str) -> tuple[list[str], str]:
    if (request.source != "motif_match"
            or request.allowed_reentry.get("mode") != "motif_choice"):
        raise ValueError("candidate router needs a Motif choice handoff")
    ids = request.allowed_reentry.get("candidates")
    if (not isinstance(ids, list) or not 2 <= len(ids) <= 8
            or any(not isinstance(item, str) or not item for item in ids)
            or len(set(ids)) != len(ids) or set(descriptions) != set(ids)
            or any(not isinstance(text, str) or not 1 <= len(text.strip()) <= 500
                   for text in descriptions.values())
            or not isinstance(context, str) or len(context) > 1000):
        raise ValueError("candidate descriptions or context exceed the handoff")
    intent = request.available_state.get("intent")
    if not isinstance(intent, str) or not intent.strip():
        raise ValueError("Motif choice needs a current task intent")
    required_output = request.available_state.get("required_output")
    if not isinstance(required_output, str) or not required_output:
        raise ValueError("Motif choice needs a required output")
    return ids, json.dumps({"intent": intent, "current_state": context,
                            "required_output": required_output},
                           ensure_ascii=False, sort_keys=True)


def _cosine(first: list[float], second: list[float]) -> float:
    if len(first) != len(second) or not first:
        raise ValueError("embedding dimensions differ")
    if any(isinstance(item, bool) or not isinstance(item, (int, float))
           or not math.isfinite(item) for item in first + second):
        raise ValueError("embedding has nonfinite or nonnumeric values")
    left = math.sqrt(sum(item * item for item in first))
    right = math.sqrt(sum(item * item for item in second))
    if not left or not right:
        raise ValueError("embedding has zero length")
    return sum(a * b for a, b in zip(first, second)) / (left * right)


def advise_with_embeddings(
    request: StructureHandoffRequest, descriptions: Mapping[str, str],
    *, context: str, port: EmbeddingPort,
    min_similarity: float, min_margin: float,
) -> MotifAdvice:
    """Rank approved candidates; thresholds must come from a caller's calibration."""
    if (not math.isfinite(min_similarity) or not math.isfinite(min_margin)
            or not -1 <= min_similarity <= 1 or not 0 <= min_margin <= 2):
        raise ValueError("invalid calibrated embedding thresholds")
    ids, state = _scope(request, descriptions, context)
    query = ("Instruct: Select the certified workflow motif whose purpose best matches "
             "the current task and state.\nQuery: " + state)
    if len(query) > 2000:
        return MotifAdvice("embedding", "defer", None, _digest(request.to_dict()),
                           {}, "input_too_long")
    vectors = port.embed([query] + [descriptions[motif_id] for motif_id in ids])
    if len(vectors) != len(ids) + 1:
        raise ValueError("embedding backend changed candidate count")
    scores = {motif_id: _cosine(vectors[0], vector)
              for motif_id, vector in zip(ids, vectors[1:])}
    ranked = sorted(scores, key=lambda motif_id: (-scores[motif_id], motif_id))
    winner = ranked[0]
    margin = scores[winner] - scores[ranked[1]]
    accepted = scores[winner] >= min_similarity and margin >= min_margin
    return MotifAdvice("embedding", "suggested" if accepted else "defer",
                       winner if accepted else None, _digest(request.to_dict()),
                       scores, "ranked_candidate" if accepted else "low_score_or_margin")


def advise_with_choice(
    request: StructureHandoffRequest, descriptions: Mapping[str, str],
    *, context: str, port: ChoicePort, model: str | None = None,
    min_probability: float, min_margin: float,
) -> MotifAdvice:
    """Use a bounded Choice backend (local Laya or Jev API)."""
    if (not math.isfinite(min_probability) or not math.isfinite(min_margin)
            or not 0 <= min_probability <= 1 or not 0 <= min_margin <= 1):
        raise ValueError("invalid calibrated choice thresholds")
    ids, state = _scope(request, descriptions, context)
    criteria = {motif_id: descriptions[motif_id] for motif_id in ids}
    criteria["__defer__"] = "No candidate fits the current goal or the evidence is insufficient."
    kwargs = {
        "state": state, "question_id": "next_motif",
        "instructions": "Choose the best current Motif, or defer if none fits. Do not authorize execution.",
        "criteria": criteria,
    }
    if model is not None:
        kwargs["model"] = model
    decision = port.choose(**kwargs)
    answer = (decision.raw.get("answers", {}).get("next_motif")
              if isinstance(decision.raw, dict)
              and isinstance(decision.raw.get("answers"), dict) else None)
    probabilities = answer.get("probabilities") if isinstance(answer, dict) else None
    if (decision.choice not in criteria or not isinstance(probabilities, dict)
            or set(probabilities) != set(criteria)
            or any(isinstance(value, bool) or not isinstance(value, (int, float))
                   or not math.isfinite(value) or not 0 <= value <= 1
                   for value in probabilities.values())):
        raise ValueError("local choice changed the Motif candidate set")
    scores = {key: float(value) for key, value in probabilities.items()}
    if (abs(sum(scores.values()) - 1) > 0.01
            or scores[decision.choice] < max(scores.values())):
        raise ValueError("local choice probabilities contradict its answer")
    runner_up = max(value for key, value in scores.items() if key != decision.choice)
    accepted = (decision.choice != "__defer__"
                and scores[decision.choice] >= min_probability
                and scores[decision.choice] - runner_up >= min_margin)
    backend = getattr(port, "backend_name", "local_choice")
    usage = decision.raw.get("usage")
    if usage is not None and (not isinstance(usage, dict)
                              or any(not isinstance(value, int) or isinstance(value, bool)
                                     or value < 0 for value in usage.values())):
        raise ValueError("choice backend returned invalid usage")
    return MotifAdvice(backend, "suggested" if accepted else "defer",
                       decision.choice if accepted else None,
                       _digest(request.to_dict()), scores,
                       "ranked_candidate" if accepted else "deferred_or_uncertain",
                       decision.model, usage)


# Preserve the earlier local-only entry point for existing callers.
advise_with_local_choice = advise_with_choice


def resume_approved_advice(controller: MotifController,
                           advice: MotifAdvice, *, approved: bool) -> MotifDecision:
    """Require an explicit calibrated/human approval before Motif reentry."""
    prior = controller.last
    if (not approved or advice.status != "suggested" or advice.motif_id is None
            or prior is None or prior.status != "needs_motif_choice"
            or prior.handoff is None
            or advice.handoff_signature != _digest(prior.handoff.to_dict())):
        raise ValueError("Motif advice is not approved for the current handoff")
    return controller.resume_selection(SemanticResolution(
        resolution_type="motif_choice", action={"motif_id": advice.motif_id},
        metadata={"handoff_signature": advice.handoff_signature,
                  "choice_backend": advice.backend}))
