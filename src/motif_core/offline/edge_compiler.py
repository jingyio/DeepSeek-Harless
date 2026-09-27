"""Compile a witnessed two-node read dependency from interleaved DSH calls.

This narrow compiler accepts a real parameter-flow edge, not a hand-authored
tool sequence. It accepts only contract-declared defaults. An unrelated failed
read may interleave; calls using the source handle, unknown or effectful calls
remain barriers.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .trace_compiler import artifact_signature, contract_signature


def _value(observation: dict[str, Any] | None, field: str) -> Any:
    value: Any = observation
    for part in field.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list) and part.isdecimal() and int(part) < len(value):
            value = value[int(part)]
        else:
            return None
    return value


def _argument_shape(arguments: Any, contract: Any) -> bool:
    if not isinstance(arguments, dict):
        return False
    required = set(contract.required_params)
    defaults = dict(contract.default_params)
    return (required <= set(arguments) <= required | set(defaults)
            and all(type(arguments[key]) is type(defaults[key])
                    for key in set(arguments) & set(defaults))
            and all(arguments.get(key, defaults[key]) == defaults[key]
                    for key in contract.witness_default_only))


def _safe_interleaving(records: list[Any], source_index: int, target_index: int,
                       handle: Any, contracts: Mapping[str, Any]) -> bool:
    """Allow unrelated failed reads, while retaining barriers on the same handle.

    Successful read-only calls may interleave freely. A failed read is irrelevant
    only when its declared contract is read-only and none of its arguments use
    the exact source handle. Unknown, effectful or malformed calls stay barriers.
    """
    for row in records[source_index + 1:target_index]:
        if row.eligible:
            continue
        contract = contracts.get(row.name)
        if (row.reason != "missing_or_failed_result" or contract is None
                or not contract.read_only or not isinstance(row.arguments, dict)
                or any(value == handle for value in row.arguments.values())):
            return False
    return True


def _witnesses(trace: Any, candidate: dict[str, Any], contracts: Mapping[str, Any]) -> list[Any]:
    source_name = candidate["from_tool"]
    target_name = candidate["to_tool"]
    source_field = candidate["from_field"]
    target_param = candidate["to_param"]
    records = list(trace.records)
    pairs = []
    for target_index, target in enumerate(records):
        if (not target.eligible or target.name != target_name
                or not _argument_shape(target.arguments, contracts[target_name])
                or (target.parameter_sources or {}).get(target_param) != {
                    "from_tool": source_name, "from_field": source_field}):
            continue
        possible = []
        for source_index, source in enumerate(records[:target_index]):
            if (not source.eligible or source.name != source_name
                    or not _argument_shape(source.arguments, contracts[source_name])):
                continue
            value = _value(source.observation, source_field)
            if (value is not None and not isinstance(value, (list, dict))
                    and type(value) is type(target.arguments[target_param])
                    and value == target.arguments[target_param]
                    and _safe_interleaving(records, source_index, target_index,
                                           value, contracts)):
                possible.append(source)
        if len(possible) == 1:
            pairs.append((possible[0], target))
    return pairs


def _check_candidate(candidate: dict[str, Any], contracts: Mapping[str, Any]) -> tuple[str, str]:
    source, target = candidate.get("from_tool"), candidate.get("to_tool")
    relation = candidate.get("version_relation", "same_source")
    if (candidate.get("status") != "candidate_only" or not isinstance(source, str)
            or not isinstance(target, str) or source == target
            or source not in contracts or target not in contracts
            or not contracts[source].read_only or not contracts[target].read_only
            or candidate.get("from_field") not in contracts[source].output_fields
            or candidate.get("to_param") not in contracts[target].required_params
            or relation not in {"same_source", "object_lookup"}
            or (relation == "object_lookup" and (
                candidate.get("to_param") != "object_id" or
                not str(candidate.get("from_field", "")).split(".")[-1].endswith("_id")))):
        raise ValueError("a witnessed read-only parameter edge is required")
    return source, target


def safe_edge_witnesses(candidate: dict[str, Any], trace: Any,
                        contracts: Mapping[str, Any]) -> list[tuple[Any, Any]]:
    """Return exact read edges; unrelated failed reads may interleave."""
    _check_candidate(candidate, contracts)
    return _witnesses(trace, candidate, contracts)


def count_safe_edge_witnesses(candidate: dict[str, Any], trace: Any,
                              contracts: Mapping[str, Any]) -> int:
    """Count exact, barrier-free witnesses without promoting a single-task edge."""
    return len(safe_edge_witnesses(candidate, trace, contracts))


def compile_witnessed_edge_motif(candidate: dict[str, Any], traces: list[Any],
                                 contracts: Mapping[str, Any]) -> dict[str, Any]:
    """Compile a safe candidate from two or more distinct real task traces."""
    source, target = _check_candidate(candidate, contracts)
    trace_ids = list(candidate.get("source_trace_ids") or [])
    by_id = {trace.trace_id: trace for trace in traces}
    if (len(trace_ids) < 2 or len(set(trace_ids)) != len(trace_ids)
            or len(by_id) != len(traces) or not set(trace_ids) <= set(by_id)):
        raise ValueError("edge compilation needs independent supporting traces")
    selected = [by_id[trace_id] for trace_id in trace_ids]
    fingerprints = [trace.task_fingerprint for trace in selected]
    if not all(fingerprints) or len(set(fingerprints)) != len(fingerprints):
        raise ValueError("supporting tasks must be distinct")
    matched = [_witnesses(trace, candidate, contracts) for trace in selected]
    if any(not pairs for pairs in matched):
        raise ValueError("a supporting trace lacks a safe exact-argument edge witness")
    observed_values = [_value(source_row.observation, candidate["from_field"])
                       for pairs in matched for source_row, _ in pairs]
    if len({str(value) for value in observed_values}) < 2:
        raise ValueError("constant values do not prove transferable parameter flow")
    motif_key = json.dumps({"edge": [source, candidate["from_field"], target,
                                      candidate["to_param"]], "traces": sorted(trace_ids)},
                           sort_keys=True, separators=(",", ":"))
    motif_id = "edge_motif_" + hashlib.sha256(motif_key.encode()).hexdigest()[:12]
    binding = {"from_tool": source, "from_field": candidate["from_field"],
               "to_param": candidate["to_param"]}
    if candidate.get("version_relation") == "object_lookup":
        binding["version_relation"] = "object_lookup"
    source_shapes = dict(contracts[source].parameter_shapes)
    target_shapes = dict(contracts[target].parameter_shapes)
    source_defaults = dict(contracts[source].default_params)
    target_defaults = dict(contracts[target].default_params)
    return {
        "schema_version": 1, "motif_id": motif_id,
        "status": "compiled_candidate", "mining_basis": "witnessed_parameter_edge",
        "argument_scope": "exact_required_arguments_only", "tools": [source, target],
        "source_trace_ids": trace_ids,
        "source_task_fingerprints": fingerprints,
        "contract_signature": contract_signature([source, target], contracts),
        "dependencies": {"required_evidence": [source, target], "operators": {
            source: {"tool": source, "read_only": True,
                     "required_params": list(contracts[source].required_params),
                     "requires": [], "bindings": [],
                     **({"parameter_shapes": source_shapes} if source_shapes else {}),
                     **({"default_params": source_defaults} if source_defaults else {})},
            target: {"tool": target, "read_only": True,
                     "required_params": list(contracts[target].required_params),
                     "requires": [{"output": source, "kind": "acquisition"}],
                     "bindings": [binding],
                     **({"parameter_shapes": target_shapes} if target_shapes else {}),
                     **({"default_params": target_defaults} if target_defaults else {})},
        }},
        "transfer_evidence": [{**binding, "to_tool": target,
                               "supporting_trace_ids": trace_ids}],
        "witness_counts": {trace.trace_id: len(pairs)
                           for trace, pairs in zip(selected, matched)},
    }


def certify_witnessed_edge_motif(compiled: dict[str, Any], heldout_trace: Any,
                                 contracts: Mapping[str, Any]) -> dict[str, Any]:
    """Certify parameter flow on an independent held-out trace, not answer quality."""
    tools = list(compiled.get("tools") or [])
    if (compiled.get("status") != "compiled_candidate" or len(tools) != 2
            or compiled.get("mining_basis") != "witnessed_parameter_edge"
            or compiled.get("contract_signature") != contract_signature(tools, contracts)
            or heldout_trace.trace_id in compiled.get("source_trace_ids", [])
            or not heldout_trace.task_fingerprint
            or heldout_trace.task_fingerprint in compiled.get("source_task_fingerprints", [])):
        raise ValueError("held-out edge certification has stale or reused provenance")
    binding = compiled["dependencies"]["operators"][tools[1]]["bindings"][0]
    candidate = {"status": "candidate_only", "from_tool": tools[0],
                 "from_field": binding["from_field"], "to_tool": tools[1],
                 "to_param": binding["to_param"],
                 **({"version_relation": binding["version_relation"]}
                    if "version_relation" in binding else {})}
    if not _witnesses(heldout_trace, candidate, contracts):
        raise ValueError("held-out trace lacks a safe exact-argument edge witness")
    certified = {**compiled, "status": "trace_validated_read_only",
                 "validation_trace_id": heldout_trace.trace_id,
                 "validation_task_fingerprint": heldout_trace.task_fingerprint}
    certified["certified_digest"] = artifact_signature(certified)
    return certified
