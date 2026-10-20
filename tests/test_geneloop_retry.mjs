/** Deterministic real HTTP + installed native loop/retry; no paid provider. */
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
import {ToolRuntime,defineTool} from '@deepseek-ai/dsh-tools';
import {LlmRuntime,LlmError,createUserMessage,isAgentLoopRequest} from '@deepseek-ai/dsh-llm';
import {resolveAdapterOptions} from '@deepseek-ai/dsh-llm-deepseek';
import {apply as nativeRetry} from '@deepseek-ai/dsh-llm-retry';
import {WebDeepSeekAdapter} from '../src/adapters/harless_reasoning.ts';
import {WEB_RETRY_POLICY,taskFailureStatus} from '../src/adapters/geneloop_retry.ts';
import {createTaskProgress} from '../src/adapters/harless_task_progress.ts';

const frame=(delta,finish_reason=null)=>'data: '+JSON.stringify({id:'local-diagnostic',object:'chat.completion.chunk',created:1,
  model:'deepseek-flash',choices:[{index:0,delta,finish_reason}]})+'\n\n';
const textResponse=text=>frame({content:text})+frame({},'stop')+'data: [DONE]\n\n';
const toolResponse=()=>frame({tool_calls:[{index:0,id:'save-once',type:'function',function:{name:'save_once',arguments:'{}'}}]})+
  frame({},'tool_calls')+'data: [DONE]\n\n';

