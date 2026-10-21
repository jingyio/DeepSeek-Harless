"""Actual member-namespace native host boot; no gateway/owner/model is started."""
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from uuid import uuid4

import pytest

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.skipif(sys.platform!='linux' or not Path('/usr/bin/bwrap').exists(),reason='Real account namespace requires Linux bubblewrap')
def test_native_host_loads_verified_skill_in_member_namespace(tmp_path):
    node=shutil.which('node')
    if not node:pytest.skip('Installed native Harness requires Node')
    node=Path(node).resolve();python=Path(sys.executable).resolve()
    fixture=tmp_path.resolve();project=fixture/'public-project';project.mkdir()
    (project/'scenarios/ppt_master').mkdir(parents=True)
    skill=fixture/'public-skill';skill.mkdir()
    raw=b'---\nname: ppt-master\ndescription: Public namespace diagnostic skill.\n---\nRead public diagnostic resources.\n'
    (skill/'SKILL.md').write_bytes(raw)
    files={'SKILL.md':hashlib.sha256(raw).hexdigest()}
    (project/'scenarios/ppt_master/skill-lock.json').write_text(json.dumps({'schema_version':1,'version':'6.6.0','files':files,
        'package_sha256':hashlib.sha256(json.dumps(files,separators=(',',':')).encode()).hexdigest()}))
    user=fixture/'user';(user/'config/presets/sss-task').mkdir(parents=True)
    for name in ('workspace','dsh','tasks'): (user/name).mkdir()
    (user/'config/presets/sss-task/preset.yml').write_text('{"name":"Namespace diagnostic"}')
    (user/'config/presets/sss-task/agent.cordis.yml').write_text('[]')
    # The exact production deployment helper validates the public installation
    # and emits the account's resource aliases; host broker inputs stay private.
    setup_script=fixture/'prepare.mjs'
    setup_script.write_text("""
import {readFileSync} from 'node:fs';
import {memberSceneDeployment} from %s;
import {composeNativeHost} from %s;
const input=JSON.parse(readFileSync(0,'utf8'));
const scene={id:'new-scene',label:'Chat',preset:'sss-task',adapter:'workspace',allowed_tools:[],
 mcp_rows:[{name:'@deepseek-ai/dsh-mcp-client',config:{serverName:'workspace',transport:'stdio',command:input.python,
 cwd:input.project,args:[input.project+'/scenarios/general/server.py']}}]};
const deployment={projectRoot:input.project,pythonExecutable:input.python,pythonRoots:input.pythonRoots,pptMasterRoot:input.skill};
const result=memberSceneDeployment({scenes:[scene]},deployment);
const patch=[...['llm-deepseek','llm-pi-ai','session-title-llm','session-log-deepseek','bash-sandbox','pwsh-sandbox','web-search-deepseek'].map(id=>({id,disabled:true})),
 {id:'web-runtime',config:{openBrowser:false,printUrl:true,surfaceContext:false,trustedHosts:[]}},
 {id:'agent-presets',config:{default:'sss-task',includeShippedRoot:false,includeUserRoot:false,
 roots:[{path:'/user/config/presets',trust:'system'}]}},
 {insert:[{id:'geneloop-tasks',name:'file:///app/src/adapters/dsh_web_tasks.ts'},
 {id:'geneloop-shell',name:'file:///app/src/adapters/geneloop_shell.ts'},
 {id:'geneloop-web-search',name:'file:///app/src/adapters/geneloop_web_search.ts'}]}];
process.stdout.write(JSON.stringify({resources:result.native_resources,mounts:result.mounts,
 patch:composeNativeHost(patch,input.source,{member:true})}));
"""%(json.dumps((ROOT/'scripts/harless_member_scenes.mjs').as_uri()),json.dumps((ROOT/'src/adapters/geneloop_native_host.mjs').as_uri())))
    python_roots=sorted({str(Path(sys.prefix).resolve()),str(Path(sys.base_prefix).resolve())})
    # System Python lives in /usr, already an immutable namespace dependency.
    # memberSceneDeployment validates installation roots, never arbitrary homes.
    request={'python':str(python),'pythonRoots':python_roots,'project':str(project),'skill':str(skill),'source':str(ROOT/'src')}
    prepared=subprocess.run([str(node),str(setup_script)],input=json.dumps(request),capture_output=True,text=True,cwd=ROOT,timeout=30)
    assert prepared.returncode==0,prepared.stderr
    deployment=json.loads(prepared.stdout)
    assert deployment['resources']=={'projectRoot':'/app','pptMasterRoot':'/opt/geneloop/ppt-master'}
    assert request['project']==str(project) and request['skill']==str(skill)
    common=json.loads((ROOT/'config/geneloop-capabilities.json').read_text())['tools']
    policy={'output':'/app/.local/web','command_resources':deployment['resources'],'endpoint':'http://127.0.0.1:1/v1',
        'control_endpoint':'http://127.0.0.1:1','control_token':'diagnostic-not-secret','allowed_tools':common,
        'capability_profile':'new-scene','provider_mode':'mock','mode':'baseline','budget_usd':None,'max_output_tokens':None,
        'scenes':[{'id':'new-scene','label':'Chat','preset':'sss-task','adapter':'workspace','allowed_tools':common,'common_tools':common,'mcp_rows':[]}]}
    (user/'config/policy.json').write_text(json.dumps(policy))
    diagnostic=user/'config/ready.mjs'
    diagnostic.write_text("""
import {readFileSync,existsSync} from 'node:fs';
import {geneLoopMounts} from 'file:///app/src/adapters/geneloop_fs.ts';
export const name='member-namespace-readiness';export const inject=['connection','skills','fs','subprocess'];
export function apply(ctx){ctx.connection.fetch.register({path:'/api/diagnostic/member-namespace',methods:['GET'],requestBody:'buffered',async fetch(request){
 const rejected=ctx.connection.requestRejection(request);if(rejected)return new Response('Unauthorized',{status:rejected});
 const policy=JSON.parse(readFileSync(process.env.SSS_WEB_POLICY,'utf8'));
 const mounts=geneLoopMounts(policy,'session-11111111-1111-4111-8111-111111111111');
 const skill=mounts.find(m=>m.logical==='/opt/geneloop/ppt-master');
 return Response.json({skills:(await ctx.skills.list({cwd:'/work'})).map(s=>s.name),
  resources:policy.command_resources,skill_mount:skill,skill_text:readFileSync(skill.host+'/SKILL.md','utf8'),
  private_host_path_visible:existsSync(%s),filesystem:ctx.fs.constructor.name,subprocess:ctx.subprocess.constructor.name});
 }});}
"""%json.dumps(str(project)))
    patch=deployment['patch']+[{'insert':[{'id':'member-namespace-ready','name':'file:///user/config/ready.mjs'}]}]
    (user/'config/host.patch.json').write_text(json.dumps(patch))
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    args=['/usr/bin/bwrap','--unshare-user','--unshare-pid','--uid','1000','--gid','1000','--die-with-parent']
    for path in ('/usr','/bin','/lib','/lib64','/etc'):
        if Path(path).exists():args+=['--ro-bind',path,path]
    args+=['--proc','/proc','--dev','/dev','--tmpfs','/tmp','--dir','/app','--dir','/opt',
        '--ro-bind',str(node.parent.parent),'/opt/node','--ro-bind',str((ROOT/'node_modules').resolve()),'/app/node_modules',
        '--ro-bind',str(ROOT/'src'),'/app/src','--ro-bind',str(ROOT/'config'),'/app/config','--bind',str(user),'/user',
        '--dir','/app/.local','--bind',str(user/'tasks'),'/app/.local/web']
    # Mirror production's public module graph; the legacy report interceptor
    # is imported by the host even when this diagnostic creates no scene Task.
    for name in ('scripts','benchmarks','motif-libraries'):
        if (ROOT/name).exists():args+=['--ro-bind',str(ROOT/name),'/app/'+name]
    for mount in deployment['mounts']:
        if mount['target']!='/app/src':args+=['--ro-bind',mount['source'],mount['target']]
    args+=['--chdir','/user/workspace','/opt/node/bin/node','/app/node_modules/@deepseek-ai/dsh/lib/bin.js',
        '--profile','web','--patch','/user/config/host.patch.json','--host','127.0.0.1','--port',str(port),'--no-open']
    environment={'PATH':'/opt/node/bin:/usr/bin:/bin','HOME':'/user/workspace','DSH_HOME':'/user/dsh',
        'SSS_WEB_POLICY':'/user/config/policy.json','SSS_PYTHON':str(python),'DEEPSEEK_API_KEY':'not-a-provider-key',
        'CHOKIDAR_USEPOLLING':'1','CHOKIDAR_INTERVAL':'1000'}
    (fixture/'namespace-command.json').write_text(json.dumps({'argv':args,'env':environment}))
    log=fixture/'member-native.log';process=None
    try:
        with log.open('w') as stream:
            boot_started=time.monotonic()
            process=subprocess.Popen(args,env=environment,stdout=stream,stderr=subprocess.STDOUT)
            base=f'http://127.0.0.1:{port}'
            client=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            deadline=time.monotonic()+180;signed_in=False
            while time.monotonic()<deadline:
                text=log.read_text();assert process.poll() is None,text[-10000:]
                launch=re.search(re.escape(base)+r'/\?token=[A-Za-z0-9_-]+',text)
                if launch and not signed_in:client.open(launch[0],timeout=10).close();signed_in=True
                if signed_in:
                    try:
                        with client.open(base+'/api/diagnostic/member-namespace',timeout=10) as response:actual=json.load(response)
                        break
                    except urllib.error.HTTPError as error:
                        if error.code not in (404,503):raise
                time.sleep(.1)
            else:pytest.fail('Member native host failed to become ready:\n'+log.read_text()[-10000:])
            (fixture/'namespace-proof.json').write_text(json.dumps({'boot_seconds':time.monotonic()-boot_started,
                'model_requests':0,'namespace':actual}))
            assert actual['skills']==['ppt-master'],actual
            assert actual['filesystem']=='GeneLoopFileSystem',actual
            assert actual['subprocess']=='GeneLoopSubprocessRuntime',actual
            assert actual['resources']==deployment['resources'],actual
            assert actual['skill_mount']=={'logical':'/opt/geneloop/ppt-master','host':'/opt/geneloop/ppt-master','writable':False},actual
            assert actual['skill_text'].encode()==raw and not actual['private_host_path_visible'],actual
            with client.open(base+'/api/harless/tasks',timeout=10) as response:assert json.load(response)['tasks']==[]
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
