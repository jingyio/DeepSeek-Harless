"""Local inherited read-graph SDK compatibility check with the new report service, no cloud."""
import argparse,hashlib,json,sys,threading,math
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scenarios/file-management'));sys.path.insert(0,str(ROOT))
from common import PREFIX,digest,save
from report_study import task_scope
from src.adapters.scenario import prepare_scenario
from src.adapters.harness_runtime import create_harness
from src.adapters.native_budget import NativeBudgetGuard
class Provider(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_POST(self):
  body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
  if self.path!='/v1/chat/completions':self.server.other+=1;self.send_error(503);return
  self.server.requests.append(body);values=[]
  for m in body['messages']:
   if m['role']=='tool':
    try:values.append(json.loads(m['content']))
    except (ValueError,TypeError):pass
  work=next((v for v in values if 'objective' in v),None);listing=next((v for v in values if 'files' in v),None)
  selections=[v for v in values if v.get('selection')=='actual_model_selected_members'];gathers={v['collection_id']:v for v in values if v.get('status')=='collection_complete'}
  if work is None:actions=[('read_task',{})]
  elif listing is None:actions=[('list_files',{})]
  elif not selections:actions=[('select_files',{'file_ids':[r['file_id'] for r in listing['files'] if r['path'].startswith('stage_a/')]})]
  elif selections[-1]['collection_id'] not in gathers:
   selected=selections[-1];ids={r['file_id'] for r in selected['files']};pins=[v for v in values if v.get('file_id') in ids and 'source_id' in v and 'status' not in v];reads=[v for v in values if v.get('file_id') in ids and 'source_id' in v and 'status' in v]
   if len(pins)<len(ids):
    done={p['file_id'] for p in pins};actions=[('pin_file',{'file_id':r['file_id']}) for r in selected['files'] if r['file_id'] not in done]
   elif len(reads)<len(ids):
    done={r['source_id'] for r in reads};actions=[('read_file',{'source_id':p['source_id']}) for p in pins if p['source_id'] not in done]
   else:actions=[('collect_reads',{'collection_id':selected['collection_id'],'source_ids':[r['source_id'] for r in reads]})]
  elif len(selections)==1:
   notice=json.loads(next(v['text'] for v in values if v.get('path')=='stage_a/followup.txt' and v.get('status')=='readable'))
   rows=[r for r in listing['files'] if r['path'].startswith('stage_b/') and ('*' in notice['followup_extensions'] or Path(r['path']).suffix.lower() in notice['followup_extensions'])]
   actions=[('select_files',{'file_ids':[r['file_id'] for r in rows]})]
  else:actions=[]
  delta={'role':'assistant','tool_calls':[{'index':i,'id':f'fixture-{len(self.server.requests)}-{i}','type':'function','function':{'name':PREFIX+n,'arguments':json.dumps(a)}} for i,(n,a) in enumerate(actions)]} if actions else {'role':'assistant','content':'Two semantic frontiers completed locally.'}
  base={'id':'fixture','created':1,'model':body['model'],'object':'chat.completion.chunk'};chunks=[{**base,'choices':[{'index':0,'delta':delta,'finish_reason':None}]},{**base,'choices':[{'index':0,'delta':{},'finish_reason':'tool_calls' if actions else 'stop'}]},{**base,'choices':[],'usage':{'prompt_tokens':100,'completion_tokens':20,'total_tokens':120}}]
  data=(''.join('data: '+json.dumps(c)+'\n\n' for c in chunks)+'data: [DONE]\n\n').encode();self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
def main():
 p=argparse.ArgumentParser();p.add_argument('--experiment',type=Path,required=True);p.add_argument('--arm',choices=['H','L1','L2'],default='L2');p.add_argument('--stale',action='store_true');a=p.parse_args();exp=a.experiment.resolve();protocol=json.loads((exp/'protocol.json').read_text());c=next(c for c in protocol['tasks'] if c['role']=='quality' and c['family']=='inventory')
 td=Path(c['task_dir']);out=exp/'sdk-checks'/uuid4().hex;out.mkdir(parents=True,mode=0o700);spec=json.loads((td/'input.json').read_text());save(out/'input.json',spec)
 prompt='Read stage_a then choose stage_b using the actual followup data; local SDK check.';(out/'prompt.md').write_text(prompt);(out/'prompt.md').chmod(0o600);config=json.loads((td/'scenario.json').read_text());config.pop('completion_guard');config['prompt']=str(out/'prompt.md');save(out/'scenario.json',config)
 prepared=prepare_scenario(out/'scenario.json',entry_motif=a.arm!='H');task=task_scope(spec);task.update(session_id='rsi-check-'+uuid4().hex,prompt_sha256=prepared['prompt_sha256'])
 if a.stale:task['input_version']='0'*64
 save(out/'scope.json',task);server=ThreadingHTTPServer(('127.0.0.1',0),Provider);server.requests=[];server.other=0;worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start();guard=NativeBudgetGuard(max_model_requests=30,max_observed_input_tokens=None)
 env={'DSH_HOME':str(out/'dsh'),'DEEPSEEK_API_KEY':'mock-no-key','DEEPSEEK_BASE_URL':f'http://127.0.0.1:{server.server_port}/v1','FM_TASK_FILE':str(out/'input.json'),'FM_OUTPUT':str(out/'delivery'),'SSS_SCENARIO_PRESENTATION':'native','SSS_SCENARIO_TOOLS':json.dumps(prepared['allowed_tools'])}
 for n in ['SSS_ENTRY_MOTIF_POLICY','SSS_ENTRY_MOTIF_TASK','SSS_TERMINAL_MOTIF_POLICY','SSS_TERMINAL_MOTIF_TASK','SSS_COLLECTION_MOTIF_POLICY','SSS_COLLECTION_MOTIF_TASK','SSS_COLLECTION_SCRIPT','SSS_COLLECTION_SCRIPT_TASK','SSS_PLAN_MOTIF_POLICY','SSS_PLAN_MOTIF_TASK','SSS_REENTRY_MOTIF_POLICY','SSS_REENTRY_MOTIF_TASK','SSS_ONLINE_MOTIF_MANIFEST','SSS_ONLINE_MOTIF_TASK']:env[n]=''
 if a.arm=='L1':env.update(SSS_COLLECTION_MOTIF_POLICY=str(exp/'L1/policy.json'),SSS_COLLECTION_MOTIF_TASK=str(out/'scope.json'))
 if a.arm=='L2':env.update(SSS_REENTRY_MOTIF_POLICY=str(exp/'L2/policy.json'),SSS_REENTRY_MOTIF_TASK=str(out/'scope.json'))
 try:
  with create_harness(root=ROOT,patches=(prepared['patch'],),env=env,cwd=str(out),runtime_cwd=str(out),provider='deepseek-official',model='deepseek-flash',max_tokens=4000,request_timeout_seconds=120) as client:result=client.run(prompt,session_id=task['session_id'],on_notification=guard.on_notification)
  save(out/'events.json',result.events);ap=out/'.local/online-motif'/(hashlib.sha256(task['session_id'].encode()).hexdigest()+'.jsonl');log=[json.loads(l) for l in ap.read_text().splitlines()] if ap.exists() else []
  assert result.finish_reason=='completed' and server.other==0;assert len(list((out/'delivery/collections').glob('*/summary.json')))==2
  expected=11 if a.arm=='H' or a.stale else 8 if a.arm=='L1' else 5;assert len(server.requests)==expected,(len(server.requests),expected)
  next_batches=sum(r['kind']=='reentry_epoch_batch_verified' for r in log)
  packets=[json.loads(p.read_text()) for p in (out/'delivery/collections').glob('*/summary.json')]
  second=next(p for p in packets if all(r['path'].startswith('stage_b/') for r in p['files']))
  expected_batches=2*math.ceil(second['count']/8)+1 if a.arm=='L2' and not a.stale else 0
  assert next_batches==expected_batches,(next_batches,expected_batches)
  r={'arm':a.arm,'stale_input':a.stale,'real_api_requests':0,'mock_http_requests':len(server.requests),'two_actual_collections':True,'second_epoch_batches':next_batches,'semantic_selector_scripted_not_training':True,'output':str(out)};save(out/'outcome.json',r);print(json.dumps(r))
 finally:server.shutdown();server.server_close();worker.join(timeout=5)
if __name__=='__main__':main()
