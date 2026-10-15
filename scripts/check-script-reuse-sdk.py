"""Real SDK + actual MCP candidate executions; no cloud, no training evidence."""
import argparse,json,sys,threading
from pathlib import Path
from uuid import uuid4
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scenarios/file-management'))
import workflow_holdout as h
from common import sha,digest,save,PREFIX
from src.adapters.scenario import prepare_scenario
from src.adapters.harness_runtime import create_harness
from src.adapters.native_budget import NativeBudgetGuard

class UnusedProvider(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        self.server.requests+=1;self.send_response(500);self.end_headers();self.wfile.write(b'unexpected provider use in zero-model candidate check')

class RepairProvider(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));self.server.bodies.append(body);values=[]
        for m in body['messages']:
            if m['role']=='tool':
                try:values.append(json.loads(m['content']))
                except (ValueError,TypeError):pass
        task=next((v for v in reversed(values) if v.get('workflow_contract')),None)
        listing=next((v for v in reversed(values) if 'files' in v and v.get('snapshot_sha256')),None)
        preview=next((v for v in reversed(values) if v.get('status')=='validated_copy_plan'),None)
        k=len(self.server.bodies)-1;actions=[]
        if k in (1,4,7):actions=[('list_files',{})]
        elif k in (2,5):
            ids={r['path']:r['file_id'] for r in listing['files']};sources=task['workflow_contract']['source_paths']
            pairs=[(n,'backup-set/'+n[len('source/'):]) for n in sources] if k==2 else [('backup-set/'+n[len('source/'):],'recovery-drill/'+n[len('source/'):]) for n in sources]
            actions=[('preview_actions',{'actions':[{'op':'copy','file_ids':[ids[n]],'destination':d} for n,d in pairs]})]
        elif k in (3,6):actions=[('execute_plan',{'plan_id':preview['plan_id']})]
        elif k==8:actions=[('submit_report',{'summary':'Local mock ordinary Harness repair after frozen script deferral and one failed acceptance','file_ids':[r['file_id'] for r in listing['files']],'gaps':[],'report_kind':'task_result'})]
        delta={'role':'assistant','tool_calls':[{'index':i,'id':f'mock-repair-{k}-{i}','type':'function','function':{'name':PREFIX+n,'arguments':json.dumps(a)}} for i,(n,a) in enumerate(actions)]} if actions else {'role':'assistant','content':'Premature delivery.' if k==0 else 'Local repair complete.'}
        base={'id':'mock','created':1,'model':body['model'],'object':'chat.completion.chunk'}
        chunks=[{**base,'choices':[{'index':0,'delta':delta,'finish_reason':None}]},{**base,'choices':[{'index':0,'delta':{},'finish_reason':'tool_calls' if actions else 'stop'}]},
                {**base,'choices':[],'usage':{'prompt_tokens':100,'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':100,'completion_tokens':20,'total_tokens':120}}]
        data=(''.join('data: '+json.dumps(v)+'\n\n' for v in chunks)+'data: [DONE]\n\n').encode();self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)

