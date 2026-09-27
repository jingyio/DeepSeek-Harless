"""Certify a proposed pure code node against independent Motif task traces."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping

from src.adapters.dsh_trajectory import DshTrace
from src.motif_core.pure_code import run_isolated

from .trace_compiler import _field_value, _occurrence, artifact_signature


def _digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def code_node_body(node: dict[str, Any]) -> dict[str, Any]:
    return {key: node[key] for key in (
        "kind", "language", "expression", "from_tool", "from_field",
        "to_tool", "to_param")}


def certify_dynamic_code_node(
    artifact: dict[str, Any], candidate: dict[str, str],
    training: list[DshTrace], heldout: DshTrace,
    contracts: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a new skill; candidate code never mutates the installed skill."""
    from src.motif_core.read_executor import _validate_artifact

    tools = _validate_artifact(artifact, contracts)
    if (len(tools) != 2 or artifact.get("code_nodes")
            or set(candidate) != {"from_tool", "from_field", "to_tool",
                                  "to_param", "expression"}
            or candidate["from_tool"] != tools[0]
            or candidate["to_tool"] != tools[1]
            or candidate["from_field"] not in contracts[tools[0]].output_fields
            or candidate["to_param"] not in contracts[tools[1]].required_params
            or any(edge["to_param"] == candidate["to_param"]
                   for edge in artifact["transfer_evidence"])):
        raise ValueError("code candidate is outside this certified skill gap")
    by_id = {trace.trace_id: trace for trace in training}
    expected = artifact["source_trace_ids"]
    if (len(by_id) != len(training) or set(by_id) != set(expected)
            or heldout.trace_id != artifact["validation_trace_id"]
            or {by_id[key].task_fingerprint for key in expected}
            != set(artifact["source_task_fingerprints"])
            or heldout.task_fingerprint != artifact["validation_task_fingerprint"]):
        raise ValueError("code candidate needs this skill's independent task evidence")
    observed = []
    for trace in [*(by_id[key] for key in expected), heldout]:
        source, target = _occurrence(trace, tools)
        value = _field_value(source.observation, candidate["from_field"])
        expected_output = target.arguments.get(candidate["to_param"])
        if (value is None or type(expected_output) is not str
                or run_isolated(candidate["expression"], value) != expected_output):
            raise ValueError("pure code contradicts an observed tool argument")
        observed.append((value, expected_output))
    training_values = observed[:-1]
    if (len({_digest(value) for value, _ in training_values}) < 2
            or len({output for _, output in training_values}) < 2
            or all(value == output for value, output in observed)):
        raise ValueError("code evidence is constant or duplicates direct transfer")
    # Reject obvious task text embedded as a literal in the skill's code.
    expression = candidate["expression"]
    if any(isinstance(item, str) and len(item) >= 8 and item in expression
           for value, output in observed for item in (value, output)):
        raise ValueError("code expression embeds observed task content")
    body = {"kind": "pure_code", "language": "sss-pure-python-expr-v1",
            **candidate}
    code_id = "code_" + _digest(body)[:16]
    node = {"node_id": code_id, **body,
            "program_digest": _digest(body),
            "source_trace_ids": list(expected),
            "source_task_fingerprints": list(artifact["source_task_fingerprints"]),
            "validation_trace_id": heldout.trace_id,
            "validation_task_fingerprint": heldout.task_fingerprint}
    updated = copy.deepcopy(artifact)
    updated["code_nodes"] = [node]
    updated["dependencies"]["code_nodes"] = [node]
    updated["dependencies"]["operators"][tools[1]]["requires"] = [
        {"output": tools[0], "kind": "acquisition"}]
    updated["code_dag"] = {"nodes": [tools[0], code_id, tools[1]],
                           "edges": [[tools[0], code_id], [code_id, tools[1]]]}
    updated["certified_digest"] = artifact_signature(updated)
    _validate_artifact(updated, contracts)
    return updated
