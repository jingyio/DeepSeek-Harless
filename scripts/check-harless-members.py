#!/usr/bin/env python3
"""Real bwrap/member/MCP deployment diagnostic; no prompt or model invocation."""
import base64
import argparse
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

def render_in_member(user_dir, task_id):
    """Run the zero-model probe with the actual gateway's bwrap mounts.

    Uses a fresh, explicitly writable diagnostic job and only that member's
    uploaded synthetic input. It is not an autonomous model generation test.
    """
    effective=json.loads((user_dir/'tasks/tasks'/task_id/'effective-config.json').read_text())
    workspace=effective['workspace']
    assert workspace.startswith('/app/.local/web/')
    host_workspace=user_dir/'tasks'/workspace.removeprefix('/app/.local/web/')
    job=json.loads((host_workspace/'job.json').read_text())
    probe_id=uuid4().hex
    host_probe=user_dir/'tasks/diagnostics'/probe_id
    sandbox_probe='/app/.local/web/diagnostics/'+probe_id
    (host_probe/'inputs').mkdir(parents=True)
    for row in job['inputs']:
        leaf=Path(row['path']).name
        shutil.copyfile(host_workspace/'inputs'/leaf,host_probe/'inputs'/leaf)
        row['path']=sandbox_probe+'/inputs/'+leaf
    job.update(job_id=probe_id,slides=1,allow_output=True)
    (host_probe/'job.json').write_text(json.dumps(job))
    shutil.copyfile(host_workspace/'approved-inputs.json',host_probe/'approved-inputs.json')
    prefix=None
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():continue
        try:argv=(process/'cmdline').read_bytes().decode().rstrip('\0').split('\0')
        except (OSError,UnicodeError):continue
        if (argv and Path(argv[0]).name=='bwrap' and str(user_dir) in argv
                and '/opt/node/bin/node' in argv):
            prefix=argv[:argv.index('/opt/node/bin/node')];break
    if prefix is None:raise RuntimeError('actual member bwrap mount arguments unavailable')
    policy=json.loads((user_dir/'config/policy.json').read_text())
    ppt=next(scene for scene in policy['scenes'] if scene['id']=='ppt')
    mcp_env=ppt['mcp_rows'][0]['config']['env']
    env={'HOME':'/user/workspace','LANG':'C.UTF-8','PYTHONUTF8':'1',
         'PATH':mcp_env['PATH'],'SSS_PYTHON':mcp_env['SSS_PPT_DELIVERY_PYTHON'],
         'HARLESS_PPT_RUNTIME_BUNDLE':str(Path(ppt['manifest']).parent),
         'FONTCONFIG_FILE':mcp_env['FONTCONFIG_FILE'],'FONTCONFIG_PATH':mcp_env['FONTCONFIG_PATH']}
    with (host_probe/'probe.log').open('w') as log:
        subprocess.run([*prefix,'/opt/node/bin/node','/app/scripts/check-ppt-runtime.mjs',
                        sandbox_probe+'/job.json'],env=env,stdout=log,stderr=subprocess.STDOUT,
                       check=True,timeout=180)
    result=json.loads((host_probe/'probe-result.json').read_text())
    assert result['delivered'] and result['model_requests']==0
    for artifact in result['delivery']['artifacts']:
        path=artifact['path'];assert path.startswith(sandbox_probe+'/validation/')
        assert (host_probe/path.removeprefix(sandbox_probe+'/')).is_file()
    return probe_id

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--render-ppt',action='store_true',help='also render one synthetic page inside each member mount')
    args=parser.parse_args()
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
        if os.environ.get('HARLESS_PPT_RUNTIME_BUNDLE'):
            config['memberSceneDeployment']['libraryRoot']=os.environ['HARLESS_PPT_RUNTIME_BUNDLE']
            config_path.write_text(json.dumps(config))
        for key,name in [('rendererRoot','HARLESS_PPT_RENDERER_ROOT'),('fontRoot','HARLESS_PPT_FONT_ROOT')]:
            if os.environ.get(name):config['memberSceneDeployment'][key]=os.environ[name]
        config_path.write_text(json.dumps(config))
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
            clients=[];user_ids={};base=f'http://127.0.0.1:{port}'
            for i,code in enumerate(codes):
                client,headers=account()
                req=urllib.request.Request(base+'/api/account/register',data=json.dumps({'inviteCode':code,
                    'username':'diagnostic'+str(i),'displayName':'Diagnostic '+str(i),'password':'OnlyDiagnosticPassword123!'}).encode(),
                    headers={'Content-Type':'application/json'})
                with client.open(req,timeout=10) as response:
                    headers.cookie=response.headers['Set-Cookie'].split(';',1)[0]
                    user_ids[client]=json.load(response)['user']['id']
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
            tasks=[];ppt_tasks=[]
            for client in clients:
                for identity in ['new-scene','ppt','paper-proofreading','research-data-analysis','files']:
                    result=scenes.settings(client,base,{'action':'select','selection':{'scene':identity,'mode':'shadow','rsi':True}})
                    assert all(s['available'] for s in result['scenes'])
                    draft=web.api(client,base,{'action':'preview','request':'Inspect the approved input only; no output writing.'})
                    name,data={'new-scene':('note.txt',b'Private diagnostic text'),
                               'ppt':('source.pdf',None),'paper-proofreading':('main.tex',b'\\cite{missing}'),
                               'research-data-analysis':('data.csv',b'x,y\n1,2\n2,4\n'),
                               'files':('note.txt',b'Private file inventory input')}[identity]
                    if data is None:
                        import io
                        from reportlab.pdfgen.canvas import Canvas
                        b=io.BytesIO();p=Canvas(b);p.drawString(80,700,'Only this account source.');p.save();data=b.getvalue()
                    draft=web.api(client,base,{'action':'upload','task_id':draft['task_id'],'name':name,'data':base64.b64encode(data).decode()})
                    assert draft['scene']==identity and draft['scene_inputs']
                    tasks.append((client,draft))
                    if identity=='ppt':ppt_tasks.append((user_ids[client],draft))
                    foreign=clients[1] if client is clients[0] else clients[0]
                    assert web.request(foreign,base,'/api/harless/tasks?task_id='+draft['task_id'])[0]==404
                    assert scenes.settings(foreign,base,session=draft['session_id'],expected=404)['error']['code']=='session_not_owned'
                    web.api(client,base,{'action':'cancel','task_id':draft['task_id']})
            assert len({task['session_id'] for _,task in tasks})==10
            assert all(web.api(c,base)['aggregate'].get('upstream_requests',0)==0 for c in clients)
            rendered=[]
            if args.render_ppt:
                for user_id,task in ppt_tasks:
                    user_dir=area/'members'/user_id
                    assert user_dir.is_dir()
                    rendered.append(render_in_member(user_dir,task['task_id']))
            report={'status':'passed','users':2,'scene_drafts':10,'actual_bwrap':True,'actual_mcp':True,
                    'model_requests':0,'member_ppt_deliveries':len(rendered),'browser_verified':False,'quality_reviewed':False}
            (area/'result.json').write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps(report))
        finally:
            if child.poll() is None:child.send_signal(signal.SIGTERM)
            try:child.wait(timeout=10)
            except subprocess.TimeoutExpired:child.kill();child.wait()
            log.close()

if __name__=='__main__':main()
