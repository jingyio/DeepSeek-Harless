"""Session-template entry; binds only the host-issued immutable management task."""
import os,json,inspect,functools
from pathlib import Path
from management_tools import ManagementScene,ManagementAction,TOOLS,operator_contract
from mcp.server import MCPServer
from mcp.types import ToolAnnotations
def serve():
    from typing import get_type_hints
    from mcp.server.mcpserver.exceptions import ToolError
    server=MCPServer('file_management');current={'key':None,'scene':None}
    def wrap(name):
        method=getattr(ManagementScene,name)
        @functools.wraps(method)
        async def call(**kwargs):
            p=Path(os.environ['FM_WEB_WORKSPACE'])/'management-binding.json'
            if not p.is_file():raise ToolError('当前会话尚未提交工作区文件任务，可以先讨论需求。')
            binding=json.loads(p.read_text());raw=Path(binding['task_file']).read_text()
            os.environ.update(FM_TASK_FILE=binding['task_file'],FM_OUTPUT=binding['delivery'],FM_JOB_FILE=binding['job_file'])
            if current['key']!=raw:current.update(key=raw,scene=ManagementScene(json.loads(raw),binding['delivery']))
            value=getattr(current['scene'],name)(**kwargs)
            return await value if inspect.isawaitable(value) else value
        hints=get_type_hints(method,include_extras=True)
        sig=inspect.signature(method)
        call.__signature__=sig.replace(parameters=[p.replace(annotation=hints.get(p.name,p.annotation)) for p in list(sig.parameters.values())[1:]])
        call.__annotations__=hints
        return call
    for n in TOOLS:server.tool(name=n,meta={'sss_learning':operator_contract(n)},annotations=ToolAnnotations(readOnlyHint=n not in ('execute_plan','restore_plan','submit_report','build_index','execute_tool_call'),destructiveHint=False,openWorldHint=False))(wrap(n))
    server.run()
if __name__=='__main__':serve()
