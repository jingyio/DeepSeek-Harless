"""Canonical window locators for the existing witnessed-edge runtime; no new core."""
import hashlib
import json
import os
from pathlib import Path
import re
from mcp.server.mcpserver.exceptions import ToolError
from pdf_tools import PdfScene,digest,inventory
from pdf_dependencies import private_file
from workflow_probe_tools import HERE,WorkflowProbeScene,make_server


def window_version():
    return digest({n:hashlib.sha256((HERE/n).read_bytes()).hexdigest() for n in
        ('pdf_window_tools.py','pdf-window-contracts.json','pdf-window-scenario.json','pdf-window-task.md',
         'workflow_probe_tools.py','pdf_tools.py','pdf_layout.py','pdf_read_plan.py')})


def decimal(value, *, minimum, maximum):
    if not isinstance(value,str) or not re.fullmatch(r'0|[1-9][0-9]{0,6}',value):
        raise ToolError('window locators require canonical decimal strings, without leading zeros')
    parsed=int(value)
    if not minimum<=parsed<=maximum:raise ToolError('window locator exceeds its bounded range')
    return parsed


class WindowScene(WorkflowProbeScene):
    def __init__(self,spec,output):
        if spec.get('kind')!='topic_search':raise ValueError('window scene only supports topic_search')
        super().__init__(spec,output)
        self.version=window_version()

    def _guard(self):
        if inventory(self.root)!=self.task['sources'] or window_version()!=self.version:
            raise ToolError('window source selection or implementation changed')

    def pin_pdf_context(self,paper_id:str,page:str,start:str,length:str)->dict:
        """Pin one model-selected window; page/start/length are canonical decimal strings, length <=12000."""
        self._active('topic_search')
        decimal(page,minimum=1,maximum=999999)
        offset=decimal(start,minimum=0,maximum=1000000)
        count=decimal(length,minimum=1,maximum=12000)
        return PdfScene.pin_pdf_context(self,paper_id,page,offset,count)


if __name__=='__main__':
    spec=json.loads(private_file(Path(os.environ['SSS_WORKFLOW_PROBE_FILE'])).read_text())
    make_server(WindowScene(spec,os.environ['SSS_WORKFLOW_PROBE_OUTPUT'])).run(transport='stdio')
