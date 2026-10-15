"""Real Harness/MCP/acceptance over a loopback scripted provider and durable price gate; zero cloud calls."""
import argparse,json,sys,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from common import PREFIX,save
from src.adapters.harness_runtime import create_harness
from src.adapters.native_budget import NativeBudgetGuard
from src.adapters.deepseek_cost_gate import create_server
from src.adapters.file_job_budget import FileJobBudget,job_command
from src.adapters.scenario import prepare_scenario
import importlib.util
sp=importlib.util.spec_from_file_location('workflow_probe_helpers',ROOT/'scripts/check-file-workflows.py');helpers=importlib.util.module_from_spec(sp);sp.loader.exec_module(helpers)

class Provider(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));self.server.requests.append(body)
        if self.path!='/v1/chat/completions':self.server.other+=1;self.send_error(503);return
        values=[]
        for m in body['messages']:
            if m['role']=='tool':
                try:v=json.loads(m['content']);values.append(v)
                except (ValueError,TypeError):pass
        task=next((v for v in reversed(values) if v.get('rename_targets')),None)
        inventory=[v for v in values if 'files' in v and all('path' in r for r in v['files'])]
        listing=inventory[-1] if inventory else None
        preview=next((v for v in values if v.get('status')=='validated_copy_plan'),None)
        auth=next((v for v in values if v.get('status')=='task_grant_authorized'),None)
        effect=next((v for v in values if v.get('status')=='executed_verified'),None)
        report=next((v for v in values if v.get('status') in ('delivered','delivered_with_gaps')),None)
        if self.server.crash and not self.server.cold and len(self.server.requests)>=6:actions=[]
        elif self.server.cold and (not task or not task.get('recovery_state')):actions=[('read_task',{})]
        elif self.server.cold:
            recorded=task['recovery_state'][0]
            restored=next((v for v in values if v.get('status')=='restored_verified'),None)
            if not listing:actions=[('list_files',{})]
            elif not restored:actions=[('restore_plan',{'plan_id':recorded['plan_id'],'authorization_id':recorded['authorization_id']})]
            elif any(r['path'].startswith('normalized/') for r in listing['files']):actions=[('list_files',{})]
            elif not report:actions=[('submit_report',{'summary':'Recorded authorized plan restored to original bytes after real MCP restart','file_ids':[r['file_id'] for r in listing['files']],'gaps':[],'report_kind':'task_result'})]
            else:actions=[]
        elif not task:actions=[('read_task',{})]
        elif not listing:actions=[('list_files',{})]
        elif not preview:
            ids={r['path']:r['file_id'] for r in listing['files']}
            actions=[('preview_actions',{'actions':[{'op':'move','file_ids':[ids[r['source']]],'destination':r['destination']} for r in task['rename_targets']]})]
        elif not auth:actions=[('authorize_plan',{'plan_id':preview['plan_id']})]
        elif not effect:actions=[('execute_plan',{'plan_id':preview['plan_id'],'authorization_id':auth['authorization_id']})]
        elif not self.server.stopped_once:self.server.stopped_once=True;actions=[]
        elif not all(any(r['path']==target['destination'] for r in listing['files']) for target in task['rename_targets']):actions=[('list_files',{})]
        elif not report:actions=[('submit_report',{'summary':'Actual renamed byte results; free scripted provider, not semantic quality evidence','file_ids':[r['file_id'] for r in listing['files']],'gaps':[],'report_kind':'task_result'})]
        else:actions=[]
        delta={'role':'assistant','tool_calls':[{'index':i,'id':f'local-{len(self.server.requests)}-{i}','type':'function','function':{'name':PREFIX+n,'arguments':json.dumps(a)}} for i,(n,a) in enumerate(actions)]} if actions else {'role':'assistant','content':'Free local workflow integration completed.'}
        base={'id':'local','created':1,'model':body['model'],'object':'chat.completion.chunk'}
        chunks=[{**base,'choices':[{'index':0,'delta':delta,'finish_reason':None}]},{**base,'choices':[{'index':0,'delta':{},'finish_reason':'tool_calls' if actions else 'stop'}]},
                {**base,'choices':[],'usage':{'prompt_tokens':100,'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':100,'completion_tokens':20,'total_tokens':120}}]
        data=(''.join('data: '+json.dumps(c)+'\n\n' for c in chunks)+'data: [DONE]\n\n').encode()
        self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)

