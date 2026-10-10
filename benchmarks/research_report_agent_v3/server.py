"""Real v3 tools served through standard MCP; no embedded agent/model loop."""
from functools import wraps
import inspect
from typing import get_type_hints

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

try:
    from . import workflow_tools as tools
except ImportError:
    import workflow_tools as tools

server = MCPServer('research-report', instructions=(
    'Real CSV statistics, graphics and PDF tools. Three mandatory LLM semantic decisions: '
    '(1) approve_analysis after input inspection; (2) approve_presentation AFTER verified '
    'statistics, selecting plots/tables/outline with actual-result reasons; (3) submit_report_text '
    'AFTER figure verification, writing ALL body paragraphs. Deterministic tools never '
    'replace scientific prose. Follow receipt next_step fields. build_evidence and '
    'verify_figures stop deterministic continuation and require the model. Numeric claims '
    'use the available {{name}} tokens; unknown design/units stay unknown. submit_report_text '
    'has a typed JSON schema: every section needs heading,paragraphs,figure_indices ([] if none), '
    'with no roles or other extra fields; include explicit boolean allow_deterministic_continuation. '
    'Disclose declared synthetic data and noncausal limits in the model-written body. Existing '
    'figure labels and consecutive list ordinals are formatting; bare statistical numbers '
    'remain prohibited. Source hashes and paths belong to sidecar records, not body prose. '
    'Treat metadata split=train/certification/evaluation only as a benchmark partition, not an experimental '
    'data-splitting design. Interpret uncertainty in its own units: slope intervals and individual prediction '
    'uncertainty have different dimensions and cannot be compared by magnitude. Do not claim that a source '
    'identifier appears inside the PDF unless that placement is actually supported. Each approval '
    'explicitly specifies its own continuation permission. All files remain inside the '
    'scoped run; hashes bind CSV, metadata and task. Task completion requires deliver_report. '
    'Preserve failed attempts and report scientific-review limits; no oracle is exposed.'))

TOOL_NAMES = ('inspect_study', 'approve_analysis', 'run_analysis', 'verify_analysis',
    'build_evidence', 'approve_presentation', 'render_figures', 'verify_figures',
    'submit_report_text', 'compose_report', 'layout_report', 'audit_layout',
    'verify_report', 'deliver_report')


def explain_validation(function):
    @wraps(function)
    def invoke(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except ValueError as error:
            raise ToolError(str(error)) from error
    # Resolve workflow-local Pydantic types before the cross-module decorator
    # is inspected by MCP. Otherwise future-annotation "ReportText" may be
    # evaluated in this wrapper's globals instead of workflow_tools.
    invoke.__annotations__ = get_type_hints(function)
    invoke.__signature__ = inspect.signature(function, eval_str=True)
    return invoke


for name in TOOL_NAMES:
    server.add_tool(explain_validation(getattr(tools, name)), name=name,
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                    idempotentHint=True, openWorldHint=False))

if __name__ == '__main__':
    tools.context.get_case_dir()
    tools.context.get_run_dir()
    server.run(transport='stdio')
