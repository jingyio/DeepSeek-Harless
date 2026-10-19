"""Free ordinary CLI/SDK/MCP lifecycle check; simulated Provider is never training."""
import importlib.util,json,os,sys,threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from common import snapshot,save,PREFIX
from workflow_tools import TOOLS
from src.adapters.continuous_rsi import records
from src.adapters.continuous_motif_learning import frame

class Provider(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_POST(self):
  b=json.loads(self.rfile.read(int(self.headers['Content-Length'])));self.server.requests.append(b);values=[]
  for m in b['messages']:
   if m['role']=='tool':
    try:values.append(json.loads(m['content']))
    except (ValueError,TypeError):pass
  task=next((v for v in values if isinstance(v,dict) and 'objective' in v),None)
  inventory=next((v for v in values if isinstance(v,dict) and 'files' in v and 'snapshot_sha256' in v and 'collection_id' not in v),None)
  selected=next((v for v in values if isinstance(v,dict) and v.get('selection')=='actual_model_selected_members'),None)
  complete=next((v for v in values if isinstance(v,dict) and v.get('status')=='collection_complete'),None)
  report=next((v for v in values if isinstance(v,dict) and v.get('status') in ('delivered','delivered_with_gaps')),None)
  pins=[v for v in values if isinstance(v,dict) and v.get('source_id') and v.get('source_version') and 'text' not in v and 'status' not in v]
  reads=[v for v in values if isinstance(v,dict) and v.get('source_id') and v.get('status') in ('readable','unreadable','metadata_only','unsupported')]
  if not task:actions=[('read_task',{})]
  elif not inventory:actions=[('list_files',{})]
  elif not selected:actions=[('select_files',{'file_ids':[r['file_id'] for r in inventory['files']]})]
  elif len(pins)<len(selected['files']):actions=[('pin_file',{'file_id':r['file_id']}) for r in selected['files'] if r['file_id'] not in {p['file_id'] for p in pins}]
  elif len(reads)<len(selected['files']):actions=[('read_file',{'source_id':p['source_id']}) for p in pins if p['source_id'] not in {r['source_id'] for r in reads}]
  elif not complete:actions=[('collect_reads',{'collection_id':selected['collection_id'],'source_ids':[r['source_id'] for r in reads]})]
  elif not report:actions=[('submit_report',{'summary':'Free lifecycle test, simulated decisions, not learning evidence','file_ids':[r['file_id'] for r in selected['files']],'gaps':[],'report_kind':'inspection'})]
  else:actions=[]
  delta={'role':'assistant','tool_calls':[{'index':i,'id':f'free-{len(self.server.requests)}-{i}','type':'function','function':{'name':PREFIX+n,'arguments':json.dumps(a)}} for i,(n,a) in enumerate(actions)]} if actions else {'role':'assistant','content':'Free check complete.'}
  base={'id':'free-rsi','created':1,'model':b['model'],'object':'chat.completion.chunk'}
  chunks=[{**base,'choices':[{'index':0,'delta':delta,'finish_reason':None}]},{**base,'choices':[{'index':0,'delta':{},'finish_reason':'tool_calls' if actions else 'stop'}]},
          {**base,'choices':[],'usage':{'prompt_tokens':100,'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':100,'completion_tokens':20,'total_tokens':120}}]
  data=(''.join('data: '+json.dumps(c)+'\n\n' for c in chunks)+'data: [DONE]\n\n').encode()
  self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)

def main():
 uid='free-'+uuid4().hex[:12];out=ROOT/'.local/continuous-rsi-checks'/uid;out.mkdir(parents=True)
 work=ROOT/'testpdf/file-management-experiment'/uid/'source';work.mkdir(parents=True);(work/'.experiment-copy').write_text(uid)
 for i in range(3):(work/f'item-{i}.txt').write_text('Free actual MCP material '+str(i))
 spec={'schema_version':1,'task_id':uid,'role':'bootstrap','family':'inventory','objective':'Read all current files using one complete selection and deliver an inspection report.',
       'workspace':str(work),'initial_snapshot':snapshot(work),'rules':{},'allowed_operations':[],
       'report_contract':{'version':'sss-file-report-v3','kind':'inspection','collection_count':1}}
 save(out/'input.json',spec);(out/'prompt.md').write_text(spec['objective']);save(out/'scenario.json',{'schema_version':1,'name':'file_management','prompt':str(out/'prompt.md'),
  'servers':[{'server_name':'file_management','transport':'stdio','command':'${PYTHON}','args':['${PROJECT_ROOT}/scenarios/file-management/report_tools.py'],
              'cwd':'${PROJECT_ROOT}','env':{'FM_TASK_FILE':{'from_env':'FM_TASK_FILE'},'FM_OUTPUT':{'from_env':'FM_OUTPUT'}}}],
  'allowed_tools':[PREFIX+n for n in TOOLS],'acceptance_guard':{'kind':'file_management','max_repairs':2}})
 state=ROOT/'.local/rsi'/uid;save(out/'rsi.json',{'schema_version':1,'format':'sss-continuous-rsi-v1','state_root':str(state),
  'workspace_roots':[str(work.parent)],'mode':'observe','provider_mode':'mock','series_cap_usd':1000,'learning_cap_usd':0,
  'auto_worker':False,'allow_material_copy':False,'limits':{'budget_usd':5,'max_steps':96,'max_output':4000,'max_repairs':2}})
 provider=ThreadingHTTPServer(('127.0.0.1',0),Provider);provider.requests=[];thread=threading.Thread(target=provider.serve_forever,daemon=True);thread.start()
 sp=importlib.util.spec_from_file_location('public_cli',ROOT/'scripts/run-file-scenario.py');runner=importlib.util.module_from_spec(sp);sp.loader.exec_module(runner)
 real_gate=runner.create_server;runner.create_server=lambda host,port,origin,budget:real_gate(host,port,f'http://127.0.0.1:{provider.server_port}',budget)
 os.environ.update(FM_TASK_FILE=str(out/'input.json'),FM_OUTPUT=str(out/'delivery'),DEEPSEEK_API_KEY='mock-no-key',DSH_HOME=str(out/'dsh'))
 sys.argv=['run-scenario','--scenario',str(out/'scenario.json'),'--rsi-config',str(out/'rsi.json'),'--budget-usd','5','--max-steps','96','--max-output','4000','--call-model']
 try:
  code=runner.main();rr=records(state);assert code==0 and len(rr)==1,{'exit':code,'records':rr}
  r=rr[0];assert r['accepted'] and r['lifecycle_verified'] and r['accounting_complete']
  try:frame(r)
  except ValueError as e:assert 'real task' in str(e)
  else:raise AssertionError('mock record was allowed to train')
  assert snapshot(work)==spec['initial_snapshot'] and (state/'queue'/(r['session_id']+'.json')).exists()
  result={'status':'passed','actual_CLI_SDK_MCP':True,'lifecycle_and_schema_verified':True,'queue_sealed':True,
          'mock_http_requests':len(provider.requests),'real_api_requests':0,'mock_training_refused':True,'output':str(out),'state_root':str(state)}
  save(out/'free-outcome.json',result);save(ROOT/'.local/continuous-rsi-free-current.json',result);print(json.dumps(result),flush=True)
 finally:provider.shutdown();provider.server_close();thread.join(timeout=5)

if __name__=='__main__':main()
