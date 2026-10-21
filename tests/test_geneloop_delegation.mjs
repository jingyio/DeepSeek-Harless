/** Native tool-subagent -> native spawn driver -> actual guarded child loop. */
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
import {LlmRuntime,createUserMessage,isAgentLoopRequest} from '@deepseek-ai/dsh-llm';
import {resolveAdapterOptions} from '@deepseek-ai/dsh-llm-deepseek';
import {SubagentRuntime} from '@deepseek-ai/dsh-subagent';
import * as nativeSpawn from '@deepseek-ai/dsh-subagent-spawn-in-process';
import * as nativeSubagentTool from '@deepseek-ai/dsh-tool-subagent';
import {scopeOf} from '@deepseek-ai/dsh-scope';
import {installTaskDelegation,TaskDelegationAdapter,resolveExecutionAgent} from '../src/adapters/geneloop_delegation.ts';
const frame=(delta,finish_reason=null)=>'data: '+JSON.stringify({id:'delegation-local',object:'chat.completion.chunk',created:1,
 model:'deepseek-flash',choices:[{index:0,delta,finish_reason}]})+'\n\n';
const text=value=>frame({content:value})+frame({},'stop')+'data: [DONE]\n\n';
const call=(id,name,args)=>frame({tool_calls:[{index:0,id,type:'function',function:{name,arguments:JSON.stringify(args)}}]})+frame({},'tool_calls')+'data: [DONE]\n\n';

async function fixture({hold=false,adapterDefault=false}={}){
 const ctx=new Context(),wire=[],delegated=[],created=[],audit=[],errors=[];let root,reads=0,release,childReady;
 const childStarted=new Promise(resolve=>childReady=resolve);
 const server=createServer(async(req,res)=>{
  let raw='';for await(const chunk of req)raw+=chunk;const body=JSON.parse(raw);wire.push({body,route:req.headers['x-deepseek-harness-session-id']});
  const last=body.messages.at(-1),child=JSON.stringify(body.messages).includes('Delegated exact source review');
  res.writeHead(200,{'Content-Type':'text/event-stream'});
  if(child&&last.role!=='tool'){childReady();if(hold)await new Promise(resolve=>release=resolve);res.end(call('read-once','read_source',{}));}
  else if(child)res.end(text('Child verified the existing source.'));
  else if(last.role==='tool')res.end(text('Parent completed from the native child result.'));
  else res.end(call('spawn-once','subagent',{description:'Review source',prompt:'Delegated exact source review',run_in_background:false}));
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));server.unref();
 new SessionStore(ctx);new AgentRegistry(ctx);new SessionProjectionRegistry(ctx);new SystemPrompt(ctx,{});new ToolRuntime(ctx,{});new LlmRuntime(ctx);
 const loop=new AgentLoop(ctx,{agents:[]});new SubagentRuntime(ctx);
 const spawnFiber=ctx.plugin(nativeSpawn,{providerName:'spawn'});await spawnFiber.await();assert.equal(spawnFiber.state,2);
 const task={request:{session_id:undefined},model_option:{provider:'deepseek-official',model:'deepseek-flash'},budget_session_id:'turn-original',status:'running',tools:[]};
 let delegation;
 const effectiveRoute={provider:'deepseek-official',model:'deepseek-flash',reasoningEffort:'off',maxTokens:adapterDefault?393216:1000};
 const hostFiber=ctx.plugin({name:'delegation-test-host',inject:['agents','subagents'],apply(scoped){
  delegation=installTaskDelegation(scoped,{taskForSession:id=>id===root?.id?task:undefined,isActive:t=>t.status==='running',
   modelRoute:()=>effectiveRoute,
   onChild:(child,owner,t)=>{assert.equal(owner,root);assert.equal(t,task);created.push(child);},audit:row=>audit.push(row)});
 }});await hostFiber.await();assert.equal(hostFiber.state,2);
 const options=resolveAdapterOptions({baseURL:`http://127.0.0.1:${server.address().port}`,reasoningEffort:'off',...(adapterDefault?{maxTokens:393216}:{})});
 ctx.llm.registerAdapter(['deepseek-official'],new TaskDelegationAdapter({options:()=>options,resolveApiKey:async()=>'synthetic-only',resolveUserId:()=>'delegation-test',
  prepareExtensions:async()=>({fields:{},accept:async()=>{}})},[],delegation));
 ctx.tools.register(defineTool({name:'read_source',description:'Read the approved synthetic source',parameters:{},output:{schema:{type:'string'},render:(_,value)=>[{type:'text',text:value}]},
  execute:async()=>{assert.equal(resolveExecutionAgent(ctx),root);reads++;return 'approved source SHA '+'a'.repeat(64);}}));
 const toolFiber=ctx.plugin(nativeSubagentTool,{provider:'geneloop-task',toolName:'subagent',modelSelectionSettings:false,enableRunInBackground:false,backgroundMode:'one-shot',maxDepth:3,
  toolFilter:{allow:['read_source']}});await toolFiber.await();assert.equal(toolFiber.state,2);
 ctx.on('llm/stream',(q,next)=>{const child=delegation.authorizeRequest(q);if(child){assert.equal(child.task,task);delegated.push(q);}
  else {assert.equal(q.sessionId,root.id);assert.ok(isAgentLoopRequest(q));}return next();},{global:true});
 ctx.on('agent/error',({error})=>errors.push(error),{global:true});
 root=await loop.create('session-'+randomUUID(),{provider:'deepseek-official',model:'deepseek-flash',reasoningEffort:'off',...(!adapterDefault?{maxTokens:1000}:{})});
 task.request.session_id=root.id;task.tools=ctx.tools.schemas(scopeOf(root.ctx));
 return {ctx,loop,root,task,delegation,wire,created,delegated,audit,errors,reads:()=>reads,childStarted,
  async run(){root.followup(createUserMessage({source:{kind:'user'},content:[{type:'text',text:'Delegate one approved source review.'}]}));await root.whenIdle();},
  async close(){release?.();await delegation.drain(task);await ctx.fiber.dispose();server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}};
}

