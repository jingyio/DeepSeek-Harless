"""Real SDK + MCP + spending proxy round trip against a local fake provider."""
import json
import re
import tempfile
import threading
from uuid import uuid4
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from src.adapters.deepseek_cost_gate import State, create_server
from src.adapters.harness_runtime import create_harness
from src.adapters.scenario import ROOT, prepare_scenario


class Provider(BaseHTTPRequestHandler):
    calls = []

    def log_message(self, *_args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.calls.append((self.path, body))
        number = len(self.calls)
        if number == 1:
            tool, arguments = 'mcp__demo__pin_note', {'object_id':'note:alpha'}
        elif number == 2:
            match = re.search(r'source-[a-f0-9]{32}', json.dumps(body['messages']))
            if not match:
                raise AssertionError('MCP pin result did not return to the model')
            tool, arguments = 'mcp__demo__read_pinned_note', {'source_id':match.group()}
        else:
            tool, arguments = None, None
        delta = {'role':'assistant'}
        if tool:
            delta['tool_calls'] = [{'index':0,'id':f'fake-call-{number}','type':'function',
                'function':{'name':tool,'arguments':json.dumps(arguments)}}]
        else:
            delta['content'] = 'The pinned note requires independent replication.'
        base = {'id':f'fake-{number}','created':1,'model':body['model'],'object':'chat.completion.chunk'}
        usage = {'prompt_tokens':100,'prompt_cache_hit_tokens':50,'prompt_cache_miss_tokens':50,
                 'completion_tokens':20,'total_tokens':120}
        chunks = [{**base,'choices':[{'index':0,'delta':delta,'finish_reason':None}]},
                  {**base,'choices':[{'index':0,'delta':{},'finish_reason':'tool_calls' if tool else 'stop'}]},
                  {**base,'choices':[],'usage':usage}]
        raw = ''.join('data: '+json.dumps(chunk)+'\n\n' for chunk in chunks)+'data: [DONE]\n\n'
        answer = raw.encode()
        self.send_response(200); self.send_header('Content-Type','text/event-stream')
        self.send_header('Content-Length',str(len(answer))); self.end_headers(); self.wfile.write(answer)


def test_native_harness_loop_executes_only_demo_mcp_through_budget_proxy():
    Provider.calls = []
    prepared = prepare_scenario(ROOT / 'scenarios/example/scenario.json')
    with tempfile.TemporaryDirectory() as temp, ThreadingHTTPServer(('127.0.0.1',0),Provider) as provider:
        state = State(cap_usd=1,output_cap=1000,record=Path(temp)/'ledger.jsonl')
        gate = create_server('127.0.0.1',0,f'http://127.0.0.1:{provider.server_port}',state)
        threads = [threading.Thread(target=server.serve_forever,daemon=True) for server in (provider,gate)]
        for thread in threads: thread.start()
        try:
            with create_harness(root=ROOT,patches=(prepared['patch'],),cwd=temp,runtime_cwd=temp,
                                provider='deepseek-official',model='deepseek-flash',max_tokens=1000,
                                request_timeout_seconds=20,
                                env={'DEEPSEEK_BASE_URL':f'http://127.0.0.1:{gate.server_port}/v1',
                                     'DEEPSEEK_API_KEY':'sss-fake-provider-only',
                                     'SSS_SCENARIO_TOOLS':json.dumps(prepared['allowed_tools']),
                                     'SSS_ONLINE_MOTIF_MANIFEST':'','SSS_ONLINE_MOTIF_TASK':''}) as harness:
                result = harness.run(prepared['prompt'],session_id='offline-mcp-loop-'+uuid4().hex)
            assert 'replication' in result.final_response, [(e.get('type'),e.get('data')) for e in result.events if e.get('type') in {'agent/error','step/end'}]
            assert len(Provider.calls) == 3
            assert all(path == '/v1/chat/completions' for path, _ in Provider.calls)
            assert all({tool['function']['name'] for tool in body['tools']} == set(prepared['allowed_tools'])
                       for _, body in Provider.calls)
            kinds = [event.get('type') for event in result.events]
            assert kinds.count('tool/call') == 2
            assert kinds.count('tool/result') == 2
            assert state.request_count == 3
            rows = [json.loads(line) for line in state.record.read_text(encoding="utf-8").splitlines()]
            assert len(rows) == 3
            assert all(row['response_usage']['prompt_cache_hit_tokens'] == 50 for row in rows)
        finally:
            for server in (gate,provider): server.shutdown()
            gate.server_close()
            for thread in threads: thread.join(timeout=5)
