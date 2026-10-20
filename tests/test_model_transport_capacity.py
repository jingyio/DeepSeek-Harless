"""Real local HTTP envelopes only; neither gate calls a paid provider."""
import hashlib
import http.client
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from src.adapters import deepseek_cost_gate, file_cost_gate
from src.adapters.model_transport import MODEL_REQUEST_MAX_BYTES, MODEL_REQUEST_TOO_LARGE


@pytest.fixture(params=[deepseek_cost_gate, file_cost_gate], ids=['web', 'file-sdk'])
def transport(request, tmp_path):
    received = []

    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            digest, remaining = hashlib.sha256(), int(self.headers['Content-Length'])
            size = remaining
            while remaining:
                part = self.rfile.read(min(remaining, 1024 * 1024))
                assert part
                digest.update(part)
                remaining -= len(part)
            received.append((self.path, size, digest.hexdigest()))
            raw = b'{"choices":[],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}'
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    provider = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
    module = request.param
    state = module.State(cap_usd=None, output_cap=None, record=tmp_path/'ledger.jsonl')
    gate = module.create_server('127.0.0.1', 0,
        f'http://127.0.0.1:{provider.server_port}', state, allow_vision=True)
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in [provider, gate]]
    for thread in threads:
        thread.start()
    try:
        yield gate, received, state
    finally:
        for server, thread in zip([provider, gate], threads):
            server.shutdown()
            server.server_close()
            thread.join(5)


def post(gate, path, body):
    conn = http.client.HTTPConnection('127.0.0.1', gate.server_port, timeout=30)
    try:
        conn.request('POST', path, body=body, headers={'Content-Type':'application/json'})
        response = conn.getresponse()
        return response.status, json.loads(response.read())
    finally:
        conn.close()


@pytest.mark.parametrize('size', [3*1024*1024, 9*1024*1024, 28*1024*1024])
def test_model_text_and_inline_images_cross_old_caps_without_truncation(transport, size):
    gate, received, state = transport
    # 28 MiB covers base64 expansion of a 20 MiB admitted image. The
    # application does not trim image data, text, output limits or history.
    body = json.dumps({'model':'deepseek-flash', 'max_tokens':393216,
        'messages':[{'role':'user', 'content':[
            {'type':'text', 'text':'context'},
            {'type':'image_url', 'image_url':{'url':'data:image/png;base64,'+'A'*size}},
        ]}]}).encode()
    status, _ = post(gate, '/v1/chat/completions', body)
    assert status == 200
    assert received == [('/v1/chat/completions', len(body), hashlib.sha256(body).hexdigest())]
    assert state.request_count == 1
    assert not state.pending


def test_vision_uses_same_capacity_above_previous_eight_mib(transport):
    gate, received, state = transport
    body = json.dumps({'model':'deepseek-flash', 'stream':False,
        'thinking':{'type':'disabled'}, 'response_format':{'type':'json_object'},
        'messages':[{'role':'user', 'content':[
            {'type':'text', 'text':'Inspect all these pixels'},
            {'type':'image_url', 'image_url':{'url':'data:image/jpeg;base64,'+'A'*(9*1024*1024)}},
        ]}]}).encode()
    assert post(gate, '/v1/vision/chat/completions', body)[0] == 200
    assert received == [('/v1/chat/completions', len(body), hashlib.sha256(body).hexdigest())]
    assert state.request_count == 1


def test_oversize_header_returns_permanent_typed_413_before_admission(transport):
    gate, received, state = transport
    conn = http.client.HTTPConnection('127.0.0.1', gate.server_port, timeout=5)
    try:
        # No 128 MiB allocation, upstream call, reservation or HTTP reset.
        conn.putrequest('POST', '/v1/chat/completions')
        conn.putheader('Content-Type', 'application/json')
        conn.putheader('Content-Length', str(MODEL_REQUEST_MAX_BYTES+1))
        conn.endheaders()
        response = conn.getresponse()
        assert response.status == 413
        value = json.loads(response.read())
        assert value['error']['code'] == MODEL_REQUEST_TOO_LARGE
        assert value['error']['type'] == 'invalid_request_error'
        assert value['error']['max_bytes'] == MODEL_REQUEST_MAX_BYTES
        assert response.getheader('Connection') == 'close'
    finally:
        conn.close()
    assert received == []
    assert state.request_count == 0
    assert not state.pending
    assert post(gate, '/v1/chat/completions',
        b'{"model":"deepseek-flash","max_tokens":1,"messages":[]}')[0] == 200
    assert state.request_count == len(received) == 1
