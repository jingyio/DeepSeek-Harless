"""Bounded semantic choice at a trace-compiled Motif's missing entry slot.

The Motif owns execution before and after the call. A Harness caller supplies
only a choice among host-approved values; it never executes the next tool.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from src.adapters.dsh_client import SemanticValidationError
from src.adapters.dsh_client import call_bounded_prompt
from src.motif_core.handoff import SemanticResolution
from src.motif_core.controller import MotifController, MotifDecision
from src.motif_core.read_executor import ReadMotifRun, resume_read_motif


def _signature(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8")).hexdigest()


def deepseek_slot_port(root: Path) -> Callable[[str], tuple[str, dict[str, Any]]]:
    """Use the existing restricted DSH SDK profile for one local gap."""
    def call(prompt: str) -> tuple[str, dict[str, Any]]:
        return call_bounded_prompt(prompt, root=root, model="deepseek-flash",
                                   max_output_tokens=300, max_prompt_characters=4000)
    return call


def resolve_and_resume_motif_choice(
    controller: MotifController, prior: MotifDecision, *,
    call_semantic: Callable[[str], tuple[str, dict[str, Any]]],
) -> tuple[MotifDecision, dict[str, Any], SemanticResolution]:
    """Let Harness choose only among motifs certified for one output goal."""
    request = prior.handoff
    if (controller.last is not prior or prior.status != "needs_motif_choice"
            or request is None or request.source != "motif_match"
            or request.allowed_reentry.get("mode") != "motif_choice"):
        raise ValueError("no current bounded Motif choice")
    candidates = request.allowed_reentry["candidates"]
    if not isinstance(candidates, list) or not 1 < len(candidates) <= 8:
        raise ValueError("Motif choice exceeds bounded candidate scope")
    prompt = json.dumps({
        "instruction": "Choose exactly one motif_id from candidates. Return JSON only: "
                       "{\"motif_id\": \"chosen id\"}.",
        "required_output": request.available_state["required_output"],
        "intent": request.available_state.get("intent", ""),
        "candidates": [{"motif_id": motif_id,
                        "tools": controller.artifacts[motif_id]["tools"],
                        "observed_connector":
                            request.available_state.get("observed_connectors", {}).get(motif_id, {})}
                       for motif_id in candidates],
    }, ensure_ascii=False, sort_keys=True)
    if len(prompt) > 4000:
        raise ValueError("Motif choice prompt exceeds its local limit")
    controller.verify_current()
    raw, metrics = call_semantic(prompt)
    try:
        if not isinstance(raw, str) or len(raw) > 6000:
            raise ValueError("semantic response is not bounded text")
        parsed = json.loads(raw)
        if not isinstance(parsed, dict) or set(parsed) != {"motif_id"}:
            raise ValueError("semantic response must contain one motif_id")
        if parsed["motif_id"] not in candidates:
            raise ValueError("semantic response selected an unauthorized Motif")
        resolution = SemanticResolution(
            resolution_type="motif_choice", action={"motif_id": parsed["motif_id"]},
            metadata={"handoff_signature": _signature(request.to_dict()),
                      "response_sha256": hashlib.sha256(raw.encode()).hexdigest()},
        )
        resumed = controller.resume_selection(resolution)
    except (ValueError, TypeError, KeyError) as exc:
        raise SemanticValidationError(str(exc), metrics=metrics,
                                      raw_response=raw) from exc
    return resumed, metrics, resolution


def _checked_candidates(
    prior: ReadMotifRun, choices: Mapping[str, Mapping[str, list[str]]],
) -> dict[str, dict[str, list[str]]]:
    request = prior.handoff
    if (prior.status != "needs_mediation" or request is None
            or request.handoff_type != "need_user_clarification"
            or request.allowed_reentry.get("mode") != "same_motif"):
        raise ValueError("Motif has no bounded, resumable parameter gap")
    if set(choices) != set(request.missing_params):
        raise ValueError("candidate tools do not match the Motif gap")
    checked: dict[str, dict[str, list[str]]] = {}
    for tool, missing in request.missing_params.items():
        options = choices[tool]
        if set(options) != set(missing):
            raise ValueError("candidate parameters do not match the Motif gap")
        checked[tool] = {}
        for param in missing:
            values = options[param]
            scoped = (request.available_state.get("candidate_values") or {}).get(tool, {}).get(param)
            if scoped is not None and values != scoped:
                raise ValueError("repeat candidates differ from current source evidence")
            mode = ((request.available_state.get("candidate_value_modes") or {})
                    .get(tool, {}).get(param))
            limit = 50 if mode == "one_of" else 8
            if (not isinstance(values, list) or not 1 <= len(values) <= limit
                    or any(not isinstance(item, str) or not item.strip()
                           or len(item) > 200 for item in values)
                    or len(set(values)) != len(values)):
                raise ValueError("candidate values must be distinct bounded strings")
            checked[tool][param] = list(values)
    return checked


def resolve_and_resume_read_motif(
    artifact: dict[str, Any], prior: ReadMotifRun, *,
    choices: Mapping[str, Mapping[str, list[str]]],
    call_semantic: Callable[[str], tuple[str, dict[str, Any]]],
    contracts: Mapping[str, Any], execute_tool: Callable[[str, dict[str, Any]], Any],
    verify_current: Callable[[], None], is_read_only: Callable[[str], bool],
    controller: MotifController | None = None,
    intent: str = "",
) -> tuple[ReadMotifRun, dict[str, Any], SemanticResolution]:
    """Resume only with a current source and an allowed choice from the model."""
    checked = _checked_candidates(prior, choices)
    if not isinstance(intent, str) or len(intent) > 1000:
        raise ValueError("semantic intent must be bounded text")
    request = prior.handoff
    assert request is not None
    handoff_signature = _signature(request.to_dict())
    candidate_signature = _signature(checked)
    subset_slots = {
        tool: selected for tool, slots in checked.items()
        if (selected := [param for param in slots
                         if param in (request.available_state.get("candidate_values") or {})
                         .get(tool, {})
                         and ((request.available_state.get("candidate_value_modes") or {})
                              .get(tool, {}).get(param)) != "one_of"])
    }
    instruction = (
        "Choose exactly one listed string for each missing slot. The value must "
        "be a string, never a list. Return JSON only: "
        "{\"slot_values\": {tool: {parameter: chosen_string}}}."
        if not subset_slots else
        "For ordinary slots choose exactly one listed string. For subset_slots "
        "choose a nonempty list in candidate order. Return JSON only: "
        "{\"slot_values\": {tool: {parameter: chosen_string_or_list}}}.")
    prompt_data = {
        "instruction": instruction,
        "motif_id": prior.motif_id,
        "input_version": prior.input_version,
        "intent": intent,
        "missing_params": request.missing_params,
        "choices": checked,
        "choice_details": request.available_state.get("candidate_details", {}),
    }
    if subset_slots:
        prompt_data["subset_slots"] = subset_slots
    prompt = json.dumps(prompt_data, ensure_ascii=False, sort_keys=True)
    if len(prompt) > 4000:
        raise ValueError("Motif semantic prompt exceeds its local limit")
    verify_current()
    raw, metrics = call_semantic(prompt)
    try:
        if not isinstance(raw, str) or len(raw) > 6000:
            raise ValueError("semantic response is not bounded text")
        parsed = json.loads(raw)
        if not isinstance(parsed, dict) or set(parsed) != {"slot_values"}:
            raise ValueError("semantic response must contain only slot_values")
        selected = parsed["slot_values"]
        if not isinstance(selected, dict) or set(selected) != set(checked):
            raise ValueError("semantic response changed the candidate tools")
        for tool, slots in checked.items():
            if not isinstance(selected[tool], dict) or set(selected[tool]) != set(slots):
                raise ValueError("semantic response changed the missing slots")
            for param, candidates in slots.items():
                chosen = selected[tool][param]
                if param in subset_slots.get(tool, ()):
                    if (not isinstance(chosen, list) or not chosen
                            or [item for item in candidates if item in chosen] != chosen):
                        raise ValueError("semantic response chose an unauthorized subset")
                elif chosen not in candidates:
                    raise ValueError("semantic response chose an unauthorized value")
        if _signature(checked) != candidate_signature:
            raise ValueError("candidate scope changed during semantic call")
        resolution = SemanticResolution(
            resolution_type="slot_fill", slot_values=selected,
            metadata={"handoff_signature": handoff_signature,
                      "candidate_signature": candidate_signature,
                      "response_sha256": hashlib.sha256(raw.encode()).hexdigest()},
        )
        if controller is not None:
            if (controller.last is None or controller.last.run is not prior
                    or controller.artifacts.get(prior.motif_id) is not artifact):
                raise ValueError("Motif controller no longer owns this suspended run")
            decision = controller.resume_slots(resolution)
            assert decision.run is not None
            resumed = decision.run
        else:
            resumed = resume_read_motif(
                artifact, prior, resolution, contracts=contracts,
                execute_tool=execute_tool, verify_current=verify_current,
                is_read_only=is_read_only)
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise SemanticValidationError(
            str(exc), metrics=metrics, raw_response=raw) from exc
    return resumed, metrics, resolution


def resolve_and_resume_controller_slots(
    controller: MotifController, *,
    choices: Mapping[str, Mapping[str, list[str]]] | None = None,
    call_semantic: Callable[[str], tuple[str, dict[str, Any]]],
    intent: str = "",
) -> tuple[MotifDecision, dict[str, Any], SemanticResolution]:
    """Resume the controller's currently suspended parameter frontier."""
    prior = controller.last.run if controller.last is not None else None
    if prior is None or prior.status != "needs_mediation":
        raise ValueError("Motif controller has no current parameter gap")
    if choices is None:
        choices = (prior.handoff.available_state.get("candidate_values")
                   if prior.handoff is not None else None)
    if choices is None:
        raise ValueError("host must provide bounded choices for entry slots")
    _run, metrics, resolution = resolve_and_resume_read_motif(
        controller.artifacts[prior.motif_id], prior, choices=choices,
        call_semantic=call_semantic, contracts=controller.contracts,
        execute_tool=controller.execute_tool,
        verify_current=controller.verify_current,
        is_read_only=controller.is_read_only, controller=controller,
        intent=intent)
    assert controller.last is not None
    return controller.last, metrics, resolution
