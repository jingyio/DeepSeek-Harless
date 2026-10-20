"""Free protocol diagnostics for the main-branch file integration."""
import json,os,subprocess,sys,threading,urllib.request
from pathlib import Path
from uuid import uuid4
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import pytest
from src.adapters.file_cost_gate import State,create_server
from src.adapters.file_web_task_budget import TaskBudgetRegistry

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def scoped_file_platform(tmp_path):
    """Real member gateway + route broker + both meters; synthetic HTTP cloud."""
    import base64,hashlib,hmac,shutil
    from concurrent.futures import ThreadPoolExecutor
    from types import SimpleNamespace
    from src.adapters.deepseek_cost_gate import State as MainState,create_server as main_gate
    from src.adapters.web_task_budget import TaskBudgetRegistry as MainRegistry,create_control_server
    node=shutil.which('node')
    if not node:pytest.skip('Node is required for the actual scoped gateway diagnostic')
    seen=[];servers=[];threads=[];barriers=[]
    class Cloud(BaseHTTPRequestHandler):
        def do_POST(self):
            payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            seen.append(payload['messages'][0]['content'])
            if barriers:barriers[0].wait(timeout=10)
            value=json.dumps({'choices':[{'message':{'content':'protocol diagnostic'},'finish_reason':'stop'}],
                'usage':{'prompt_tokens':10,'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':10,'completion_tokens':1,'total_tokens':11}}).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(value)));self.end_headers();self.wfile.write(value)
        def log_message(self,*_):pass
    def start(server):
        servers.append(server);t=threading.Thread(target=server.serve_forever,daemon=True);threads.append(t);t.start();return server
    token='diagnostic-control-token-not-a-secret-001';admin='diagnostic-admin-not-a-secret'
    cloud=start(ThreadingHTTPServer(('127.0.0.1',0),Cloud))
    main=MainState(cap_usd=.5,output_cap=1000,record=tmp_path/'main-ledger.jsonl')
    registry=MainRegistry(run_state=main,tasks_root=tmp_path/'.local/tasks',max_task_budget_usd=.25)
    control=start(create_control_server('127.0.0.1',0,registry,control_token=token))
    meter=start(main_gate('127.0.0.1',0,f'http://127.0.0.1:{cloud.server_port}',main,
        state_selector=registry.state_for,allowed_models={'deepseek-flash'}))
    db=tmp_path/'accounts';db.mkdir()
    (db/'accounts.json').write_text(json.dumps({'version':1,'users':[{'id':'alice'},{'id':'bob'}],
        'invites':[],'sessions':[],'ownerClaim':None}))
    config={'dataDir':str(db),'membersDir':str(tmp_path/'members'),'publicOrigin':'https://app.example.test',
        'adminToken':admin,'apiKey':'synthetic-cloud-key','scopedBudgetPort':1,'upstreamControlPort':control.server_port,
        'memberPolicy':{'control_token':token,'budget_usd':.25}}
    source="""
import {once} from 'node:events';
import {createGateway} from 'GATEWAY_URI';
import {startBroker} from 'BROKER_URI';
const config=JSON.parse(process.argv[2]),meter=Number(process.argv[3]);
const broker=startBroker({port:0,target:'http://127.0.0.1:'+meter+'/v1',controlToken:config.memberPolicy.control_token});
await once(broker,'listening');config.upstreamBrokerPort=broker.address().port;
const gateway=createGateway(config);
gateway.scopedBudget.listen(0,'127.0.0.1');await once(gateway.scopedBudget,'listening');
console.log(JSON.stringify({base:'http://127.0.0.1:'+gateway.scopedBudget.address().port}));
process.stdin.resume();process.stdin.on('end',()=>{gateway.close();broker.close();});
"""
    fixture=tmp_path/'scoped-file-platform.mjs'
    fixture.write_text(source.replace('GATEWAY_URI',(ROOT/'scripts/harless_gateway.mjs').as_uri()).replace(
        'BROKER_URI',(ROOT/'scripts/web_budget_broker.mjs').as_uri()),encoding='utf-8')
    process=subprocess.Popen([node,'--experimental-strip-types',str(fixture),json.dumps(config),str(meter.server_port)],
        cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            line=pool.submit(process.stdout.readline).result(timeout=20)
        assert line,process.stderr.read()
        base=json.loads(line)['base']
        def delegated(user,purpose):return base64.urlsafe_b64encode(hmac.new(admin.encode(),(purpose+':'+user).encode(),hashlib.sha256).digest()).decode().rstrip('=')
        def policy(user):return {'endpoint':base+'/v1','control_endpoint':base,'budget_broker_endpoint':base,
            'budget_task_prefix':hashlib.sha256(user.encode()).hexdigest()[:8],'control_token':delegated(user,'control')}
        def request(path,payload,*,user='alice',session=None):
            headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+delegated(user,'model'),
                'X-DeepSeek-Harness-Session-Id':session} if session else {'X-SSS-Control-Token':delegated(user,'control')})}
            with urllib.request.urlopen(urllib.request.Request(base+path,data=json.dumps(payload).encode(),headers=headers),timeout=15) as response:
                return json.load(response)
        yield SimpleNamespace(start=start,seen=seen,barriers=barriers,main=main,registry=registry,
            policy=policy,request=request,delegated=delegated,tmp=tmp_path)
    finally:
        process.stdin.close()
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        process.stdout.close();process.stderr.close()
        for server in reversed(servers):server.shutdown();server.server_close()
        for thread in threads:thread.join(timeout=10)


