"""Versioned batch handles and journaled, resumable effects in the original grant."""
import copy,csv,json,os,shutil,zipfile,sys
from pathlib import Path
from typing import Annotated
from uuid import uuid4
from pydantic import Field
from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from mcp.server.mcpserver.exceptions import ToolError
from common import ROOT,HERE,digest,sha,snapshot
sys.path.insert(0,str(ROOT))
from plan_tools import atomic
from operation_tools import OperationScene,TOOLS as OLD_TOOLS,operator_contract as old_contract,operation_version as old_version
from file_tools import Action

TOOLS=[*OLD_TOOLS,'pin_files','read_files']
Handles=Annotated[list[str],Field(min_length=1,max_length=40)]
def operation_version():
    return digest({'service':sha(__file__),'parent':old_version(),'quality':sha(HERE/'operation_contract_v2.py'),'job':sha(ROOT/'src/adapters/operation_job.ts')})
def operator_contract(name):
    c=old_contract(name)
    if name=='inspect_plan_result':c={**c,'exports':['primary_file_id','files[].file_id']}
    if name in ('pin_files','read_files'):
        c={'format':'sss-mcp-learning-v1','effect':'read','auto_continue':True,'exports':['source_ids'] if name=='pin_files' else [],
           'statuses':['pinned_batch'] if name=='pin_files' else ['read_batch_complete']}
    return c