async function fixture(respond,{delay=1}={}) {
  const requests=[],events=[],errors=[],guarded=[];let toolCalls=0;
  let scheduled;const retryScheduled=new Promise(resolve=>{scheduled=resolve;});
  const progress=createTaskProgress(),ctx=new Context();
  const server=createServer(async(req,res)=>{
    let body='';for await(const part of req)body+=part;
    requests.push({body:JSON.parse(body),session:req.headers['x-deepseek-harness-session-id']});
    respond(req,res,requests.length);
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  server.unref();
  new SessionStore(ctx);new AgentRegistry(ctx);new SessionProjectionRegistry(ctx);
  new SystemPrompt(ctx,{});new ToolRuntime(ctx,{});new LlmRuntime(ctx);
  const loop=new AgentLoop(ctx,{agents:[]});
  nativeRetry(ctx,{}, {random:()=>.5});
  const options=resolveAdapterOptions({baseURL:`http://127.0.0.1:${server.address().port}`,
    reasoningEffort:'off',retryPolicy:{...WEB_RETRY_POLICY,backoff:{initialDelayMs:delay,maxDelayMs:30_000,jitterRatio:0}}});
  ctx.llm.registerAdapter(['deepseek-official'],new WebDeepSeekAdapter({options:()=>options,
    resolveApiKey:async()=>'diagnostic-only',resolveUserId:()=> 'retry-test',prepareExtensions:async()=>({fields:{},accept:async()=>{}})}));
  ctx.tools.register(defineTool({name:'save_once',description:'Count one diagnostic side effect',parameters:{},
    output:{schema:{type:'object',additionalProperties:false,properties:{ok:{type:'boolean',required:true}}},render:()=>[{type:'text',text:'saved'}]},
    execute:async()=>{toolCalls++;return {ok:true};}}));
  ctx.on('session/event',(_session,event)=>{events.push(event);progress.event(event);if(event.type==='llm/retry')scheduled(event);},{global:true});
  ctx.on('agent/error',({error})=>errors.push(error),{global:true});
  ctx.on('llm/stream',(request,next)=>{
    assert.equal(isAgentLoopRequest(request),true);guarded.push(request);progress.beginAttempt();
    return (async function*(){for await(const chunk of next()){progress.chunk(chunk);yield chunk;}})();
  },{global:true});
  const agent=await loop.create('session-'+randomUUID(),{provider:'deepseek-official',model:'deepseek-flash',reasoningEffort:'off',maxTokens:50});
  return {agent,requests,events,errors,guarded,progress,retryScheduled,toolCalls:()=>toolCalls,
    async run(){agent.followup(createUserMessage({content:[{type:'text',text:'Local recovery diagnostic'}]}));await agent.whenIdle();},
    async close(){await ctx.fiber.dispose();server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}};
}

test('native retry recovers HTTP 503 in the same guarded task step',async()=>{
  const f=await fixture((_req,res,count)=>{
    if(count===1){res.writeHead(503,{'Content-Type':'application/json','Retry-After':'0.001'});res.end(JSON.stringify({error:{message:'temporary unavailable'}}));}
    else {res.writeHead(200,{'Content-Type':'text/event-stream'});res.end(textResponse('Recovered reply'));}
  });
  try {await f.run();assert.equal(f.requests.length,2,JSON.stringify({errors:f.errors.map(error=>({message:error.message,code:error.code})),events:f.events.map(row=>row.type)}));assert.equal(f.errors.length,0);
    assert.equal(f.guarded.length,2);assert.equal(new Set(f.guarded.map(row=>row.sessionId)).size,1);
    assert.equal(f.events.filter(row=>row.type==='llm/retry').length,1);
    assert.equal(f.progress.snapshot().answer,'Recovered reply');
  } finally {await f.close();}
});

test('upstream 429 retries with native Retry-After; permanent 4xx and true quota do not retry',async()=>{
  for(const [code,body,attempts,status] of [
    [429,{message:'Rate limited'},2,'failed'],[400,{message:'Invalid argument'},1,'failed'],
    [401,{message:'Bad credentials'},1,'failed'],[403,{message:'Permission denied'},1,'failed'],
    [422,{message:'Invalid input'},1,'failed'],
    [429,{code:'GENELOOP_BUDGET_EXHAUSTED',type:'quota_exceeded',message:'approved research budget exhausted'},1,'budget_exhausted'],
  ]) {
    const f=await fixture((_req,res,count)=>{
      if(count===1){res.writeHead(code,{'Content-Type':'application/json','Retry-After':'1'});res.end(JSON.stringify({error:body}));}
      else {res.writeHead(200,{'Content-Type':'text/event-stream'});res.end(textResponse('Recovered reply'));}
    });
    try {await f.run();assert.equal(f.requests.length,attempts);
      if(attempts===1){assert.equal(f.errors.length,1);assert.equal(taskFailureStatus(f.errors[0]),status);}
      else {assert.equal(f.errors.length,0);assert.equal(f.events.find(row=>row.type==='llm/retry').data.delayMs,1000);}
    } finally {await f.close();}
  }
});

test('failed partial output is withdrawn and completed side effects are not replayed',async()=>{
  const f=await fixture((_req,res,count)=>{
    res.writeHead(200,{'Content-Type':'text/event-stream'});
    if(count===1)res.end(toolResponse());
    else if(count===2){res.write(frame({content:'Discarded partial'}));setTimeout(()=>res.destroy(),10);}
    else res.end(textResponse('Single successful answer'));
  });
  try {
    await f.run();assert.equal(f.requests.length,3);assert.equal(f.errors.length,0);assert.equal(f.toolCalls(),1);
    assert.deepEqual(f.requests[1].body,f.requests[2].body,'retry reconstructs the same history including completed tool results');
    assert.equal(f.events.filter(row=>row.type==='tool/call').length,1);
    assert.equal(f.events.filter(row=>row.type==='assistant/attempt').length,1);
    assert.deepEqual(f.progress.snapshot().messages.map(row=>row.text),['Single successful answer']);
    assert.doesNotMatch(JSON.stringify(f.progress.snapshot()),/Discarded partial/);
    assert.equal(f.progress.snapshot().answer,'Single successful answer');
  } finally {await f.close();}
});

test('cancellation interrupts a long native backoff without dispatching another HTTP request',async()=>{
  const f=await fixture((_req,res)=>{res.writeHead(503,{'Content-Type':'application/json'});res.end('{"error":{"message":"temporary unavailable"}}');},{delay:30_000});
  try {
    const running=f.run();await f.retryScheduled;const start=performance.now();
    f.agent.cancel({kind:'user'});await running;
    assert.ok(performance.now()-start<1000,'cancellation must not wait for backoff');
    assert.equal(f.requests.length,1);assert.equal(f.events.filter(row=>row.type==='llm/retry-started').length,0);
  } finally {await f.close();}
});

test('task status uses native failure classes, never arbitrary 429 or budget message text',()=>{
  for(const error of [new LlmError('HTTP 429','RATE_LIMIT',{status:429}),{failure:{code:'RATE_LIMIT',status:429}},
    {error:{code:'RATE_LIMIT'}},new Error('HTTP 429; budget note'), 'approved research budget exhausted'])assert.equal(taskFailureStatus(error),'failed');
  for(const error of [new LlmError('Account balance exhausted','QUOTA'),{failure:{code:'QUOTA'}},
    {error:{code:'GENELOOP_BUDGET_EXHAUSTED'}},new Error('wrapper',{cause:{code:'budget_exhausted'}}),
    {cause:{cause:{cause:{failure:{code:'QUOTA'}}}}}])assert.equal(taskFailureStatus(error),'budget_exhausted');
  assert.equal(taskFailureStatus(new DOMException('Stopped','AbortError')),'cancelled');
  const cycle={};cycle.cause=cycle;assert.equal(taskFailureStatus(cycle),'failed');
});
