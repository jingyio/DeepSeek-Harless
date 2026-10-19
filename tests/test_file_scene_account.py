"""Free protocol diagnostics for the main-branch file integration."""
import json,os,subprocess,sys,threading,urllib.request
from pathlib import Path
from uuid import uuid4
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import pytest
from src.adapters.file_cost_gate import State,create_server
from src.adapters.file_web_task_budget import TaskBudgetRegistry

ROOT=Path(__file__).resolve().parents[1]


def test_acceptance_recognizes_only_the_host_owned_account_copy_root(monkeypatch):
    import importlib.util, tempfile
    sys.path.insert(0,str(ROOT/'scenarios/file-management'))
    from management_prepare import make_spec
    module_spec=importlib.util.spec_from_file_location('file_account_acceptance',ROOT/'scripts/validate-file-delivery.py')
    module=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(module)
    from common import save,sha
    with tempfile.TemporaryDirectory(dir=ROOT/'.local',prefix='file-acceptance-test-') as temporary:
        base=Path(temporary);account=base/'account-a';work=account/'management-copies/work';work.mkdir(parents=True)
        (work/'note.txt').write_text('synthetic source')
        task=make_spec(work,task_id='owned',objective='盘点文件',owner='a',workspace_id='a')
        taskfile=account/'task.json';save(taskfile,task)
        monkeypatch.setenv('HARLESS_MANAGEMENT_PRIVATE_ROOT',str(account))
        from management_tools import ManagementScene
        scene=ManagementScene(task,account/'delivery');scene.read_task()
        result=module.check(taskfile,sha(taskfile),account/'delivery',account/'acceptance',0,{'events':[],'receipt':None})
        assert result['passed'] is False and not result.get('fatal')
        assert (account/'acceptance/round-00/workspace/note.txt').read_text()=='synthetic source'
        # A valid marker and frozen task in another account still grant no access.
        monkeypatch.setenv('HARLESS_MANAGEMENT_PRIVATE_ROOT',str(base/'account-b'))
        with pytest.raises(ValueError,match='workspace outside'):
            module.check(taskfile,sha(taskfile),account/'delivery',account/'rejected',0,{'events':[],'receipt':None})


def test_account_libraries_have_separate_persistent_homes_and_no_cloud_calls():
    base=ROOT/'.local/account-isolation-tests'/uuid4().hex
    code="""import sys,json;sys.path.insert(0,'scenarios/file-management')
from management_web import default_config
from src.adapters.continuous_rsi import load_config,STATE_HOME
p=default_config(False);c=load_config(p)
print(json.dumps({'config':str(p),'state':c['state_root'],'workspaces':c['workspace_roots'],'home':str(STATE_HOME)}))"""
    rows=[]
    for name in ['alice','bob']:
        env={**os.environ,'HARLESS_MANAGEMENT_PRIVATE_ROOT':str(base/name)}
        value=json.loads(subprocess.check_output([sys.executable,'-c',code],cwd=ROOT,env=env,text=True))
        assert str(base/name) in value['state'] and all(str(base/name) in p for p in value['workspaces'])
        assert not list(Path(value['state']).glob('records/*.json'))
        rows.append(value)
    assert rows[0]['state']!=rows[1]['state']
    assert rows[0]['config']!=rows[1]['config']


def test_platform_task_recovery_preserves_unknown_usage_and_original_limits(tmp_path):
    directory=tmp_path/'.local';directory.mkdir();checkpoint=directory/'global.json'
    checkpoint.write_text(json.dumps({'request_count':0,'reserved_usd':0}))
    run=State(cap_usd=.5,output_cap=1000,checkpoint=checkpoint,record=None)
    registry=TaskBudgetRegistry(run_state=run,tasks_root=directory/'tasks',max_task_budget_usd=.25)
    task='a'*32;session='turn-'+task
    registry.register(task,session,.25);registry.activate(session)
    body=json.dumps({'model':'deepseek-flash','messages':[{'role':'user','content':'diagnostic'}],'max_tokens':20}).encode()
    request=registry.by_session[session].book(body)
    assert request is not None
    original_cost=run.reserved_usd
    resumed_run=State(cap_usd=.5,output_cap=1000,checkpoint=checkpoint,record=None)
    resumed=TaskBudgetRegistry(run_state=resumed_run,tasks_root=directory/'tasks',max_task_budget_usd=.25)
    value=resumed.register(task,session,.25,restore_ledger=True)
    assert value['upstream_requests']==1 and value['unknown_usage_requests']==1
    assert resumed_run.request_count==1 and resumed_run.reserved_usd==original_cost
    assert resumed.by_session[session].state.reserved_usd==original_cost
    with pytest.raises(ValueError):
        other=TaskBudgetRegistry(run_state=resumed_run,tasks_root=directory/'tasks',max_task_budget_usd=.25)
        other.register(task,session,.2,restore_ledger=True)


