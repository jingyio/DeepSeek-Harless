"""Real SDK/MCP with a free scripted HTTP provider; no efficiency claim."""
import argparse
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4
import sys
from common import ROOT,HERE,PREFIX,digest,save
sys.path.insert(0,str(ROOT))
from src.adapters.scenario import prepare_scenario
from src.adapters.harness_runtime import create_harness
from src.adapters.native_budget import NativeBudgetGuard
from file_tools import FileScene
import importlib.util

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
study=module('fm_sdk_study',HERE/'online-study.py')

class Provider(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if self.path!='/v1/chat/completions':
            self.server.embeddings+=1;self.send_error(503);return
        self.server.requests.append(body);observations=[]
        for message in body['messages']:
            if message['role']=='tool':
                try:observations.append(json.loads(message['content']))
                except (ValueError,TypeError):pass
        work=next((v for v in observations if 'objective' in v),None)
        listing=next((v for v in observations if 'files' in v),None)
        pins=[v for v in observations if 'source_id' in v and 'status' not in v]
        reads=[v for v in observations if 'source_id' in v and 'status' in v]
        if work is None:actions=[('read_task',{})]
        elif listing is None:actions=[('list_files',{})]
        elif not pins:
            chosen=[v for v in listing['files'] if v['path'] in ('inbox/brief.docx','inbox/poster.png','bad/broken.docx')]
            actions=[('pin_file',{'file_id':v['file_id']}) for v in chosen]
        else:
            done={v['source_id'] for v in reads}
            actions=[('read_file',{'source_id':p['source_id']}) for p in pins if p['source_id'] not in done]
        delta={'role':'assistant'}
        if actions:
            delta['tool_calls']=[{'index':i,'id':f'fixture-{len(self.server.requests)}-{i}','type':'function',
                'function':{'name':PREFIX+n,'arguments':json.dumps(a)}} for i,(n,a) in enumerate(actions)]
        else:delta['content']='Local protocol check finished.'
        base={'id':'fixture','created':1,'model':body['model'],'object':'chat.completion.chunk'}
        chunks=[{**base,'choices':[{'index':0,'delta':delta,'finish_reason':None}]},
                {**base,'choices':[{'index':0,'delta':{},'finish_reason':'tool_calls' if actions else 'stop'}]},
                {**base,'choices':[],'usage':{'prompt_tokens':100,'completion_tokens':20,'total_tokens':120}}]
        result=(''.join('data: '+json.dumps(c)+'\n\n' for c in chunks)+'data: [DONE]\n\n').encode()
        self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(result)))
        self.end_headers();self.wfile.write(result)

def check(exp,mode):
    out=exp/'sdk-checks'/uuid4().hex;out.mkdir(parents=True,mode=0o700)
    origin=next(c for c in json.loads((exp/'protocol.json').read_text())['tasks'] if c['arm']=='M' and c['family']=='inventory')
    spec=json.loads((Path(origin['task_dir'])/'input.json').read_text());save(out/'input.json',spec)
    prompt='Read selected office files using the actual native tools; local protocol fixture.'
    (out/'prompt.md').write_text(prompt)
    config=json.loads((Path(origin['task_dir'])/'scenario.json').read_text());config.pop('completion_guard');config['prompt']=str(out/'prompt.md')
    save(out/'scenario.json',config);prepared=prepare_scenario(out/'scenario.json')
    manifest=exp/'online-manifest.json'
    if mode=='old':manifest=Path(json.loads((exp/'protocol.json').read_text())['parent'])/'learned/online-manifest.json'
    task=study.structured_task(spec,stale=mode=='stale');save(out/'motif-task.json',task)
    online=module('fm_sdk_online',ROOT/'scripts/prepare-online-motif.py').prepare(manifest,out/'motif-task.json')
    provider=ThreadingHTTPServer(('127.0.0.1',0),Provider);provider.requests=[];provider.embeddings=0
    worker=threading.Thread(target=provider.serve_forever,daemon=True);worker.start()
    guard=NativeBudgetGuard(max_model_requests=12,max_observed_input_tokens=None)
    try:
        env={'DSH_HOME':str(out/'dsh'),'DEEPSEEK_API_KEY':'mock-no-key','DEEPSEEK_BASE_URL':f'http://127.0.0.1:{provider.server_port}/v1',
             'FM_TASK_FILE':str(out/'input.json'),'FM_OUTPUT':str(out/'delivery'),
             'SSS_SCENARIO_TOOLS':json.dumps(prepared['allowed_tools']),'SSS_SCENARIO_PRESENTATION':'native',
             'SSS_ONLINE_MOTIF_MANIFEST':str(manifest),'SSS_ONLINE_MOTIF_TASK':str(out/'motif-task.json'),
             'SSS_ONLINE_MOTIF_MODE':'execute','SSS_ONLINE_MOTIF_PROMPT_SHA256':prepared['prompt_sha256'],
             'SSS_MOTIF_EMBEDDING_ENDPOINT':f'http://127.0.0.1:{provider.server_port}/v1/embeddings','SSS_MOTIF_EMBEDDING_MODEL':'disabled',
             'SSS_ENTRY_MOTIF_POLICY':'','SSS_ENTRY_MOTIF_TASK':'','SSS_TERMINAL_MOTIF_POLICY':'','SSS_TERMINAL_MOTIF_TASK':''}
        with create_harness(root=ROOT,patches=(prepared['patch'],online['patch']),env=env,cwd=str(out),runtime_cwd=str(out),
                            provider='deepseek-official',model='deepseek-flash',max_tokens=1000,request_timeout_seconds=120) as client:
            result=client.run(prompt,session_id=task['session_id'],on_notification=guard.on_notification)
        save(out/'events.json',result.events)
        audit_path=out/'.local/online-motif'/(hashlib.sha256(task['session_id'].encode()).hexdigest()+'.jsonl')
        audit=[json.loads(l) for l in audit_path.read_text().splitlines()]
        reads=[json.loads(p.read_text()) for p in (out/'delivery/reads').glob('*.json')]
        skips=sum(v['kind']=='model_request_skipped_verified' for v in audit)
        assert result.finish_reason=='completed' and len(reads)==3
        assert {v['status'] for v in reads}=={'readable','metadata_only','unreadable'}
        assert len(provider.requests)==(4 if mode=='fresh' else 5) and skips==(1 if mode=='fresh' else 0)
        assert provider.embeddings==(1 if mode=='old' else 0)
        outcome={'mode':mode,'real_api_requests':0,'mock_http_requests':len(provider.requests),'actual_reads':3,
                 'verified_batches':skips,'embedding_requests':provider.embeddings,'output':str(out),
                 'scope':'protocol validation only; not training or real efficiency evidence'}
        save(out/'outcome.json',outcome);print(json.dumps(outcome),flush=True)
    finally:provider.shutdown();provider.server_close();worker.join(timeout=5)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--experiment',type=Path,required=True);p.add_argument('--mode',choices=['old','fresh','stale'],required=True)
    a=p.parse_args();check(a.experiment.resolve(),a.mode)
