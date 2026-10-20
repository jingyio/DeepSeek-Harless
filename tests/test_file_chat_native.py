"""No-paid File -> Chat regression against the installed native Web Harness.

Only the File worker and completion HTTP response are deterministic fixtures.
Native sessions, presets, projections, both host plugins and RPC are real.
"""
import http.cookiejar
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import threading
import time
import urllib.request
from uuid import uuid4
import pytest

ROOT=Path(__file__).resolve().parents[1]


def test_native_file_chat_file_keeps_started_parent_preset_and_private_copy():
    node=shutil.which('node')
    if not node:pytest.skip('Native Harness diagnostic requires Node')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    seen=[];answers=[];first_completion=threading.Event();release_completion=threading.Event()
    class Diagnostic(BaseHTTPRequestHandler):
        def do_POST(self):
            value=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path=='/v1/chat/completions':
                seen.append(value)
                if len(seen)==1:
                    first_completion.set()
                    assert release_completion.wait(15),'Native diagnostic did not release its first Chat completion'
                # The user never supplies this value. A later File request
                # can recall it only from the real completed Chat answer.
                answer='你好，本轮助手代号是 CM-'+uuid4().hex[:8];answers.append(answer)
                rows=[{'choices':[{'index':0,'delta':{'content':answer},'finish_reason':None}]},
                    {'choices':[{'index':0,'delta':{},'finish_reason':'stop'}],
                     'usage':{'prompt_tokens':10,'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':10,'completion_tokens':2,'total_tokens':12}}]
                raw=(''.join('data: '+json.dumps(row,ensure_ascii=False)+'\n\n' for row in rows)+'data: [DONE]\n\n').encode()
                self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            else:
                raw=json.dumps({'stats':{'upstream_requests':0,'estimated_cost_usd':0,'usage_complete':True}}).encode()
                self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def do_GET(self):
            raw=b'{"stats":{"upstream_requests":0,"estimated_cost_usd":0,"usage_complete":true}}'
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def log_message(self,*_):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Diagnostic)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    endpoint=f'http://127.0.0.1:{server.server_port}'
    # A member's persisted File home is inside policy.output. Keep this fixture
    # beneath the real checkout's private root for the normal path validation.
    output=ROOT/'.local/native-file-chat-tests'/uuid4().hex;output.mkdir(parents=True)
    try:
        presets=output/'presets/sss-task';presets.mkdir(parents=True)
        (presets/'preset.yml').write_text(json.dumps({'name':'Native diagnostic Chat'}))
        (presets/'agent.cordis.yml').write_text('[]')
        policy={'output':str(output),'endpoint':endpoint+'/v1','control_endpoint':endpoint,'budget_broker_endpoint':endpoint,
            'control_token':'native-diagnostic-control-not-secret','budget_task_prefix':'abcdef12','budget_usd':None,
            'max_output_tokens':1000,'mode':'baseline','provider_mode':'mock','allowed_tools':['diagnostic-file-host'],
            'capability_profile':'new-scene','comparison_scenes':['paper-proofreading'],
            'scenes':[{'id':'new-scene','label':'Chat','preset':'sss-task','adapter':'workspace','allowed_tools':[],'mcp_rows':[]},
                {'id':'files','label':'Files','preset':'sss-files','adapter':'files','allowed_tools':['mcp__file_management__read_task'],'mcp_rows':[]},
                {'id':'paper-proofreading','label':'Paper','preset':'sss-paper','adapter':'workspace','allowed_tools':[],'mcp_rows':[]}]}
        (output/'policy.json').write_text(json.dumps(policy))
        task_plugin=output/'native-tasks-fixture.mjs'
        task_plugin.write_text("export {inject,name,apply} from '"+(ROOT/'src/adapters/dsh_web_tasks.ts').as_uri()+"';",encoding='utf-8')
        plugin=output/'native-file-fixture.mjs'
        plugin.write_text("""
import {EventEmitter} from 'node:events';
import {readFileSync,appendFileSync} from 'node:fs';
import {Session} from '@deepseek-ai/dsh-session';
import {createAssistantMessage,createUserMessage} from '@deepseek-ai/dsh-llm';
import {inject as taskInject} from 'TASKS_URI';
import {installFileScene} from 'FILE_URI';
export const inject=taskInject,name='native-file-diagnostic';
export function apply(ctx){
 const agents=new Map();ctx.on('agent/created',({agent})=>agents.set(agent.session.id,agent));
 ctx.effect(()=>ctx.connection.fetch.register({path:'/api/diagnostic/open',methods:['POST'],requestBody:'buffered',async fetch(request){
  const rejected=ctx.connection.requestRejection(request);if(rejected)return new Response('Unauthorized',{status:rejected});
  const {sessionId}=await request.json(),agent=agents.get(sessionId);if(!agent)return new Response('Not found',{status:404});
  const turn=1+Math.max(0,...agent.session.snapshotEvents().filter(e=>e.type==='turn/start').map(e=>e.data.turn));
  agent.session.append('turn/start',{turn});return Response.json({sessionId,turn});
 }}),'diagnostic-unmanaged-turn');
 ctx.on('agent-preset/selected',(sessionId,agentPreset)=>appendFileSync(process.env.SSS_WEB_POLICY+'.preset-events',JSON.stringify({sessionId,agentPreset})+'\\n'));
 installFileScene(ctx,()=>{
  const child=new EventEmitter();child.stdout=new EventEmitter();child.stdout.setEncoding=()=>{};child.stderr=new EventEmitter();
  child.kill=()=>child.emit('close',143);
  child.stdin={end(raw){const q=JSON.parse(raw),input=JSON.parse(readFileSync(q.request_file));
   appendFileSync(process.env.SSS_WEB_POLICY+'.file-requests',JSON.stringify(input)+'\\n');
   setImmediate(()=>{
    const sdk=new Session('diagnostic-sdk'),source={provider:'deepseek-official',model:'deepseek-flash'};
    sdk.append('step/start',{turn:1,step:1});
    sdk.append('assistant/message',{turn:1,step:1,stream:[],message:createAssistantMessage({source,content:[
     {type:'text',text:'DIAGNOSTIC_INTERNAL_PARSE_PROGRESS'},
     {type:'tool-call',id:'diagnostic-read',name:'mcp__file_management__read_task',arguments:'{}'}]})},{surfaceOp:'append'});
    const call=sdk.append('tool/call',{turn:1,step:1,callId:'diagnostic-read',name:'mcp__file_management__read_task',arguments:'{}'});
    sdk.append('tool/result',{turn:1,step:1,message:createUserMessage({source:{kind:'tool',callId:'diagnostic-read'},
     content:[{type:'tool-result',toolCallId:'diagnostic-read',isError:false,content:[{type:'text',text:'DIAGNOSTIC_INTERNAL_EXTRACTED_BYTES'}]}]})},
     {surfaceOp:'append',sourceEventSeqs:[call.seq]});
    sdk.append('step/end',{turn:1,step:1});sdk.append('step/start',{turn:1,step:2});
    sdk.append('assistant/message',{turn:1,step:2,stream:[],message:createAssistantMessage({source,content:[{type:'text',text:'File 公开结果 '+input.task_id}]})},{surfaceOp:'append'});
    sdk.append('step/end',{turn:1,step:2});
    for(const event of sdk.snapshotEvents())child.stdout.emit('data',JSON.stringify({kind:'event',event})+'\\n');
    child.stdout.emit('data',JSON.stringify({kind:'result',status:'completed',metrics:{acceptance_passed:true,upstream_requests:0,budget_accounted_usd:0},artifacts:[]})+'\\n');child.emit('close',0);
   });
  }};return child;
 });
}
""".replace('TASKS_URI',(ROOT/'src/adapters/dsh_web_tasks.ts').as_uri()).replace('FILE_URI',(ROOT/'src/adapters/harless_file_scene.ts').as_uri()),encoding='utf-8')
        patch=[{'id':name,'disabled':True} for name in ('llm-deepseek','llm-pi-ai','session-title-llm','llm-retry','compaction-basic','command-compact','session-log-deepseek','goal','goal-round-driver')]
        patch += [{'id':'web-runtime','config':{'openBrowser':False,'printUrl':True,'surfaceContext':False,'trustedHosts':[]}},
            {'id':'agent-presets','config':{'default':'sss-task','includeShippedRoot':False,'includeUserRoot':False,'roots':[{'path':str(output/'presets'),'trust':'system'}]}},
            {'insert':[{'id':'native-task-diagnostic','name':task_plugin.as_uri()},
                {'id':'native-file-chat-diagnostic','name':plugin.as_uri()}]}]
        patch_file=output/'host.patch.json';patch_file.write_text(json.dumps(patch))
        env={**os.environ,'DSH_HOME':str(output/'dsh'),'SSS_WEB_POLICY':str(output/'policy.json'),'DEEPSEEK_API_KEY':'diagnostic-not-a-provider-key'}
        log=(output/'native.log').open('w',encoding='utf-8')
        process=subprocess.Popen([node,str(ROOT/'node_modules/@deepseek-ai/dsh/lib/bin.js'),'--profile','web','--patch',str(patch_file),
            '--host','127.0.0.1','--port',str(port),'--no-open'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        try:
            deadline=time.monotonic()+40;launch=None
            while time.monotonic()<deadline:
                text=(output/'native.log').read_text(encoding='utf-8')
                match=re.search(r'http://127\.0\.0\.1:'+str(port)+r'/\?token=[A-Za-z0-9_-]+',text)
                if match:launch=match[0];break
                if process.poll() is not None:raise AssertionError('Native fixture failed:\n'+text[-8000:])
                time.sleep(.1)
            assert launch,'Native fixture startup timed out'
            client=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            client.open(launch,timeout=10).close();base=f'http://127.0.0.1:{port}'
            def request(path,value=None):
                with client.open(urllib.request.Request(base+path,data=None if value is None else json.dumps(value).encode(),
                    headers={'Origin':base,'Content-Type':'application/json'}),timeout=20) as response:return json.load(response)
            def rpc(method,value):
                result=request('/api/'+method,{'type':'client-request','rpcId':str(uuid4()),'method':method,'payload':{'args':{'request':value}}})['result']
                assert result['ok'],result
                return result['value']
            def new_session():
                session=rpc('session/create',{})['sessionId']
                rpc('session/selectModel',{'sessionId':session,'provider':'deepseek-official','model':'deepseek-flash','reasoningEffort':'off'})
                return session
            session=new_session();foreign=new_session()
            def send(text,target=session,request_id=None):return rpc('session/prompt',{'sessionId':target,'requestId':request_id or str(uuid4()),'mode':'queue','content':[{'type':'text','text':text}]})
            def settled(path):
                deadline=time.monotonic()+25
                while time.monotonic()<deadline:
                    value=request(path)
                    if value.get('status')=='completed':return value
                    time.sleep(.1)
                raise AssertionError('Native diagnostic did not settle: '+json.dumps(value))
            send('/file inspect own copy')
            settled('/api/harless/file-scene?session_id='+session+'&turn=1')
            first=json.loads((output/'policy.json.file-requests').read_text().splitlines()[0])
            preset_log=output/'policy.json.preset-events'
            parent_presets_before=[json.loads(line) for line in preset_log.read_text().splitlines() if json.loads(line)['sessionId']==session] if preset_log.exists() else []
            # Before the fix this real native RPC returns agent-preset/locked.
            greeting_id=str(uuid4());greeting=send('你好',request_id=greeting_id)
            assert greeting.get('comparison_id'),'Started File parent must continue through the existing private Chat route'
            assert first_completion.wait(10)
            try:
                retry=send('你好',request_id=greeting_id)
                assert retry['comparison_id']==greeting['comparison_id'],'An active Chat retry is still idempotent'
            finally:release_completion.set()
            view=settled('/api/harless/comparisons?session_id='+session+'&id='+greeting['comparison_id'])
            assert view['presentation']=='single' and view['lanes']['baseline']['answer'].startswith('你好')
            assert view['lanes']['baseline']['session_id']!=session
            own_answer=view['lanes']['baseline']['answer']
            send('/file inspect another copy',foreign)
            settled('/api/harless/file-scene?session_id='+foreign+'&turn=1')
            other=send('你好，请生成本轮代号',foreign)
            other_view=settled('/api/harless/comparisons?session_id='+foreign+'&id='+other['comparison_id'])
            other_answer=other_view['lanes']['baseline']['answer']
            assert own_answer!=other_answer and own_answer in answers and other_answer in answers
            recall='/file 请引用刚才助手生成的代号，继续使用本会话副本'
            assert 'CM-' not in recall
            send(recall)
            lines=(output/'policy.json.file-requests').read_text().splitlines()
            assert len(lines)==3
            other_file=json.loads(lines[1]);second=json.loads(lines[2])
            assert first['workspace_id']==second['workspace_id']!=other_file['workspace_id']
            assert any(row['text']=='你好' for row in second['prior_context'])
            assert any(row['role']=='assistant' and row['text']==own_answer for row in second['prior_context'])
            assert any(row['role']=='assistant' and row['text']=='File 公开结果 '+first['task_id'] for row in second['prior_context'])
            assert 'DIAGNOSTIC_INTERNAL_' not in json.dumps(second['prior_context'],ensure_ascii=False)
            assert other_answer not in json.dumps(second['prior_context'],ensure_ascii=False)
            settled('/api/harless/file-scene?session_id='+session+'&turn=3')
            next_greeting=send('你好，再聊一句')
            next_view=settled('/api/harless/comparisons?session_id='+session+'&id='+next_greeting['comparison_id'])
            next_answer=next_view['lanes']['baseline']['answer']
            send('/file 引用刚才两个助手代号，不要从其他会话取值')
            settled('/api/harless/file-scene?session_id='+session+'&turn=5')
            latest=json.loads((output/'policy.json.file-requests').read_text().splitlines()[-1])
            assert latest['workspace_id']==first['workspace_id']
            assert [row['text'] for row in latest['prior_context'] if row['role']=='assistant' and row['text'].startswith('你好')]==[own_answer,next_answer]
            assert 'DIAGNOSTIC_INTERNAL_' not in json.dumps(latest['prior_context'],ensure_ascii=False)
            assert len(seen)==3,'Only three local synthetic Chat completions; File fixture never calls a provider'
            # An unmanaged open native turn has no ordinary host Task. It
            # must still block both routes without invoking either fixture.
            busy=new_session();request('/api/diagnostic/open',{'sessionId':busy})
            for text in ('你好','/file 不得覆盖正在运行的请求'):
                rejected=request('/api/session/prompt',{'type':'client-request','rpcId':str(uuid4()),'method':'session/prompt',
                    'payload':{'args':{'request':{'sessionId':busy,'requestId':str(uuid4()),'mode':'queue','content':[{'type':'text','text':text}]}}}})['result']
                assert not rejected['ok'],rejected
                if text=='你好':assert rejected['error']['code']=='session_busy',rejected
            assert len(seen)==3 and len((output/'policy.json.file-requests').read_text().splitlines())==4
            parent_presets_after=[json.loads(line) for line in preset_log.read_text().splitlines() if json.loads(line)['sessionId']==session] if preset_log.exists() else []
            assert parent_presets_after==parent_presets_before,'A started parent never changes its native preset'
        finally:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
            log.close()
    finally:
        release_completion.set()
        server.shutdown();server.server_close();thread.join(timeout=5)
        # Retain this diagnostic's private native logs for review.
