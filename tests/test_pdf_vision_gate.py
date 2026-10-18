import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.error
import urllib.request

from src.adapters.deepseek_cost_gate import State, create_server
from src.adapters.web_task_budget import TaskBudgetRegistry


def test_pdf_vision_gate_ownership_model_payload_and_accounting(tmp_path):
    received = []
    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_POST(self):
            received.append((self.path,json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
            raw=json.dumps({'choices':[{'finish_reason':'stop','message':{'content':'visible chart'}}],
                'usage':{'prompt_tokens':10,'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':10,
                         'completion_tokens':4,'total_tokens':14}}).encode()
            self.send_response(200);self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    upstream=ThreadingHTTPServer(('127.0.0.1',0),Upstream)
    state=State(cap_usd=None,output_cap=None,record=tmp_path/'.local/ledger.jsonl')
    registry=TaskBudgetRegistry(run_state=state,tasks_root=tmp_path/'.local/tasks')
    registry.register('a'*32,'owned-pro-task',None,model='deepseek-v4-pro')
    gate=create_server('127.0.0.1',0,f'http://127.0.0.1:{upstream.server_port}',state,
        state_selector=registry.state_for,allow_vision=True,allowed_models={'deepseek-flash','deepseek-v4-pro'})
    for server in (upstream,gate): threading.Thread(target=server.serve_forever,daemon=True).start()
    payload={'model':'deepseek-flash','stream':False,'thinking':{'type':'disabled'},'response_format':{'type':'json_object'},
             'messages':[{'role':'user','content':[{'type':'text','text':'read Figure 1'},
                {'type':'image_url','image_url':{'url':'data:image/jpeg;base64,YWJj'}}]}]}
    def send(body,session='owned-pro-task',path='/v1/vision/chat/completions'):
        req=urllib.request.Request(f'http://127.0.0.1:{gate.server_port}'+path,
            data=json.dumps(body).encode(),headers={'X-DeepSeek-Harness-Session-Id':session,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=5) as response:return response.status,response.read()
        except urllib.error.HTTPError as error:return error.code,error.read()
    try:
        assert send(payload)[0]==403
        registry.activate('owned-pro-task')
        assert send(payload,session='foreign-task')[0]==403
        assert send(payload,path='/v1/chat/completions')[0]==400  # Normal Pro pin remains immutable.
        assert send({**payload,'model':'deepseek-v4-pro'})[0]==400
        assert send({**payload,'tools':[]})[0]==400
        invalid=json.loads(json.dumps(payload));invalid['messages'][0]['content'][1]['image_url']['url']='https://private/image'
        assert send(invalid)[0]==400
        assert send({**payload,'messages':[None]})[0]==400
        assert not received and state.request_count==0
        assert send(payload)[0]==200
        assert received[0][0]=='/v1/chat/completions' and received[0][1]['model']=='deepseek-flash'
        assert registry.stats('owned-pro-task')['upstream_requests']==state.request_count==1
        ledger=state.record.read_text()
        assert 'pdf_vision' in ledger and 'deepseek-flash' in ledger and 'YWJj' not in ledger
        registry.cancel('owned-pro-task')
        assert send(payload)[0]==403
        assert state.request_count==1
    finally:
        for server in (gate,upstream):server.shutdown();server.server_close()
