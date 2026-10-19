"""Original file guards plus explicit MCP operator authority and result handles."""
from __future__ import annotations
import copy,json,os
from pathlib import Path
from uuid import uuid4
from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from mcp.server.mcpserver.exceptions import ToolError
from common import HERE,digest,sha,save
from file_tools import Action
from report_tools import ReportScene,report_version

FORMAT='sss-mcp-learning-v1'
TOOLS=['read_task','list_files','select_files','pin_file','read_file','collect_reads','hash_files','build_index',
       'search_index','compare_snapshot','preview_actions','execute_plan','inspect_plan_result','restore_plan','submit_report']

def operation_version():
    return digest({'operation_tools.py':sha(__file__),'operation_contract.py':sha(HERE/'operation_contract.py'),'report_version':report_version()})

def operator_contract(name):
    # These declarations express tool authority, never a sequence of tools.
    rows={'list_files':('read',False,[],None),'pin_file':('read',True,['source_id'],None),
          'read_file':('read',True,[],['readable','metadata_only','unreadable','unsupported']),
          'preview_actions':('stage',False,['plan_id'],['validated_copy_plan']),
          'execute_plan':('authorized_write',True,['receipt_id'],['executed_verified']),
          'inspect_plan_result':('read',True,['primary_file_id'],['verified_plan_results'])}
    effect,auto,exports,statuses=rows.get(name,('semantic',False,[],None))
    return {'format':FORMAT,'effect':effect,'auto_continue':auto,'exports':exports,**({'statuses':statuses} if statuses else {}),
            **({'scope_requirements':{'result_read_allowed':True}} if name=='inspect_plan_result' else {}),
            **({'safe_interleaving':True} if name=='list_files' else {})}

class OperationScene(ReportScene):
    def __init__(self,spec,output):
        super().__init__(spec,output);self.result_handles={}
        if not spec.get('operation_contract'):raise ValueError('operation task requires independent delivery contract')
        self.learning_scope={'input_sha256':self.input_digest,'execution_version':operation_version(),
             'permission_sha256':digest({'operations':spec['allowed_operations'],'rules':spec['rules']}),
             'initial_snapshot_sha256':digest(spec['initial_snapshot']),'result_read_allowed':spec['operation_contract']['require_result_read']}
    def stamp(self,out,authorized=False):
        return {**copy.deepcopy(out),'_sss_scope':self.learning_scope,'_sss_authorized':authorized}
    def read_task(self):
        return self.stamp({**super().read_task(),'learning_scope':self.learning_scope,
                           'operation_request':self.spec['operation_contract']['actions'],
                           'require_result_read':self.spec['operation_contract']['require_result_read']})
    def pin_file(self,file_id:str):return self.stamp(super().pin_file(file_id))
    def list_files(self):return self.stamp(super().list_files())
    def read_file(self,source_id:str):return self.stamp(super().read_file(source_id))
    def preview_actions(self,actions:list[Action]):
        """Stage only original task-authorized source/destination/operation tuples."""
        wanted=self.spec['operation_contract']['actions'];actual=[]
        for raw in actions:
            a=raw.model_dump() if isinstance(raw,Action) else Action(**raw).model_dump()
            if len(a['file_ids'])!=1:raise ToolError('this delivery grant requires one original source per action')
            _,name=self.file(a['file_ids'][0]);actual.append({'op':a['op'],'source':name,'destination':a['destination'],'format':a['format']})
        if any(a not in wanted for a in actual):raise ToolError('plan differs from original task source/destination/operation grant')
        return self.stamp(super().preview_actions(actions))
    def execute_plan(self,plan_id:str):
        out=super().execute_plan(plan_id)
        existing=next((rid for rid,pid in self.result_handles.items() if pid==plan_id),None)
        rid=existing or 'receipt-'+uuid4().hex;self.result_handles[rid]=plan_id
        value={**out,'receipt_id':rid};save(self.output/'operation-receipts'/f'{rid}.json',value)
        return self.stamp(value,True)
    def inspect_plan_result(self,receipt_id:str):
        """Verify one real execution receipt and expose current output identities."""
        self.active()
        if not self.learning_scope['result_read_allowed']:raise ToolError('original task permits execution receipt only; result inspection not granted')
        plan_id=self.result_handles.get(receipt_id)
        if not plan_id or plan_id not in self.receipts:raise ToolError('unknown actual result receipt')
        journal=json.loads((self.output/'journals'/f'{plan_id}.json').read_text())
        if journal['status']!='executed_verified' or journal['after']!=self.expected:raise ToolError('stale result receipt')
        names=[a['destination'] for a in journal['completed']]
        files=[{'path':n,'file_id':self.file_id(n),'sha256':self.expected[n]} for n in names]
        out={'status':'verified_plan_results','receipt_id':receipt_id,'plan_id':plan_id,'files':files,
             'primary_file_id':files[0]['file_id'] if len(files)==1 else None,'snapshot_sha256':digest(self.expected)}
        save(self.output/'result-inspections'/f'{receipt_id}.json',out);return self.stamp(out)

def serve():
    scene=OperationScene(json.loads(Path(os.environ['FM_TASK_FILE']).read_text()),os.environ['FM_OUTPUT']);server=MCPServer('file_management')
    for name in TOOLS:
        server.tool(name=name,annotations=ToolAnnotations(readOnlyHint=name not in ('execute_plan','restore_plan','build_index','submit_report'),
             destructiveHint=False,openWorldHint=False),meta={'sss_learning':operator_contract(name)})(getattr(scene,name))
    server.run()
if __name__=='__main__':serve()
