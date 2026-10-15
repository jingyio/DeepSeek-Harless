"""Actual SDK/MCP normal/crash cold transport checks; scripted loopback provider, zero cloud."""
import argparse,json,sys,threading,hashlib
from pathlib import Path
from uuid import uuid4
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scenarios/file-management'))
import workflow_holdout as w
from common import save,PREFIX,sha
from src.adapters.scenario import prepare_scenario
from src.adapters.harness_runtime import create_harness
from src.adapters.native_budget import NativeBudgetGuard
from src.adapters.file_job_budget import FileJobBudget,job_command
from src.adapters.deepseek_cost_gate import create_server

class Provider(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_POST(self):
  body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));self.server.requests.append(body);values=[]
  for m in body['messages']:
   if m['role']=='tool':
    try:values.append(json.loads(m['content']))
    except (ValueError,TypeError):pass
  task=next((v for v in reversed(values) if v.get('rename_targets')),None)
  listing=next((v for v in reversed(values) if 'files' in v and all('path' in r for r in v['files'])),None)
  preview=next((v for v in values if v.get('status')=='validated_copy_plan'),None)
  auth=next((v for v in values if v.get('status')=='task_grant_authorized'),None)
  effect=next((v for v in values if v.get('status')=='executed_verified'),None)
  restored=next((v for v in values if v.get('status')=='restored_verified'),None)
  report=next((v for v in values if v.get('status') in ('delivered','delivered_with_gaps')),None)
  if not task:actions=[('read_task',{})]
  elif not listing:actions=[('list_files',{})]
  elif self.server.cold:
   record=task['recovery_state'][0];kw={'plan_id':record['plan_id'],'authorization_id':record['authorization_id']}
   if self.server.condition=='N' and not effect:actions=[('execute_plan',kw)]
   elif self.server.condition=='E' and not restored:actions=[('restore_plan',kw)]
   elif self.server.condition=='E' and any(r['path'].startswith('normalized/') for r in listing['files']):actions=[('list_files',{})]
   elif not report:actions=[('submit_report',{'summary':'Cold free SDK same task, actual persisted plan and original limits','file_ids':[r['file_id'] for r in listing['files']],'gaps':[],'report_kind':'task_result'})]
   else:actions=[]
  elif not preview:
   ids={r['path']:r['file_id'] for r in listing['files']};actions=[('preview_actions',{'actions':[{'op':'move','file_ids':[ids[r['source']]],'destination':r['destination']} for r in task['rename_targets']]})]
  elif not auth:actions=[('authorize_plan',{'plan_id':preview['plan_id']})]
  elif not effect:actions=[('execute_plan',{'plan_id':preview['plan_id'],'authorization_id':auth['authorization_id']})]
  else:actions=[]
  delta={'role':'assistant','tool_calls':[{'index':i,'id':f'mock-{len(self.server.requests)}-{i}','type':'function','function':{'name':PREFIX+n,'arguments':json.dumps(a)}} for i,(n,a) in enumerate(actions)]} if actions else {'role':'assistant','content':'Free controlled transport check completed.'}
  base={'id':'mock','created':1,'model':body['model'],'object':'chat.completion.chunk'};chunks=[{**base,'choices':[{'index':0,'delta':delta,'finish_reason':None}]},{**base,'choices':[{'index':0,'delta':{},'finish_reason':'tool_calls' if actions else 'stop'}]},
   {**base,'choices':[],'usage':{'prompt_tokens':100,'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':100,'completion_tokens':20,'total_tokens':120}}]
  data=(''.join('data: '+json.dumps(v)+'\n\n' for v in chunks)+'data: [DONE]\n\n').encode();self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)

