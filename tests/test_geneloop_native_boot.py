"""Full installed Web profile and native-host composition; no model requests.

This exercises Cordis dependency isolation, rather than calling apply(rootCtx).
Only a loopback diagnostic meter is provided; any completion request is a failure.
"""
import http.cookiejar
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_full_native_host_boots_and_exposes_scoped_controls_without_model_work():
    node = shutil.which('node')
    if not node:
        pytest.skip('Installed native Harness diagnostic requires Node')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    model_requests = []

    class Meter(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length', 0)))
            if self.path.endswith('/chat/completions'):
                model_requests.append(self.path)
                self.send_response(500)
                raw = b'{"error":{"message":"Model work is forbidden by this diagnostic"}}'
            else:
                self.send_response(200)
                raw = b'{"stats":{"upstream_requests":0,"estimated_cost_usd":0,"usage_complete":true}}'
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Meter)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    output = ROOT / '.local/native-boot-tests' / uuid4().hex
    output.mkdir(parents=True, mode=0o700)
    process = None
    try:
        preset = output / 'presets/sss-task'
        preset.mkdir(parents=True)
        (preset / 'preset.yml').write_text('{"name":"Native boot diagnostic"}', encoding='utf-8')
        common = json.loads((ROOT / 'config/geneloop-capabilities.json').read_text(encoding='utf-8'))['tools']
        # sessionPreset appends commonToolRows once when common_tools is set.
        (preset / 'agent.cordis.yml').write_text('[]', encoding='utf-8')
        endpoint = f'http://127.0.0.1:{server.server_port}'
        policy = {'output': str(output), 'endpoint': endpoint + '/v1', 'control_endpoint': endpoint,
                  'control_token': 'loopback-diagnostic-not-secret', 'allowed_tools': common,
                  'capability_profile': 'new-scene', 'mode': 'baseline', 'budget_usd': None,
                  'max_output_tokens': None, 'provider_mode': 'mock',
                  'scenes': [{'id': 'new-scene', 'label': 'Chat', 'preset': 'sss-task',
                              'adapter': 'workspace', 'allowed_tools': common,
                              'common_tools': common, 'mcp_rows': []}]}
        (output / 'policy.json').write_text(json.dumps(policy), encoding='utf-8')
        # Persisted owned private and merely reserved identities must never be
        # exposed as public command targets, including on a cold host load.
        hidden = {key: 'session-' + str(uuid4()) for key in ('private', 'reserved', 'unknown')}
        hidden.update(raw=str(uuid4()), retired_raw=str(uuid4()))
        principal = 'local-operator'
        home = output / 'home'
        home.mkdir()
        ownership_scope = hashlib.sha256(json.dumps({'home': str(home), 'principal': principal},
                           sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        ownership = home / ('harless-web-ownership-' + ownership_scope + '.json')
        ownership.write_text(json.dumps({'scope': ownership_scope, 'sessions': [hidden['private'], hidden['reserved']],
                             'bound': [], 'chat_only_sessions': []}), encoding='utf-8')
        (output / 'private-lane-sessions.json').write_text(json.dumps({'version': 1, 'principal': principal,
            'sessions': {hidden['private']: 'session-' + str(uuid4()), hidden['reserved']: 'session-' + str(uuid4())}}), encoding='utf-8')
        patch = [{'id': name, 'disabled': True} for name in
                 ('llm-deepseek', 'llm-pi-ai', 'session-title-llm', 'session-log-deepseek',
                  'bash-sandbox', 'pwsh-sandbox', 'web-search-deepseek')]
        patch += [{'id': 'web-runtime', 'config': {'openBrowser': False, 'printUrl': True,
                                                  'surfaceContext': False, 'trustedHosts': []}},
                  {'id': 'agent-presets', 'config': {'default': 'sss-task', 'includeShippedRoot': False,
                                                   'includeUserRoot': False,
                                                   'roots': [{'path': str(output / 'presets'), 'trust': 'system'}]}},
                  {'insert': [{'id': 'geneloop-tasks-boot',
                               'name': (ROOT / 'src/adapters/dsh_web_tasks.ts').as_uri()},
                              {'id': 'geneloop-shell', 'name': (ROOT / 'src/adapters/geneloop_shell.ts').as_uri()},
                              {'id': 'geneloop-web-search', 'name': (ROOT / 'src/adapters/geneloop_web_search.ts').as_uri()}]}]
        composition = subprocess.run([node, str(ROOT / 'src/adapters/geneloop_native_host.mjs'),
                                      '--source-dir', str(ROOT / 'src')],
                                     input=json.dumps(patch), text=True, capture_output=True,
                                     encoding='utf-8', cwd=ROOT, timeout=20)
        assert composition.returncode == 0, composition.stderr
        patch = json.loads(composition.stdout)
        diagnostic = output / 'native-ready.mjs'
        diagnostic.write_text("""
import {scopeOf} from '@deepseek-ai/dsh-scope';
import {createHash} from 'node:crypto';
export const name='native-boot-readiness';
export const inject=['connection','agents','agentPresets','commands','compaction','planMode','goals','subagents','sessions','tools','fs','skills','userQuestions'];
export function apply(ctx){
 const handles=[];ctx.effect(()=>async()=>{for(const handle of handles.reverse())await handle.dispose();},'native-diagnostic-handles');
 ctx.effect(()=>ctx.connection.fetch.register({path:'/api/diagnostic/command-targets',methods:['POST'],requestBody:'buffered',async fetch(request){
  const rejected=ctx.connection.requestRejection(request);if(rejected)return new Response('Unauthorized',{status:rejected});
  try{
  const {ids,parent}=await request.json(),owner=ctx.agents.get(parent);
  for(const key of ['private','unknown','raw','retired_raw']){
   const child=key==='raw'||key==='retired_raw';
   const handle=await ctx.agents.create({sessionId:ids[key],agentOptions:{provider:'deepseek-official',model:'deepseek-flash'},
    ...(child?{parentAgent:owner}:{}),meta:{agentPreset:'sss-task',...(child?{parentSession:parent,origin:'subagent'}:{})},
    setup:async agentCtx=>{await ctx.agentPresets.mount(agentCtx,'sss-task');}});
   if(key==='retired_raw')await handle.dispose();else handles.push(handle);
  }
  return Response.json({created:true});
  }catch(error){return Response.json({diagnostic_error:String(error),stack:error.stack},{status:500});}
 }}),'native-command-targets');
 ctx.effect(()=>ctx.connection.fetch.register({path:'/api/diagnostic/native-ready',methods:['GET'],requestBody:'buffered',async fetch(request){
  const rejected=ctx.connection.requestRejection(request);if(rejected)return new Response('Unauthorized',{status:rejected});
  const id=new URL(request.url).searchParams.get('session_id'),agent=id?ctx.agents.get(id):undefined;
  return Response.json({compaction:typeof ctx.compaction.compactNow==='function',
   plan:typeof ctx.planMode.get==='function',goal:typeof ctx.goals.get==='function',
   persistence:typeof ctx.sessions.flush==='function',questions:typeof ctx.userQuestions.ask==='function',
   spawn:!!ctx.subagents.getProvider('spawn'),delegation:!!ctx.subagents.getProvider('geneloop-task'),
   tools:ctx.tools.schemas(agent?scopeOf(agent.ctx):undefined).map(t=>t.name),
   ...(agent?{events_sha256:createHash('sha256').update(JSON.stringify(agent.session.snapshotEvents())).digest('hex'),
     plan_state:ctx.planMode.get(agent),user_messages:agent.session.snapshotEvents().filter(e=>e.type==='user/message').length}:{} )});
 }}),'native-boot-readiness');
}
""", encoding='utf-8')
        patch.append({'insert': [{'id': 'native-ready-diagnostic', 'name': diagnostic.as_uri()}]})
        patch_file = output / 'host.patch.json'
        patch_file.write_text(json.dumps(patch), encoding='utf-8')
        env = {**os.environ, 'DSH_HOME': str(output / 'home'), 'SSS_WEB_POLICY': str(output / 'policy.json'),
               'DEEPSEEK_API_KEY': 'not-a-provider-key', 'CHOKIDAR_USEPOLLING': '1', 'CHOKIDAR_INTERVAL': '1000'}
        with (output / 'native.log').open('w', encoding='utf-8') as log:
            process = subprocess.Popen([node, str(ROOT / 'node_modules/@deepseek-ai/dsh/lib/bin.js'),
                                        '--profile', 'web', '--patch', str(patch_file),
                                        '--host', '127.0.0.1', '--port', str(port), '--no-open'],
                                       cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
            client = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                      urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            base = f'http://127.0.0.1:{port}'

            def request(path, body=None):
                try:
                    with client.open(urllib.request.Request(base + path,
                           data=None if body is None else json.dumps(body).encode(),
                           headers={'Origin': base, 'Content-Type': 'application/json'}), timeout=10) as response:
                        return json.load(response)
                except urllib.error.HTTPError as error:
                    if error.code == 500:
                        raise AssertionError(error.read().decode()) from error
                    raise

            deadline = time.monotonic() + 45
            signed_in = False
            while time.monotonic() < deadline:
                text = (output / 'native.log').read_text(encoding='utf-8')
                assert process.poll() is None, text[-8000:]
                match = re.search(re.escape(base) + r'/\?token=[A-Za-z0-9_-]+', text)
                if match and not signed_in:
                    client.open(match[0], timeout=10).close()
                    signed_in = True
                if signed_in:
                    try:
                        ready = request('/api/diagnostic/native-ready')
                        break
                    except urllib.error.HTTPError as error:
                        if error.code not in (404, 503):
                            raise
                time.sleep(.1)
            else:
                pytest.fail('Composed native services did not activate:\n' + text[-8000:])
            assert all(ready[key] for key in ('compaction', 'plan', 'goal', 'persistence',
                                             'questions', 'spawn', 'delegation')), ready

            def rpc(method, args):
                result = request('/api/' + method, {'type': 'client-request', 'rpcId': str(uuid4()),
                                  'method': method, 'payload': {'args': args}})['result']
                assert result['ok'], json.dumps(result, ensure_ascii=False)
                return result.get('value')

            session = rpc('session/create', {'request': {}})['sessionId']
            tools = request('/api/diagnostic/native-ready?session_id=' + session)['tools']
            assert set(common) <= set(tools), tools
            names = {row['name'] for row in rpc('commands/list', {'agentId': session})}
            assert {'plan', 'goal', 'compact'} <= names
            for line in ('/plan', '/plan off', '/compact'):
                result = rpc('commands/execute', {'agentId': session, 'line': line, 'submittedAttachments': []})
                assert result['result']['kind'] == 'success', result
            invalid = rpc('commands/execute', {'agentId': session, 'line': '/goal --rounds 0 no-work', 'submittedAttachments': []})
            assert invalid['result']['kind'] == 'error'
            assert rpc('goals/get', {'agentId': session}) is None
            assert request('/api/harless/questions?session_id=' + session) == {'questions': []}
            assert request('/api/harless/tasks')['tasks'] == []
            assert request('/api/diagnostic/command-targets', {'ids': hidden, 'parent': session}) == {'created': True}
            footprints = {key: request('/api/diagnostic/native-ready?session_id=' + hidden[key])
                          for key in ('private', 'unknown', 'raw')}
            ownership_before = ownership.read_bytes()
            denied = []
            for target in hidden.values():
                for method, args in (
                    ('list', {'agentId': target}),
                    ('execute', {'agentId': target, 'line': '/plan PRIVATE_PLAN_BYPASS', 'submittedAttachments': []}),
                    ('execute', {'agentId': target, 'line': '/compact', 'submittedAttachments': []}),
                    ('execute', {'agentId': target, 'line': '/arbitrary-control', 'submittedAttachments': []}),
                ):
                    frame = {'type': 'client-request', 'rpcId': str(uuid4()), 'method': 'commands/' + method,
                             'payload': {'args': args}}
                    result = request('/api/commands/' + method, frame)['result']
                    assert not result['ok'] and result['error']['code'] == 'gateway/forbidden', result
                    denied.append({'endpoint': 'commands/' + method, 'args': args})
            # Use the installed browser's actual WS MUX carrier, and pass the
            # temporary fixture cookie through stdin rather than argv/logs.
            cookie = '; '.join(cookie.name + '=' + cookie.value for handler in client.handlers
                               if isinstance(handler, urllib.request.HTTPCookieProcessor)
                               for cookie in handler.cookiejar)
            ws_test = r'''
import WebSocket from 'ws';import {readFileSync} from 'node:fs';import {randomUUID} from 'node:crypto';
const input=JSON.parse(readFileSync(0,'utf8')),ws=new WebSocket(input.origin.replace('http:','ws:')+'/api/remote.mux',
 {headers:{cookie:input.cookie,Origin:input.origin}});
await new Promise((resolve,reject)=>{ws.once('open',resolve);ws.once('error',reject);});
try{for(const entry of input.denied){const id=randomUUID();
 const response=await new Promise((resolve,reject)=>{const timeout=setTimeout(()=>reject(Error('Command boundary WS timeout')),10000);
  const listener=raw=>{const value=JSON.parse(raw.toString());if(value.streamId!==id)return;
   clearTimeout(timeout);ws.off('message',listener);resolve(value);};ws.on('message',listener);
  ws.send(JSON.stringify({type:'open',streamId:id,endpoint:entry.endpoint,payload:{args:entry.args}}));});
 if(response.type!=='error'||response.error?.code!=='gateway/forbidden')throw Error('Private command WS boundary was bypassed');
 }console.log(JSON.stringify({denied:input.denied.length}));}finally{ws.close();}
'''
            ws_result = subprocess.run([node, '--input-type=module', '-e', ws_test],
                        input=json.dumps({'origin': base, 'cookie': cookie, 'denied': denied}),
                        text=True, capture_output=True, encoding='utf-8', cwd=ROOT, timeout=25)
            assert ws_result.returncode == 0, ws_result.stderr
            assert json.loads(ws_result.stdout) == {'denied': len(denied)}
            for key, before in footprints.items():
                after = request('/api/diagnostic/native-ready?session_id=' + hidden[key])
                for field in ('events_sha256', 'plan_state', 'user_messages'):
                    assert after[field] == before[field], (key, field)
            assert ownership.read_bytes() == ownership_before, 'Denied commands may not adopt an unknown child or change ownership'
            assert request('/api/harless/tasks')['tasks'] == []
            assert model_requests == [], 'Native control-only boot must never call a model'
    finally:
        if process:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        # This test's private logs remain available on failure; no user state is read.
