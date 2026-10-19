"""Free actual CLI/SDK/MCP check, including a candidate interpreter fixture.

The fixture is explicitly mock and cannot enter real learning/activation.
"""
import importlib.util,json,os,sys,threading,time
from pathlib import Path
from uuid import uuid4
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from common import save,PREFIX,DATA,digest
from operation_prepare import prepare_case
from src.adapters.continuous_rsi import records,initialize,load_config,actual_schemas,source_map
from src.adapters.mcp_learning import adapter
from src.motif_core.offline.operation_graph import catalog
from src.motif_core.offline.experience_registry import ExperienceRegistry,sha
from src.adapters.file_scenario import prepare_scenario

class Provider(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_POST(self):
  body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));self.server.requests.append(body);values=[]
  time.sleep(getattr(self,'response_delay',0))
  for m in body['messages']:
   if m['role']=='tool':
    try:values.append(json.loads(m['content']))
    except (ValueError,TypeError):pass
  find=lambda pred:next((v for v in reversed(values) if isinstance(v,dict) and pred(v)),None)
  task=find(lambda v:'operation_request' in v);inv=find(lambda v:'files' in v and 'status' not in v and 'snapshot_sha256' in v)
  plan=find(lambda v:v.get('status')=='validated_copy_plan');receipt=find(lambda v:v.get('status')=='executed_verified')
  inspection=find(lambda v:v.get('status')=='verified_plan_results');pin=find(lambda v:(v.get('source_id') and 'status' not in v) or v.get('status')=='pinned_batch')
  read=find(lambda v:(v.get('source_id') and 'status' in v) or v.get('status')=='read_batch_complete');report=find(lambda v:v.get('status') in ('delivered','delivered_with_gaps'))
  if task and task.get('recovery_state'):
   prior=next((r for r in task['recovery_state'] if r['status'] in ('executing','executed_verified')),None)
   if prior:
    plan=plan or prior
    if prior.get('receipt_id'):receipt=receipt or prior
  if not task:action=('read_task',{})
  elif not inv:action=('list_files',{})
  elif not plan:
   reqs=task['operation_request'];aa=[{'op':r['op'],'file_ids':[next(f['file_id'] for f in inv['files'] if f['path']==r['source'])],'destination':r['destination'],'format':r['format']} for r in reqs]
   action=('preview_actions',{'actions':aa})
  elif not receipt:action=('execute_plan',{'plan_id':plan['plan_id']})
  elif task['require_result_read'] and not inspection:action=('inspect_plan_result',{'receipt_id':receipt['receipt_id']})
  elif task['require_result_read'] and not pin:action=('pin_files',{'file_ids':[f['file_id'] for f in inspection['files']]}) if any(t['function']['name'].endswith('__pin_files') for t in body['tools']) and len(inspection['files'])>1 else ('pin_file',{'file_id':inspection['primary_file_id']})
  elif task['require_result_read'] and not read:action=('read_files',{'source_ids':pin['source_ids']}) if 'source_ids' in pin else ('read_file',{'source_id':pin['source_id']})
  elif not any(r['path']==task['operation_request'][0]['destination'] for r in inv['files']):action=('list_files',{})
  elif not report:action=('submit_report',{'summary':'Explicit mock provider check of actual file operation and result reading','file_ids':[r['file_id'] for r in inv['files']],'gaps':[],'report_kind':'task_result'})
  else:action=None
  count=len(self.server.requests);delta={'role':'assistant','tool_calls':[{'index':0,'id':'mock-op-'+str(count),'type':'function','function':{'name':PREFIX+action[0],'arguments':json.dumps(action[1])}}]} if action else {'role':'assistant','content':'Mock done.'}
  base={'id':'mock-op','created':1,'model':body['model'],'object':'chat.completion.chunk'}
  chunks=[{**base,'choices':[{'index':0,'delta':delta,'finish_reason':None}]},{**base,'choices':[{'index':0,'delta':{},'finish_reason':'tool_calls' if action else 'stop'}]},
          {**base,'choices':[],'usage':{'prompt_tokens':100,'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':100,'completion_tokens':20,'total_tokens':120}}]
  data=(''.join('data: '+json.dumps(c)+'\n\n' for c in chunks)+'data: [DONE]\n\n').encode()
  self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)

