"""Bind human-readable MCP tool docs to an approved executable contract.

The schema is matching metadata only. It cannot authorize a tool or alter a
certified Motif's read-only execution contract.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from src.adapters.dsh_trajectory import ToolContract


def bind_mcp_descriptions(
    contracts: Mapping[str, ToolContract], tools_result: Any,
) -> dict[str, ToolContract]:
    rows = tools_result.get("tools") if isinstance(tools_result, dict) else tools_result
    if not isinstance(rows, list):
        raise ValueError("MCP tool schema must contain a tools list")
    by_name: dict[str, dict] = {}
    for row in rows:
        name = row.get("name") if isinstance(row, dict) else None
        if not isinstance(name, str) or not name or name in by_name:
            raise ValueError("MCP tool names are missing or repeated")
        by_name[name] = row
    updated = {}
    for name, contract in contracts.items():
        schema = by_name.get(name)
        if schema is None:
            raise ValueError(f"approved tool missing from MCP schema: {name}")
        description = schema.get("description")
        parameters = schema.get("inputSchema")
        if (not isinstance(description, str)
                or not 1 <= len(description.strip()) <= 160
                or not isinstance(parameters, dict)
                or parameters.get("type") != "object"
                or not isinstance(parameters.get("properties"), dict)
                or not isinstance(parameters.get("required", []), list)
                or any(not isinstance(key, str) for key in parameters.get("required", []))
                or set(parameters.get("required", [])) != set(contract.required_params)
                or not set(contract.required_params) <= set(parameters["properties"])):
            raise ValueError(f"MCP schema does not match approved tool: {name}")
        updated[name] = replace(contract, description=description.strip())
    return updated
