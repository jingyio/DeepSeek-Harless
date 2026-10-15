"""Actual SDK rejects an old service certificate; simulated ordinary provider, zero paid calls."""
import argparse,json,sys,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scenarios/file-management'))
import auto_rsi as rsi
from common import save,sha,snapshot
from src.adapters.scenario import prepare_scenario
from src.adapters.harness_runtime import create_harness
from src.adapters.native_budget import NativeBudgetGuard

class Stop(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        request=json.loads(self.rfile.read(int(self.headers['Content-Length'])));self.server.requests.append(request)
        base={'id':'local-report-version','created':1,'model':request['model'],'object':'chat.completion.chunk'}
        chunks=[{**base,'choices':[{'index':0,'delta':{'role':'assistant','content':'Local simulated ordinary fallback. No file operations performed; task unfinished.'},'finish_reason':None}]},
                {**base,'choices':[{'index':0,'delta':{},'finish_reason':'stop'}]},
                {**base,'choices':[],'usage':{'prompt_tokens':100,'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':100,'completion_tokens':20,'total_tokens':120}}]
        data=(''.join('data: '+json.dumps(c)+'\n\n' for c in chunks)+'data: [DONE]\n\n').encode()
        self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--experiment',type=Path,required=True);args=parser.parse_args();exp=args.experiment.resolve()
    p=rsi.read(exp/'protocol.json');t,cases=rsi.make(exp,'probe','FM05:min',False,0,'old-service-free-'+uuid4().hex[:6],('F',));case=cases[0]
    out,spec,env,_=rsi.h.instantiate(exp,case,p,True)
    rsi.experience_binding(exp,case,p,out,spec,env,Path(p['parent_registry_file']))
    prepared=prepare_scenario(Path(case['task_dir'])/'scenario.json')
    server=ThreadingHTTPServer(('127.0.0.1',0),Stop);server.requests=[]
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    env.update(DEEPSEEK_API_KEY='mock-no-key',DEEPSEEK_BASE_URL=f'http://127.0.0.1:{server.server_port}/v1',
               DSH_HOME=str(out/'dsh'),SSS_SCENARIO_PRESENTATION='native',SSS_SCENARIO_TOOLS=json.dumps(prepared['allowed_tools']))
    guard=NativeBudgetGuard(max_model_requests=8,max_observed_input_tokens=None);termination=None
    try:
        try:
            with create_harness(root=ROOT,patches=(prepared['patch'],str(exp/'control.patch.yml')),env=env,cwd=str(out),runtime_cwd=str(out),
                                provider='deepseek-official',model='deepseek-flash',max_tokens=4000,request_timeout_seconds=15) as client:
                client.run(prepared['prompt'],session_id='free-report-version-'+uuid4().hex,on_notification=guard.on_notification)
        except Exception as error:termination=type(error).__name__+': '+str(error)
        audit=[json.loads(l) for l in (out/'experience-audit.jsonl').read_text().splitlines()]
        save(out/'mock-requests.json',server.requests);save(out/'free-sdk-events.json',guard.events)
        assert not any(r['kind']=='experience_selected' for r in audit)
        assert any(r['kind']=='experience_deferred' and r['reason']=='no_verified_experience' for r in audit)
        rejected=[r for v in audit if v['kind']=='experience_retrieval' for r in v.get('rejected',[])]
        assert any(r['reason']=='goal_rule_permission_state_or_schema_mismatch' for r in rejected),rejected
        assert snapshot(spec['workspace'])==spec['initial_snapshot'] and not (out/'delivery/report.json').exists()
        assert len(server.requests)==3
        assert len([e for e in guard.events if e['type']=='user/message' and e['data'].get('source',{}).get('kind')=='task-acceptance-repair'])==2
        result={'status':'passed','actual_sdk_and_mcp':True,'old_service_rejected':True,'ordinary_fallback_simulated':True,
                'mock_http_requests':3,'real_api_requests':0,'repairs':2,'no_effects':True,'output':str(out),'termination':termination,
                'check_source_sha256':sha(__file__)}
        save(out/'free-sdk-outcome.json',result);save(exp/'free-old-service-summary.json',result);print(json.dumps(result),flush=True)
    finally:server.shutdown();server.server_close();worker.join(timeout=5)

if __name__=='__main__':main()
