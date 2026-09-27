"""Compose two witnessed read edges only when they share the same middle call.

This compiles a three-node partial dependency graph from actual DSH traces.
Interleaved safe reads may remain between nodes, but no failed or unapproved
call may be crossed. Semantic entry arguments stay as runtime slots.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .edge_compiler import _check_candidate, _witnesses, compile_witnessed_edge_motif
from .trace_compiler import artifact_signature, contract_signature


def _chains(trace: Any, first: dict[str, Any], second: dict[str, Any],
            contracts: Mapping[str, Any]) -> list[tuple[Any, Any, Any]]:
    left = _witnesses(trace, first, contracts)
    right = _witnesses(trace, second, contracts)
    return [(source, middle, target)
            for source, middle in left for next_middle, target in right
            if middle is next_middle]


def _operator(name: str, contracts: Mapping[str, Any], *, parent: str | None = None,
              field: str = "", param: str = "") -> dict[str, Any]:
    contract = contracts[name]
    row = {"tool": name, "read_only": True,
           "required_params": list(contract.required_params),
           "requires": ([{"output": parent, "kind": "acquisition"}] if parent else []),
           "bindings": ([{"from_tool": parent, "from_field": field,
                          "to_param": param}] if parent else [])}
    if contract.collection_params:
        row["collection_params"] = list(contract.collection_params)
    if contract.parameter_shapes:
        row["parameter_shapes"] = dict(contract.parameter_shapes)
    if contract.default_params:
        row["default_params"] = dict(contract.default_params)
    return row


def compile_witnessed_chain_motif(first: dict[str, Any], second: dict[str, Any],
                                  traces: list[Any], contracts: Mapping[str, Any]
                                  ) -> dict[str, Any]:
    """Compile three read nodes from two independently mined causal edges."""
    source, middle = _check_candidate(first, contracts)
    next_middle, target = _check_candidate(second, contracts)
    if middle != next_middle or len({source, middle, target}) != 3:
        raise ValueError("candidate edges do not form a three-node chain")
    trace_ids = sorted(set(first.get("source_trace_ids") or []) &
                       set(second.get("source_trace_ids") or []))
    by_id = {trace.trace_id: trace for trace in traces}
    if (len(trace_ids) < 2 or len(by_id) != len(traces)
            or not set(trace_ids) <= set(by_id)):
        raise ValueError("chain needs two distinct shared supporting traces")
    selected = [by_id[trace_id] for trace_id in trace_ids]
    fingerprints = [trace.task_fingerprint for trace in selected]
    if not all(fingerprints) or len(set(fingerprints)) != len(fingerprints):
        raise ValueError("chain support must come from distinct tasks")
    first_scoped = {**first, "source_trace_ids": trace_ids}
    second_scoped = {**second, "source_trace_ids": trace_ids}
    compile_witnessed_edge_motif(first_scoped, selected, contracts)
    compile_witnessed_edge_motif(second_scoped, selected, contracts)
    matches = [_chains(trace, first, second, contracts) for trace in selected]
    if any(not group for group in matches):
        raise ValueError("edge witnesses do not share one safe middle invocation")
    tools = [source, middle, target]
    key = json.dumps({"tools": tools,
                      "edges": [[first["from_field"], first["to_param"]],
                                [second["from_field"], second["to_param"]]],
                      "traces": trace_ids}, sort_keys=True, separators=(",", ":"))
    binding_a = {"from_tool": source, "from_field": first["from_field"],
                 "to_tool": middle, "to_param": first["to_param"],
                 "supporting_trace_ids": trace_ids}
    binding_b = {"from_tool": middle, "from_field": second["from_field"],
                 "to_tool": target, "to_param": second["to_param"],
                 "supporting_trace_ids": trace_ids}
    return {
        "schema_version": 1,
        "motif_id": "chain_motif_" + hashlib.sha256(key.encode()).hexdigest()[:12],
        "status": "compiled_candidate", "mining_basis": "witnessed_parameter_chain",
        "argument_scope": "required_and_declared_defaults", "tools": tools,
        "source_trace_ids": trace_ids,
        "source_task_fingerprints": fingerprints,
        "contract_signature": contract_signature(tools, contracts),
        "dependencies": {"required_evidence": tools, "operators": {
            source: _operator(source, contracts),
            middle: _operator(middle, contracts, parent=source,
                              field=first["from_field"], param=first["to_param"]),
            target: _operator(target, contracts, parent=middle,
                              field=second["from_field"], param=second["to_param"]),
        }},
        "transfer_evidence": [binding_a, binding_b],
        "witness_counts": {trace.trace_id: len(group)
                           for trace, group in zip(selected, matches)},
    }


def certify_witnessed_chain_motif(compiled: dict[str, Any], heldout_trace: Any,
                                  contracts: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the complete chain on a different task; answer quality is separate."""
    tools = list(compiled.get("tools") or [])
    if (compiled.get("status") != "compiled_candidate" or len(tools) != 3
            or compiled.get("mining_basis") != "witnessed_parameter_chain"
            or compiled.get("contract_signature") != contract_signature(tools, contracts)
            or heldout_trace.trace_id in compiled.get("source_trace_ids", [])
            or not heldout_trace.task_fingerprint
            or heldout_trace.task_fingerprint in compiled.get("source_task_fingerprints", [])):
        raise ValueError("held-out chain certification has stale or reused provenance")
    operators = compiled["dependencies"]["operators"]
    first_binding = operators[tools[1]]["bindings"][0]
    second_binding = operators[tools[2]]["bindings"][0]
    first = {"status": "candidate_only", "from_tool": tools[0],
             "from_field": first_binding["from_field"], "to_tool": tools[1],
             "to_param": first_binding["to_param"]}
    second = {"status": "candidate_only", "from_tool": tools[1],
              "from_field": second_binding["from_field"], "to_tool": tools[2],
              "to_param": second_binding["to_param"]}
    if not _chains(heldout_trace, first, second, contracts):
        raise ValueError("held-out trace lacks a safe connected chain")
    certified = {**compiled, "status": "trace_validated_read_only",
                 "validation_trace_id": heldout_trace.trace_id,
                 "validation_task_fingerprint": heldout_trace.task_fingerprint}
    certified["certified_digest"] = artifact_signature(certified)
    return certified
