"""Free real Harness/MCP repair, retry exhaustion and shared-budget diagnostics."""
import argparse,hashlib,json,os,sys,threading
from pathlib import Path
from uuid import uuid4
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from common import save,snapshot,PREFIX
from src.adapters.scenario import prepare_scenario
from src.adapters.harness_runtime import create_harness
from src.adapters.native_budget import NativeBudgetGuard
from src.adapters.deepseek_cost_gate import State,create_server

class Provider(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_POST(self):
  body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));self.server.requests.append(body);values=[]
  for message in body['messages']:
   if message['role']=='tool':
    try:values.append(json.loads(message['content']))
    except (ValueError,TypeError):pass
  work=next((v for v in values if isinstance(v,dict) and 'objective' in v),None)
  listings=[v for v in values if isinstance(v,dict) and 'files' in v];listing=listings[-1] if listings else None
  reports=[v for v in values if isinstance(v,dict) and v.get('status') in ('delivered','delivered_with_gaps')]
  repaired='任务程序验收未通过' in json.dumps(body['messages'],ensure_ascii=False)
  plans=[v for v in values if isinstance(v,dict) and v.get('status')=='validated_copy_plan']
  executed=any(isinstance(v,dict) and v.get('status')=='executed_verified' for v in values)
  actions=[]
  if work is None:actions=[('read_task',{})]
  elif listing is None:actions=[('list_files',{})]
  elif not reports:actions=[('submit_report',{'summary':'Deliberately incomplete first delivery for fault injection.','file_ids':[r['file_id'] for r in listing['files']],'gaps':[]})]
  elif not repaired:actions=[]
  elif self.server.case=='exhaustion':
   if not self.server.forbidden_attempts:
    self.server.forbidden_attempts+=1;actions=[('preview_actions',{'actions':[{'op':'move','file_ids':[listing['files'][0]['file_id']],'destination':'normalized/txt/item_01.txt'}]})]
  elif not plans:
   rows=sorted((r for r in listing['files'] if r['path'].startswith('inbox/')),key=lambda r:r['path'])
   actions=[('preview_actions',{'actions':[{'op':'move','file_ids':[r['file_id']],'destination':f'normalized/{Path(r["path"]).suffix[1:]}/item_{i:02d}{Path(r["path"]).suffix}'} for i,r in enumerate(rows,1)]})]
  elif not executed:actions=[('execute_plan',{'plan_id':plans[-1]['plan_id']})]
  elif any(r['path'].startswith('inbox/') for r in listing['files']):actions=[('list_files',{})]
  elif len(reports)==1:actions=[('submit_report',{'summary':'Corrected global numbering.','file_ids':[r['file_id'] for r in listing['files']],'gaps':[]})]
  delta={'role':'assistant','tool_calls':[{'index':i,'id':f'fixture-{len(self.server.requests)}-{i}','type':'function','function':{'name':PREFIX+n,'arguments':json.dumps(a)}} for i,(n,a) in enumerate(actions)]} if actions else {'role':'assistant','content':'Stop and let the fixed acceptance guard decide.'}
  base={'id':'repair-fixture','created':1,'model':body['model'],'object':'chat.completion.chunk'}
  chunks=[{**base,'choices':[{'index':0,'delta':delta,'finish_reason':None}]},{**base,'choices':[{'index':0,'delta':{},'finish_reason':'tool_calls' if actions else 'stop'}]},{**base,'choices':[],'usage':{'prompt_tokens':100,'completion_tokens':20,'total_tokens':120}}]
  data=(''.join('data: '+json.dumps(c)+'\n\n' for c in chunks)+'data: [DONE]\n\n').encode();self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)