def test_web_file_profile_inherits_uncapped_policy_without_resetting_existing_state():
    base=ROOT/'.local/account-isolation-tests'/uuid4().hex
    base.mkdir(parents=True)
    policy=base/'policy.json';policy.write_text(json.dumps({k:None for k in ['budget_usd','run_budget_usd','request_limit','max_output_tokens']}))
    code="""import sys,json,os;sys.path.insert(0,'scenarios/file-management')
from management_web import default_config
from src.adapters.continuous_rsi import load_config,read
from src.motif_core.offline.experience_registry import durable
from pathlib import Path
os.environ.pop('SSS_WEB_POLICY',None)
old=default_config(False);before=load_config(old);pool=Path(before['state_root'])/'pool.json'
durable(pool,{'runs':{'old-task':{'status':'settled','cap_usd':5,'cost_usd':0.02,'role':'ordinary'}}})
os.environ['SSS_WEB_POLICY']=sys.argv[1]
new=default_config(False);after=load_config(new)
assert old!=new and before['state_root']==after['state_root']
assert all(v is None for v in after['limits'].values())
assert after['series_cap_usd'] is None and after['learning_cap_usd'] is None
assert read(pool)['runs']['old-task']['cost_usd']==0.02
print('uncapped-policy-and-original-accounting-preserved')"""
    env={**os.environ,'HARLESS_MANAGEMENT_PRIVATE_ROOT':str(base/'account')}
    assert 'uncapped-policy-and-original-accounting-preserved' in subprocess.check_output([sys.executable,'-c',code,str(policy)],cwd=ROOT,env=env,text=True)


def test_unlimited_platform_meter_is_still_required_for_semantic_calls(monkeypatch):
    from src.adapters.dsh_client import require_budget_gate
    monkeypatch.setenv('DEEPSEEK_BASE_URL','http://127.0.0.1:37724/v1')
    monkeypatch.setenv('SSS_BUDGET_GATE_ACTIVE','1');monkeypatch.setenv('SSS_BUDGET_LEDGER','private-ledger.jsonl')
    monkeypatch.setenv('SSS_BUDGET_CAP_USD','null');require_budget_gate()
    monkeypatch.delenv('SSS_BUDGET_LEDGER')
    with pytest.raises(ValueError):require_budget_gate()


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