def main():
    p=argparse.ArgumentParser();p.add_argument('--experiment',type=Path);p.add_argument('--crash',action='store_true');a=p.parse_args()
    exp=a.experiment or Path(json.loads((ROOT/'.local/file-management/workflow-current.json').read_text())['experiment'])
    protocol=json.loads((exp/'protocol.json').read_text());t=next(t for t in protocol['tasks'] if t['task_id']==('probe-FM38-E' if a.crash else 'probe-FM38-N'))
    out,spec=helpers.instantiate(exp,t,'sdk');cfg=json.loads((Path(t['task_dir'])/'scenario.json').read_text());save(out/'scenario.json',cfg);prepared=prepare_scenario(out/'scenario.json')
    server=ThreadingHTTPServer(('127.0.0.1',0),Provider);server.requests=[];server.other=0;server.stopped_once=False;server.crash=a.crash;server.cold=False
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    state=FileJobBudget(out/'job.json',out/'mock-price-ledger.jsonl');gate=create_server('127.0.0.1',0,f'http://127.0.0.1:{server.server_port}',state)
    gate_worker=threading.Thread(target=gate.serve_forever,daemon=True);gate_worker.start();session='workflow-sdk-'+uuid4().hex
    env={'DEEPSEEK_API_KEY':'mock-no-key','DEEPSEEK_BASE_URL':f'http://127.0.0.1:{gate.server_port}/v1','DSH_HOME':str(out/'dsh'),
         'FM_TASK_FILE':str(out/'input.json'),'FM_OUTPUT':str(out/'delivery'),'FM_JOB_FILE':str(out/'job.json'),
         'SSS_SCENARIO_PRESENTATION':'native','SSS_SCENARIO_TOOLS':json.dumps(prepared['allowed_tools']),'SSS_BUDGET_LEDGER':str(out/'mock-price-ledger.jsonl')}
    for n in ('ENTRY','TERMINAL','COLLECTION','PLAN','REENTRY','ONLINE'):env['SSS_'+n+'_MOTIF_POLICY']='';env['SSS_'+n+'_MOTIF_TASK']=''
    env.update(SSS_ONLINE_MOTIF_MANIFEST='',SSS_COLLECTION_SCRIPT='',SSS_COLLECTION_SCRIPT_TASK='')
    guard=NativeBudgetGuard(max_model_requests=96,max_observed_input_tokens=None)
    try:
        with create_harness(root=ROOT,patches=(prepared['patch'],),env=env,cwd=str(out),runtime_cwd=str(out),provider='deepseek-official',model='deepseek-flash',max_tokens=4000,request_timeout_seconds=120) as client:
            try:result=client.run(prepared['prompt'],session_id=session,on_notification=guard.on_notification)
            except Exception:
                if not a.crash:raise
                result=None
        if a.crash:
            save(out/'warm-events.json',guard.events)
            warm=job_command(out/'job.json','state')['state']
            assert warm['status']=='running' and warm['repairs']==1 and warm['checks']==1
            server.cold=True
            with create_harness(root=ROOT,patches=(prepared['patch'],),env=env,cwd=str(out),runtime_cwd=str(out),provider='deepseek-official',model='deepseek-flash',max_tokens=4000,request_timeout_seconds=120) as client:
                result=client.run(prepared['prompt'],session_id=session+'-cold',on_notification=guard.on_notification)
        save(out/'harness-events.json',result.events);save(out/'mock-requests.json',server.requests)
        job=job_command(out/'job.json','state')['state']
        assert result.finish_reason=='completed' and job['status']=='completed' and job['repairs']==1 and job['checks']==2
        assert server.other==0 and job['requests']==len(server.requests)
        # A cold proxy cannot reset or admit a completed task.
        restarted=FileJobBudget(out/'job.json',out/'mock-price-ledger.jsonl')
        assert restarted.book(json.dumps({'model':'deepseek-flash','max_tokens':1,'messages':[]}).encode()) is None
        outcome={'status':'passed','actual_harness_and_mcp':True,'actual_acceptance_repair':1,'checks':2,
                 'mock_http_requests':len(server.requests),'persistent_proxy_requests':job['requests'],
                 'synthetic_booked_peak_usd_not_real_cost':job['spent_units']/1e9,'real_api_requests':0,'estimated_real_model_cost_usd':0,
                 'completed_task_rejected_after_proxy_restart':True,'scripted_selection_not_training':True,'output':str(out)}
        outcome['cold_harness_restart_after_actual_mcp_crash']=a.crash
        save(out/'sdk-outcome.json',outcome);print(json.dumps(outcome))
    except Exception as e:
        save(out/'sdk-outcome.json',{'status':'failed','error':type(e).__name__+': '+str(e),'real_api_requests':0,'output':str(out)});raise
    finally:gate.shutdown();gate.server_close();gate_worker.join(timeout=5);server.shutdown();server.server_close();worker.join(timeout=5)

if __name__=='__main__':main()
