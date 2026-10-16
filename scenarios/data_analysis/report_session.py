"""Session 上传文件接入已有 V3 报告工具；不添加模型循环或训练步骤。"""
from pathlib import Path
import json
import os
import sys
from functools import wraps
from typing import get_type_hints
import inspect

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
for variable in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ.setdefault(variable, '1')
from scenarios.data_analysis.report_intake import ReportIntake

WORK = Path(os.environ['HARLESS_REPORT_WORKSPACE']).resolve()
PRIVATE_ROOT=Path(os.environ.get('HARLESS_PRIVATE_ROOT',str(ROOT/'.local'))).resolve()
if '.local' not in PRIVATE_ROOT.parts or WORK.name != 'work' or not WORK.is_relative_to(PRIVATE_ROOT):
    raise ValueError('report requires a private Session workspace')
DATA = WORK / 'report/sources'
RUN = WORK / 'outputs/report'
os.environ.update(RRA_DATA_ROOT=str(DATA), RRA_RUN_ROOT=str(RUN), RRA_CASE='uploaded')
intake = ReportIntake(WORK)

def guard():
    return intake.prepare()

# Source preparation is deliberately independent of MCP and the statistics
# stack. A reference-only turn must not import NumPy just to admit its files.
if __name__ == '__main__' and '--prepare-only' in sys.argv:
    prepared = guard()
    print(json.dumps({'prepared': True, 'report_ready': prepared['report_ready'],
                      'status': prepared['status'], 'mode': 'existing_intake_no_model'}))
    sys.exit(0)

from benchmarks.research_report_agent_v3 import workflow_tools
from benchmarks.research_report_agent_v3.server import TOOL_NAMES
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

def guarded(fn):
    @wraps(fn)
    def invoke(*args, **kwargs):
        try:
            prepared = guard()
            if not prepared['report_ready']:
                if fn.__name__ == 'inspect_study':
                    return prepared
                raise ValueError(prepared['next_step'])
            result = fn(*args, **kwargs)
            if fn.__name__ == 'inspect_study':
                result = {**result, 'report_ready': True, 'attachment_sources': prepared['attachment_sources']}
            guard()
            return result
        except ValueError as error:
            raise ToolError(str(error)) from error
    invoke.__annotations__ = get_type_hints(fn)
    invoke.__signature__ = inspect.signature(fn, eval_str=True)
    return invoke

# Preserve the existing 14 tools, their typed schema and semantic boundaries.
server = MCPServer('research-report', instructions=(ROOT / 'scenarios/data_analysis/report-prompt.md').read_text())
for name in TOOL_NAMES:
    from mcp.types import ToolAnnotations
    server.add_tool(guarded(getattr(workflow_tools, name)), name=name,
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False))

@server.tool()
def read_image_table(name: str, sha256: str, start_row: int = 1, row_count: int = 10):
    """View enlarged ORIGINAL table pixels for 1-based data rows, at most 10 rows.
    Read every row strip before record_image_table. Match row identifiers and exact
    digits including the final row; this is visual evidence, not OCR verification.
    """
    from mcp.types import CallToolResult,TextContent,ImageContent
    import base64
    try:
        meta,pixels=intake.read_image_table(name,sha256,start_row,row_count)
        return CallToolResult(content=[TextContent(type='text',text=json.dumps(meta)),
            ImageContent(type='image',data=base64.b64encode(pixels).decode('ascii'),mime_type='image/png')])
    except ValueError as error: raise ToolError(str(error)) from error

@server.tool()
def record_image_table(name: str, sha256: str, columns: list[str], rows: list[list[str]]) -> dict:
    """Record a clearly legible table from a native image in this request. Use exact
    attachment_sources name/SHA256, original column labels and every row as literal
    strings (empty cells=''). Never infer missing cells, invent values or overwrite
    a frozen transcription. This records MODEL VISUAL TRANSCRIPTION, not verified
    OCR. Then inspect_study and follow the unchanged statistical/report workflow.
    """
    try: return intake.record_image_table(name,sha256,columns,rows)
    except ValueError as error: raise ToolError(str(error)) from error

@server.tool()
def export_input_review(title: str, sections: list[dict], source_versions: dict) -> dict:
    """If no analyzable table exists, export the actual reference review and missing-data
    requirements as PDF + Markdown. sections=[{heading,paragraphs:[text]}]. Use the
    complete attachment_sources filename:sha256 map. This is NOT a statistical
    report; never invent observations/results or bypass the statistical workflow.
    """
    prepared=guard()
    if prepared['report_ready']:
        return {'exported':False,'reason':'statistical_analysis_required',
                'next_step':'An analyzable data table exists. Use the statistical report workflow and deliver_report.'}
    from src.adapters.session_report import SessionReport
    from src.adapters.session_files import SessionFiles
    return SessionReport(SessionFiles(WORK/'inputs'),'input-review').export(title,sections,source_versions)

if __name__ == '__main__':
    server.run(transport='stdio')
