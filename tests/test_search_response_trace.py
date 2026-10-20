import hashlib
import json
import unittest
import tempfile
import threading
import urllib.request
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from src.adapters.search_evidence_accounting import search_response_trace,instrument_search_server
from src.adapters.deepseek_cost_gate import create_server,State

class SearchTraceTests(unittest.TestCase):
    def test_query_correlation_does_not_log_prompt_or_response_contents(self):
        request={'model':'deepseek-v4-flash','messages':[{'content':'private query'}]}
        response={'content':[{'type':'server_tool_use'},
            {'type':'web_search_tool_result','content':[{'type':'web_search_result','url':'https://example.org','encrypted_content':'private'}]},
            {'type':'text','text':'private answer','citations':[]}]}
        result=search_response_trace(request,json.dumps(response).encode())
        self.assertEqual(result['request_sha256'],hashlib.sha256(json.dumps(request,sort_keys=True,separators=(',',':')).encode()).hexdigest())
        self.assertEqual(result['server_tool_calls'],1)
        self.assertEqual(result['source_item_fields'],['encrypted_content','type','url'])
        self.assertNotIn('private',json.dumps(result))
        self.assertNotIn('example.org',json.dumps(result))

    def test_invalid_shapes_do_not_interrupt_accounting(self):
        for answer in (b'not-json',b'[]',b'{"content":null}',b'{"content":[{"type":"web_search_tool_result","content":null}]}'):
            self.assertFalse(search_response_trace({},answer)['response_shape_known'])

    def test_instrumented_gate_preserves_actual_admission_and_settlement(self):
        class Upstream(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                raw=json.dumps({'content':[{'type':'server_tool_use'},{'type':'web_search_tool_result','content':[]}],
                    'usage':{'input_tokens':32,'output_tokens':10}}).encode()
                self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        with tempfile.TemporaryDirectory() as directory:
            record=Path(directory)/'ledger.jsonl';state=State(cap_usd=1,output_cap=4096,record=record,request_limit=2)
            upstream=ThreadingHTTPServer(('127.0.0.1',0),Upstream)
            gate=instrument_search_server(create_server('127.0.0.1',0,f'http://127.0.0.1:{upstream.server_port}',state,allow_search=True))
            threads=[threading.Thread(target=s.serve_forever,daemon=True)for s in (upstream,gate)]
            for t in threads:t.start()
            try:
                body={'model':'deepseek-flash','max_tokens':128,'messages':[{'role':'user','content':'query'}],
                    'tools':[{'type':'web_search_20250305','name':'web_search','max_uses':3}]}
                opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(urllib.request.Request(f'http://127.0.0.1:{gate.server_port}/v1/search/messages',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'}))as response:self.assertEqual(response.status,200)
                row=json.loads(record.read_text().splitlines()[-1]);self.assertEqual(row['request_id'],1)
                self.assertEqual(row['response_usage']['prompt_tokens'],32);self.assertEqual(row['search_trace']['server_tool_calls'],1)
                self.assertEqual(state.request_count,1);self.assertEqual(state.pending,{})
            finally:
                for s in (gate,upstream):s.shutdown();s.server_close()
                for t in threads:t.join(timeout=2)

if __name__=='__main__':unittest.main()