def test_member_file_routes_concurrently_through_real_scoped_gateway_and_broker(scoped_file_platform):
    from concurrent.futures import ThreadPoolExecutor
    from src.adapters.management_platform_budget import PlatformBudget
    f=scoped_file_platform
    payload={'model':'deepseek-flash','messages':[{'role':'user','content':'unbound'}],'max_tokens':20}
    with pytest.raises(urllib.error.HTTPError) as denied:
        f.request('/v1/chat/completions',payload,session='session-'+str(uuid4()))
    assert denied.value.code==403 and f.main.request_count==0
    routes=[];locals=[];inners=[]
    for label in ('A','B'):
        out=f.tmp/label;out.mkdir()
        route=PlatformBudget(f.policy('alice'),'file-'+label,'deepseek-flash',.25,out,False);routes.append(route)
        local=State(cap_usd=.25,output_cap=1000,record=out/'local-ledger.jsonl');locals.append(local)
        inners.append(f.start(create_server('127.0.0.1',0,route.upstream,local,
            forward_headers=route.headers,forward_model_alias=False)))
    def call(index,label):
        request=urllib.request.Request(f'http://127.0.0.1:{inners[index].server_port}/v1/chat/completions',
            data=json.dumps({**payload,'messages':[{'role':'user','content':label}]}).encode(),
            headers={'Content-Type':'application/json','Authorization':'Bearer '+f.delegated('alice','model')})
        with urllib.request.urlopen(request,timeout=15) as response:return response.status
    f.barriers.append(threading.Barrier(2))
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(call,index,label) for index,label in enumerate(('A','B'))]
        assert [future.result(timeout=20) for future in futures]==[200,200]
    f.barriers.clear()
    assert sorted(f.seen)==['A','B'] and f.main.request_count==2
    assert routes[0].session!=routes[1].session
    sessions=[route.headers({})['X-DeepSeek-Harness-Session-Id'] for route in routes]
    assert sessions[0]!=sessions[1] and all(session.startswith('session-') for session in sessions)
    for route,local in zip(routes,locals):
        assert f.registry.stats(route.session)['upstream_requests']==local.request_count==1
    with pytest.raises(urllib.error.HTTPError) as foreign:
        f.request('/v1/chat/completions',payload,user='bob',session=sessions[0])
    assert foreign.value.code==403
    with pytest.raises(urllib.error.HTTPError) as wrong_pair:
        f.request('/unbind',{'session_id':sessions[0],'budget_session_id':routes[1].session})
    assert wrong_pair.value.code==409
    routes[0].close()
    with pytest.raises(urllib.error.HTTPError) as closed:
        f.request('/v1/chat/completions',payload,session=sessions[0])
    assert closed.value.code==403
    assert call(1,'B-still-active')==200
    routes[1].close()
    assert f.main.request_count==3 and sorted(f.seen)==['A','B','B-still-active']
    for route in routes:
        counters=f.registry.stats(route.session)
        assert not counters['active'] and counters['cancelled'] and counters['usage_complete']
        assert (route.out/'platform-accounting.json').exists()
    assert f.main.reserved_usd==sum(local.reserved_usd for local in locals)


def test_member_file_bind_failure_cancels_only_new_budget_without_model_request(scoped_file_platform,monkeypatch):
    from uuid import UUID
    from src.adapters import management_platform_budget as platform
    f=scoped_file_platform;out=f.tmp/'original';out.mkdir()
    original=platform.PlatformBudget(f.policy('alice'),'original','deepseek-flash',.25,out,False)
    route=original.headers({})['X-DeepSeek-Harness-Session-Id']
    # A collision with another account must be rejected by the real gateway;
    # setup failure must not return an endpoint that could issue a model call.
    monkeypatch.setattr(platform,'uuid4',lambda:UUID(route.removeprefix('session-')))
    rejected=f.tmp/'rejected';rejected.mkdir()
    with pytest.raises(urllib.error.HTTPError) as denied:
        platform.PlatformBudget(f.policy('bob'),'rejected','deepseek-flash',.25,rejected,False)
    assert denied.value.code==403 and f.main.request_count==0 and f.seen==[]
    failed=[value for key,value in f.registry.by_session.items() if key!=original.session]
    assert len(failed)==1
    counters=f.registry.stats(failed[0].session_id)
    assert counters['cancelled'] and not counters['active'] and counters['upstream_requests']==0
    assert f.registry.stats(original.session)['active']
    original.close()


