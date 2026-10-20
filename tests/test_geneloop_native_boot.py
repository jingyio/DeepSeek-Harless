"""Full installed Web profile and native-host composition; no model requests.

This exercises Cordis dependency isolation, rather than calling apply(rootCtx).
Only a loopback diagnostic meter is provided; any completion request is a failure.
"""
import http.cookiejar
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
export const name='native-boot-readiness';
export const inject=['connection','agents','compaction','planMode','goals','subagents','sessions','tools','fs','skills','userQuestions'];
export function apply(ctx){
 ctx.effect(()=>ctx.connection.fetch.register({path:'/api/diagnostic/native-ready',methods:['GET'],requestBody:'buffered',async fetch(request){
  const rejected=ctx.connection.requestRejection(request);if(rejected)return new Response('Unauthorized',{status:rejected});
  const id=new URL(request.url).searchParams.get('session_id'),agent=id?ctx.agents.get(id):undefined;
  return Response.json({compaction:typeof ctx.compaction.compactNow==='function',
   plan:typeof ctx.planMode.get==='function',goal:typeof ctx.goals.get==='function',
   persistence:typeof ctx.sessions.flush==='function',questions:typeof ctx.userQuestions.ask==='function',
   spawn:!!ctx.subagents.getProvider('spawn'),delegation:!!ctx.subagents.getProvider('geneloop-task'),
   tools:ctx.tools.schemas(agent?scopeOf(agent.ctx):undefined).map(t=>t.name)});
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
                with client.open(urllib.request.Request(base + path,
                       data=None if body is None else json.dumps(body).encode(),
                       headers={'Origin': base, 'Content-Type': 'application/json'}), timeout=10) as response:
                    return json.load(response)

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
