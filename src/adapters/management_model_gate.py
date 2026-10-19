"""Account-local durable admission; forwards through the existing platform meter.

This process owns no Agent loop or credentials store. The parent issues immutable
task routes. Both local job and upstream account/global limits apply to each HTTP.
"""
import hashlib,hmac,json,os,re,sys,threading,time
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from src.adapters.file_cost_gate import State,create_server
from src.adapters.operation_budget import OperationBudget
from src.adapters.continuous_rsi import private


def main():
    config=json.loads(sys.stdin.readline())
    root=private(config['routes']);root.mkdir(parents=True,exist_ok=True,mode=0o700)
    upstream=urlsplit(config['upstream'])
    if upstream.scheme!='http' or upstream.hostname!='127.0.0.1' or upstream.path not in ('','/v1'):
        raise ValueError('management gate must use the original loopback platform meter')
    credential=os.environ.get('DEEPSEEK_API_KEY','sss-mock-only')
    cache={}
    def route(headers):
        auth=next((v for k,v in headers.items() if k.lower()=='authorization'),'')
        if not hmac.compare_digest(auth,'Bearer '+credential):raise PermissionError('account model authority required')
        session=next((v for k,v in headers.items() if k.lower()=='x-deepseek-harness-session-id'),'')
        if not re.fullmatch(r'(?:session-[a-f0-9-]{36}|sss-[a-f0-9]{32})',session):raise PermissionError('native session required')
        p=root/(session+'.json')
        if p.is_symlink():raise PermissionError('route symlink refused')
        value=json.loads(p.read_text());job=private(value['job_file']);ledger=private(value['ledger_file'])
        if job.parent!=ledger.parent or ledger.name!='ledger.jsonl' or job.parent.name!=value['task_id']:
            raise PermissionError('original task route binding differs')
        return value,job,ledger
    def select(headers):
        value,job,ledger=route(headers)
        key=(str(job),hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest())
        if key not in cache:cache[key]=OperationBudget(job,ledger)
        return cache[key]
    def forward(headers):
        value,_,_=route(headers)
        if not config['broker']:
            headers={k:v for k,v in headers.items() if k.lower()!='x-deepseek-harness-session-id'}
            headers['X-DeepSeek-Harness-Session-Id']=value['budget_session_id']
        return headers
    server=create_server('127.0.0.1',0,upstream.scheme+'://'+upstream.netloc,
        State(cap_usd=0,output_cap=4000,record=root/'refused-requests.jsonl'),state_selector=select,forward_headers=forward,allow_files=False)
    def supervise():
        while True:
            time.sleep(2)
            try:os.kill(config['owner_pid'],0)
            except OSError:server.shutdown();return
    threading.Thread(target=supervise,daemon=True).start()
    print(json.dumps({'endpoint':f'http://127.0.0.1:{server.server_address[1]}/v1'}),flush=True)
    server.serve_forever()

if __name__=='__main__':main()