test('native child inherits parent task route, workspace, tool boundary and meter without rewriting history',async()=>{
 const f=await fixture();try{
  await f.run();assert.equal(f.errors.length,0,f.errors.map(e=>e.message).join('\n'));assert.equal(f.created.length,1);assert.equal(f.reads(),1);
  assert.equal(f.delegated.length,2);assert.equal(f.wire.length,4);
  assert.ok(f.wire.every(row=>row.route===f.root.id),'all actual HTTP requests use the same original task route');
  const child=f.created[0];assert.match(child.id,/^[a-f0-9-]{36}$/);assert.equal(child.session.header.parentSession,f.root.id);
  assert.ok(f.delegated.every(q=>q.sessionId===child.id&&isAgentLoopRequest(q)),'actual native child log/request id is unchanged');
  assert.ok(f.delegated.every(q=>q.tools.length===1&&q.tools[0].name==='read_source'));
  assert.equal(f.delegation.isChild(child.id),false,'native foreground collection disposes and revokes its child');
  assert.equal(f.root.session.snapshotEvents().filter(e=>e.type==='tool/result').length,1);
 }finally{await f.close();}
});

test('native child pins the actual admitted adapter capacity when the parent creation options omit maxTokens',async()=>{
 const f=await fixture({adapterDefault:true});try{
  assert.equal(f.root.options.maxTokens,undefined);
  await f.run();assert.equal(f.errors.length,0,f.errors.map(e=>e.message).join('\n'));
  assert.equal(f.created.length,1);assert.equal(f.reads(),1);assert.equal(f.delegated.length,2);
  assert.equal(f.root.session.requestHeader().config.maxTokens,393216);
  assert.equal(f.created[0].options.maxTokens,393216);
  assert.ok(f.delegated.every(q=>q.maxTokens===393216));assert.equal(f.wire.length,4);
  assert.ok(f.wire.every(row=>row.body.max_tokens===393216&&row.route===f.root.id));
 }finally{await f.close();}
});

test('a foreign live agent or changed model cannot acquire the parent task authority',async()=>{
 const f=await fixture();try{
  const other=await f.loop.create('session-'+randomUUID(),{provider:'deepseek-official',model:'deepseek-flash',reasoningEffort:'off',maxTokens:1000});
  const base={label:'unauthorized',prompt:[{type:'text',text:'No request may be sent'}],signal:new AbortController().signal};
  await assert.rejects(f.ctx.subagents.start('geneloop-task',{...base,parent:other}),/no longer active/);
  await assert.rejects(f.ctx.subagents.start('geneloop-task',{...base,parent:f.root,agentOptions:{model:'deepseek-pro'}}),/route/);
  assert.equal(f.wire.length,0);assert.equal(f.created.length,0);
  assert.throws(()=>resolveExecutionAgent(f.ctx,{id:'forged',session:{id:randomUUID(),header:{parentSession:f.root.id}}}),/Unrecognized/);
 }finally{await f.close();}
});

test('simultaneous native starts have distinct immutable child identities on the same parent task',async()=>{
 const f=await fixture();try{
  const run=label=>f.ctx.subagents.start('geneloop-task',{parent:f.root,label,prompt:[{type:'text',text:'Delegated exact source review '+label}],
   toolFilter:{allow:['read_source']},signal:new AbortController().signal});
  const runs=await Promise.all([run('one'),run('two')]);assert.notEqual(runs[0].id,runs[1].id);
  const results=await Promise.all(runs.map(r=>r.result));assert.ok(results.every(r=>r.stopReason==='completed'));
  assert.equal(f.reads(),2);assert.equal(f.wire.length,4);assert.ok(f.wire.every(row=>row.route===f.root.id));
  await Promise.all(runs.map(r=>r.dispose()));assert.ok(runs.every(r=>!f.delegation.isChild(r.id)));
 }finally{await f.close();}
});

test('a cancelled or superseded root task revokes delegated transport and filesystem authority',async()=>{
 const f=await fixture({hold:true});try{
  const pending=f.run();await f.childStarted;const child=f.created[0];f.task.status='cancelled';
  assert.throws(()=>f.delegation.transportSession(child.id),/no longer active/);
  assert.throws(()=>resolveExecutionAgent(f.ctx,child),/no longer active/);
  f.root.cancel({kind:'user'},{keepInbox:false});await f.delegation.drain(f.task);await pending;
  assert.equal(f.reads(),0);
 }finally{await f.close();}
});

test('cancelling a native parent aborts and drains its running child before the task meter can close',async()=>{
 const f=await fixture({hold:true});try{
  const pending=f.run();await f.childStarted;assert.equal(f.created.length,1);const child=f.created[0];
  f.root.cancel({kind:'user'},{keepInbox:false});await f.delegation.drain(f.task);await pending;
  assert.equal(f.delegation.isChild(child.id),false);assert.equal(f.ctx.agents.get(child.id),undefined);
  assert.equal(f.reads(),0);assert.equal(f.wire.length,2);assert.ok(f.wire.every(row=>row.route===f.root.id));
 }finally{await f.close();}
});
