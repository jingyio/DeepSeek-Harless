"""Search must use the same admitted task ledger as chat, without leaking content."""
import http.client
import json
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from src.adapters.deepseek_cost_gate import State, create_server, response_usage


def test_native_search_usage_and_admitted_route():
    usage = {'input_tokens': 12, 'cache_creation_input_tokens': 2, 'cache_read_input_tokens': 8, 'output_tokens': 3}
    assert response_usage('application/json', json.dumps({'usage': usage}).encode()) == {
        'prompt_tokens': 22, 'prompt_cache_hit_tokens': 8, 'prompt_cache_miss_tokens': 14,
        'completion_tokens': 3, 'total_tokens': 25}
    assert response_usage('application/json', b'{"usage":{"input_tokens":true,"output_tokens":1}}') == {}
    calls = []

    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_POST(self):
            calls.append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
            raw = json.dumps({'content': [{'type': 'text', 'text': 'private search result'}], 'usage': usage}).encode()
            self.send_response(200); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)

    session = 'session-11111111-1111-4111-8111-111111111111'
    with tempfile.TemporaryDirectory() as tmp:
        state = State(cap_usd=None, output_cap=None, request_limit=None, record=Path(tmp)/'ledger.jsonl')
        def select(headers):
            if {k.lower(): v for k,v in headers.items()}.get('x-deepseek-harness-session-id') != session:
                raise PermissionError('unadmitted')
            return state
        upstream = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
        gate = create_server('127.0.0.1', 0, f'http://127.0.0.1:{upstream.server_port}', state,
                             state_selector=select, allow_search=True, allowed_models={'deepseek-flash','deepseek-v4-pro'})
        servers = [upstream, gate]
        for server in servers: threading.Thread(target=server.serve_forever, daemon=True).start()
        body = {'model':'deepseek-flash','max_tokens':4096,'messages':[{'role':'user','content':'private query'}],
                'tools':[{'type':'web_search_20250305','name':'web_search','max_uses':3}]}
        def request(path, data):
            conn = http.client.HTTPConnection('127.0.0.1', gate.server_port, timeout=5)
            try:
                conn.request('POST', path, json.dumps(data), {'Content-Type':'application/json'})
                reply = conn.getresponse(); reply.read(); return reply.status
            finally: conn.close()
        try:
            assert request('/v1/search/messages', body) == 403
            assert request(f'/v1/search/{session}/messages', body) == 200
            assert calls[0][0] == '/anthropic/v1/messages'
            assert calls[0][1]['model'] == 'deepseek-v4-flash'
            assert state.request_count == 1
            assert request(f'/v1/search/{session}/messages', {**body,'model':'unpriced'}) == 400
            assert request(f'/v1/search/{session}/messages', {**body,'tools':[]}) == 400
            assert request(f'/v1/search/{session}/messages', {**body,'messages':['invalid']}) == 400
            assert request(f'/v1/search/{session}/messages', {**body,'messages':[{'role':'user','content':None}]}) == 400
            assert len(calls) == 1
            log = state.record.read_text()
            assert 'web_search' in log and 'private search result' not in log and 'private query' not in log
            assert json.loads(log.splitlines()[-1])['response_usage']['total_tokens'] == 25
        finally:
            for server in reversed(servers): server.shutdown(); server.server_close()