class OperationSceneV2(OperationScene):
    fields=('plans','receipts','result_handles','handles','reads','index','collections','collection_results','search_receipts')
    def __init__(self,spec,output):
        self.state_file=Path(output)/'operation-state-v2.json';state=json.loads(self.state_file.read_text()) if self.state_file.exists() else None
        original=copy.deepcopy(spec)
        if state:
            if state['state_sha256']!=digest({k:v for k,v in state.items() if k!='state_sha256'}) or state['input_sha256']!=digest(original) or state['execution_version']!=operation_version():raise ValueError('operation recovery task/version/state changed')
            actual=snapshot(spec['workspace']);allowed=[state['expected']]
            for j in state.get('journals',{}).values():
                if j['status']=='executing':allowed+=j.get('inflight_states',[])
            if actual not in allowed:raise ValueError('unrecorded file changes; recovery refused')
            spec={**spec,'initial_snapshot':actual}
        super().__init__(spec,output);self.spec=original;self.input_digest=digest(original)
        self.learning_scope.update(input_sha256=self.input_digest,execution_version=operation_version(),initial_snapshot_sha256=digest(original['initial_snapshot']))
        self.journals={}
        if state:
            for key in self.fields:setattr(self,key,state[key])
            self.journals=state['journals']
        self.persist()
    def persist(self):
        body={'schema_version':2,'input_sha256':self.input_digest,'execution_version':operation_version(),'expected':self.expected,
              'journals':self.journals,**{k:getattr(self,k) for k in self.fields}}
        body['state_sha256']=digest(body);atomic(self.state_file,body)
        for pid,j in self.journals.items():atomic(self.output/'journals'/f'{pid}.json',j)
    def active(self):
        super().active()
        if os.environ.get('FM_JOB_FILE'):
            from src.adapters.operation_budget import command
            s=command(os.environ['FM_JOB_FILE'],'state')['state']
            if s['task_sha256']!=sha(Path(os.environ['FM_TASK_FILE'])) or s['execution_version_sha256']!=operation_version() or s['status']!='running' or s['spent_units']>=int(s['limits']['budget_usd']*1e9):raise ToolError('original task permission/version/budget inactive')
    def read_task(self):
        v=super().read_task()
        return {**v,'require_source_read':self.spec['operation_contract'].get('require_source_read',False),
          'reading_state':[{'path':r['path'],'source_id':r['source_id'],'status':r['status']} for r in self.reads.values()],
          'recovery_state':[{'plan_id':pid,'status':j['status'],'receipt_id':next((r for r,p in self.result_handles.items() if p==pid),None)} for pid,j in self.journals.items()],
          'recovery_instruction':'Reuse actual prior receipts. For an executing plan call execute_plan with its recorded plan_id; it completes only the remaining journaled boundaries. Do not create duplicate effects.',
          'batch_instruction':'For several produced files, use pin_files with actual inspect_plan_result.files file_id values, then read_files with its actual source_ids. Individual pin_file/read_file remain available.'}
    def preview_actions(self,actions:list[Action]):
        v=super().preview_actions(actions);self.persist();return v
    def pin_file(self,file_id:str):
        v=super().pin_file(file_id);self.persist();return v
    def read_file(self,source_id:str):
        v=super().read_file(source_id);self.persist();return v
    def pin_files(self,file_ids:Handles):
        self.active()
        if len(file_ids)!=len(set(file_ids)):raise ToolError('unique current file handles required')
        for fid in file_ids:self.file(fid)
        rows=[self.pin_file(fid) for fid in file_ids]
        return self.stamp({'status':'pinned_batch','file_ids':file_ids,'source_ids':[r['source_id'] for r in rows],'count':len(rows)})
    def read_files(self,source_ids:Handles):
        self.active()
        if len(source_ids)!=len(set(source_ids)) or any(s not in self.handles for s in source_ids):raise ToolError('unique actual pinned handles required')
        rows=[self.read_file(s) for s in source_ids]
        return self.stamp({'status':'read_batch_complete','reads':rows,'count':len(rows)})
    def stage(self,a,source):
        staged=self.output/'effect-staging'/uuid4().hex;staged.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        if a['op'] in ('copy','move','quarantine'):shutil.copyfile(source,staged)
        elif a['op']=='archive':
            with zipfile.ZipFile(staged,'w',zipfile.ZIP_DEFLATED) as z:z.write(source,a['source'])
            with zipfile.ZipFile(staged) as z:
                if z.testzip():raise ToolError('archive integrity failure')
        else:
            status,text,meta=self.parse(source)
            if status!='readable':raise ToolError('conversion source unreadable')
            if a['format']=='csv':
                with staged.open('w',encoding='utf-8',newline='') as f:csv.writer(f).writerows(meta['rows'])
            elif a['format']=='text':staged.write_text(text,encoding='utf-8')
            else:raise ToolError('unsupported conversion format')
        with staged.open('r+b') as f:os.fsync(f.fileno())
        return staged
    def execute_plan(self,plan_id:str):
        self.active();plan=self.plans.get(plan_id)
        if not plan:raise ToolError('unknown actual plan')
        if plan_id in self.receipts:
            if self.receipts[plan_id]['snapshot_sha256']!=digest(self.expected):raise ToolError('prior receipt is stale')
            return self.receipt(plan_id)
        j=self.journals.get(plan_id)
        if j and j['status']=='executed_verified' and j['after']==self.expected:
            self.receipts[plan_id]={'plan_id':plan_id,'status':'executed_verified','operation_count':len(j['completed']),
                'journal_sha256':digest(j),'snapshot_sha256':digest(self.expected)}
            return self.receipt(plan_id)
        if not j:
            if plan['snapshot']!=self.expected:raise ToolError('plan snapshot changed')
            for n,h in self.expected.items():
                p=self.output/'backups'/plan_id/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(self.root/n,p)
                if sha(p)!=h:raise ToolError('backup version changed')
            j={'plan_id':plan_id,'before':copy.deepcopy(self.expected),'actions':plan['actions'],'completed':[],'status':'executing','inflight_states':[]}
            self.journals[plan_id]=j;self.persist()
        if j['status']!='executing':raise ToolError('prior plan is inactive')
        for a in plan['actions'][len(j['completed']):]:
            self.guard();flight=j.get('flight')
            if not flight:
                _,name=self.file(a['file_ids'][0]);staged=self.stage({**a,'source':name},self.root/name);h=sha(staged)
                before=copy.deepcopy(self.expected);both={**before,a['destination']:h};after=dict(both)
                if a['op'] in ('move','quarantine'):after.pop(name)
                flight={'staged':str(staged),'sha256':h,'source':name,'before':before,'both':both,'after':after}
                j.update(flight=flight,inflight_states=[before,both,after]);self.persist()
            if self.expected not in (flight['before'],flight['both'],flight['after']):raise ToolError('effect boundary changed')
            dest=self.path(a['destination']);dest.parent.mkdir(parents=True,exist_ok=True)
            if self.expected==flight['before']:
                if sha(Path(flight['staged']))!=flight['sha256']:raise ToolError('staged payload changed')
                os.link(flight['staged'],dest)
                # No-overwrite publication; the prior journal already names this exact byte boundary.
                if getattr(self,'crash_after_publish',False) or self.spec.get('recovery_crash_after_publish') and not (self.output/'crash-probe-used.json').exists():
                    atomic(self.output/'crash-probe-used.json',{'original_plan':plan_id,'published_sha256':flight['sha256']});os._exit(75)
            if a['op'] in ('move','quarantine') and snapshot(self.root)==flight['both']:(self.root/flight['source']).unlink()
            self.expected=snapshot(self.root)
            if self.expected!=flight['after']:raise ToolError('unexpected effect footprint')
            j['completed'].append(a);j.update(after=self.expected,inflight_states=[]);j.pop('flight',None);self.persist()
        j.update(status='executed_verified',after=self.expected);self.persist()
        self.receipts[plan_id]={'plan_id':plan_id,'status':'executed_verified','operation_count':len(j['completed']),
             'journal_sha256':digest(j),'snapshot_sha256':digest(self.expected)}
        return self.receipt(plan_id)
    def receipt(self,plan_id):
        rid=next((r for r,p in self.result_handles.items() if p==plan_id),None) or 'receipt-'+uuid4().hex
        self.result_handles[rid]=plan_id;self.persist();value={**self.receipts[plan_id],'receipt_id':rid}
        atomic(self.output/'operation-receipts'/f'{rid}.json',value);return self.stamp(value,True)
    def restore_plan(self,plan_id:str):
        # Original scope and exact current snapshot remain required by the parent.
        v=super().restore_plan(plan_id)
        if plan_id in self.journals:self.journals[plan_id]['status']='restored_verified'
        self.persist();return v

def serve():
    scene=OperationSceneV2(json.loads(Path(os.environ['FM_TASK_FILE']).read_text()),os.environ['FM_OUTPUT']);server=MCPServer('file_management')
    for n in TOOLS:server.tool(name=n,meta={'sss_learning':operator_contract(n)},annotations=ToolAnnotations(readOnlyHint=n not in ('execute_plan','restore_plan','submit_report','build_index'),destructiveHint=False,openWorldHint=False))(getattr(scene,n))
    server.run()
if __name__=='__main__':serve()
