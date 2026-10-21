/** Installed native File capabilities over loopback HTTP; no paid provider calls. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {randomUUID} from 'node:crypto';
import {Context} from '@deepseek-ai/cordis';
import {AgentRegistry} from '@deepseek-ai/dsh-agent';
import {AgentLoop} from '@deepseek-ai/dsh-agent-loop';
import {Session,SessionStore} from '@deepseek-ai/dsh-session';
import {SessionProjectionRegistry} from '@deepseek-ai/dsh-session-projection';
import {SystemPrompt} from '@deepseek-ai/dsh-system-prompt';
import {ToolRuntime,defineTool} from '@deepseek-ai/dsh-tools';
import {LlmRuntime,createUserMessage} from '@deepseek-ai/dsh-llm';
import {TokenMeter} from '@deepseek-ai/dsh-token-meter';
import {DeepSeekAdapter,resolveAdapterOptions} from '@deepseek-ai/dsh-llm-deepseek';
import {BasicCompactionEngine} from '@deepseek-ai/dsh-compaction-basic';
import {apply as nativeRetry} from '@deepseek-ai/dsh-llm-retry';
import {apply as nativeTodo} from '@deepseek-ai/dsh-tool-todo';
import {apply as scenarioGuard} from '../src/adapters/dsh_scenario_guard.mjs';
import {fileEventProjection} from '../src/adapters/file_event_projection.ts';
import {createTaskProgress} from '../src/adapters/harless_task_progress.ts';
import {WEB_RETRY_POLICY} from '../src/adapters/geneloop_retry.ts';
const sse=(delta,finish_reason=null)=>'data: '+JSON.stringify({id:'file-native-local',object:'chat.completion.chunk',created:1,
 model:'deepseek-flash',choices:[{index:0,delta,finish_reason}]})+'\n\n';

async function fixture({transient=false,summaryFail=false}={}){
 const ctx=new Context(),requests=[],errors=[],progress=createTaskProgress();let toolSideEffects=0;
 const parent=new Session('native-parent');parent.append('turn/start',{turn:1});
 parent.append('user/message',createUserMessage({content:[{type:'text',text:'用户原始文件要求'}],source:{kind:'user'}}),{surfaceOp:'append'});
 const projection=fileEventProjection(parent,1);
 const server=createServer(async(req,res)=>{
  let raw='';for await(const part of req)raw+=part;const value=JSON.parse(raw);
  const summary=JSON.stringify(value.messages.at(-1)?.content).includes('acting as a compaction engine');
  requests.push({value,summary,session:req.headers['x-deepseek-harness-session-id']});
  if(transient&&requests.length===1||summary&&summaryFail){res.writeHead(503,{'Content-Type':'application/json'});res.end(JSON.stringify({error:{message:'diagnostic service unavailable'}}));return;}
  res.writeHead(200,{'Content-Type':'text/event-stream'});
  if(!summary&&!value.messages.some(row=>row.role==='tool'))res.end(sse({tool_calls:[{index:0,id:'todo-1',type:'function',function:{name:'todo_write',arguments:JSON.stringify({todos:[{content:'核对文档原件',status:'in_progress'},{content:'整理交付',status:'in_progress'}]})}}]})+sse({},'tool_calls')+'data: [DONE]\n\n');
  else res.end(sse({content:summary?'Preserve original SHA and user requirements; pending tasks remain pending.':'Document evidence verified. '.repeat(150)})+sse({},'stop')+'data: [DONE]\n\n');
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));server.unref();
 new SessionStore(ctx);new AgentRegistry(ctx);new SessionProjectionRegistry(ctx);new SystemPrompt(ctx,{});new ToolRuntime(ctx,{});new LlmRuntime(ctx);new TokenMeter(ctx);
 const loop=new AgentLoop(ctx,{agents:[]});nativeTodo(ctx,{allowParallelInProgress:true});nativeRetry(ctx,{}, {random:()=>.5});
 const options=resolveAdapterOptions({baseURL:`http://127.0.0.1:${server.address().port}`,reasoningEffort:'off',
  retryPolicy:{...WEB_RETRY_POLICY,backoff:{initialDelayMs:1,maxDelayMs:30000,jitterRatio:0}}});
 ctx.llm.registerAdapter(['deepseek-official'],new DeepSeekAdapter({options:()=>options,resolveApiKey:async()=>'diagnostic-only',
  resolveUserId:()=>'file-native-local',prepareExtensions:async()=>({fields:{},accept:async()=>{}})}));
 ctx.tools.register(defineTool({name:'Bash',description:'Must remain inaccessible',parameters:{},
  output:{schema:{type:'object',additionalProperties:false,properties:{ok:{type:'boolean',required:true}}},render:()=>[]},execute:()=>{toolSideEffects++;return {ok:true};}}));
 const previous=process.env.SSS_SCENARIO_TOOLS;process.env.SSS_SCENARIO_TOOLS=JSON.stringify(['todo_write']);
 try{scenarioGuard(ctx);}finally{if(previous===undefined)delete process.env.SSS_SCENARIO_TOOLS;else process.env.SSS_SCENARIO_TOOLS=previous;}
 const engine=new BasicCompactionEngine(ctx,{auto:false,maxTokens:1000,compactionRetries:0});
 const agent=await loop.create('file-sdk-'+randomUUID(),{provider:'deepseek-official',model:'deepseek-flash',reasoningEffort:'off',maxTokens:1000});
 ctx.on('agent/error',({error})=>errors.push(error),{global:true});
 ctx.on('session/event',(session,event)=>{if(session.id===agent.session.id){projection(event);progress.event(event);}},{global:true});
 return {ctx,agent,parent,engine,requests,errors,progress,sideEffects:()=>toolSideEffects,
  async run(){agent.followup(createUserMessage({source:{kind:'user'},content:[{type:'text',text:'SDK generated frozen task contract '+ 'original document facts '.repeat(1200)}]}));await agent.whenIdle();},
  async close(){await ctx.fiber.dispose();server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}};
}

test('actual File native loop retries 503, executes todo once, and retains the strict tool boundary',async()=>{
 const f=await fixture({transient:true});try{
  await f.run();assert.equal(f.errors.length,0,f.errors.map(e=>e.message).join('\n'));assert.equal(f.requests.length,3);
  assert.equal(new Set(f.requests.map(row=>row.session)).size,1);
  assert.ok(f.requests.every(row=>row.value.tools.every(tool=>tool.function.name==='todo_write')));
  const source=f.agent.session.snapshotEvents(),shown=f.parent.snapshotEvents();
  assert.equal(source.filter(e=>e.type==='todo/write').length,1);assert.equal(shown.filter(e=>e.type==='todo/write').length,1);
  assert.equal(shown.filter(e=>e.type==='llm/retry').length,1);assert.equal(shown.filter(e=>e.type==='llm/retry-started').length,1);
  assert.equal(f.progress.snapshot().todos.length,2);assert.ok(f.progress.snapshot().todos.every(row=>row.status==='in_progress'));
  const denied=await f.ctx.tools.execute({name:'Bash',arguments:{},agent:f.agent,callId:'blocked',signal:new AbortController().signal});
  assert.equal(denied.isError,true);assert.equal(f.sideEffects(),0);
 }finally{await f.close();}
});

test('actual File native compaction uses the same routed session, keeps original journal and preserves parent prompt',async()=>{
 const f=await fixture();try{
  await f.run();const original=f.agent.session.snapshotEvents().map(row=>JSON.stringify(row)),parentBefore=[...f.parent.surface.nodes];
  const result=await f.engine.compactNow(f.agent,new AbortController().signal,'file-compact');
  assert.ok(result);assert.equal(f.requests.filter(row=>row.summary).length,1);assert.equal(new Set(f.requests.map(row=>row.session)).size,1);
  original.forEach((row,index)=>assert.equal(JSON.stringify(f.agent.session.eventAt(index)),row));
  assert.ok(f.agent.session.snapshotEvents().some(row=>row.surfaceOp?.op==='replace'));
  assert.deepEqual(f.parent.surface.nodes,parentBefore,'different SDK contract must not overwrite parent user history');
  assert.equal(f.parent.snapshotEvents().find(row=>row.type==='geneloop/file-compaction').data.projectedSurface,false);
  assert.equal(f.progress.snapshot().progress.label,'上下文已整理，继续处理请求');
 }finally{await f.close();}
});

test('failed File native summary keeps both original surfaces and closes the projected compaction state',async()=>{
 const f=await fixture({summaryFail:true});try{
  await f.run();const source=[...f.agent.session.surface.nodes],parent=[...f.parent.surface.nodes];
  await assert.rejects(f.engine.compactNow(f.agent,new AbortController().signal,'failed-file-compact'));
  assert.deepEqual(f.agent.session.surface.nodes,source);assert.deepEqual(f.parent.surface.nodes,parent);
  assert.equal(f.parent.snapshotEvents().filter(e=>e.type==='compaction/end').length,1);
  assert.equal(f.parent.snapshotEvents().filter(e=>e.type==='geneloop/file-compaction').length,0);
  assert.equal(f.progress.snapshot().progress.status,'failed');
 }finally{await f.close();}
});