def test_member_file_committed_bind_with_lost_reply_cleans_the_exact_pair(scoped_file_platform,monkeypatch):
    from uuid import UUID
    from src.adapters import management_platform_budget as platform
    f=scoped_file_platform;out=f.tmp/'lost-reply';out.mkdir()
    call=platform.PlatformBudget.call;seen=[];bound={}
    lost=json.JSONDecodeError('Synthetic committed bind reply was incomplete','{',1)
    def lose_bind_reply(self,path,value,**kwargs):
        seen.append((path,dict(value)))
        result=call(self,path,value,**kwargs)
        if path=='/bind':bound.update(value);raise lost
        return result
    with monkeypatch.context() as patch:
        patch.setattr(platform.PlatformBudget,'call',lose_bind_reply)
        with pytest.raises(json.JSONDecodeError) as failed:
            platform.PlatformBudget(f.policy('alice'),'lost-reply','deepseek-flash',.25,out,False)
    assert failed.value is lost
    assert [path for path,_ in seen]==['/tasks/register','/tasks/activate','/bind','/unbind','/tasks/cancel']
    assert seen[2][1]==seen[3][1]==bound
    assert f.registry.stats(bound['budget_session_id'])['cancelled']
    payload={'model':'deepseek-flash','messages':[{'role':'user','content':'must stay unbound'}],'max_tokens':20}
    with pytest.raises(urllib.error.HTTPError) as denied:
        f.request('/v1/chat/completions',payload,session=bound['session_id'])
    assert denied.value.code==403 and f.main.request_count==0 and f.seen==[]
    # Both gateway ownership and broker mapping must be gone. Another account
    # can now bind this synthetic ID to its own independently registered budget.
    monkeypatch.setattr(platform,'uuid4',lambda:UUID(bound['session_id'].removeprefix('session-')))
    other=f.tmp/'new-owner';other.mkdir()
    replacement=platform.PlatformBudget(f.policy('bob'),'new-owner','deepseek-flash',.25,other,False)
    replacement.close()


@pytest.mark.parametrize('phase',['setup','close'])
def test_member_file_unbind_failure_still_cancels_without_hiding_setup_error(scoped_file_platform,monkeypatch,phase):
    from src.adapters import management_platform_budget as platform
    f=scoped_file_platform;out=f.tmp/phase;out.mkdir()
    call=platform.PlatformBudget.call;seen=[];bound={}
    lost=json.JSONDecodeError('Synthetic bind reply lost','{',1)
    unbind=ConnectionError('Synthetic unbind unavailable')
    def fail_cleanup(self,path,value,**kwargs):
        seen.append(path)
        if path=='/unbind':raise unbind
        result=call(self,path,value,**kwargs)
        if path=='/bind':
            bound.update(value)
            if phase=='setup':raise lost
        return result
    with monkeypatch.context() as patch:
        patch.setattr(platform.PlatformBudget,'call',fail_cleanup)
        if phase=='setup':
            with pytest.raises(json.JSONDecodeError) as failed:
                platform.PlatformBudget(f.policy('alice'),phase,'deepseek-flash',.25,out,False)
            assert failed.value is lost and failed.value.platform_cleanup_failures==(unbind,)
        else:
            route=platform.PlatformBudget(f.policy('alice'),phase,'deepseek-flash',.25,out,False)
            with pytest.raises(ConnectionError) as failed:route.close()
            assert failed.value is unbind
            assert (out/'platform-accounting.json').exists()
    assert seen[-2:]==['/unbind','/tasks/cancel']
    counters=f.registry.stats(bound['budget_session_id'])
    assert counters['cancelled'] and not counters['active'] and counters['upstream_requests']==0
    assert f.main.request_count==0 and f.seen==[]
    # The diagnostic never changes the binding pair or retries a model request.
    f.request('/unbind',bound)
