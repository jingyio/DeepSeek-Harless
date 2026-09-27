"""Certify an observed source -> repeated-read Motif with exact list flow.

This is a narrow, evidence-backed adaptation of MotifAgent's verified repeat
frontier. It never infers a user-selected subset from the source list. Such a
choice remains a semantic gap until separately validated.
"""

from __future__ import annotations

from typing import Any, Mapping

from .trace_compiler import artifact_signature, contract_signature


def _list_path(observation: Any, path: str) -> list[Any] | None:
    value = observation
    for part in path.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    if (not isinstance(value, list) or len(value) < 2
            or any(item in (None, "") or isinstance(item, (list, dict)) for item in value)
            or len({str(item) for item in value}) != len(value)):
        return None
    return value


def _occurrence(trace: Any, source: str, repeated: str) -> tuple[Any, list[Any]]:
    records = list(trace.records)
    found: list[tuple[Any, list[Any]]] = []
    for index, row in enumerate(records):
        if not row.eligible or row.name != source:
            continue
        end = index + 1
        while end < len(records) and records[end].eligible and records[end].name == repeated:
            end += 1
        if end - index >= 3:
            found.append((row, records[index + 1:end]))
    if len(found) != 1:
        raise ValueError("repeat Motif needs one safe source and repeated-read occurrence")
    return found[0]


def _verify(trace: Any, source: str, repeated: str, source_param: str,
            repeat_param: str, output_field: str) -> tuple[list[Any], list[Any]]:
    first, calls = _occurrence(trace, source, repeated)
    if (not isinstance(first.arguments, dict)
            or set(first.arguments) != {source_param}
            or first.arguments.get(source_param) in (None, "", [])
            or isinstance(first.arguments[source_param], (list, dict))):
        raise ValueError("repeat source lacks a valid entry binding")
    values = _list_path(first.observation, output_field)
    if values is None or len(calls) > len(values):
        raise ValueError("repeat source list does not match observed calls")
    selected = [call.arguments.get(repeat_param) if isinstance(call.arguments, dict)
                else None for call in calls]
    if (len({str(item) for item in selected}) != len(selected)
            or [item for item in values if any(type(item) is type(chosen)
                                              and item == chosen for chosen in selected)]
            != selected):
        raise ValueError("repeated reads are not an ordered source subset")
    for call, expected in zip(calls, selected):
        if (not isinstance(call.arguments, dict)
                or set(call.arguments) != {repeat_param}
                or type(call.arguments[repeat_param]) is not type(expected)
                or call.arguments[repeat_param] != expected
                or (call.parameter_sources or {}).get(repeat_param) != {
                    "from_tool": source, "from_field": output_field}):
            raise ValueError("repeated read lacks exact declared list provenance")
    return values, selected


def compile_repeat_read_motif(candidate: dict[str, Any], traces: list[Any],
                              contracts: Mapping[str, Any]) -> dict[str, Any]:
    tools = list(candidate.get("tools") or [])
    if (candidate.get("status") != "candidate_only" or len(tools) != 2
            or tools[0].endswith("+") or not tools[1].endswith("+")
            or tools[0] == tools[1][:-1]):
        raise ValueError("only a source followed by repeated reads can be compiled")
    source, token = tools
    repeated = token[:-1]
    source_contract, repeat_contract = contracts.get(source), contracts.get(repeated)
    if (source_contract is None or repeat_contract is None
            or not source_contract.read_only or not repeat_contract.read_only
            or len(source_contract.required_params) != 1
            or len(repeat_contract.required_params) != 1
            or len(source_contract.output_fields) != 1
            or source_contract.collection_params or repeat_contract.collection_params):
        raise ValueError("repeat Motif requires one source entry and one scalar read parameter")
    trace_ids = list(candidate.get("source_trace_ids") or [])
    by_id = {row.trace_id: row for row in traces}
    if (len(trace_ids) < 2 or len(set(trace_ids)) != len(trace_ids)
            or len(by_id) != len(traces) or not set(trace_ids) <= set(by_id)):
        raise ValueError("repeat Motif needs independent supporting traces")
    selected = [by_id[trace_id] for trace_id in trace_ids]
    fingerprints = [row.task_fingerprint for row in selected]
    if not all(fingerprints) or len(set(fingerprints)) != len(fingerprints):
        raise ValueError("repeat Motif support must cover distinct tasks")
    source_param = source_contract.required_params[0]
    repeat_param = repeat_contract.required_params[0]
    output_field = source_contract.output_fields[0]
    values = [_verify(row, source, repeated, source_param, repeat_param,
                      output_field) for row in selected]
    if len({str(row) for row in values}) < 2:
        raise ValueError("identical repeated lists do not prove reusable flow")
    policy = ("bounded_subset" if any(len(source_list) > len(chosen)
                                      for source_list, chosen in values)
              else "all_candidates")
    frontier = {"status": "verified", "policy": policy,
                "from_tool": source, "from_field": output_field,
                "to_tool": token, "to_param": repeat_param}
    return {
        "schema_version": 1, "motif_id": candidate["motif_id"],
        "status": "compiled_candidate", "tools": tools,
        "source_trace_ids": trace_ids,
        "source_task_fingerprints": fingerprints,
        "contract_signature": contract_signature(tools, contracts),
        "dependencies": {
            "required_evidence": tools,
            "operators": {
                source: {"tool": source, "read_only": True,
                         "required_params": [source_param], "requires": [],
                         "bindings": []},
                token: {"tool": token, "read_only": True,
                        "required_params": [repeat_param],
                        "requires": [{"output": source, "kind": "precondition"}],
                        "bindings": [], "selection_frontiers": [frontier]},
            },
        },
        "transfer_evidence": [],
        "selection_evidence": [{**frontier, "supporting_trace_ids": trace_ids}],
    }


def certify_repeat_read_motif(compiled: dict[str, Any], heldout_trace: Any,
                              contracts: Mapping[str, Any]) -> dict[str, Any]:
    source, token = compiled.get("tools", [None, None])
    if (compiled.get("status") != "compiled_candidate"
            or not isinstance(source, str) or not isinstance(token, str)
            or compiled.get("contract_signature")
            != contract_signature([source, token], contracts)
            or heldout_trace.trace_id in compiled.get("source_trace_ids", [])
            or not heldout_trace.task_fingerprint
            or heldout_trace.task_fingerprint in compiled.get("source_task_fingerprints", [])):
        raise ValueError("held-out repeat provenance is stale or reused")
    frontier = compiled["dependencies"]["operators"][token]["selection_frontiers"][0]
    source_list, chosen = _verify(
        heldout_trace, source, token[:-1], contracts[source].required_params[0],
        frontier["to_param"], frontier["from_field"])
    if (frontier["policy"] == "all_candidates" and source_list != chosen
            or frontier["policy"] == "bounded_subset"
            and len(source_list) == len(chosen)):
        raise ValueError("held-out trace contradicts repeated selection policy")
    certified = {**compiled, "status": "trace_validated_read_only",
                 "validation_trace_id": heldout_trace.trace_id,
                 "validation_task_fingerprint": heldout_trace.task_fingerprint}
    certified["certified_digest"] = artifact_signature(certified)
    return certified
