"""Durable, explicitly task-authorized byte-preserving copy plans. No arbitrary writes."""
from __future__ import annotations
import copy,json,os,shutil
from pathlib import Path
from uuid import uuid4
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from common import ROOT,DATA,digest,sha,snapshot,save
from file_tools import FileScene,Action

def execution_version():
 return digest({'plan_tools.py':sha(__file__),'file_tools.py':sha(ROOT/'scenarios/file-management/file_tools.py'),
                'common.py':sha(ROOT/'scenarios/file-management/common.py'),'protocol':'sss-copy-plan-v1'})
def atomic(path,value):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700);temp=path.with_name(path.name+'.'+uuid4().hex+'.tmp')
 with temp.open('x',encoding='utf-8') as f:
  os.chmod(temp,0o600);f.write(json.dumps(value,ensure_ascii=False,indent=2));f.flush();os.fsync(f.fileno())
 os.replace(temp,path)

class PlanScene(FileScene):
 def __init__(self,spec,output):
  original=copy.deepcopy(spec);out=Path(output).resolve();state_path=out/'plan-state.json'
  if not out.is_relative_to((ROOT/'.local').resolve()):raise ValueError('private output required')
  state=json.loads(state_path.read_text()) if state_path.exists() else None
  if state:
   unsigned={k:v for k,v in state.items() if k!='state_sha256'}
   if state.get('state_sha256')!=digest(unsigned) or state.get('input_sha256')!=digest(original) or state.get('execution_version_sha256')!=execution_version():raise ValueError('durable plan state input/version changed')
   spec=copy.deepcopy(spec);spec['initial_snapshot']=snapshot(spec['workspace'])
  super().__init__(spec,output);self.spec=original;self.input_digest=digest(original)
  grant=self.spec.get('write_grant',{})
  if grant.get('schema_version')!=1 or not 1<=grant.get('max_actions',0)<=6 or not isinstance(grant.get('allow_restore'),bool):raise ValueError('bounded task write grant required')
  if not set(grant.get('allowed_ops',[]))<=set(('copy','move','quarantine')) or not grant.get('allowed_ops'):raise ValueError('only byte preserving grant operations')
  if not grant.get('source_paths') or any(n not in original['initial_snapshot'] or n=='.experiment-copy' for n in grant['source_paths']):raise ValueError('grant sources must be original files')
  if not grant.get('destination_prefixes') or any(not p.endswith('/') or str(self.path(p.rstrip('/')))==str(self.root) for p in grant['destination_prefixes']):raise ValueError('relative destination prefixes required')
  self.grant=grant;self.authorizations={};self.journals={};self.restored={};self.state_path=state_path
  if state:
   self.plans=state['plans'];self.authorizations=state['authorizations'];self.receipts=state['receipts'];self.journals=state['journals'];self.restored=state['restored']
   actual=snapshot(self.root);expected=state['expected']
   if actual!=expected:
    live=[j for j in self.journals.values() if j['status'] in ('executing','restoring') and actual in j.get('inflight_states',[])]
    if len(live)!=1:raise ValueError('unrecorded workspace changes: refuse restart/recovery')
   self.expected=actual
   for j in self.journals.values():
    if j['status']=='executing':j.update(status='partial_failure',after=actual,diagnostic='restart_at_recorded_atomic_boundary')
    elif j['status']=='restoring':j.update(after=actual)
   self.persist()
  else:self.persist()
 def persist(self):
  for pid,j in self.journals.items():atomic(self.output/'journals'/f'{pid}.json',j)
  state={'schema_version':1,'input_sha256':self.input_digest,'execution_version_sha256':execution_version(),
   'expected':self.expected,'plans':self.plans,'authorizations':self.authorizations,'receipts':self.receipts,'journals':self.journals,'restored':self.restored}
  state['state_sha256']=digest(state);atomic(self.state_path,state)
 def read_task(self):
  r=super().read_task();return {**r,'write_grant':self.grant,'grant_sha256':digest(self.grant),
   'execution_version_sha256':execution_version(),'authorization_scope':'explicit_frozen_task_experiment_copy_only'}
 def permission(self,actions):
  if not 1<=len(actions)<=self.grant['max_actions']:raise ToolError('plan exceeds task grant count')
  for a in actions:
   if a['op'] not in self.grant['allowed_ops'] or a['format']!='none' or len(a['file_ids'])!=1:raise ToolError('plan effect outside task write grant')
   _,name=self.file(a['file_ids'][0])
   if name not in self.grant['source_paths'] or not any(a['destination'].startswith(p) for p in self.grant['destination_prefixes']):raise ToolError('plan source/destination outside exact task grant')
 def preview_actions(self,actions:list[Action]):
  """Validate current actions against frozen source, destination, operation and count grants; no effects."""
  self.active();serialized=[a.model_dump() if isinstance(a,Action) else Action(**a).model_dump() for a in actions];self.permission(serialized)
  packet=super().preview_actions(serialized)
  packet.update(input_sha256=self.input_digest,snapshot_sha256=digest(self.expected),execution_version_sha256=execution_version(),
   grant_sha256=digest(self.grant),copy_only=True,permission_status='within_task_grant')
  packet['preview_sha256']=digest(packet);self.plans[packet['plan_id']]['preview']=packet;self.persist();return copy.deepcopy(packet)
 def authorize_plan(self,plan_id:str):
  """Issue a durable one-plan token only within the already authorized frozen experiment task grant."""
  self.active();plan=self.plans.get(plan_id)
  if not plan or plan['snapshot']!=self.expected or plan_id in self.journals:raise ToolError('unknown, stale or consumed plan')
  self.permission(plan['actions']);p=plan['preview']
  existing=next((a for a in self.authorizations.values() if a['plan_id']==plan_id),None)
  if existing:return copy.deepcopy(existing)
  token={'authorization_id':'authorization-'+uuid4().hex,'plan_id':plan_id,'plan_sha256':p['plan_sha256'],
   'preview_sha256':p['preview_sha256'],'input_sha256':self.input_digest,'snapshot_sha256':digest(self.expected),
   'execution_version_sha256':execution_version(),'grant_sha256':digest(self.grant),'copy_only':True,
   'status':'task_grant_authorized','single_plan':True,'operation_count':len(plan['actions'])}
  token['authorization_sha256']=digest(token);self.authorizations[token['authorization_id']]=token;self.persist();return copy.deepcopy(token)
 def authorization(self,pid,aid):
  token=self.authorizations.get(aid);plan=self.plans.get(pid)
  if not token or not plan or token['plan_id']!=pid or token['input_sha256']!=self.input_digest or token['grant_sha256']!=digest(self.grant) or token['execution_version_sha256']!=execution_version():raise ToolError('unknown, unrelated or revoked authorization')
  p=plan['preview'];body={k:v for k,v in plan.items() if k!='preview'}
  if digest(body)!=p['plan_sha256'] or token['plan_sha256']!=p['plan_sha256'] or token['preview_sha256']!=p['preview_sha256']:raise ToolError('plan changed after preview/authorization')
  return token,plan
 def publish(self,source,destination):
  """Stage bytes privately, then link without overwriting; both roots must share a filesystem."""
  destination.parent.mkdir(parents=True,exist_ok=True);stage=self.output/'staging'/uuid4().hex;stage.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
  with Path(source).open('rb') as src,stage.open('xb') as dst:
   os.chmod(stage,0o600);shutil.copyfileobj(src,dst);dst.flush();os.fsync(dst.fileno())
  try:os.link(stage,destination)
  finally:stage.unlink(missing_ok=True)
 def execute_plan(self,plan_id:str,authorization_id:str):
  """Consume exact durable task authorization once; journal atomic boundaries and verify byte effects."""
  self.active();token,plan=self.authorization(plan_id,authorization_id)
  if plan_id in self.restored:raise ToolError('restored authorization cannot execute again')
  if plan_id in self.receipts:
   receipt=self.receipts[plan_id]
   if receipt['snapshot_sha256']!=digest(self.expected):raise ToolError('old receipt is not current workspace')
   return copy.deepcopy(receipt)
  if plan_id in self.journals:raise ToolError('interrupted execution cannot retry effects; restore_plan with exact authorization')
  if plan['snapshot']!=self.expected or token['snapshot_sha256']!=digest(self.expected):raise ToolError('stale authorized snapshot')
  self.permission(plan['actions']);before=copy.deepcopy(self.expected);backups=self.output/'backups'/plan_id
  for name in before:
   dst=backups/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(self.root/name,dst)
   if sha(dst)!=before[name]:raise ToolError('preimage backup changed')
  j={'plan_id':plan_id,'authorization_id':authorization_id,'before':before,'after':before,'actions':plan['actions'],'completed':[],
   'status':'executing','input_sha256':self.input_digest,'grant_sha256':digest(self.grant),'execution_version_sha256':execution_version()}
  self.journals[plan_id]=j;self.persist()
  try:
   for a in plan['actions']:
    self.guard();src,name=self.file(a['file_ids'][0]);dest=self.path(a['destination'])
    both={**self.expected,a['destination']:self.expected[name]};after=copy.deepcopy(both)
    if a['op']!='copy':del after[name]
    j['inflight_states']=[copy.deepcopy(self.expected),both,after];self.persist()
    self.publish(src,dest)
    if sha(dest)!=before[name]:raise ValueError('effect bytes mismatch')
    if a['op']!='copy':src.unlink()
    self.expected=snapshot(self.root)
    if self.expected!=after:raise ValueError('effect footprint changed')
    j['completed'].append(a);j.update(after=self.expected,inflight_states=[]);self.persist()
    if self.spec.get('fault_after_operations')==len(j['completed']):raise RuntimeError('frozen experiment fault after atomic operation')
  except Exception as e:
   actual=snapshot(self.root)
   if actual==self.expected or actual in j.get('inflight_states',[]):
    self.expected=actual;j.update(status='partial_failure',after=actual,diagnostic=type(e).__name__)
   else:j.update(status='external_conflict',observed_conflict_snapshot=actual,diagnostic=type(e).__name__)
   self.persist();raise ToolError('partial execution retained; restore_plan with the same authorization or report conflict') from e
  j.update(status='executed_verified',inflight_states=[]);self.persist()
  receipt={'plan_id':plan_id,'authorization_id':authorization_id,'status':'executed_verified','operation_count':len(j['completed']),
   'plan_sha256':token['plan_sha256'],'authorization_sha256':token['authorization_sha256'],'grant_sha256':digest(self.grant),
   'input_sha256':self.input_digest,'execution_version_sha256':execution_version(),'snapshot_sha256':digest(self.expected),
   'journal_sha256':digest(j),'copy_only':True}
  self.receipts[plan_id]=receipt;self.persist();return copy.deepcopy(receipt)
 def restore_plan(self,plan_id:str,authorization_id:str):
  """Restore known preimages only while the current snapshot equals this plan's journaled effect boundary."""
  self.active();token,plan=self.authorization(plan_id,authorization_id)
  if not self.grant['allow_restore']:raise ToolError('restoration outside task grant')
  if plan_id in self.restored:
   receipt=self.restored[plan_id]
   if receipt['snapshot_sha256']!=digest(self.expected):raise ToolError('later changes prohibit idempotent restore')
   return copy.deepcopy(receipt)
  j=self.journals.get(plan_id)
  if not j or j['status'] not in ('executed_verified','partial_failure','restoring') or j['after']!=self.expected:raise ToolError('unknown/unrecorded/later changes prohibit restore')
  for name,h in j['before'].items():
   if sha(self.output/'backups'/plan_id/name)!=h:raise ToolError('preimage bytes changed')
  j['status']='restoring';self.persist()
  # No original byte is overwritten. Missing originals are republished; only recorded additions removed.
  for name,h in j['before'].items():
   if name in self.expected:
    if self.expected[name]!=h:raise ToolError('changed original prohibits restoration')
    continue
   next_state={**self.expected,name:h};j['inflight_states']=[copy.deepcopy(self.expected),next_state];self.persist()
   self.publish(self.output/'backups'/plan_id/name,self.path(name));self.expected=snapshot(self.root)
   if self.expected!=next_state:raise ToolError('restoration footprint changed')
   j.update(after=self.expected,inflight_states=[]);self.persist()
  for name in sorted(set(self.expected)-set(j['before'])):
   next_state={n:h for n,h in self.expected.items() if n!=name};j['inflight_states']=[copy.deepcopy(self.expected),next_state];self.persist()
   self.path(name).unlink();self.expected=snapshot(self.root)
   if self.expected!=next_state:raise ToolError('restoration footprint changed')
   j.update(after=self.expected,inflight_states=[]);self.persist()
  if self.expected!=j['before']:raise ToolError('restore postcondition failed')
  j.update(status='restored_verified',inflight_states=[]);self.persist()
  receipt={'plan_id':plan_id,'authorization_id':authorization_id,'status':'restored_verified','snapshot_sha256':digest(self.expected),
   'input_sha256':self.input_digest,'grant_sha256':digest(self.grant),'journal_sha256':digest(j),'copy_only':True}
  self.restored[plan_id]=receipt;self.receipts[plan_id]=receipt;self.persist();return copy.deepcopy(receipt)

def serve():
 scene=PlanScene(json.loads(Path(os.environ['FM_TASK_FILE']).read_text()),os.environ['FM_OUTPUT']);server=MCPServer('file_management')
 for n in ('read_task','list_files','pin_file','read_file','hash_files','build_index','search_index','compare_snapshot','preview_actions','authorize_plan','execute_plan','restore_plan','submit_report'):
  server.tool(name=n,annotations=ToolAnnotations(readOnlyHint=n not in ('build_index','execute_plan','restore_plan','submit_report'),destructiveHint=False,openWorldHint=False))(getattr(scene,n))
 server.run()
if __name__=='__main__':serve()
