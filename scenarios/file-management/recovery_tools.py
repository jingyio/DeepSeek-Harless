"""TaskScene effect guards plus PlanScene durable authorization, bounded by the TS job ledger."""
from __future__ import annotations
import json,os,sys
from pathlib import Path
from typing import Literal
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from common import ROOT,HERE,digest,sha,save
sys.path.insert(0,str(ROOT))
from src.adapters.file_job_budget import job_command
from plan_tools import PlanScene,execution_version as plan_version
from task_tools import TaskScene,task_version
from workflow_contract import VERSION,contract
from workflow_tools import TOOLS
from file_tools import Action
from workflow_delivery import current_ids,finish_report,report_facts

def recovery_version():
    return digest({'recovery_tools.py':sha(__file__),'workflow_contract.py':sha(HERE/'workflow_contract.py'),
                   'workflow_delivery.py':sha(HERE/'workflow_delivery.py'),
                   'plan':plan_version(),'task':task_version(),'job_runtime':sha(ROOT/'src/adapters/file_workflow_job.ts'),
                   'budget_bridge':sha(ROOT/'src/adapters/file_job_budget.py'),
                   'acceptance_guard':sha(ROOT/'src/adapters/file_acceptance_guard.ts')})

class RecoveryScene(TaskScene,PlanScene):
    def __init__(self,spec,output,job_file):
        self.job_file=Path(job_file);self.workflow=contract(spec);state=job_command(job_file,'state')['state']
        if self.workflow.workflow_id!='FM38' or state['execution_version_sha256']!=recovery_version():raise ValueError('recovery execution version changed')
        if spec.get('task_contract',{}).get('kind')!='rename':raise ValueError('this recovery batch supports only explicit rename/rollback tasks')
        if sha(state['task_file'])!=state['task_sha256'] or digest(json.loads(Path(state['task_file']).read_text()))!=digest(spec):raise ValueError('recovery task/permission changed')
        if Path(output).resolve()!=Path(state['delivery_root']).resolve():raise ValueError('recovery delivery binding changed')
        super().__init__(spec,output);self.execution_version=recovery_version()
    def job_guard(self):
        s=job_command(self.job_file,'state')['state']
        if sha(s['task_file'])!=s['task_sha256'] or s['execution_version_sha256']!=recovery_version():raise ToolError('frozen recovery input/version changed')
        if s['status']!='running' or s['spent_units']>=int(s['limits']['budget_usd']*1e9):raise ToolError('original task permission/budget inactive')
        return s
    def read_task(self):
        s=job_command(self.job_file,'state')['state']
        plans=[]
        for pid,plan in self.plans.items():
            tokens=[a for a in self.authorizations.values() if a['plan_id']==pid]
            journal=self.journals.get(pid)
            plans.append({'plan_id':pid,'authorization_id':tokens[0]['authorization_id'] if len(tokens)==1 else None,
                          'status':journal['status'] if journal else 'previewed',
                          'actions':plan['actions'],'restore_allowed':self.grant['allow_restore'],
                          'current_snapshot_matches_journal':bool(journal and journal.get('after')==self.expected)})
        return {**super().read_task(),'workflow_contract':self.workflow.model_dump(),'recovery_execution_version_sha256':recovery_version(),
                'task_lifecycle':{k:s[k] for k in ('status','requests','steps','repairs','checks','spent_units','limits')},
                'recovery_goal':self.workflow.recovery_goal,'recovery_state':plans,
                'reading_instruction':'Only workflow_contract.allowed_reads authorize content reads. This rename/rollback task is metadata-only: use list_files/hash_files; do not pin/read original contents.',
                'recovery_instruction':'For rollback, use the actual recorded plan_id and authorization_id; never repeat partial effects or invent identifiers.',
                'private_ledger_model_access':False,'task_result_serialization':report_facts()}
    def pin_file(self,file_id:str):
        _,name=self.file(file_id)
        if name not in self.workflow.allowed_reads:raise ToolError('read outside workflow original scope; metadata-only rename uses list_files/hash_files')
        return super().pin_file(file_id)
    def preview_actions(self,actions:list[Action]):
        self.job_guard();return super().preview_actions(actions)
    def authorize_plan(self,plan_id:str):
        self.job_guard();return super().authorize_plan(plan_id)
    def execute_plan(self,plan_id:str,authorization_id:str):
        self.job_guard();return super().execute_plan(plan_id,authorization_id)
    def restore_plan(self,plan_id:str,authorization_id:str):
        self.job_guard();return super().restore_plan(plan_id,authorization_id)
    def publish(self,source,destination):
        super().publish(source,destination)
        # Frozen free crash probe: the parent PlanScene has already journaled this boundary.
        if self.spec.get('recovery_crash_after_publish') and not getattr(self,'_published',False):
            self._published=True;os._exit(75)
    def submit_report(self,summary:str,file_ids:list[str],gaps:list[str],report_kind:Literal['task_result','inspection','literal_search'],search_receipt_id:str|None=None):
        """Submit semantic summary/gaps with task_result and file_ids=[]; derive structure from guarded current MCP state. Original job permission and budget remain required."""
        self.job_guard()
        receipt=super().submit_report(summary,current_ids(self),gaps,report_kind,search_receipt_id)
        self.job_guard()
        return finish_report(self,receipt,file_ids,{'workflow_contract_version':VERSION,
                                                  'recovery_execution_version_sha256':recovery_version()})

def serve():
    scene=RecoveryScene(json.loads(Path(os.environ['FM_TASK_FILE']).read_text()),os.environ['FM_OUTPUT'],os.environ['FM_JOB_FILE']);server=MCPServer('file_management')
    for name in (*TOOLS[:11],'authorize_plan',*TOOLS[11:]):
        server.tool(name=name,annotations=ToolAnnotations(readOnlyHint=name not in ('build_index','authorize_plan','execute_plan','restore_plan','submit_report'),destructiveHint=False,openWorldHint=False))(getattr(scene,name))
    server.run()
if __name__=='__main__':serve()
