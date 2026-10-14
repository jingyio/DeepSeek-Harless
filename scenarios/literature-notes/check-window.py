"""Actual SDK/MCP with a local fixture provider; never training or API efficiency evidence."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from uuid import uuid4
from pdf_tools import ROOT,digest,save_private
from pdf_window_tools import HERE,WindowScene,window_version
from pdf_dependencies import private_file
sys.path.insert(0,str(ROOT))
from src.adapters.scenario import prepare_scenario
from src.adapters.harness_runtime import create_harness
from src.adapters.native_budget import NativeBudgetGuard

PREFIX='mcp__literature_workflow_probe__'


class FixtureProvider(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if self.path!='/v1/chat/completions':
            self.server.embedding_requests+=1;self.send_error(503);return
        self.server.requests.append(body)
        observations=[]
        for message in body['messages']:
            if message['role']=='tool':
                try:observations.append(json.loads(message['content']))
                except (ValueError,TypeError):pass
        work=next((v for v in observations if v.get('kind')=='topic_search'),None)
        pins=[v for v in observations if 'source_id'in v and 'text'not in v]
        reads=[v for v in observations if 'text'in v]
        if work is None:actions=[('read_workflow_input',{})]
        elif not pins:
            actions=[('pin_pdf_context',{'paper_id':p['paper_id'],'page':'1','start':'10','length':'1000'})for p in work['papers']]
        else:
            completed={v['version_sha256']for v in reads}
            actions=[('read_pinned_pdf_context',{'source_id':p['source_id']})for p in pins if p['version_sha256']not in completed]
        delta={'role':'assistant'}
        if actions:
            delta['tool_calls']=[{'index':i,'id':'fixture-'+str(len(self.server.requests))+'-'+str(i),'type':'function',
                'function':{'name':PREFIX+name,'arguments':json.dumps(args)}}for i,(name,args)in enumerate(actions)]
        else:delta['content']='Free protocol fixture completed; no scientific interpretation or real API call.'
        base={'id':'fixture','created':1,'model':body['model'],'object':'chat.completion.chunk'}
        chunks=[{**base,'choices':[{'index':0,'delta':delta,'finish_reason':None}]},
                {**base,'choices':[{'index':0,'delta':{},'finish_reason':'tool_calls'if actions else'stop'}]},
                {**base,'choices':[],'usage':{'prompt_tokens':100,'completion_tokens':20,'total_tokens':120}}]
        result=(''.join('data: '+json.dumps(chunk)+'\n\n'for chunk in chunks)+'data: [DONE]\n\n').encode()
        self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(result)))
        self.end_headers();self.wfile.write(result)


def check(experiment,stale=False):
    out=experiment/'sdk-checks'/uuid4().hex;out.mkdir(mode=0o700,parents=True)
    spec=json.loads((experiment/'eval-orchestration/input.json').read_text())
    scene=WindowScene(spec,out/'delivery');save_private(out/'input.json',spec)
    prompt='Read the selected PDF first-page windows using the native tools; free protocol fixture.'
    (out/'prompt.md').write_text(prompt);(out/'prompt.md').chmod(0o600)
    config=json.loads((HERE/'pdf-window-scenario.json').read_text());config.pop('completion_guard');config['prompt']=str(out/'prompt.md')
    save_private(out/'scenario.json',config)
    prepared=prepare_scenario(out/'scenario.json')
    manifest=private_file(experiment/'learned/online-manifest.json')
    provenance=json.loads((experiment/'learned/provenance.json').read_text())
    if provenance['window_version']!=window_version():raise ValueError('library changed')
    versions=[scene.document_version(p['paper_id'])for p in spec['task']['sources']['papers']]
    if stale:versions=['a'*64]
    task={'schema_version':1,'task_id':out.name,'session_id':'window-check-'+uuid4().hex,'intent':'Read current windows',
          'input_version':digest(spec),'bindings':{},'source_versions':{PREFIX+'pin_pdf_context':versions,PREFIX+'read_pinned_pdf_context':versions}}
    save_private(out/'motif-task.json',task)
    path=ROOT/'scripts/prepare-online-motif.py';loader=importlib.util.spec_from_file_location('window_check_online',path)
    online=importlib.util.module_from_spec(loader);loader.loader.exec_module(online);patch=online.prepare(manifest,out/'motif-task.json')
    provider=ThreadingHTTPServer(('127.0.0.1',0),FixtureProvider);provider.requests=[];provider.embedding_requests=0
    threading.Thread(target=provider.serve_forever,daemon=True).start();guard=NativeBudgetGuard(max_model_requests=12,max_observed_input_tokens=None)
    try:
        env={'DSH_HOME':str(out/'dsh'),'DEEPSEEK_API_KEY':'mock-no-key','DEEPSEEK_BASE_URL':f'http://127.0.0.1:{provider.server_port}/v1',
             'SSS_WORKFLOW_PROBE_FILE':str(out/'input.json'),'SSS_WORKFLOW_PROBE_OUTPUT':str(out/'delivery'),
             'SSS_SCENARIO_TOOLS':json.dumps(prepared['allowed_tools']),'SSS_SCENARIO_PRESENTATION':'native',
             'SSS_ONLINE_MOTIF_MANIFEST':str(manifest),'SSS_ONLINE_MOTIF_TASK':str(out/'motif-task.json'),
             'SSS_ONLINE_MOTIF_MODE':'execute','SSS_ONLINE_MOTIF_PROMPT_SHA256':prepared['prompt_sha256'],
             'SSS_MOTIF_EMBEDDING_ENDPOINT':f'http://127.0.0.1:{provider.server_port}/v1/embeddings','SSS_MOTIF_EMBEDDING_MODEL':'disabled',
             'SSS_ENTRY_MOTIF_POLICY':'','SSS_ENTRY_MOTIF_TASK':'','SSS_TERMINAL_MOTIF_POLICY':'','SSS_TERMINAL_MOTIF_TASK':''}
        with create_harness(root=ROOT,patches=(prepared['patch'],patch['patch']),env=env,cwd=str(out),runtime_cwd=str(out),
                            provider='deepseek-official',model='deepseek-flash',max_tokens=1000,request_timeout_seconds=120)as client:
            result=client.run(prompt,session_id=task['session_id'],on_notification=guard.on_notification)
        save_private(out/'events.json',result.events)
        audit_path=out/'.local/online-motif'/(hashlib.sha256(task['session_id'].encode()).hexdigest()+'.jsonl')
        audit=[json.loads(l)for l in audit_path.read_text().splitlines()];skips=sum(r['kind']=='model_request_skipped_verified'for r in audit)
        pins={};reads=[]
        for event in result.events:
            if event['type']=='tool/call':
                data=event['data'];args=json.loads(data['arguments']);name=data['name'].removeprefix(PREFIX)
                if name=='read_workflow_input':scene.read_workflow_input()
                if name=='pin_pdf_context':pins.update({scene.pin_pdf_context(**args)['source_id']:args})
                if name=='read_pinned_pdf_context':reads.append(scene.read_pinned_pdf_context(**args))
        assert result.finish_reason=='completed'and len(reads)==3 and len(pins)==3 and provider.embedding_requests==0
        assert skips==(0 if stale else 1)and len(provider.requests)==(4 if stale else 3)
        report={'output':str(out),'real_api_requests':0,'mock_provider_requests':len(provider.requests),
                'actual_sdk_windows_read':len(reads),'verified_runtime_batches':skips,'embedding_requests':provider.embedding_requests,
                'stale_version_fallback':stale,'scope':'actual MCP/SDK protocol, local fixture only; not scientific quality or training'}
        save_private(out/'outcome.json',report);print(json.dumps(report))
    finally:provider.shutdown();provider.server_close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--experiment',type=Path,required=True);p.add_argument('--stale',action='store_true');a=p.parse_args()
    check(private_file(a.experiment/'protocol.json').parent,a.stale)
