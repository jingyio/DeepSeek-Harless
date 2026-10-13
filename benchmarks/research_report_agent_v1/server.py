"""Real, scoped statistics/plot/document tools exposed through stdio MCP."""
from __future__ import annotations

from functools import wraps
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from common import get_case_dir, get_run_dir
from data_tools import inspect_study, plan_analysis, run_analysis, verify_analysis
from report_ops import (plan_figures, render_figures, verify_figures,
                        plan_report, export_report, verify_report)


server = MCPServer("research-report", instructions=(
    "Real CSV analysis, figure rendering and PDF export on synthetic research observations. "
    "Choose scientific design, missingness treatment, figure types and interpretation explicitly. "
    "All writes are confined to this run; records bind current source bytes. "
    "The independent oracle is inaccessible. Never represent generated observations as real experiments."))


def explain_validation(function):
    """Expose deliberate input rejections so the real agent can repair its call.

    MCP 2.2 masks unexpected exceptions. Keep that protection for crashes;
    these tools use ValueError for bounded, user-correctable validation errors.
    wraps preserves the original function signature and model-facing schema.
    """
    @wraps(function)
    def invoke(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except ValueError as error:
            raise ToolError(str(error)) from error
    return invoke


for function in (inspect_study, plan_analysis, run_analysis, verify_analysis,
                 plan_figures, render_figures, verify_figures,
                 plan_report, export_report, verify_report):
    server.add_tool(explain_validation(function), name=function.__name__, annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False))


if __name__ == "__main__":
    get_case_dir()
    get_run_dir()
    server.run(transport="stdio")
