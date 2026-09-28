"""Conservative MotifAgent-style operator compilation from successful traces.

This is the deterministic read-only slice of the frozen operatorizer and
dependency compiler. A mined sequence is only a candidate. Parameter transfer
is compiled when the same unique output field explains a required argument in
distinct tasks and a held-out task. Unproved arguments remain entry slots.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping


_FIELD = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.(?:[A-Za-z_][A-Za-z0-9_]*|[0-9]+))*$")


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8")).hexdigest()


def artifact_signature(artifact: dict[str, Any]) -> str:
    return _digest({key: value for key, value in artifact.items()
                    if key != "certified_digest"})


def contract_signature(tools: list[str], contracts: Mapping[str, Any]) -> str:
    rows = []
    for index, name in enumerate(tools):
        contract = contracts.get(name.rstrip("+"))
        if contract is None or not contract.read_only:
            raise ValueError(f"tool lacks a read-only contract: {name}")
        if not contract.replay_stable and not (
                index == 0 and contract.observed_anchor and len(tools) == 2):
            raise ValueError(f"tool lacks replay-stable observations: {name}")
        if contract.observed_anchor and (index != 0 or contract.replay_stable):
            raise ValueError(f"observed anchor must be an unstable first tool: {name}")
        fields = list(contract.output_fields)
        if any(not _FIELD.fullmatch(field) for field in fields):
            raise ValueError(f"invalid output field contract: {name}")
        collections = list(contract.collection_params)
        if (len(collections) != len(set(collections))
                or any(field not in contract.required_params for field in collections)):
            raise ValueError(f"invalid collection parameter contract: {name}")
        row = {"tool": name, "required_params": list(contract.required_params),
               "read_only": True, "output_fields": fields}
        if contract.observed_anchor:
            row["observed_anchor"] = True
        if collections:
            row["collection_params"] = collections
        shapes = dict(contract.parameter_shapes)
        if shapes:
            if (set(shapes) - set(contract.required_params)
                    or any(value not in {"string_list_allow_empty", "measure_list"}
                           for value in shapes.values())):
                raise ValueError(f"invalid parameter shapes: {name}")
            row["parameter_shapes"] = shapes
        defaults = dict(contract.default_params)
        if defaults:
            if (len(defaults) != len(contract.default_params)
                    or set(defaults) & set(contract.required_params)
                    or any(value is None or isinstance(value, (list, dict))
                           for value in defaults.values())):
                raise ValueError(f"invalid default parameter contract: {name}")
            row["default_params"] = defaults
        default_only = list(contract.witness_default_only)
        if default_only:
            if (len(default_only) != len(set(default_only))
                    or not set(default_only) <= set(defaults)):
                raise ValueError(f"invalid witness default restriction: {name}")
            row["witness_default_only"] = default_only
        rows.append(row)
    return _digest(rows)


def _occurrence(trace: Any, tools: list[str]) -> list[Any]:
    records = list(trace.records)
    matches = [records[index:index + len(tools)]
               for index in range(len(records) - len(tools) + 1)
               if all(row.eligible and row.name == name
                      for row, name in zip(records[index:index + len(tools)], tools))]
    if len(matches) != 1:
        raise ValueError(f"trace {trace.trace_id} needs exactly one safe motif occurrence")
    return matches[0]


def _field_value(observation: dict[str, Any] | None, path: str) -> Any:
    value: Any = observation
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list) and part.isdecimal() and int(part) < len(value):
            value = value[int(part)]
        else:
            return None
    if value in (None, "", []) or isinstance(value, dict):
        return None
    if isinstance(value, list) and any(
            item in (None, "") or isinstance(item, (list, dict))
            for item in value):
        return None
    return value


def _valid_param(value: Any, *, collection: bool, shape: str = "") -> bool:
    if shape == "string_list_allow_empty":
        return isinstance(value, list) and all(isinstance(item, str) and item
                                               for item in value)
    if shape == "measure_list":
        return (isinstance(value, list) and 1 <= len(value) <= 8
                and all(isinstance(item, dict) and isinstance(item.get("name"), str)
                        and item.get("name") and isinstance(item.get("op"), str)
                        and item.get("op") for item in value))
    if collection:
        return (isinstance(value, list) and bool(value)
                and all(item not in (None, "") and not isinstance(item, (list, dict))
                        for item in value))
    return value not in (None, "", []) and not isinstance(value, (list, dict))


def _matches_transfer(occurrences: list[list[Any]], *, source_index: int,
                      target_index: int, field: str, param: str) -> bool:
    values = []
    for rows in occurrences:
        source = _field_value(rows[source_index].observation, field)
        target = rows[target_index].arguments.get(param)
        declared_source = (rows[target_index].parameter_sources or {}).get(param)
        if declared_source != {"from_tool": rows[source_index].name,
                               "from_field": field}:
            return False
        if (source is None or target is None or type(source) is not type(target)
                or source != target):
            return False
        values.append(source)
    # A constant coincidence across all training tasks is insufficient to
    # infer a reusable parameter edge.
    return len({_digest(value) for value in values}) >= 2


def compile_read_motif(candidate: dict[str, Any], traces: list[Any],
                       contracts: Mapping[str, Any]) -> dict[str, Any]:
    """Compile a mined candidate, never authorize it for execution yet."""
    tools = list(candidate.get("tools") or [])
    trace_ids = list(candidate.get("source_trace_ids") or [])
    if (candidate.get("status") != "candidate_only" or len(tools) < 2
            or any(not isinstance(name, str) or name.endswith("+") for name in tools)
            or len(set(tools)) != len(tools)
            or len(trace_ids) < 2 or len(set(trace_ids)) != len(trace_ids)):
        raise ValueError("compiler needs a non-repeated, independently mined read motif")
    signature = contract_signature(tools, contracts)
    by_id = {trace.trace_id: trace for trace in traces}
    if len(by_id) != len(traces) or not set(trace_ids) <= set(by_id):
        raise ValueError("supporting trace IDs are missing or repeated")
    selected = [by_id[key] for key in trace_ids]
    fingerprints = [trace.task_fingerprint for trace in selected]
    if any(not value for value in fingerprints) or len(set(fingerprints)) != len(fingerprints):
        raise ValueError("support must come from distinct identified tasks")
    occurrences = [_occurrence(trace, tools) for trace in selected]
    operators: dict[str, dict[str, Any]] = {}
    transfer_evidence = []
    for index, name in enumerate(tools):
        required = list(contracts[name].required_params)
        if len(required) != len(set(required)):
            raise ValueError("duplicate required parameter in tool contract")
        for rows in occurrences:
            arguments = rows[index].arguments
            if not isinstance(arguments, dict) or any(
                key not in arguments or not _valid_param(
                    arguments[key], collection=key in contracts[name].collection_params,
                    shape=dict(contracts[name].parameter_shapes).get(key, ""))
                for key in required
            ):
                raise ValueError("supporting trace lacks a valid required parameter")
        bindings = []
        parents = []
        for param in required:
            matches = [(prior, field) for prior in range(index)
                       for field in contracts[tools[prior]].output_fields
                       if _matches_transfer(occurrences, source_index=prior,
                                            target_index=index, field=field, param=param)]
            if len(matches) != 1:
                continue
            prior, field = matches[0]
            parent = tools[prior]
            bindings.append({"from_tool": parent, "from_field": field,
                             "to_param": param})
            if parent not in parents:
                parents.append(parent)
            transfer_evidence.append({"from_tool": parent, "from_field": field,
                                      "to_tool": name, "to_param": param,
                                      "supporting_trace_ids": trace_ids})
        operators[name] = {
            "tool": name, "read_only": True, "required_params": required,
            "requires": [{"output": parent, "kind": "acquisition"} for parent in parents],
            "bindings": bindings,
        }
        if contracts[name].parameter_shapes:
            operators[name]["parameter_shapes"] = dict(contracts[name].parameter_shapes)
        if contracts[name].default_params:
            operators[name]["default_params"] = dict(contracts[name].default_params)
        if contracts[name].collection_params:
            operators[name]["collection_params"] = list(contracts[name].collection_params)
    return {
        "schema_version": 1, "motif_id": candidate["motif_id"],
        "status": "compiled_candidate", "tools": tools,
        "source_trace_ids": trace_ids,
        "source_task_fingerprints": fingerprints,
        "contract_signature": signature,
        "dependencies": {"required_evidence": tools, "operators": operators},
        "transfer_evidence": transfer_evidence,
    }


def certify_read_motif(compiled: dict[str, Any], heldout_trace: Any,
                       contracts: Mapping[str, Any]) -> dict[str, Any]:
    """Check parameter transfers on an unseen task before read-only execution."""
    tools = list(compiled.get("tools") or [])
    if (compiled.get("status") != "compiled_candidate"
            or compiled.get("contract_signature") != contract_signature(tools, contracts)
            or heldout_trace.trace_id in compiled.get("source_trace_ids", [])
            or not heldout_trace.task_fingerprint
            or heldout_trace.task_fingerprint in compiled.get("source_task_fingerprints", [])):
        raise ValueError("held-out Motif certification has stale or reused provenance")
    rows = _occurrence(heldout_trace, tools)
    for index, name in enumerate(tools):
        arguments = rows[index].arguments
        if not isinstance(arguments, dict) or any(
            param not in arguments or not _valid_param(
                arguments[param], collection=param in contracts[name].collection_params,
                shape=dict(contracts[name].parameter_shapes).get(param, ""))
            for param in contracts[name].required_params
        ):
            raise ValueError("held-out trace lacks a valid required parameter")
        for binding in compiled["dependencies"]["operators"][name]["bindings"]:
            prior = tools.index(binding["from_tool"])
            source = _field_value(rows[prior].observation, binding["from_field"])
            target = rows[index].arguments.get(binding["to_param"])
            declared_source = (rows[index].parameter_sources or {}).get(binding["to_param"])
            if (declared_source != {"from_tool": binding["from_tool"],
                                   "from_field": binding["from_field"]}
                    or source is None or type(source) is not type(target) or source != target):
                raise ValueError("held-out trace contradicts compiled parameter transfer")
    certified = {**compiled, "status": "trace_validated_read_only",
                 "validation_trace_id": heldout_trace.trace_id,
                 "validation_task_fingerprint": heldout_trace.task_fingerprint}
    certified["certified_digest"] = artifact_signature(certified)
    return certified
