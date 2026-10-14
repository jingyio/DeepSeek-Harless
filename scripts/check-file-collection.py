"""Actual SDK/MCP with a local scripted provider; never training or cloud efficiency evidence."""
import argparse
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import sys
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scenarios/file-management'));sys.path.insert(0,str(ROOT))
from common import PREFIX,digest,save
from collection_study import task_scope
from src.adapters.scenario import prepare_scenario
from src.adapters.harness_runtime import create_harness
from src.adapters.native_budget import NativeBudgetGuard

class Provider(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if self.path!='/v1/chat/completions':self.server.other_requests+=1;self.send_error(503);return
        self.server.requests.append(body);observations=[]
        for message in body['messages']:
            if message['role']=='tool':
                try:observations.append(json.loads(message['content']))
                except (ValueError,TypeError):pass
        work=next((v for v in observations if 'objective' in v),None)
        listing=next((v for v in observations if 'files' in v),None)
        selection=next((v for v in observations if v.get('selection')=='actual_model_selected_members'),None)
        pins=[v for v in observations if 'source_id' in v and 'status' not in v]
        reads=[v for v in observations if 'source_id' in v and 'status' in v]
        gathered=next((v for v in observations if v.get('status')=='collection_complete'),None)
        if work is None:actions=[('read_task',{})]
        elif listing is None:actions=[('list_files',{})]
        elif selection is None:actions=[('select_files',{'file_ids':[r['file_id'] for r in listing['files']]})]
        elif len(pins)<selection['count']:
            done={p['file_id'] for p in pins};actions=[('pin_file',{'file_id':r['file_id']}) for r in selection['files'] if r['file_id'] not in done]
        elif len(reads)<selection['count']:
            done={r['source_id'] for r in reads};actions=[('read_file',{'source_id':p['source_id']}) for p in pins if p['source_id'] not in done]
        elif gathered is None:actions=[('collect_reads',{'collection_id':selection['collection_id'],'source_ids':[r['source_id'] for r in reads]})]
        else:actions=[]
        delta={'role':'assistant'}
        if actions:
            delta['tool_calls']=[{'index':i,'id':f'fixture-{len(self.server.requests)}-{i}','type':'function',
                'function':{'name':PREFIX+n,'arguments':json.dumps(a)}} for i,(n,a) in enumerate(actions)]
        else:delta['content']='Local selected-collection protocol check complete.'
        base={'id':'fixture','created':1,'model':body['model'],'object':'chat.completion.chunk'}
        chunks=[{**base,'choices':[{'index':0,'delta':delta,'finish_reason':None}]},
                {**base,'choices':[{'index':0,'delta':{},'finish_reason':'tool_calls' if actions else 'stop'}]},
                {**base,'choices':[],'usage':{'prompt_tokens':100,'completion_tokens':20,'total_tokens':120}}]
        result=(''.join('data: '+json.dumps(c)+'\n\n' for c in chunks)+'data: [DONE]\n\n').encode()
        self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(result)));self.end_headers();self.wfile.write(result)