def main():
 p=argparse.ArgumentParser();p.add_argument('--case',choices=['pass','exhaustion','budget'],default='pass');a=p.parse_args();uid=uuid4().hex
 out=ROOT/'.local/acceptance-repair-checks'/uid;work=ROOT/'testpdf/file-management-experiment'/('repair-check-'+uid)
 (work/'inbox').mkdir(parents=True);(work/'.experiment-copy').write_text(uid);(work/'inbox/a.txt').write_text('text bytes');(work/'inbox/z.md').write_text('markdown bytes')
 spec={'workspace':str(work),'task_id':uid,'family':'rename','objective':'Rename all inbox files with globally numbered destinations.','rules':{},'allowed_operations':[] if a.case=='exhaustion' else ['move'],'initial_snapshot':snapshot(work)}
 save(out/'input.json',spec);(out/'prompt.md').write_text('Use actual tools. The provider fixture injects one incomplete first report. Repair only inside the original permissions.');(out/'prompt.md').chmod(0o600)
 names=['read_task','list_files','pin_file','read_file','hash_files','build_index','search_index','compare_snapshot','preview_actions','execute_plan','restore_plan','submit_report']
 config={'schema_version':1,'name':'file_management','prompt':str(out/'prompt.md'),'servers':[{'server_name':'file_management','transport':'stdio','command':'${PYTHON}','args':['${PROJECT_ROOT}/scenarios/file-management/file_tools.py'],'cwd':'${PROJECT_ROOT}','env':{'FM_TASK_FILE':{'from_env':'FM_TASK_FILE'},'FM_OUTPUT':{'from_env':'FM_OUTPUT'}}}], 'allowed_tools':[PREFIX+n for n in names],'acceptance_guard':{'kind':'file_management','max_repairs':2}}
 save(out/'scenario.json',config);prepared=prepare_scenario(out/'scenario.json')
 provider=ThreadingHTTPServer(('127.0.0.1',0),Provider);provider.requests=[];provider.case=a.case;provider.forbidden_attempts=0
 threads=[threading.Thread(target=provider.serve_forever,daemon=True)];threads[0].start()
 state=State(cap_usd=.25,output_cap=1000,record=out/'ledger.jsonl',request_limit=2 if a.case=='budget' else 30)
 gate=create_server('127.0.0.1',0,f'http://127.0.0.1:{provider.server_port}',state);threads.append(threading.Thread(target=gate.serve_forever,daemon=True));threads[-1].start()
 session='acceptance-'+uid;guard=NativeBudgetGuard(max_model_requests=20,max_observed_input_tokens=None)
 env={**os.environ,'DEEPSEEK_API_KEY':'mock-no-key','DEEPSEEK_BASE_URL':f'http://127.0.0.1:{gate.server_port}/v1','DSH_HOME':str(out/'dsh'),'FM_TASK_FILE':str(out/'input.json'),'FM_OUTPUT':str(out/'delivery'),'SSS_SCENARIO_TOOLS':json.dumps(prepared['allowed_tools']),'SSS_SCENARIO_PRESENTATION':'native','SSS_BUDGET_LEDGER':str(out/'ledger.jsonl')}
 for n in ['SSS_ONLINE_MOTIF_MANIFEST','SSS_ONLINE_MOTIF_TASK','SSS_ENTRY_MOTIF_POLICY','SSS_ENTRY_MOTIF_TASK','SSS_TERMINAL_MOTIF_POLICY','SSS_TERMINAL_MOTIF_TASK','SSS_COLLECTION_MOTIF_POLICY','SSS_COLLECTION_MOTIF_TASK','SSS_COLLECTION_SCRIPT','SSS_COLLECTION_SCRIPT_TASK','SSS_PLAN_MOTIF_POLICY','SSS_PLAN_MOTIF_TASK','SSS_REENTRY_MOTIF_POLICY','SSS_REENTRY_MOTIF_TASK']:env[n]=''
 error=None;result=None
 try:
  with create_harness(root=ROOT,patches=(prepared['patch'],),env=env,cwd=str(out),runtime_cwd=str(out),provider='deepseek-official',model='deepseek-flash',max_tokens=1000,request_timeout_seconds=60) as client:
   result=client.run(prepared['prompt'],session_id=session,on_notification=guard.on_notification)
 except Exception as exc:error=str(exc)
 finally:
  for server in [gate,provider]:server.shutdown();server.server_close()
  for thread in threads:thread.join(timeout=5)
 save(out/'events.json',guard.events);save(out/'provider-requests.json',provider.requests)
 archive=ROOT/'.local/task-acceptance'/hashlib.sha256(session.encode()).hexdigest();checks=[json.loads(x.read_text()) for x in sorted(archive.glob('round-*/result.json'))]
 repairs=[e for e in guard.events if e.get('type')=='user/message' and e.get('data',{}).get('source',{}).get('kind')=='task-acceptance-repair']
 body={'case':a.case,'error':error,'finish_reason':result.finish_reason if result else None,'checks':checks,'repairs':len(repairs),'mock_http_requests':len(provider.requests),'budget_accounted_usd':state.reserved_usd,'real_api_requests':0,'output':str(out)};save(out/'outcome.json',body)
 if a.case=='pass':assert result and result.finish_reason=='completed' and len(checks)==2 and not checks[0]['passed'] and checks[1]['passed'] and len(repairs)==1,body
 elif a.case=='exhaustion':assert len(checks)==3 and all(not x['passed'] for x in checks) and len(repairs)==2 and snapshot(work)==spec['initial_snapshot'],body
 else:assert len(provider.requests)==2 and state.request_count==2 and snapshot(work)==spec['initial_snapshot'],body
 print(json.dumps({k:v for k,v in body.items() if k!='checks'},ensure_ascii=False))
if __name__=='__main__':main()
