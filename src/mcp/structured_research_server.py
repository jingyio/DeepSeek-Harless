"""Focused read-only MCP surface for versioned research-data operations.

The full local research server still exposes Python and Quarto. This smaller
surface can be composed for a data-audit phase without changing task content.
"""

from __future__ import annotations

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from src.mcp.structured_research_tools import (
    aggregate_records, compare_results, compare_sources, inspect_records,
    list_research_sources, mcp_safe, pin_source, rank_grouped_result,
)

server = MCPServer(
    "sss-structured-research",
    instructions="Read-only, version-bound research data operations. Pin a local source "
    "file, inspect a JSON/CSV/TSV record set, and choose explicit grouped "
    "calculations. Source changes invalidate old IDs. These tools calculate "
    "requested quantities but do not decide scientific meaning.",
)

for function in (list_research_sources, pin_source, inspect_records, aggregate_records,
                 rank_grouped_result,
                 compare_sources, compare_results):
    server.add_tool(mcp_safe(function), name=function.__name__,
                    annotations=ToolAnnotations(readOnlyHint=True,
                                                destructiveHint=False,
                                                openWorldHint=False))


if __name__ == "__main__":
    server.run(transport="stdio")
