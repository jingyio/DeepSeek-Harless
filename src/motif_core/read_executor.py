"""Verified read-only Motif execution on the migrated MotifAgent runtime.

This uses the frozen runtime's evidence, dependency and frame semantics. The
tool client is supplied by the host; only trace-validated operators may run.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .context_manager import MotifContextManager
from .dependencies import resolve_dependencies
from .failure_feedback import dependency_failure_witness
from .offline.failure_evolution import active_guard_matches, validate_active_guard
from .handoff import (
    SemanticResolution, StructureHandoffRequest,
    build_blocking_precheck_handoff, build_runtime_failure_handoff,
)
from .offline.trace_compiler import artifact_signature, contract_signature
from .offline.local_programs import compile_local_programs
from .pure_code import validate_expression


def _signature(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8")).hexdigest()


def _validate_artifact(artifact: dict[str, Any], contracts: Mapping[str, Any]) -> list[str]:
    tools = list(artifact.get("tools") or [])
    repeated = bool(tools and tools[-1].endswith("+"))
    if (artifact.get("status") != "trace_validated_read_only"
            or len(tools) < 2 or len(set(tools)) != len(tools)
            or (repeated and (len(tools) != 2 or tools[0].endswith("+")
                              or tools[0] == tools[1][:-1]))
            or (not repeated and any(name.endswith("+") for name in tools))
            or artifact.get("certified_digest") != artifact_signature(artifact)
            or artifact.get("contract_signature") != contract_signature(tools, contracts)):
        raise ValueError("Motif is not a current trace-validated read-only artifact")
    if repeated and (len(contracts[tools[0]].output_fields) != 1
                     or len(contracts[tools[1][:-1]].required_params) != 1):
        raise ValueError("repeated Motif contract no longer has one list frontier")
    graph = artifact.get("dependencies") or {}
    operators = graph.get("operators") or {}
    code_nodes = artifact.get("code_nodes", [])
    if code_nodes:
        from .offline.dynamic_code_nodes import code_node_body
        if (repeated or len(tools) != 2 or len(code_nodes) != 1
                or graph.get("code_nodes") != code_nodes):
            raise ValueError("Motif code graph is unsupported or changed")
        code = code_nodes[0]
        if (not isinstance(code, dict) or not all(key in code for key in (
                "kind", "language", "expression", "from_tool", "from_field",
                "to_tool", "to_param", "node_id", "program_digest"))):
            raise ValueError("Motif code node is incomplete")
        validate_expression(code["expression"])
        body = code_node_body(code)
        if (code.get("kind") != "pure_code"
                or code.get("language") != "sss-pure-python-expr-v1"
                or code.get("program_digest") != _signature(body)
                or code.get("node_id") != "code_" + _signature(body)[:16]
                or code.get("from_tool") != tools[0]
                or code.get("to_tool") != tools[1]
                or code.get("from_field") not in contracts[tools[0]].output_fields
                or code.get("to_param") not in contracts[tools[1]].required_params
                or code.get("source_trace_ids") != artifact["source_trace_ids"]
                or code.get("source_task_fingerprints")
                   != artifact["source_task_fingerprints"]
                or code.get("validation_trace_id") != artifact["validation_trace_id"]
                or code.get("validation_task_fingerprint")
                   != artifact["validation_task_fingerprint"]
                or any(edge["to_param"] == code["to_param"]
                       for edge in artifact["transfer_evidence"])
                or artifact.get("code_dag") != {
                    "nodes": [tools[0], code["node_id"], tools[1]],
                    "edges": [[tools[0], code["node_id"]],
                              [code["node_id"], tools[1]]]}
        ):
            raise ValueError("Motif code node differs from its certified gap")
    elif graph.get("code_nodes") or artifact.get("code_dag"):
        raise ValueError("Motif has an unbound code graph")
    if graph.get("required_evidence") != tools or set(operators) != set(tools):
        raise ValueError("Motif operator graph does not match its execution plan")
    for index, name in enumerate(tools):
        node = operators[name]
        base = name.rstrip("+")
        if (node.get("tool") != name or node.get("read_only") is not True
                or node.get("required_params") != list(contracts[base].required_params)
                or node.get("collection_params", []) != list(contracts[base].collection_params)
                or node.get("parameter_shapes", {}) != dict(contracts[base].parameter_shapes)
                or node.get("default_params", {}) != dict(contracts[base].default_params)):
            raise ValueError("Motif operator contract changed")
        expected_parents = []
        for edge in node.get("bindings", []):
            parent = edge.get("from_tool")
            if (parent not in tools[:index]
                    or edge.get("from_field") not in contracts[parent.rstrip("+")].output_fields
                    or edge.get("to_param") not in contracts[base].required_params):
                raise ValueError("Motif parameter edge is unsupported")
            if parent not in expected_parents:
                expected_parents.append(parent)
        if (code_nodes and name == code_nodes[0]["to_tool"]
                and code_nodes[0]["from_tool"] not in expected_parents):
            expected_parents.append(code_nodes[0]["from_tool"])
        if repeated and index == 1:
            frontier_rows = node.get("selection_frontiers") or []
            policy = (frontier_rows[0].get("policy")
                      if len(frontier_rows) == 1 and isinstance(frontier_rows[0], dict)
                      else None)
            expected_frontier = {
                "status": "verified", "policy": policy,
                "from_tool": tools[0],
                "from_field": contracts[tools[0]].output_fields[0],
                "to_tool": name,
                "to_param": contracts[base].required_params[0],
            }
            if (node.get("bindings") != []
                    or policy not in {"all_candidates", "bounded_subset"}
                    or node.get("selection_frontiers") != [expected_frontier]
                    or node.get("requires") != [{"output": tools[0],
                                                   "kind": "precondition"}]):
                raise ValueError("repeated read frontier differs from certified evidence")
        elif node.get("requires") != [
            {"output": parent, "kind": "acquisition"} for parent in expected_parents
        ]:
            raise ValueError("Motif dependencies differ from verified parameter edges")
    declared = [{"from_tool": edge["from_tool"], "from_field": edge["from_field"],
                 "to_tool": name, "to_param": edge["to_param"],
                 "supporting_trace_ids": artifact["source_trace_ids"]}
                for name in tools
                for edge in operators[name].get("bindings", [])]
    if artifact.get("transfer_evidence") != declared:
        raise ValueError("Motif transfer evidence differs from executable bindings")
    selection = ([{**operators[tools[1]]["selection_frontiers"][0],
                   "supporting_trace_ids": artifact["source_trace_ids"]}]
                 if repeated else [])
    if artifact.get("selection_evidence", []) != selection:
        raise ValueError("Motif selection evidence differs from repeat frontier")
    dag = artifact.get("dag")
    if ("local_programs" in artifact
            and artifact["local_programs"] != compile_local_programs(artifact)):
        raise ValueError("Motif local code differs from certified parameter edges")
    if dag is not None and dag != {
        "nodes": tools,
        "order_edges": [[tools[index], tools[index + 1]]
                        for index in range(len(tools) - 1)],
        "parameter_edges": [[row["from_tool"], row["to_tool"]]
                            for row in declared + selection],
        "parallel_groups": [[name] for name in tools],
    }:
        raise ValueError("Motif DAG differs from its certified operator order")
    return tools


@dataclass
class ReadMotifRun:
    status: str
    motif_id: str
    bindings: dict[str, dict[str, Any]]
    input_version: str
    revision: int
    manager: MotifContextManager
    outputs: dict[str, Any]
    events: list[dict[str, Any]]
    handoff: StructureHandoffRequest | None = None
    failure_witness: dict[str, Any] | None = None
    node_versions: dict[str, str] | None = None


def run_read_motif(
    artifact: dict[str, Any], *, contracts: Mapping[str, Any],
    bindings: dict[str, dict[str, Any]], input_version: str,
    execute_tool: Callable[[str, dict[str, Any]], Any],
    verify_current: Callable[[], None],
    is_read_only: Callable[[str], bool],
    manager: MotifContextManager | None = None, revision: int = 1,
    active_guards: tuple[dict[str, Any], ...] = (),
    node_versions: Mapping[str, str] | None = None,
) -> ReadMotifRun:
    """Advance verified graph nodes; return a typed handoff on a local gap."""
    tools = _validate_artifact(artifact, contracts)
    versions = (dict(node_versions) if node_versions is not None
                else {tool: input_version for tool in tools})
    if (set(versions) != set(tools)
            or any(not isinstance(value, str) or not value for value in versions.values())):
        raise ValueError("Motif needs a current version for every operator")
    for guard in active_guards:
        validate_active_guard(guard, artifact)
    if not input_version or revision < 1 or set(bindings) - set(tools):
        raise ValueError("Motif input version or tool bindings are invalid")
    for name, params in bindings.items():
        if (not isinstance(params, dict) or set(params) -
                (set(contracts[name.rstrip("+")].required_params)
                 | set(dict(contracts[name.rstrip("+")].default_params)))):
            raise ValueError("Motif binding contains an unsupported parameter")
    verify_current()
    manager = manager or MotifContextManager()
    motif_id = str(artifact["motif_id"])
    frame = manager.activate_motif(
        motif_id, execution_plan=tools, plan_step=0, motif_tools=set(tools))
    events: list[dict[str, Any]] = []

    def emit(event: str, **payload: Any) -> None:
        events.append({"event": event, **payload})

    def checked_execute(tool: str, params: dict[str, Any]) -> Any:
        verify_current()
        if not is_read_only(tool.rstrip("+")):
            raise ValueError("tool lost its read-only authorization")
        return execute_tool(tool.rstrip("+"), params)

    effective_versions = dict(versions)
    for code in artifact.get("code_nodes", []):
        target = code["to_tool"]
        effective_versions[target] = _signature(
            [versions[target], code["program_digest"]])
    result = resolve_dependencies(
        artifact["dependencies"], manager.evidence, bindings,
        checked_execute, lambda tool: is_read_only(tool.rstrip("+")), emit,
        guard=lambda tool, params: not any(active_guard_matches(
            item, artifact, operator=tool,
            binding_signature=_signature(params), input_version=input_version)
            for item in active_guards), node_versions=effective_versions)
    outputs = {name: manager.evidence.get(name) for name in tools
               if name in manager.evidence}
    if result.status == "SUCCESS":
        frame.completed_tools.update(tools)
        frame.tool_results.update(outputs)
        manager.add_completed_motif(motif_id, outputs)
        return ReadMotifRun("completed", motif_id, bindings, input_version,
                            revision, manager, outputs, events,
                            node_versions=versions)

    missing = {result.tool: list(result.missing)} if result.missing else {}
    available = {"artifact_signature": artifact["certified_digest"],
                 "binding_signature": _signature(bindings),
                 "completed_outputs_signature": _signature(outputs),
                 "input_version": input_version,
                 "node_version_signature": _signature(versions),
                 "blocked_operator": result.tool}
    if result.candidates and result.tool and result.missing:
        available["candidate_values"] = {
            result.tool: {result.missing[0]: list(result.candidates)}}
        if result.candidate_mode:
            available["candidate_value_modes"] = {
                result.tool: {result.missing[0]: result.candidate_mode}}
        if result.candidate_details:
            available["candidate_details"] = {
                result.tool: {result.missing[0]: result.candidate_details}}
    if result.reason == "semantic_binding_required" and missing:
        handoff = build_blocking_precheck_handoff(
            motif_id=motif_id, missing_params=missing, available_state=available)
        status = "needs_mediation"
        witness = None
    else:
        handoff = build_runtime_failure_handoff(
            motif_id=motif_id, error_type="tool_error",
            available_state=available, reason=result.reason)
        status = "blocked"
        witness = dependency_failure_witness(
            motif_id=motif_id, result=result,
            metadata=artifact["dependencies"],
            binding=bindings.get(result.tool, {}), input_version=input_version)
    manager.suspend_motif(
        motif_id=motif_id, execution_plan=tools,
        plan_step=tools.index(result.tool) if result.tool in tools else 0,
        motif_tools=set(tools), completed_tools=set(outputs),
        tool_results=outputs, missing_params=missing, revision=revision)
    return ReadMotifRun(status, motif_id, bindings, input_version, revision,
                        manager, outputs, events, handoff, witness, versions)


def resume_read_motif(
    artifact: dict[str, Any], prior: ReadMotifRun,
    resolution: SemanticResolution, *, contracts: Mapping[str, Any],
    execute_tool: Callable[[str, dict[str, Any]], Any],
    verify_current: Callable[[], None],
    is_read_only: Callable[[str], bool],
    active_guards: tuple[dict[str, Any], ...] = (),
) -> ReadMotifRun:
    """Accept only values for the blocked slots, then reenter the same graph."""
    request = prior.handoff
    if (prior.status != "needs_mediation" or request is None
            or request.motif_id != artifact.get("motif_id")
            or request.allowed_reentry.get("mode") != "same_motif"
            or request.available_state.get("artifact_signature") != artifact.get("certified_digest")
            or request.available_state.get("binding_signature") != _signature(prior.bindings)
            or request.available_state.get("completed_outputs_signature")
            != _signature(prior.outputs)
            or request.available_state.get("input_version") != prior.input_version
            or request.available_state.get("node_version_signature")
            != _signature(prior.node_versions)
            or resolution.resolution_type != "slot_fill"
            or resolution.metadata.get("handoff_signature") != _signature(request.to_dict())):
        raise ValueError("semantic resolution cannot reenter this Motif")
    expected = request.missing_params
    values = resolution.slot_values
    def valid_slot(tool: str, param: str, value: Any) -> bool:
        scoped = (request.available_state.get("candidate_values") or {}).get(tool, {}).get(param)
        if scoped is not None:
            mode = ((request.available_state.get("candidate_value_modes") or {})
                    .get(tool, {}).get(param))
            if mode == "one_of":
                return any(type(item) is type(value) and item == value for item in scoped)
            return (isinstance(value, list) and bool(value)
                    and [item for item in scoped if any(type(item) is type(chosen)
                                                        and item == chosen for chosen in value)]
                    == value)
        shape = dict(contracts[tool.rstrip("+")].parameter_shapes).get(param)
        if shape == "string_list_allow_empty":
            return isinstance(value, list) and all(isinstance(item, str) and item
                                                   for item in value)
        if shape == "measure_list":
            return (isinstance(value, list) and 1 <= len(value) <= 8
                    and all(isinstance(item, dict) and isinstance(item.get("name"), str)
                            and item.get("name") and isinstance(item.get("op"), str)
                            and item.get("op") for item in value))
        if param in contracts[tool.rstrip("+")].collection_params:
            return (isinstance(value, list) and bool(value)
                    and all(item not in (None, "") and not isinstance(item, (list, dict))
                            for item in value))
        return value not in (None, "", []) and not isinstance(value, (list, dict))
    if set(values) != set(expected) or any(
        not isinstance(values[tool], dict) or set(values[tool]) != set(params)
        or any(not valid_slot(tool, param, value)
               for param, value in values[tool].items())
        for tool, params in expected.items()
    ):
        raise ValueError("semantic resolution contains missing or unauthorized slots")
    verify_current()
    next_bindings = {tool: dict(params) for tool, params in prior.bindings.items()}
    for tool, params in values.items():
        next_bindings.setdefault(tool, {}).update(params)
    frame = prior.manager.mark_resumed(prior.motif_id, prior.revision + 1)
    if frame is None:
        raise ValueError("Motif frame is no longer suspended")
    for tool, params in values.items():
        for param, value in params.items():
            frame.validate_slot(tool, param, value,
                                dependency_signatures=(prior.input_version,))
    return run_read_motif(
        artifact, contracts=contracts, bindings=next_bindings,
        input_version=prior.input_version, execute_tool=execute_tool,
        verify_current=verify_current, is_read_only=is_read_only,
        manager=prior.manager, revision=prior.revision + 1,
        active_guards=active_guards, node_versions=prior.node_versions)
