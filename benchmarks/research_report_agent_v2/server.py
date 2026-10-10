"""Scoped v2 statistics, scientific composition and PDF tools over stdio MCP."""
from __future__ import annotations

from functools import wraps
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from common import get_case_dir, get_run_dir
from workflow_tools import (inspect_study, approve_workflow, run_analysis,
    verify_analysis, build_evidence, approve_interpretation, render_figures,
    verify_figures, compose_report, layout_report, audit_layout, verify_report,
    deliver_report)


server = MCPServer('research-report', instructions=(
    'Real scoped CSV statistics, PNG/SVG/PDF figures and PDF documents. '
    'Begin by inspecting the actual input. Explicitly approve one workflow '
    'covering scientific design, columns, complete-case treatment, figures and '
    'the user report constraints/outline. Standard interpretation uses verified '
    'values and transparent deterministic scientific paragraphs; custom mode '
    'requires an LLM approve_interpretation after observing actual evidence. '
    'Approval may authorize only scoped deterministic continuation; follow '
    'receipt next_step fields, stop at semantic handoffs or failed checks. '
    'All writes stay in this run. Input hashes include data, metadata and task. '
    'Data are synthetic only if metadata explicitly declares this. '
    'Task completion requires successful deliver_report; automatic checks do '
    'not replace independent scientific review. No oracle is exposed.'))


def explain_validation(function):
    @wraps(function)
    def invoke(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except ValueError as error:
            raise ToolError(str(error)) from error
    return invoke


for function in (inspect_study, approve_workflow, run_analysis, verify_analysis,
                 build_evidence, approve_interpretation, render_figures,
                 verify_figures, compose_report, layout_report, audit_layout,
                 verify_report, deliver_report):
    server.add_tool(explain_validation(function), name=function.__name__,
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                    idempotentHint=True, openWorldHint=False))


if __name__ == '__main__':
    get_case_dir()
    get_run_dir()
    server.run(transport='stdio')