def check(exp,wid,repair=False):
    p=json.loads((exp/'protocol.json').read_text());c=next(c for c in p['tasks'] if c['role']=='certify' and c['arm']=='L' and c['workflow_id']==wid and c['condition']=='E')
    out,spec,env,_=h.instantiate(exp,c,p,True);prepared=prepare_scenario(Path(c['task_dir'])/'scenario.json')
    rec=next(r for r in json.loads((exp/'candidate-lock.json').read_text())['scripts'] if r['workflow_id']==wid)
    if repair:
        s=json.loads(Path(rec['path']).read_text());s['objective_sha256']=digest('controlled incompatible objective');del s['script_digest'];s['script_digest']=digest(s)
        save(out/'incompatible-free-script.json',s);rec={**rec,'path':str(out/'incompatible-free-script.json'),'sha256':sha(out/'incompatible-free-script.json')}
    b={'role':'free','script_file':rec['path'],'script_file_sha256':rec['sha256'],'task_file':str(out/'input.json'),'task_file_sha256':sha(out/'input.json'),
       'runtime_sha256':sha(ROOT/'src/adapters/dsh_learned_script.ts'),'prompt_sha256':prepared['prompt_sha256'],'audit_file':str(out/'learned-script-audit.jsonl')};save(out/'binding.json',b)
    server=ThreadingHTTPServer(('127.0.0.1',0),RepairProvider if repair else UnusedProvider);server.requests=0;server.bodies=[];worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    env.update(DEEPSEEK_API_KEY='mock-no-key',DEEPSEEK_BASE_URL=f'http://127.0.0.1:{server.server_port}/v1',DSH_HOME=str(out/'dsh'),SSS_LEARNED_SCRIPT_BINDING=str(out/'binding.json'),
               SSS_SCENARIO_PRESENTATION='native',SSS_SCENARIO_TOOLS=json.dumps(prepared['allowed_tools']))
    for n in ['SSS_ONLINE_MOTIF_MANIFEST','SSS_ONLINE_MOTIF_TASK','SSS_ENTRY_MOTIF_POLICY','SSS_ENTRY_MOTIF_TASK','SSS_TERMINAL_MOTIF_POLICY','SSS_TERMINAL_MOTIF_TASK','SSS_COLLECTION_MOTIF_POLICY','SSS_COLLECTION_MOTIF_TASK','SSS_COLLECTION_SCRIPT','SSS_COLLECTION_SCRIPT_TASK','SSS_REENTRY_MOTIF_POLICY','SSS_REENTRY_MOTIF_TASK','SSS_PLAN_MOTIF_POLICY','SSS_PLAN_MOTIF_TASK','SSS_DURABLE_PLAN_BINDING']:env[n]=''
    guard=NativeBudgetGuard(max_model_requests=96,max_observed_input_tokens=None)
    try:
        with create_harness(root=ROOT,patches=(prepared['patch'],str(exp/'control.patch.yml')),env=env,cwd=str(out),runtime_cwd=str(out),provider='deepseek-official',model='deepseek-flash',max_tokens=4000,request_timeout_seconds=15) as client:
            result=client.run(prepared['prompt'],session_id='script-sdk-'+uuid4().hex,on_notification=guard.on_notification)
        receipt=h.receipt_from(guard.events);report=json.loads((out/'delivery/report.json').read_text());review=h.verify_workflow(spec,report,out/'delivery',guard.events)
        save(out/'events.json',guard.events);assert result.finish_reason=='completed' and review['passed'] and receipt['artifact_sha256']==digest(report) and server.requests==0
        if repair:
            repairs=[e for e in guard.events if e.get('type')=='user/message' and e['data'].get('source',{}).get('kind')=='task-acceptance-repair']
            assert len(repairs)==1 and len(server.bodies)==10
            auto=[e for e in guard.events if e.get('type')=='tool/call' and e['data']['callId'].startswith('sss-')];assert len(auto)==1 and auto[0]['data']['name']==PREFIX+'read_task'
            save(out/'mock-requests.json',server.bodies)
        r={'status':'passed','workflow_id':wid,'real_api_requests':0,'mock_http_requests':len(server.bodies),'actual_mcp_and_sdk':True,'not_training':True,'ordinary_acceptance_repair':repair,'output':str(out)};save(out/'sdk-outcome.json',r);return r
    except Exception as e:save(out/'sdk-outcome.json',{'status':'failed','error':str(e),'output':str(out),'real_api_requests':0});save(out/'events.json',guard.events);raise
    finally:server.shutdown();server.server_close();worker.join(timeout=5)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--experiment',type=Path,required=True);args=a.parse_args();rows=[]
    for wid in ('FM05','FM17'):r=check(args.experiment.resolve(),wid);rows.append(r);print(json.dumps(r),flush=True)
    r=check(args.experiment.resolve(),'FM17',True);rows.append(r);print(json.dumps(r),flush=True)
    save(args.experiment/'free-sdk-summary.json',{'passed':3,'checks':3,'real_api_requests':0,'results':rows})
