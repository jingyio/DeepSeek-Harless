"""Real local HTTP: transient retries retain one task's funds and request count."""
import json,threading,urllib.request,urllib.error
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from src.adapters.file_cost_gate import State,create_server

def test_transient_retry_has_two_total_attempts_and_keeps_failed_cost(tmp_path,monkeypatch):
    import src.adapters.file_cost_gate as gate
    monkeypatch.setattr(gate.time,'sleep',lambda delay:None)
    class Upstream(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            body=self.rfile.read(int(self.headers['Content-Length']));self.server.bodies.append(body)
            code=self.server.statuses.pop(0) if self.server.statuses else 503
            value={'error':'too busy'} if code==503 else {'usage':{'prompt_tokens':10,'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':10,'completion_tokens':1,'total_tokens':11}}
            raw=json.dumps(value).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    upstream=ThreadingHTTPServer(('127.0.0.1',0),Upstream);upstream.bodies=[];upstream.statuses=[503,503,200]
    state=State(cap_usd=1,output_cap=20,request_limit=4,record=tmp_path/'ledger.jsonl')
    proxy=create_server('127.0.0.1',0,f'http://127.0.0.1:{upstream.server_port}',state)
    threads=[threading.Thread(target=s.serve_forever,daemon=True) for s in (upstream,proxy)]
    for t in threads:t.start()
    body=json.dumps({'model':'deepseek-flash','max_tokens':20,'messages':[{'role':'user','content':'bounded request'}]}).encode()
    def post():
        req=urllib.request.Request(f'http://127.0.0.1:{proxy.server_port}/v1/chat/completions',data=body,headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req) as r:return r.status
        except urllib.error.HTTPError as r:return r.code
    try:
        assert post()==200 and state.request_count==3 and state.provider_retries==2
        rows=[json.loads(l) for l in state.record.read_text().splitlines()]
        assert [r['response_status'] for r in rows]==[503,503,200]
        assert all(r['reservation_released_usd']==0 for r in rows[:2])
        assert state.reserved_usd>=sum(r['reserved_upper_usd'] for r in rows[:2])
        assert len(set(upstream.bodies))==1
        assert post()==503 and state.request_count==4
        assert post()==429 and state.request_count==4  # Original request ceiling never resets.
    finally:
        for s in (proxy,upstream):s.shutdown();s.server_close()
        for t in threads:t.join(timeout=2)