def run(candidate):
    uid='free-operation-'+uuid4().hex[:10];out=ROOT/'.local/general-rsi-checks'/uid;work=DATA/uid/'source'
    spec=prepare_case(out,work,read_result=True);state=ROOT/'.local/rsi'/uid
    cfg={'schema_version':1,'format':'sss-continuous-rsi-v1','adapter':'file_operations_v1','state_root':str(state),
         'workspace_roots':[str(work.parent)],'mode':'observe','provider_mode':'mock','series_cap_usd':1000,'learning_cap_usd':5,
         'auto_worker':False,'allow_material_copy':False,'limits':{'budget_usd':5,'max_steps':96,'max_output':4000,'max_repairs':2}}
    save(out/'rsi.json',cfg)
    if candidate:
        import asyncio
        schemas=asyncio.run(actual_schemas(prepare_scenario(out/'scenario.json'),out/'input.json',out/'schema','file_operations_v1'));tc=catalog(schemas)
        ns=[PREFIX+n for n in ('preview_actions','execute_plan','inspect_plan_result','pin_file','read_file')]
        fields=['plan_id','receipt_id','primary_file_id','source_id'];params=['plan_id','receipt_id','file_id','source_id']
        nodes=[{'tool':ns[0],'bindings':{}}]+[{'tool':ns[i+1],'bindings':{params[i]:{'node':i,'path':fields[i]}}} for i in range(4)]
        a={'kind':'learned_mcp_operation_dag','status':'trace_validated_effectful','execution_version':adapter(cfg['adapter']).scope(spec)['execution_version'],
           'nodes':nodes,'tool_contracts':{n:tc[n] for n in ns},'max_nodes':8,'source_task_fingerprints':['mock-one','mock-two'],'validation_task_fingerprint':'mock-cert'}
        a['certified_digest']=digest(a);p={'schema_version':1,'format':'sss-operation-graph-v1','execution_version_sha256':a['execution_version'],'artifact':a};p['policy_digest']=digest(p)
        save(out/'mock-interpreter-fixture.json',p);initialize(load_config(out/'rsi.json'));reg=ExperienceRegistry(state/'registry');relative,h=reg.object(out/'mock-interpreter-fixture.json')
        view={'schema_version':1,'format':'sss-experience-registry-v1','generation':0,'parent_digest':None,'reason':'explicit mock interpreter fixture',
              'automatic_selection_uses_profile_id':False,'entries':[{'entry_id':p['policy_digest'],'kind':'operation_graph','payload':relative,'sha256':h,
              'artifact_digest':p['policy_digest'],'runtime_source':source_map(adapter(cfg['adapter']).runtime_sources()),'state':'candidate','activated_generation':1}]};view['registry_digest']=digest(view)
        save(state/'mock-registry.json',view);cfg.update(role='candidate_certification',registry_file=str(state/'mock-registry.json'));save(out/'rsi.json',cfg)
    provider=ThreadingHTTPServer(('127.0.0.1',0),Provider);provider.requests=[];thread=threading.Thread(target=provider.serve_forever,daemon=True);thread.start()
    sp=importlib.util.spec_from_file_location('operation_cli',ROOT/'scripts/run-file-scenario.py');runner=importlib.util.module_from_spec(sp);sp.loader.exec_module(runner)
    original=runner.create_server;runner.create_server=lambda host,port,origin,state:original(host,port,f'http://127.0.0.1:{provider.server_port}',state)
    os.environ.update(FM_TASK_FILE=str(out/'input.json'),FM_OUTPUT=str(out/'delivery'),DEEPSEEK_API_KEY='mock',DSH_HOME=str(out/'dsh'))
    sys.argv=['scenario','--scenario',str(out/'scenario.json'),'--rsi-config',str(out/'rsi.json'),'--budget-usd','5','--max-steps','96','--max-output','4000','--call-model']
    try:
        status=runner.main();r=records(state)[0];assert status==0 and r['accepted'] and r['lifecycle_verified'],{'status':status,'record':r}
        audit=[json.loads(l) for l in (Path(r['run_dir'])/'experience-audit.jsonl').read_text().splitlines()]
        assert audit[0]['kind']=='experience_runtime_ready'
        if candidate:assert r['verified_motif_batches']==4 and not r['deferred'],r
        assert (work/'results/copy.txt').read_bytes()==(work/'notes.txt').read_bytes()
        value={'status':'passed','actual_CLI_SDK_MCP':True,'fixture_candidate':candidate,'model_requests':len(provider.requests),
               'verified_structural_requests':r['verified_motif_batches'],'real_cloud_requests':0,'output':str(out),'mock_not_training':True}
        save(out/'free-outcome.json',value);print(json.dumps(value),flush=True)
    finally:provider.shutdown();provider.server_close();thread.join(timeout=5)

if __name__=='__main__':run('--candidate' in sys.argv)
