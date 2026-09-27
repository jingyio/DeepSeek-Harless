"""确定性依赖求解：仅消费 artifact 和 Context，不调用模型或持有业务状态。"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable
from .evidence import BoundEvidence
from src.semantic_inputs import SemanticInputRequired


@dataclass(frozen=True)
class DependencyResult:
    status: str
    reason: str = ""
    tool: str = ""
    missing: tuple[str, ...] = ()
    error_class: str = ""
    candidates: tuple[Any, ...] = ()
    binding_signature: str = ""
    candidate_mode: str = ""
    candidate_details: dict[str, Any] | None = None


def resolve_dependencies(metadata: dict, evidence: dict, bindings: dict, execute: Callable,
                         is_read_only: Callable, emit: Callable,
                         guard: Callable[[str, dict[str, Any]], bool] | None = None,
                         node_versions: dict[str, str] | None = None,
                         ) -> DependencyResult:
    operators = metadata.get("operators", {})
    visiting: set[str] = set()
    resolved: dict[str, Any] = {}
    signatures: dict[str, str | None] = {}

    def repeat_param(node, params):
        repeated = [
            str(frontier.get("to_param") or "")
            for frontier in node.get("selection_frontiers", [])
            if isinstance(frontier, dict)
            and frontier.get("status") == "verified"
            and str(frontier.get("to_tool") or "").rstrip("+") == str(node.get("tool") or "").rstrip("+")
            and isinstance(params.get(str(frontier.get("to_param") or "")), list)
        ]
        return repeated[0] if len(repeated) == 1 else None

    def visit(tool):
        if tool in visiting:
            return DependencyResult("BLOCKED", "dependency_cycle", tool)
        node = operators.get(tool)
        if not node or not node.get("read_only") or not is_read_only(tool):
            return DependencyResult("BLOCKED", "unverified_dependency", tool)
        visiting.add(tool)
        try:
            params = dict(bindings.get(tool, {}))
            collection_params = set(node.get("collection_params", []))
            defaults = node.get("default_params", {})
            if any(key in params and type(params[key]) is not type(value)
                   for key, value in defaults.items()):
                return DependencyResult("BLOCKED", "default_binding_invalid", tool,
                                        tuple(defaults))
            for key, value in defaults.items():
                params.setdefault(key, value)
            param_shapes = node.get("parameter_shapes", {})
            missing = lambda: tuple(
                p for p in node.get("required_params", [])
                if p not in params or
                (params[p] in (None, "", []) and
                 not (param_shapes.get(p) == "string_list_allow_empty" and params[p] == [])))
            has_current_precondition = False
            for requirement in node.get("requires", []):
                parent = requirement if isinstance(requirement, str) else requirement["output"]
                kind = "precondition" if isinstance(requirement, str) else requirement.get("kind", "precondition")
                if kind not in {"acquisition", "precondition"}:
                    return DependencyResult("BLOCKED", "unknown_dependency_kind", tool)
                if kind == "precondition":
                    has_current_precondition = True
                result = visit(parent)
                if result.status != "SUCCESS":
                    return result
            for edge in node.get("bindings", []):
                value = resolved.get(edge["from_tool"])
                for part in edge["from_field"].split("."):
                    value = value.get(part) if isinstance(value, dict) else None
                if (value is not None and not isinstance(value, dict)
                        and (not isinstance(value, list)
                             or edge["to_param"] in collection_params)):
                    if edge["to_param"] in params and params[edge["to_param"]] != value:
                        return DependencyResult("BLOCKED", "conflicting_binding", tool, (edge["to_param"],))
                    params.setdefault(edge["to_param"], value)
            for frontier in node.get("selection_frontiers", []):
                if (frontier.get("status") != "verified"
                        or frontier.get("policy") not in {"all_candidates", "bounded_subset"}):
                    continue
                source = resolved.get(frontier["from_tool"])
                for part in frontier["from_field"].split("."):
                    source = source.get(part) if isinstance(source, dict) else None
                if (not isinstance(source, list) or len(source) < 2
                        or any(item in (None, "") or isinstance(item, (list, dict))
                               for item in source)
                        or len({str(item) for item in source}) != len(source)):
                    return DependencyResult("BLOCKED", "selection_evidence_missing", tool)
                param = frontier["to_param"]
                if frontier["policy"] == "all_candidates":
                    if param in params and params[param] != source:
                        return DependencyResult("BLOCKED", "conflicting_binding", tool, (param,))
                    params.setdefault(param, source)
                elif param not in params:
                    return DependencyResult("BLOCKED", "semantic_binding_required", tool,
                                            (param,), candidates=tuple(source))
                else:
                    chosen = params[param]
                    if (not isinstance(chosen, list) or not chosen
                            or len({str(item) for item in chosen}) != len(chosen)
                            or [item for item in source if any(type(item) is type(value)
                                                               and item == value for value in chosen)]
                            != chosen):
                        return DependencyResult("BLOCKED", "selection_binding_invalid",
                                                tool, (param,))
            repeated_param = repeat_param(node, params)
            list_params = [key for key, value in params.items() if isinstance(value, list)]
            if any(key in params and shape in {"string_list_allow_empty", "measure_list"}
                   and not isinstance(params[key], list)
                   for key, shape in param_shapes.items()):
                return DependencyResult("BLOCKED", "collection_binding_invalid", tool,
                                        tuple(param_shapes))
            if any(
                (not isinstance(params[key], list)
                 or any(not isinstance(item, str) or not item for item in params[key]))
                if param_shapes.get(key) == "string_list_allow_empty" else
                (not 1 <= len(params[key]) <= 8 or any(
                    not isinstance(item, dict) or not isinstance(item.get("name"), str)
                    or not item.get("name") or not isinstance(item.get("op"), str)
                    or not item.get("op") for item in params[key]))
                if param_shapes.get(key) == "measure_list" else
                (not params[key] or any(item in (None, "") or isinstance(item, (list, dict))
                                        for item in params[key]))
                for key in list_params):
                return DependencyResult("BLOCKED", "collection_binding_invalid", tool,
                                        tuple(list_params))
            if any(key not in collection_params and key != repeated_param
                   and key not in param_shapes
                   for key in list_params):
                return DependencyResult("BLOCKED", "collection_binding_unverified", tool, tuple(list_params))
            if missing():
                return DependencyResult("BLOCKED", "semantic_binding_required", tool, missing())
            cache_version = None
            if node_versions is not None:
                cache_version = hashlib.sha256(json.dumps({
                    "self": node_versions[tool],
                    "parents": [(row if isinstance(row, str) else row["output"],
                                 signatures[row if isinstance(row, str) else row["output"]])
                                for row in node.get("requires", [])],
                }, sort_keys=True, ensure_ascii=False,
                    separators=(",", ":")).encode()).hexdigest()
            if guard is not None and not guard(tool, params):
                return DependencyResult("BLOCKED", "active_negative_guard", tool)
            # A cached child result is usable only after current preconditions and
            # parameter-flow constraints have been checked.  Returning above the
            # requires loop would let an old result bypass a newly failed guard.
            # A precondition can change the meaning of a child result without
            # changing explicit parameters. Reuse it only when versioned
            # parent signatures are included in the child's cache key.
            if ((not has_current_precondition or node_versions is not None)
                    and repeated_param is None and isinstance(evidence, BoundEvidence)):
                cached = evidence.lookup(tool, params, version=cache_version)
                if cached is not None:
                    resolved[tool] = cached["value"]
                    signatures[tool] = cache_version
                    # The exact bound hit is now this invocation's output.
                    # A previous invocation of the same tool may have left a
                    # different value under the compatibility tool-name key.
                    dict.__setitem__(evidence, tool, cached["value"])
                    emit("dependency_cache_hit", tool=tool)
                    return DependencyResult("SUCCESS")
            invocations = [params]
            if repeated_param is not None:
                values = params.get(repeated_param) or []
                if not values or len({str(value) for value in values}) != len(values):
                    return DependencyResult("BLOCKED", "collection_binding_invalid", tool, (repeated_param,))
                invocations = [{**params, repeated_param: value} for value in values]
            payloads = []
            for invocation in invocations:
                cached = (evidence.lookup(tool, invocation, version=cache_version)
                          if isinstance(evidence, BoundEvidence) and (
                              not has_current_precondition or node_versions is not None)
                          else None)
                if cached is not None:
                    payloads.append(cached["value"])
                    continue
                try:
                    payload = execute(tool, invocation)
                except SemanticInputRequired as exc:
                    if (exc.parameter not in node.get("default_params", {})
                            or exc.parameter in bindings.get(tool, {})):
                        return DependencyResult("BLOCKED", "dependency_tool_error", tool,
                                                error_class=type(exc).__name__)
                    return DependencyResult("BLOCKED", "semantic_binding_required", tool,
                                            (exc.parameter,), candidates=exc.candidates,
                                            candidate_mode="one_of",
                                            candidate_details=exc.details)
                except Exception as exc:
                    return DependencyResult("BLOCKED", "dependency_tool_error", tool,
                                            error_class=type(exc).__name__,
                                            binding_signature=hashlib.sha256(json.dumps(
                                                invocation, sort_keys=True,
                                                ensure_ascii=False,
                                                separators=(",", ":")).encode()).hexdigest())
                if isinstance(evidence, BoundEvidence):
                    if not evidence.record(tool, invocation, payload,
                                           version=cache_version):
                        return DependencyResult("BLOCKED", "dependency_tool_error", tool,
                                                binding_signature=hashlib.sha256(json.dumps(
                                                    invocation, sort_keys=True,
                                                    ensure_ascii=False,
                                                    separators=(",", ":")).encode()).hexdigest())
                else:
                    evidence[tool] = payload
                payloads.append(payload)
            resolved[tool] = payloads if repeated_param is not None else payloads[0]
            signatures[tool] = cache_version
            if isinstance(evidence, BoundEvidence):
                dict.__setitem__(evidence, tool, resolved[tool])
            return DependencyResult("SUCCESS")
        finally:
            visiting.remove(tool)

    emit("dependency_resolve_start")
    for tool in metadata.get("required_evidence", []):
        result = visit(tool)
        if result.status != "SUCCESS":
            emit("dependency_blocked", reason=result.reason, tool=result.tool, missing=list(result.missing))
            return result
    emit("dependency_resolve_success")
    return DependencyResult("SUCCESS")
