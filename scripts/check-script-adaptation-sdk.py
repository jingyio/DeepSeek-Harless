"""Actual SDK/MCP zero-model v2 or local-provider v1 draft/repair; never training."""
import argparse,json,sys,threading
from pathlib import Path
from uuid import uuid4
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scenarios/file-management'))
import workflow_holdout as h
import script_adaptation_study as s
from common import save,digest,PREFIX
from src.adapters.scenario import prepare_scenario
from src.adapters.harness_runtime import create_harness
from src.adapters.native_budget import NativeBudgetGuard

class Provider(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));self.server.bodies.append(body)
        if not self.server.repair:self.send_response(500);self.end_headers();self.wfile.write(b'unexpected model request');return
        values=[]
        for m in body['messages']:
            if m['role']=='tool':
                try:values.append(json.loads(m['content']))
                except (ValueError,TypeError):pass
        task=next(v for v in reversed(values) if v.get('workflow_contract'));listing=next((v for v in reversed(values) if 'files' in v and v.get('snapshot_sha256')),None)
        pin=next((v for v in reversed(values) if 'source_id' in v and 'source_version' in v),None);preview=next((v for v in reversed(values) if v.get('status')=='validated_copy_plan'),None)
        k=len(self.server.bodies)-1;aa=[]
        if k in (0,5,8):aa=[('list_files',{})]
        elif k==1:aa=[('pin_file',{'file_id':next(r['file_id'] for r in listing['files'] if r['path']==task['workflow_contract']['context_paths'][0])})]
        elif k==2:aa=[('read_file',{'source_id':pin['source_id']})]
        elif k in (3,6):
            rows={r['path']:r for r in listing['files']};sources=[n for n in task['workflow_contract']['source_paths'] if not (rows[n]['extension']=='.txt' and rows[n]['bytes']==0)]
            pairs=[(n,'backup-set/'+n[len('source/'):]) for n in sources] if k==3 else [('backup-set/'+n[len('source/'):],'recovery-drill/'+n[len('source/'):]) for n in sources]
            aa=[('preview_actions',{'actions':[{'op':'copy','file_ids':[rows[n]['file_id']],'destination':d} for n,d in pairs]})]
        elif k in (4,7):aa=[('execute_plan',{'plan_id':preview['plan_id']})]
        elif k==9:aa=[('submit_report',{'summary':'Local simulated ordinary repair after explicit failed draft; real rule read, filtered originals and actual backup identities','file_ids':[r['file_id'] for r in listing['files']],'gaps':[],'report_kind':'task_result'})]
        delta={'role':'assistant','tool_calls':[{'index':i,'id':f'mock-adapt-{k}-{i}','type':'function','function':{'name':PREFIX+n,'arguments':json.dumps(a)}} for i,(n,a) in enumerate(aa)]} if aa else {'role':'assistant','content':'Local repair complete.'}
        base={'id':'mock','created':1,'model':body['model'],'object':'chat.completion.chunk'}
        chunks=[{**base,'choices':[{'index':0,'delta':delta,'finish_reason':None}]},{**base,'choices':[{'index':0,'delta':{},'finish_reason':'tool_calls' if aa else 'stop'}]},
            {**base,'choices':[],'usage':{'prompt_tokens':100,'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':100,'completion_tokens':20,'total_tokens':120}}]
        data=(''.join('data: '+json.dumps(v)+'\n\n' for v in chunks)+'data: [DONE]\n\n').encode();self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)

def check(exp,case,p,repair=False):
    out,spec,env,_=h.instantiate(exp,case,p,True);s.bind(exp,case,p,out,spec,env,True);prepared=prepare_scenario(Path(case['task_dir'])/'scenario.json')
    server=ThreadingHTTPServer(('127.0.0.1',0),Provider);server.bodies=[];server.repair=repair;worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    env.update(DEEPSEEK_API_KEY='mock-no-key',DEEPSEEK_BASE_URL=f'http://127.0.0.1:{server.server_port}/v1',DSH_HOME=str(out/'dsh'),SSS_SCENARIO_PRESENTATION='native',SSS_SCENARIO_TOOLS=json.dumps(prepared['allowed_tools']))
    for n in ['SSS_ONLINE_MOTIF_MANIFEST','SSS_ONLINE_MOTIF_TASK','SSS_ENTRY_MOTIF_POLICY','SSS_ENTRY_MOTIF_TASK','SSS_TERMINAL_MOTIF_POLICY','SSS_TERMINAL_MOTIF_TASK','SSS_COLLECTION_MOTIF_POLICY','SSS_COLLECTION_MOTIF_TASK','SSS_COLLECTION_SCRIPT','SSS_COLLECTION_SCRIPT_TASK','SSS_REENTRY_MOTIF_POLICY','SSS_REENTRY_MOTIF_TASK','SSS_PLAN_MOTIF_POLICY','SSS_PLAN_MOTIF_TASK','SSS_DURABLE_PLAN_BINDING']:env[n]=''
    guard=NativeBudgetGuard(max_model_requests=96,max_observed_input_tokens=None)
    try:
        with create_harness(root=ROOT,patches=(prepared['patch'],str(exp/'control.patch.yml')),env=env,cwd=str(out),runtime_cwd=str(out),provider='deepseek-official',model='deepseek-flash',max_tokens=4000,request_timeout_seconds=15) as client:
            result=client.run(prepared['prompt'],session_id='adapt-sdk-'+uuid4().hex,on_notification=guard.on_notification)
        save(out/'events.json',guard.events);save(out/'mock-requests.json',server.bodies)
        receipt=receipt_from= h.receipt_from(guard.events);report=json.loads((out/'delivery/report.json').read_text());review=h.verify_workflow(spec,report,out/'delivery',guard.events)
        assert result.finish_reason=='completed' and review['passed'] and receipt['artifact_sha256']==digest(report)
        rr=[e for e in guard.events if e.get('type')=='user/message' and e['data'].get('source',{}).get('kind')=='task-acceptance-repair']
        if repair:
            assert len(server.bodies)==11 and len(rr)==1 and (out/'repair-probe-marker.json').exists()
            auto=[e for e in guard.events if e.get('type')=='tool/call' and e['data']['callId'].startswith('sss-')];assert len(auto)==1
        else:assert not server.bodies and not rr
        r={'status':'passed','task_id':case['task_id'],'output':str(out),'actual_sdk_and_mcp':True,'real_api_requests':0,'mock_http_requests':len(server.bodies),'ordinary_acceptance_repairs':len(rr),'not_training':True};save(out/'sdk-outcome.json',r);return r
    except Exception as e:save(out/'sdk-outcome.json',{'status':'failed','error':str(e),'output':str(out),'real_api_requests':0});save(out/'events.json',guard.events);raise
    finally:server.shutdown();server.server_close();worker.join(timeout=5)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--experiment',type=Path,required=True);a.add_argument('--repair-only',action='store_true');args=a.parse_args();exp=args.experiment.resolve();p=json.loads((exp/'protocol.json').read_text());rows=[]
    if not args.repair_only:
        for c in p['tasks']:
            if c['role']=='certify':r=check(exp,c,p);rows.append(r);print(json.dumps(r),flush=True)
    c=next(c for c in p['tasks'] if c['role']=='validate' and c['workflow_id']=='FM17' and c['condition']=='R');r=check(exp,c,p,True);rows.append(r);print(json.dumps(r),flush=True)
    save(exp/('free-repair-sdk-summary.json' if args.repair_only else 'free-v2-sdk-summary.json'),{'checks':len(rows),'passed':len(rows),'real_api_requests':0,'results':rows})