def check(exp,stale=False,script=False):
    out=exp/'sdk-checks'/uuid4().hex;out.mkdir(parents=True,mode=0o700)
    protocol=json.loads((exp/'protocol.json').read_text());case=next(c for c in protocol['tasks'] if c['role']=='evaluate' and c['family']=='inventory' and c['variant']=='eval_m')
    origin=Path(case['task_dir']);spec=json.loads((origin/'input.json').read_text());save(out/'input.json',spec)
    prompt='Read my selected complete file set using the actual native tools; local protocol check.'
    (out/'prompt.md').write_text(prompt);(out/'prompt.md').chmod(0o600)
    config=json.loads((origin/'scenario.json').read_text());config.pop('completion_guard');config['prompt']=str(out/'prompt.md');save(out/'scenario.json',config)
    prepared=prepare_scenario(out/'scenario.json',entry_motif=True);task=task_scope(spec)
    task.update(session_id='collection-check-'+uuid4().hex,prompt_sha256=prepared['prompt_sha256'])
    if stale:task['snapshot_sha256']='0'*64
    save(out/'collection-task.json',task);policy=exp/'script.json' if script else exp/'learned/policy.json'
    provider=ThreadingHTTPServer(('127.0.0.1',0),Provider);provider.requests=[];provider.other_requests=0
    worker=threading.Thread(target=provider.serve_forever,daemon=True);worker.start();guard=NativeBudgetGuard(max_model_requests=30,max_observed_input_tokens=None)
    try:
        env={'DSH_HOME':str(out/'dsh'),'DEEPSEEK_API_KEY':'mock-no-key','DEEPSEEK_BASE_URL':f'http://127.0.0.1:{provider.server_port}/v1',
             'FM_TASK_FILE':str(out/'input.json'),'FM_OUTPUT':str(out/'delivery'),'SSS_SCENARIO_TOOLS':json.dumps(prepared['allowed_tools']),
             'SSS_SCENARIO_PRESENTATION':'native','SSS_COLLECTION_MOTIF_POLICY':str(policy),'SSS_COLLECTION_MOTIF_TASK':str(out/'collection-task.json'),
             'SSS_ENTRY_MOTIF_POLICY':'','SSS_ENTRY_MOTIF_TASK':'','SSS_TERMINAL_MOTIF_POLICY':'','SSS_TERMINAL_MOTIF_TASK':'',
             'SSS_ONLINE_MOTIF_MANIFEST':'','SSS_ONLINE_MOTIF_TASK':''}
        if script:
            env.update(SSS_COLLECTION_MOTIF_POLICY='',SSS_COLLECTION_MOTIF_TASK='',SSS_COLLECTION_SCRIPT=str(policy),SSS_COLLECTION_SCRIPT_TASK=str(out/'collection-task.json'))
        else:env.update(SSS_COLLECTION_SCRIPT='',SSS_COLLECTION_SCRIPT_TASK='')
        with create_harness(root=ROOT,patches=(prepared['patch'],),env=env,cwd=str(out),runtime_cwd=str(out),
                            provider='deepseek-official',model='deepseek-flash',max_tokens=4000,request_timeout_seconds=120) as client:
            result=client.run(prompt,session_id=task['session_id'],on_notification=guard.on_notification)
        save(out/'events.json',result.events)
        audit_path=out/'.local/online-motif'/(hashlib.sha256(task['session_id'].encode()).hexdigest()+'.jsonl')
        audit=[json.loads(l) for l in audit_path.read_text().splitlines()]
        reads=list((out/'delivery/reads').glob('*.json'));summaries=list((out/'delivery/collections').glob('*/summary.json'))
        verified=sum(r['kind']==('collection_script_batch_verified' if script else 'collection_model_request_bypassed_verified') for r in audit)
        assert result.finish_reason=='completed' and len(reads)==20 and len(summaries)==1
        assert len(provider.requests)==(7 if stale else 4) and verified==(0 if stale else 7) and provider.other_requests==0
        assert json.loads(summaries[0].read_text())['count']==20
        outcome={'handwritten_script':script,'real_api_requests':0,'mock_http_requests':len(provider.requests),'actual_reads':20,'verified_batches':verified,
                 'other_requests':provider.other_requests,'stale_snapshot_fallback':stale,'output':str(out),
                 'scope':'actual SDK/MCP protocol only; scripted selection is not training or real task efficiency evidence'}
        save(out/'outcome.json',outcome);print(json.dumps(outcome),flush=True)
    finally:provider.shutdown();provider.server_close();worker.join(timeout=5)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--experiment',type=Path,required=True);p.add_argument('--stale',action='store_true');p.add_argument('--script',action='store_true');args=p.parse_args();check(args.experiment.resolve(),args.stale,args.script)
