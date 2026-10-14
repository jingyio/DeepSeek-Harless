"""Session 上传文件接入已有 V3 报告工具；不添加模型循环或训练步骤。"""
from pathlib import Path
import hashlib
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
from benchmarks.research_report_agent_v3.intake import materialize
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

def guard():
    approved = json.loads((WORK / 'approved-inputs.json').read_text())['files']
    if set(approved) != {p.name for p in (WORK / 'inputs').iterdir()}:
        raise ValueError('approved report sources changed')
    for name, expected in approved.items():
        p = WORK / 'inputs' / name
        if p.is_symlink() or p.stat().st_nlink != 1 or hashlib.sha256(p.read_bytes()).hexdigest() != expected:
            raise ValueError('approved report source version changed')
    sources = DATA / 'cases/uploaded'
    if not sources.exists():
        files = list((WORK / 'inputs').iterdir())
        csvs = [p for p in files if p.suffix.lower() in ('.csv', '.tsv')]
        if len(csvs) != 1:
            raise ValueError('请上传一份 CSV/TSV；可额外上传一份研究说明 JSON。')
        request = WORK / 'report/request.txt'
        source = csvs[0]
        if source.suffix.lower() == '.tsv':
            import csv, io
            converted = io.StringIO()
            writer = csv.writer(converted)
            for row in csv.reader(io.StringIO(source.read_text(encoding='utf-8-sig')), delimiter='\t'):
                writer.writerow(row)
            source = WORK / 'report/converted.csv'
            source.write_text(converted.getvalue(), encoding='utf-8')
        studies = [p for p in files if p.suffix.lower() == '.json']
        if len(studies) > 1:
            raise ValueError('仅支持一份研究说明 JSON。')
        materialize(data=source, request_file=request, destination=DATA,
                    study_json=studies[0] if studies else None, case_id='uploaded')
    frozen = WORK / 'report/source-lock.json'
    hashes = {name: hashlib.sha256((sources / name).read_bytes()).hexdigest() for name in ('data.csv','study.json','task.txt')}
    if frozen.exists():
        if json.loads(frozen.read_text()) != hashes:
            raise ValueError('report input snapshot changed')
    else:
        frozen.write_text(json.dumps(hashes)); frozen.chmod(0o600)

def guarded(fn):
    @wraps(fn)
    def invoke(*args, **kwargs):
        try:
            guard(); result = fn(*args, **kwargs); guard(); return result
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
        guard()
        print(json.dumps({'prepared': True, 'mode': 'existing_intake_no_model'}))
    else:
        server.run(transport='stdio')
