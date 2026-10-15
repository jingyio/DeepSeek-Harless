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
from benchmarks.research_report_agent_v3 import workflow_tools
from benchmarks.research_report_agent_v3.server import TOOL_NAMES
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

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

if __name__ == '__main__':
    if '--prepare-only' in sys.argv:
        prepared = guard()
        print(json.dumps({'prepared': True, 'report_ready': prepared['report_ready'],
                          'status': prepared['status'], 'mode': 'existing_intake_no_model'}))
    else:
        server.run(transport='stdio')
