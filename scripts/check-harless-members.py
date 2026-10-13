#!/usr/bin/env python3
"""Real bwrap/member/MCP deployment diagnostic; no prompt or model invocation."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('scenes',ROOT/'scripts/check-harless-scenes.py')
scenes=importlib.util.module_from_spec(spec);spec.loader.exec_module(scenes)
web=scenes.web

def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0));return s.getsockname()[1]

class AccountHeaders(urllib.request.BaseHandler):
    def __init__(self):self.cookie=''
    def http_request(self,req):
        req.add_header('Origin','https://launch.example.test')
        if self.cookie:req.add_header('Cookie',self.cookie)
        return req
    https_request=http_request

def account():
    headers=AccountHeaders()
    return urllib.request.build_opener(urllib.request.ProxyHandler({}),headers),headers

def main():
    if sys.platform!='linux' or not shutil.which('bwrap'):raise RuntimeError('requires Linux bwrap')
    os.umask(0o077)
    area=ROOT/'.local/member-scene-checks'/uuid4().hex;area.mkdir(parents=True)
    port,scope=free_port(),free_port()
    with scenes.launch(free_port(),'member-scene-diagnostic-owner') as (owner,owner_base,output):
        policy=json.loads((output/'policy.json').read_text())
        # include-system-site-packages venvs may inherit the parent venv; mount
        # the exact dependency roots returned by the configured interpreter.
        roots={sys.prefix,sys.base_prefix}
        cfg=Path(sys.prefix)/'pyvenv.cfg'
        if cfg.exists():
            for line in cfg.read_text().splitlines():
                if line.startswith('home = '):roots.add(str(Path(line.split(' = ',1)[1]).parent))
        node=Path(shutil.which('node')).resolve()
        config={'dataDir':str(area/'accounts'),'membersDir':str(area/'members'),
                'publicOrigin':'https://launch.example.test','port':port,'scopedBudgetPort':scope,
                'ownerPort':int(owner_base.rsplit(':',1)[1]),'ownerTokenFile':str(output/'access-url.txt'),
                'accountHtml':str(ROOT/'src/adapters/harless_account.html'),
                'nodeRoot':str(node.parent.parent),'nodeModules':str((ROOT/'node_modules').resolve()),
                'sourceDir':str(ROOT/'src'),'memberPolicy':policy,
                'memberPatch':json.loads((output/'host.patch.yml').read_text()),
                'memberSceneDeployment':{'projectRoot':str(ROOT),'pythonExecutable':sys.executable,'pythonRoots':sorted(roots)},
                'upstreamControlPort':int(policy['control_endpoint'].rsplit(':',1)[1]),
                'upstreamBrokerPort':int(policy['control_endpoint'].rsplit(':',1)[1]),
                'adminToken':uuid4().hex}
        config_path=area/'gateway.json';config_path.write_text(json.dumps(config))
        log=(area/'gateway.log').open('w')
        child=subprocess.Popen(['node',str(ROOT/'scripts/harless_gateway.mjs'),str(config_path)],
            cwd=ROOT,env={**os.environ,'DEEPSEEK_API_KEY':'no-model-diagnostic-delegate'},stdout=log,stderr=subprocess.STDOUT)
        try:
            for _ in range(100):
                if child.poll() is not None:raise RuntimeError('diagnostic gateway startup failed')
                try:
                    with socket.create_connection(('127.0.0.1',port),timeout=.1):break
                except OSError:time.sleep(.1)
            codes=subprocess.check_output(['node',str(ROOT/'scripts/harless_gateway.mjs'),str(config_path),'invite','2'],text=True).splitlines()
            clients=[];base=f'http://127.0.0.1:{port}'
            for i,code in enumerate(codes):
                client,headers=account()
                req=urllib.request.Request(base+'/api/account/register',data=json.dumps({'inviteCode':code,
                    'username':'diagnostic'+str(i),'displayName':'Diagnostic '+str(i),'password':'OnlyDiagnosticPassword123!'}).encode(),
                    headers={'Content-Type':'application/json'})
                with client.open(req,timeout=10) as response:
                    headers.cookie=response.headers['Set-Cookie'].split(';',1)[0];json.load(response)
                clients.append(client)
            # Trigger both isolated processes before waiting; startup remains concurrent.
            for client in clients:web.request(client,base,'/api/workspace/ready')
            for client in clients:
                for _ in range(80):
                    status,value=web.request(client,base,'/api/workspace/ready')
                    if status==200:break
                    if status>=400:raise RuntimeError('member startup failed; inspect private gateway log')
                    time.sleep(.5)
                else:raise RuntimeError('member startup timeout')
            tasks=[]
            for client in clients:
                for identity in ['new-scene','ppt','paper-proofreading','research-data-analysis']:
                    result=scenes.settings(client,base,{'action':'select','selection':{'scene':identity,'mode':'shadow','rsi':True}})
                    assert all(s['available'] for s in result['scenes'])
                    draft=web.api(client,base,{'action':'preview','request':'Inspect the approved input only; no output writing.'})
                    name,data={'new-scene':('note.txt',b'Private diagnostic text'),
                               'ppt':('source.pdf',None),'paper-proofreading':('main.tex',b'\\cite{missing}'),
                               'research-data-analysis':('data.csv',b'x,y\n1,2\n2,4\n')}[identity]
                    if data is None:
                        import io
                        from reportlab.pdfgen.canvas import Canvas
                        b=io.BytesIO();p=Canvas(b);p.drawString(80,700,'Only this account source.');p.save();data=b.getvalue()
                    draft=web.api(client,base,{'action':'upload','task_id':draft['task_id'],'name':name,'data':base64.b64encode(data).decode()})
                    assert draft['scene']==identity and draft['scene_inputs']
                    tasks.append((client,draft))
                    foreign=clients[1] if client is clients[0] else clients[0]
                    assert web.request(foreign,base,'/api/harless/tasks?task_id='+draft['task_id'])[0]==404
                    assert scenes.settings(foreign,base,session=draft['session_id'],expected=404)['error']['code']=='session_not_owned'
                    web.api(client,base,{'action':'cancel','task_id':draft['task_id']})
            assert len({task['session_id'] for _,task in tasks})==8
            assert all(web.api(c,base)['aggregate'].get('upstream_requests',0)==0 for c in clients)
            report={'status':'passed','users':2,'scene_drafts':8,'actual_bwrap':True,'actual_mcp':True,
                    'model_requests':0,'browser_verified':False,'quality_reviewed':False}
            (area/'result.json').write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps(report))
        finally:
            if child.poll() is None:child.send_signal(signal.SIGTERM)
            try:child.wait(timeout=10)
            except subprocess.TimeoutExpired:child.kill();child.wait()
            log.close()

if __name__=='__main__':main()
