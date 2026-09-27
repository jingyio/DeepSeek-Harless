"""Parse approved MCP tool contracts identically for audit and compilation."""

from __future__ import annotations

from typing import Any

from .dsh_trajectory import ToolContract


def _pairs(spec: dict[str, Any], field: str) -> tuple[tuple[str, Any], ...]:
    raw = spec.get(field, [])
    if (not isinstance(raw, list)
            or any(not isinstance(row, list) or len(row) != 2
                   or not isinstance(row[0], str) or not row[0]
                   for row in raw)
            or len({row[0] for row in raw}) != len(raw)):
        raise ValueError(f"invalid {field} in approved tool contract")
    return tuple((row[0], row[1]) for row in raw)


def parse_tool_contracts(rows: dict[str, Any]) -> dict[str, ToolContract]:
    if not isinstance(rows, dict) or not rows:
        raise ValueError("manifest needs approved tool contracts")
    result = {}
    for name, spec in rows.items():
        if (not isinstance(name, str) or not name
                or not isinstance(spec, dict)
                or not isinstance(spec.get("required_params"), list)
                or not isinstance(spec.get("output_fields", []), list)
                or not isinstance(spec.get("provenance_params", []), list)
                or not isinstance(spec.get("collection_params", []), list)
                or not isinstance(spec.get("witness_default_only", []), list)
                or not isinstance(spec.get("description", ""), str)
                or type(spec.get("replay_stable")) is not bool):
            raise ValueError("invalid approved tool contract")
        shapes = _pairs(spec, "parameter_shapes")
        defaults = _pairs(spec, "default_params")
        default_only = spec.get("witness_default_only", [])
        if (any(value not in {"string_list_allow_empty", "measure_list"}
                for _, value in shapes)
                or not {key for key, _ in shapes} <= set(spec["required_params"])
                or not {key for key, _ in defaults}.isdisjoint(spec["required_params"])
                or any(not isinstance(key, str) or not key for key in default_only)
                or len(set(default_only)) != len(default_only)
                or not set(default_only) <= {key for key, _ in defaults}):
            raise ValueError("invalid parameter shape or default in approved tool contract")
        result[name] = ToolContract(
            tuple(spec["required_params"]), spec.get("read_only") is True,
            tuple(spec.get("output_fields", [])),
            tuple(spec.get("collection_params", [])),
            spec.get("description", ""),
            tuple(spec.get("provenance_params", [])), shapes, defaults,
            tuple(default_only), spec["replay_stable"])
    return result