def test_additive_meter_header_transform_preserves_the_platform_route(tmp_path):
    seen=[]
    class Upstream(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            seen.append((self.path,self.headers.get('X-DeepSeek-Harness-Session-Id')))
            value=json.dumps({'choices':[{'message':{'content':'diagnostic'},'finish_reason':'stop'}],
                'usage':{'prompt_tokens':10,'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':10,'completion_tokens':1,'total_tokens':11}}).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(value)));self.end_headers();self.wfile.write(value)
        def log_message(self,*_):pass
    upstream=ThreadingHTTPServer(('127.0.0.1',0),Upstream)
    thread=threading.Thread(target=upstream.serve_forever,daemon=True);thread.start()
    state=State(cap_usd=.1,output_cap=1000,record=tmp_path/'diagnostic-ledger.jsonl')
    gate=create_server('127.0.0.1',0,f'http://127.0.0.1:{upstream.server_port}',state,
        forward_headers=lambda h:{**h,'X-DeepSeek-Harness-Session-Id':'turn-'+'b'*32})
    worker=threading.Thread(target=gate.serve_forever,daemon=True);worker.start()
    try:
        request=urllib.request.Request(f'http://127.0.0.1:{gate.server_port}/v1/chat/completions',
            data=json.dumps({'model':'deepseek-flash','messages':[{'role':'user','content':'diagnostic'}],'max_tokens':20}).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request) as response:assert response.status==200
        assert seen==[('/v1/chat/completions','turn-'+'b'*32)] and state.request_count==1
    finally:
        gate.shutdown();gate.server_close();upstream.shutdown();upstream.server_close();worker.join();thread.join()


def test_file_sdk_uses_existing_platform_model_port_and_settles_both_ledgers(tmp_path):
    """Actual nested HTTP meters, deterministic fake cloud; zero paid calls."""
    from src.adapters.deepseek_cost_gate import State as MainState, create_server as main_gate
    from src.adapters.web_task_budget import TaskBudgetRegistry as MainRegistry, create_control_server
    from src.adapters.management_platform_budget import PlatformBudget
    seen=[]
    class Cloud(BaseHTTPRequestHandler):
        def do_POST(self):
            payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            seen.append(payload['model'])
            value=json.dumps({'choices':[{'message':{'content':'protocol diagnostic'},'finish_reason':'stop'}],
                'usage':{'prompt_tokens':10,'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':10,'completion_tokens':1,'total_tokens':11}}).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(value)));self.end_headers();self.wfile.write(value)
        def log_message(self,*_):pass
    servers=[];threads=[]
    def start(server):
        servers.append(server);t=threading.Thread(target=server.serve_forever,daemon=True);threads.append(t);t.start();return server
    try:
        cloud=start(ThreadingHTTPServer(('127.0.0.1',0),Cloud))
        main=MainState(cap_usd=.5,output_cap=1000,record=tmp_path/'main-ledger.jsonl')
        registry=MainRegistry(run_state=main,tasks_root=tmp_path/'.local/tasks',max_task_budget_usd=.25)
        control=start(create_control_server('127.0.0.1',0,registry,control_token='diagnostic-token-not-a-secret-0001'))
        meter=start(main_gate('127.0.0.1',0,f'http://127.0.0.1:{cloud.server_port}',main,
            state_selector=registry.state_for,allowed_models={'deepseek-flash'}))
        policy={'endpoint':f'http://127.0.0.1:{meter.server_port}/v1',
            'control_endpoint':f'http://127.0.0.1:{control.server_port}','control_token':'diagnostic-token-not-a-secret-0001'}
        route=PlatformBudget(policy,'diagnostic-session','deepseek-flash',.25,tmp_path,False)
        local=State(cap_usd=.25,output_cap=1000,record=tmp_path/'local-ledger.jsonl')
        inner=start(create_server('127.0.0.1',0,route.upstream,local,
            forward_headers=route.headers,forward_model_alias=False))
        req=urllib.request.Request(f'http://127.0.0.1:{inner.server_port}/v1/chat/completions',
            data=json.dumps({'model':'deepseek-flash','messages':[{'role':'user','content':'diagnostic'}],'max_tokens':20}).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req) as response:assert response.status==200
        assert seen==['deepseek-flash']
        assert main.request_count==local.request_count==1
        assert main.reserved_usd==local.reserved_usd
        route.close()
        assert (tmp_path/'platform-accounting.json').exists()
    finally:
        for server in reversed(servers):server.shutdown();server.server_close()
        for thread in threads:thread.join()
