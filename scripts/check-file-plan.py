"""Actual SDK/MCP effect capability check against a local scripted provider; zero cloud calls."""
import argparse,hashlib,json,shutil,sys,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scenarios/file-management'));sys.path.insert(0,str(ROOT))
from common import PREFIX,DATA,digest,save,snapshot
from plan_study import scope,expected_actions
from src.adapters.scenario import prepare_scenario
from src.adapters.harness_runtime import create_harness
from src.adapters.native_budget import NativeBudgetGuard
class Provider(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_POST(self):
  body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));self.server.requests.append(body)
  if self.path!='/v1/chat/completions':self.server.other+=1;self.send_error(503);return
  values=[]
  for m in body['messages']:
   if m['role']=='tool':
    try:values.append(json.loads(m['content']))
    except (ValueError,TypeError):pass
  work=next((v for v in values if v.get('write_grant')),None);listing=next((v for v in values if 'files' in v),None)
  preview=next((v for v in values if v.get('status')=='validated_copy_plan'),None);auth=next((v for v in values if v.get('status')=='task_grant_authorized'),None);receipt=next((v for v in values if v.get('status')=='executed_verified'),None)
  if not work:actions=[('read_task',{})]
  elif not listing:actions=[('list_files',{})]
  elif not preview:actions=[('preview_actions',{'actions':self.server.actions})]
  elif not auth:actions=[('authorize_plan',{'plan_id':preview['plan_id']})]
  elif not receipt:actions=[('execute_plan',{'plan_id':preview['plan_id'],'authorization_id':auth['authorization_id']})]
  else:actions=[]
  delta={'role':'assistant','tool_calls':[{'index':i,'id':f'mock-{len(self.server.requests)}-{i}','type':'function','function':{'name':PREFIX+n,'arguments':json.dumps(a)}} for i,(n,a) in enumerate(actions)]} if actions else {'role':'assistant','content':'Local capability check completed.'}
  base={'id':'fixture','created':1,'model':body['model'],'object':'chat.completion.chunk'};chunks=[{**base,'choices':[{'index':0,'delta':delta,'finish_reason':None}]},{**base,'choices':[{'index':0,'delta':{},'finish_reason':'tool_calls' if actions else 'stop'}]},{**base,'choices':[],'usage':{'prompt_tokens':100,'completion_tokens':20,'total_tokens':120}}]
  data=(''.join('data: '+json.dumps(c)+'\n\n' for c in chunks)+'data: [DONE]\n\n').encode();self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
def main():
 p=argparse.ArgumentParser();p.add_argument('--experiment',type=Path,required=True);p.add_argument('--stale',action='store_true');a=p.parse_args();exp=a.experiment.resolve();out=exp/'sdk-checks'/uuid4().hex;out.mkdir(parents=True,mode=0o700)
 protocol=json.loads((exp/'protocol.json').read_text());case=next(c for c in protocol['tasks'] if c['family']=='copy_holdout');td=Path(case['task_dir']);spec=json.loads((td/'input.json').read_text());work=DATA/exp.name/'sdk-copies'/out.name;shutil.copytree(case['pristine'],work);spec['workspace']=str(work);save(out/'input.json',spec)
 (out/'prompt.md').write_text('Local explicit task-copy capability check.');(out/'prompt.md').chmod(0o600);config=json.loads((td/'scenario.json').read_text());config.pop('completion_guard');config['prompt']=str(out/'prompt.md');save(out/'scenario.json',config)
 prepared=prepare_scenario(out/'scenario.json',entry_motif=True);task=scope(spec);task.update(session_id='plan-check-'+uuid4().hex,prompt_sha256=prepared['prompt_sha256'])
 if a.stale:task['input_version']='0'*64
 save(out/'plan-task.json',task);server=ThreadingHTTPServer(('127.0.0.1',0),Provider);server.requests=[];server.other=0;server.actions=expected_actions(spec);worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start();guard=NativeBudgetGuard(max_model_requests=20,max_observed_input_tokens=None)
 env={'DSH_HOME':str(out/'dsh'),'DEEPSEEK_API_KEY':'mock-no-key','DEEPSEEK_BASE_URL':f'http://127.0.0.1:{server.server_port}/v1','FM_TASK_FILE':str(out/'input.json'),'FM_OUTPUT':str(out/'delivery'),
  'SSS_SCENARIO_PRESENTATION':'native','SSS_SCENARIO_TOOLS':json.dumps(prepared['allowed_tools']),'SSS_PLAN_MOTIF_POLICY':str(exp/'learned/policy.json'),'SSS_PLAN_MOTIF_TASK':str(out/'plan-task.json')}
 for name in ('SSS_ENTRY_MOTIF_POLICY','SSS_ENTRY_MOTIF_TASK','SSS_TERMINAL_MOTIF_POLICY','SSS_TERMINAL_MOTIF_TASK','SSS_COLLECTION_MOTIF_POLICY','SSS_COLLECTION_MOTIF_TASK','SSS_COLLECTION_SCRIPT','SSS_COLLECTION_SCRIPT_TASK','SSS_ONLINE_MOTIF_MANIFEST','SSS_ONLINE_MOTIF_TASK'):env[name]=''
 try:
  with create_harness(root=ROOT,patches=(prepared['patch'],),env=env,cwd=str(out),runtime_cwd=str(out),provider='deepseek-official',model='deepseek-flash',max_tokens=4000,request_timeout_seconds=120) as client:result=client.run('Local explicit task-copy capability check.',session_id=task['session_id'],on_notification=guard.on_notification)
  save(out/'events.json',result.events);log=[json.loads(l) for l in (out/'.local/online-motif'/(hashlib.sha256(task['session_id'].encode()).hexdigest()+'.jsonl')).read_text().splitlines()];verified=sum(r['kind']=='plan_model_request_bypassed_verified' for r in log)
  assert result.finish_reason=='completed' and len(server.requests)==(6 if a.stale else 4) and verified==(0 if a.stale else 2) and server.other==0
  from src.motif_core.offline.plan_compiler import effect_snapshot
  assert snapshot(work)==effect_snapshot(scope(spec),expected_actions(spec))
  r={'real_api_requests':0,'mock_http_requests':len(server.requests),'verified_continuations':verified,'stale_input_fallback':a.stale,'byte_effects_verified':True,'scripted_selection_not_training':True,'output':str(out)};save(out/'outcome.json',r);print(json.dumps(r))
 finally:server.shutdown();server.server_close();worker.join(timeout=5)
if __name__=='__main__':main()