def check(exp,condition,arm):
 p=json.loads((exp/'protocol.json').read_text());c={**next(c for c in p['probes'] if c['workflow_id']=='FM38' and c['condition']==condition),'arm':arm}
 out,spec,env,policy=w.instantiate(exp,c,p,True);prepared=prepare_scenario(Path(c['task_dir'])/'scenario.json',entry_motif=arm=='M')
 task=json.loads((out/'scope.json').read_text());task.update(session_id='holdout-sdk-'+uuid4().hex,prompt_sha256=prepared['prompt_sha256']);save(out/'scope.json',task)
 server=ThreadingHTTPServer(('127.0.0.1',0),Provider);server.requests=[];server.cold=False;server.condition=condition;worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
 budget=FileJobBudget(out/'job.json',out/'mock-cost-ledger.jsonl');gate=create_server('127.0.0.1',0,f'http://127.0.0.1:{server.server_port}',budget);gw=threading.Thread(target=gate.serve_forever,daemon=True);gw.start()
 env.update(DEEPSEEK_API_KEY='mock-no-key',DEEPSEEK_BASE_URL=f'http://127.0.0.1:{gate.server_port}/v1',DSH_HOME=str(out/'dsh'),SSS_SCENARIO_PRESENTATION='native',SSS_SCENARIO_TOOLS=json.dumps(prepared['allowed_tools']),SSS_BUDGET_LEDGER=str(out/'mock-cost-ledger.jsonl'))
 for n in ['SSS_ONLINE_MOTIF_MANIFEST','SSS_ONLINE_MOTIF_TASK','SSS_ENTRY_MOTIF_POLICY','SSS_ENTRY_MOTIF_TASK','SSS_TERMINAL_MOTIF_POLICY','SSS_TERMINAL_MOTIF_TASK','SSS_COLLECTION_MOTIF_POLICY','SSS_COLLECTION_MOTIF_TASK','SSS_COLLECTION_SCRIPT','SSS_COLLECTION_SCRIPT_TASK','SSS_REENTRY_MOTIF_POLICY','SSS_REENTRY_MOTIF_TASK','SSS_PLAN_MOTIF_POLICY','SSS_PLAN_MOTIF_TASK','SSS_DURABLE_PLAN_BINDING']:env[n]=''
 if arm=='M':env.update(SSS_PLAN_MOTIF_POLICY=str(policy),SSS_PLAN_MOTIF_TASK=str(out/'scope.json'),SSS_DURABLE_PLAN_BINDING=str(out/'binding.json'))
 guard=NativeBudgetGuard(max_model_requests=96,max_observed_input_tokens=None);error=None
 try:
  try:
   with create_harness(root=ROOT,patches=(prepared['patch'],str(exp/'control.patch.yml')),env=env,cwd=str(out),runtime_cwd=str(out),provider='deepseek-official',model='deepseek-flash',max_tokens=4000,request_timeout_seconds=120) as client:client.run(prepared['prompt'],session_id=task['session_id'],on_notification=guard.on_notification)
  except Exception as e:error=str(e)
  marker=json.loads((out/'control-marker.json').read_text());assert marker['interrupted'];warm=job_command(out/'job.json','state')['state'];assert warm['status']=='running'
  save(out/'warm-events.json',guard.events);save(out/'warm-job.json',warm)
  if condition=='E':
   rd=job_command(out/'job.json','begin-check')['round'];trace=ROOT/'.local/task-acceptance'/hashlib.sha256(str(out/'job.json').encode()).hexdigest()
   failed=w.mcp.validator.check(out/'input.json',sha(out/'input.json'),out/'delivery',trace,rd,{'receipt':None,'events':guard.events});assert not failed['passed'];job_command(out/'job.json','repair',{'round':rd,'errors':failed['errors']})
  server.cold=True
  with create_harness(root=ROOT,patches=(prepared['patch'],str(exp/'control.patch.yml')),env=env,cwd=str(out),runtime_cwd=str(out),provider='deepseek-official',model='deepseek-flash',max_tokens=4000,request_timeout_seconds=120) as client:result=client.run(prepared['prompt'],session_id=task['session_id']+'-cold',on_notification=guard.on_notification)
  state=job_command(out/'job.json','state')['state'];assert state['status']=='completed' and state['requests']==len(server.requests) and state['limits']==warm['limits']
  assert state['repairs']==(1 if condition=='E' else 0);assert result.finish_reason=='completed'
  save(out/'events.json',guard.events);save(out/'mock-requests.json',server.requests)
  r={'status':'passed','condition':condition,'arm':arm,'mock_http_requests':len(server.requests),'real_api_requests':0,'estimated_real_model_cost_usd':0,'same_job_cold_harness_restart':True,'warm_requests':warm['requests'],'final_requests':state['requests'],'repairs':state['repairs'],'error_at_frozen_boundary':error,'not_training':True,'output':str(out)};save(out/'sdk-outcome.json',r);return r
 except Exception as e:save(out/'sdk-outcome.json',{'status':'failed','error':type(e).__name__+': '+str(e),'output':str(out),'real_api_requests':0});raise
 finally:gate.shutdown();gate.server_close();gw.join(timeout=5);server.shutdown();server.server_close();worker.join(timeout=5)

if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--experiment',type=Path,required=True);args=a.parse_args()
 rows=[]
 for condition,arm in [('N','H'),('N','M'),('E','H'),('E','M')]:r=check(args.experiment.resolve(),condition,arm);rows.append(r);print(json.dumps(r),flush=True)
 save(args.experiment/'free-sdk-summary.json',{'checks':4,'passed':4,'real_api_requests':0,'results':rows})
