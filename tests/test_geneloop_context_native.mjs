/** Installed native agent loop + DeepSeek adapter over local synthetic HTTP. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {randomUUID} from 'node:crypto';
import {Context} from '@deepseek-ai/cordis';
import {AgentRegistry} from '@deepseek-ai/dsh-agent';
import {AgentLoop} from '@deepseek-ai/dsh-agent-loop';
import {SessionStore} from '@deepseek-ai/dsh-session';
import {SessionProjectionRegistry} from '@deepseek-ai/dsh-session-projection';
import {SystemPrompt} from '@deepseek-ai/dsh-system-prompt';
import {ToolRuntime} from '@deepseek-ai/dsh-tools';
import {LlmRuntime,createUserMessage,isAgentLoopRequest} from '@deepseek-ai/dsh-llm';
import {TokenMeter} from '@deepseek-ai/dsh-token-meter';
import {resolveAdapterOptions} from '@deepseek-ai/dsh-llm-deepseek';
import {WebDeepSeekAdapter} from '../src/adapters/harless_reasoning.ts';
import {GeneLoopContextEngine,createContextAdmission,assertContextUserEnvelope,CONTEXT_INSTRUCTION} from '../src/adapters/geneloop_context.ts';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';
const frame=(text,finish_reason=null)=>'data: '+JSON.stringify({id:'context-local',object:'chat.completion.chunk',created:1,
 model:'deepseek-flash',choices:[{index:0,delta:{content:text},finish_reason}]})+'\n\n';

async function nativeFixture({pressure=true,overflow=false,hold=false}={}){
 const ctx=new Context(),wire=[],guarded=[],errors=[],meter=[],audit=[];let active=true,normalCalls=0,overflowSent=false,release;
 let summaryReady;const summaryStarted=new Promise(resolve=>summaryReady=resolve);
 const server=createServer(async(req,res)=>{
  let raw='';for await(const part of req)raw+=part;const value=JSON.parse(raw),last=value.messages.at(-1)?.content;
  const summary=JSON.stringify(last).includes(CONTEXT_INSTRUCTION.slice(0,70));wire.push({summary,value});
  if(summary){summaryReady();if(hold)await new Promise(resolve=>release=resolve);}
  else {normalCalls++;if(overflow&&normalCalls===2&&!overflowSent){overflowSent=true;res.writeHead(400,{'Content-Type':'application/json'});
   res.end(JSON.stringify({error:{code:'context_length_exceeded',message:'maximum context length exceeded'}}));return;}}
  const text=summary?'Checkpoint: preserve original source SHA, confirmed facts and current objective.':normalCalls===1?'Retained recent result. '.repeat(90):'Continued using retained evidence.';
  res.writeHead(200,{'Content-Type':'text/event-stream'});res.end(frame(text)+frame('','stop')+'data: [DONE]\n\n');
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));server.unref();
 new SessionStore(ctx);new AgentRegistry(ctx);new SessionProjectionRegistry(ctx);new SystemPrompt(ctx,{});new ToolRuntime(ctx,{});new LlmRuntime(ctx);new TokenMeter(ctx);
 const loop=new AgentLoop(ctx,{agents:[]}),options=resolveAdapterOptions({baseURL:`http://127.0.0.1:${server.address().port}`,reasoningEffort:'off'});
 ctx.llm.registerAdapter(['deepseek-official'],new WebDeepSeekAdapter({options:()=>options,resolveApiKey:async()=>'local-context-diagnostic',
  resolveUserId:()=>'context-test',prepareExtensions:async()=>({fields:{},accept:async()=>{}})}));
 const capacity=(await ctx.llm.resolveModelInfo('deepseek-official','deepseek-flash')).context.contextWindow;
 let agent;const task={request:{},model_option:{provider:'deepseek-official',model:'deepseek-flash'},budget_session_id:'original-context-task',humans:new Map(),current:new Set()};
 const admission=createContextAdmission({policy:{budget_task_prefix:'1234abcd',budget_usd:null},taskForSession:id=>id===agent?.session.id?task:undefined,isActive:()=>active,
  ensureOwned:async id=>assert.equal(id,agent.session.id),control:async(path,body)=>{meter.push({path,body});return {upstream_requests:1};},
  broker:async(path,body)=>{meter.push({path,body});},audit:row=>audit.push(row)});
 const engine=new GeneLoopContextEngine(ctx,admission,{thresholdRatio:pressure?1000/capacity:.99,retainTokens:200,maxTokens:1000,compactionRetries:0});
 ctx.on('session/event',(_session,event)=>{if(event.type==='turn/start')task.current.clear();if(event.type==='user/message'&&event.data.source?.kind==='user'){
  task.humans.set(event.data.id,digest(event.data.content));task.current.add(event.data.id);}}, {global:true});
 ctx.on('agent/error',({error})=>errors.push(error),{global:true});
 ctx.on('llm/stream',(q,next)=>{
  guarded.push(q);
  if(q.purpose==='compaction')admission.assertAuthorized(q);
  else {assert.ok(isAgentLoopRequest(q));assertContextUserEnvelope(q,agent.session,task.humans,task.current);}
  return next();
 },{global:true});
 agent=await loop.create('session-'+randomUUID(),{provider:'deepseek-official',model:'deepseek-flash',reasoningEffort:'off',maxTokens:1000});task.request.session_id=agent.session.id;
 return {ctx,agent,engine,admission,wire,guarded,errors,meter,audit,summaryStarted,
  async send(text){agent.followup(createUserMessage({source:{kind:'user'},content:[{type:'text',text}]}));await agent.whenIdle();},
  idleMeter(){active=false;},release:()=>release?.(),async close(){release?.();await ctx.fiber.dispose();server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}};
}

test('real native pre-step pressure summarizes then continues through a branded guarded loop request',async()=>{
 const f=await nativeFixture();try{
  await f.send('Original evidence '+ 'measured source facts '.repeat(1400));
  assert.equal(f.wire.filter(row=>row.summary).length,0,'cold first request has no prior pressure envelope');
  const before=f.agent.session.snapshotEvents().map(e=>JSON.stringify(e));
  await f.send('Continue with the same evidence.');
  assert.equal(f.errors.length,0,f.errors.map(e=>e.message).join('\n'));assert.equal(f.wire.filter(row=>row.summary).length,1);
  assert.equal(f.wire.filter(row=>!row.summary).length,2);assert.equal(f.meter.length,0,'automatic call stays on the existing task meter');
  before.forEach((row,i)=>assert.equal(JSON.stringify(f.agent.session.eventAt(i)),row));
  assert.equal(f.agent.session.snapshotEvents().filter(e=>e.type==='compaction/summary').length,1);
 }finally{await f.close();}
});

test('real provider context overflow invokes native reduction and retries that same loop',async()=>{
 const f=await nativeFixture({pressure:false,overflow:true});try{
  await f.send('Original evidence '+ 'measured source facts '.repeat(1400));await f.send('Continue after provider overflow.');
  assert.equal(f.errors.length,0,f.errors.map(e=>e.message).join('\n'));
  assert.equal(f.wire.filter(row=>row.summary).length,1);assert.equal(f.wire.filter(row=>!row.summary).length,3);
  const requests=f.guarded.filter(q=>q.purpose!=='compaction');assert.equal(new Set(requests.map(q=>q.sessionId)).size,1);
  assert.ok(requests.at(-1).messages.some(m=>m.source?.plugin==='compact'));
 }finally{await f.close();}
});

test('actual agent maintenance blocks another maintenance and cancellation keeps original surface',async()=>{
 const f=await nativeFixture({pressure:false,hold:true});try{
  await f.send('Original evidence '+ 'measured source facts '.repeat(1400));f.idleMeter();
  const before=f.agent.session.surface.nodes.slice(),abort=new AbortController();
  const pending=f.engine.compactNow(f.agent,abort.signal,'native-cancel');await f.summaryStarted;
  assert.throws(()=>f.agent.runMaintenance(async()=>{}),/active work/);
  abort.abort(new DOMException('User cancelled maintenance','AbortError'));await assert.rejects(pending,/cancel/i);
  assert.deepEqual(f.agent.session.surface.nodes,before);assert.equal(f.agent.session.snapshotEvents().filter(e=>e.type==='compaction/summary').length,0);
  assert.equal(f.meter.at(-1).path,'/tasks/cancel');assert.equal(f.meter.at(-2).path,'/unbind');
 }finally{await f.close();}
});
