// Local synthetic provider; real installed DSH compaction, surface and meter.
import test from 'node:test';
import assert from 'node:assert/strict';
import {Context} from '@deepseek-ai/cordis';
import {Session} from '@deepseek-ai/dsh-session';
import {TokenMeter} from '@deepseek-ai/dsh-token-meter';
import {SessionProjectionRegistry} from '@deepseek-ai/dsh-session-projection';
import {createUserMessage,createAssistantMessage,createSystemMessage} from '@deepseek-ai/dsh-llm';
import {CommandRuntime} from '@deepseek-ai/dsh-commands';
import {apply as nativeCompact} from '@deepseek-ai/dsh-command-compact';
import {GeneLoopContextEngine,createContextAdmission,assertContextUserEnvelope,routeNativeCompact} from '../src/adapters/geneloop_context.ts';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';

function fixture({window=2000,active=true,summary='Verified sources retained. Continue the current request.',config={},failure,finish={kind:'stop'},executionAgent}={}){
 const ctx=new Context(),requests=[],calls=[],audit=[];new SessionProjectionRegistry(ctx);new TokenMeter(ctx);
 const sessions=new Map(),tasks=new Map();let blocked;
 const admission=createContextAdmission({policy:{budget_task_prefix:'abcdef12',budget_usd:null},
  taskForSession:id=>tasks.get(id),isActive:t=>t.status==='running',executionAgent,ensureOwned:async id=>{if(!sessions.has(id))throw Error('not owned');},
  control:async(path,body)=>{calls.push({path,body});if(blocked===path)throw Error('synthetic lost reply');return {upstream_requests:1};},
  broker:async(path,body)=>{calls.push({path,body});if(blocked===path)throw Error('synthetic lost reply');},audit:row=>audit.push(row)});
 ctx.llm={resolveModelInfo:async()=>({context:{contextWindow:window}}),
  async *stream(q){admission.assertAuthorized(q);requests.push(q);
   if(failure)throw failure;
   assert.throws(()=>admission.assertAuthorized(q),/Unapproved/,'the permit cannot authorize a second model call');
   yield {type:'text-delta',index:0,text:summary};yield {type:'finish',reason:finish,usage:{inputTokens:500,outputTokens:12}};
  }};
 ctx.sessions={async flush(){}};
 const engine=new GeneLoopContextEngine(ctx,admission,{retainTokens:300,compactionRetries:0,...config});
 function agent(id='owned',length=6000,attachments=[]){
  const session=Session.create(id),user=createUserMessage({source:{kind:'user',rpcId:'initial-'+id},content:[{type:'text',text:'Source SHA '+ 'a'.repeat(64)+' '+ 'initial facts '.repeat(length/14)},...attachments]});
  session.append('system/message',{message:createSystemMessage('Keep source identity and permissions.','diagnostic-system')},{surfaceOp:'append'});
  session.append('turn/start',{turn:1});session.append('user/message',user,{surfaceOp:'append'});
  session.append('step/start',{turn:1,step:1});
  session.append('request/header',{header:{config:{provider:'deepseek-official',model:'deepseek-flash',maxTokens:393216}},reason:'initial'});
  session.append('assistant/message',{turn:1,step:1,stream:[],message:createAssistantMessage({source:{provider:'deepseek-official',model:'deepseek-flash'},content:[{type:'text',text:'Earlier result '.repeat(100)}]})},{surfaceOp:'append'});
  session.append('step/end',{turn:1,step:1});session.append('turn/end',{turn:1,reason:{kind:'completed'}});
  const current=createUserMessage({source:{kind:'user',rpcId:'current-'+id},content:[{type:'text',text:'Continue precisely with the original source.'}]});
  session.append('turn/start',{turn:2});session.append('user/message',current,{surfaceOp:'append'});
  const a={session,options:{provider:'deepseek-official',model:'deepseek-flash'},
   async runMaintenance(fn){return fn(new AbortController().signal);}};
  sessions.set(id,a);tasks.set(id,{request:{session_id:id},model_option:{provider:'deepseek-official',model:'deepseek-flash'},budget_session_id:'turn-original-'+id,status:active?'running':'completed'});
  return {agent:a,user,current,humans:new Map([[user.id,digest(user.content)],[current.id,digest(current.content)]]),currentHumans:new Set([current.id])};
 }
 return {ctx,engine,admission,requests,calls,audit,agent,sessions,tasks,block:path=>blocked=path,async close(){await ctx.fiber.dispose();}};
}
const requestMessages=session=>session.surface.nodes.map(seq=>session.deriveEventMessage(session.eventAt(seq))).filter(Boolean);

test('native pressure leaves a short conversation untouched and spends nothing',async()=>{
 const f=fixture({window:100000});try{
  const a=f.agent(),before=JSON.stringify(a.agent.session.snapshotEvents());
  assert.equal(await f.engine.compactIfNeeded(a.agent,'pressure',new AbortController().signal),null);
  assert.equal(JSON.stringify(a.agent.session.snapshotEvents()),before);assert.equal(f.requests.length,0);assert.equal(f.calls.length,0);
 }finally{await f.close();}
});

test('native window pressure compacts only surface, retains journal and original source identities',async()=>{
 const f=fixture();try{
  const a=f.agent(),before=a.agent.session.snapshotEvents().map(e=>JSON.stringify(e));
  const result=await f.engine.compactIfNeeded(a.agent,'pressure',new AbortController().signal);
  assert.ok(result);assert.equal(f.requests.length,1);assert.equal(f.calls.length,0,'active task uses its original bound meter');
  before.forEach((row,i)=>assert.equal(JSON.stringify(a.agent.session.eventAt(i)),row));
  const messages=requestMessages(a.agent.session);assert.ok(messages.some(m=>m.source?.plugin==='compact'));
  assertContextUserEnvelope({messages},a.agent.session,a.humans,a.currentHumans);
  assert.equal(f.requests[0].purpose,'compaction');assert.equal(f.requests[0].messages[0].role,'system');
  assert.ok(f.requests[0].messages.some(m=>m.id===a.user.id));
  assert.throws(()=>f.admission.assertAuthorized(f.requests[0]),/Unapproved/,'permit expires after exactly this stream');
  assert.throws(()=>f.admission.assertAuthorized({...f.requests[0]}),/Unapproved/);
 }finally{await f.close();}
});

test('trusted delegated compaction keeps its own history and original root task meter',async()=>{
 let owner;const f=fixture({executionAgent:agent=>agent.session.id==='child'?owner:agent});try{
  owner=f.agent('root').agent;const child=f.agent('child');f.tasks.delete('child');
  assert.ok(await f.engine.compactIfNeeded(child.agent,'pressure',new AbortController().signal));
  assert.equal(f.calls.length,0);assert.equal(f.requests[0].sessionId,'child');
  assert.equal(f.audit[0].budget_session_id,'turn-original-root');
  assert.equal(owner.session.snapshotEvents().filter(e=>e.type==='compaction/summary').length,0);
 }finally{await f.close();}
});

test('overflow forces balanced native reduction below normal pressure threshold',async()=>{
 const f=fixture({window:100000});try{
  const a=f.agent();assert.equal(await f.engine.compactIfNeeded(a.agent,'pressure',new AbortController().signal),null);
  assert.ok(await f.engine.compactIfNeeded(a.agent,'context-overflow',new AbortController().signal));assert.equal(f.requests.length,1);
  const replacement=requestMessages(a.agent.session).find(m=>m.source?.plugin==='compact');
  assert.ok(replacement);assertContextUserEnvelope({messages:requestMessages(a.agent.session)},a.agent.session,a.humans,a.currentHumans);
 }finally{await f.close();}
});

test('native compact never splits an unfinished assistant tool call from its future result',async()=>{
 const f=fixture();try{
  const a=f.agent(),s=a.agent.session;s.append('step/start',{turn:2,step:1});
  const call=s.append('assistant/message',{turn:2,step:1,stream:[],message:createAssistantMessage({source:{provider:'deepseek-official',model:'deepseek-flash'},content:[{type:'tool-call',id:'pending-call',name:'read_file',arguments:'{}'}]})},{surfaceOp:'append'});
  const result=await f.engine.compactIfNeeded(a.agent,'context-overflow',new AbortController().signal);
  assert.ok(result);assert.ok(!result.shadowedSeqs.includes(call.seq));assert.ok(s.surface.nodes.includes(call.seq));
  assert.equal(s.eventAt(call.seq).data.message.content[0].id,'pending-call');
  assertContextUserEnvelope({messages:requestMessages(s)},s,a.humans,a.currentHumans);
 }finally{await f.close();}
});

test('native nested checkpoints prove current human identity without copying it into a new user instruction',async()=>{
 const f=fixture();try{
  const a=f.agent(),s=a.agent.session;
  await f.engine.compactIfNeeded(a.agent,'context-overflow',new AbortController().signal);
  s.append('user/message',createUserMessage({source:{kind:'plugin',plugin:'diagnostic-context'},content:[{type:'text',text:'Reference data '.repeat(600)}]}),{surfaceOp:'append'});
  await f.engine.compactIfNeeded(a.agent,'context-overflow',new AbortController().signal);
  const messages=requestMessages(s);assert.ok(!messages.some(m=>m.id===a.current.id));
  assertContextUserEnvelope({messages},s,a.humans,a.currentHumans);
  assert.equal(s.snapshotEvents().filter(e=>e.type==='compaction/summary').length,2);
 }finally{await f.close();}
});

test('file and image references reach summary unchanged and remain in immutable history',async()=>{
 const f=fixture();try{
  const attachments=[{type:'file',attachment:{attachmentId:'a'.repeat(64),name:'source.pdf',bytes:42}},
   {type:'image',attachment:{attachmentId:'b'.repeat(64),name:'figure.png',bytes:12,width:1,height:1,mediaType:'image/png'}}];
  const a=f.agent('owned',6000,attachments),before=JSON.stringify(a.user);
  await f.engine.compactIfNeeded(a.agent,'context-overflow',new AbortController().signal);
  const original=f.requests[0].messages.find(m=>m.id===a.user.id);assert.equal(JSON.stringify(original),before);
  assert.deepEqual(a.agent.session.snapshotEvents().find(e=>e.type==='user/message'&&e.data.id===a.user.id).data.content.slice(1),attachments);
 }finally{await f.close();}
});

test('truncated or failed summary cannot replace evidence with an incomplete checkpoint',async()=>{
 for(const config of [{finish:{kind:'max-tokens'}},{failure:new Error('synthetic provider disconnected')}]){
  const f=fixture(config);try{
   const a=f.agent(),before=a.agent.session.surface.nodes.slice();
   await assert.rejects(f.engine.compactIfNeeded(a.agent,'context-overflow',new AbortController().signal));
   assert.deepEqual(a.agent.session.surface.nodes,before);assert.equal(a.agent.session.snapshotEvents().filter(e=>e.type==='compaction/summary').length,0);
   assert.ok(a.agent.session.snapshotEvents().at(-1).data.error);
  }finally{await f.close();}
 }
});

test('idle native compact reuses originals and accounts maintenance on the existing platform ledger',async()=>{
 const f=fixture({active:false});try{
  const a=f.agent();a.agent.session.append('turn/end',{turn:2,reason:{kind:'completed'}});
  const result=await f.engine.compactNow(a.agent,new AbortController().signal,'native-command-id');assert.ok(result);
  assert.deepEqual(f.calls.map(c=>c.path),['/tasks/register','/tasks/activate','/bind','/unbind','/tasks/cancel']);
  assert.equal(f.calls[0].body.budget_usd,null);assert.match(f.calls[0].body.task_id,/^abcdef12[a-f0-9]{24}$/);
  assert.deepEqual(f.calls[2].body,f.calls[3].body);assert.equal(result.sourceCommandId,'native-command-id');
 }finally{await f.close();}
});

test('lost register and bind replies cannot silently leak a maintenance route',async()=>{
 for(const lost of ['/tasks/register','/bind']){
  const f=fixture({active:false});try{
   const a=f.agent();a.agent.session.append('turn/end',{turn:2,reason:{kind:'completed'}});f.block(lost);
   const before=a.agent.session.surface.nodes.slice();await assert.rejects(f.engine.compactNow(a.agent,new AbortController().signal),/summary/);
   assert.deepEqual(a.agent.session.surface.nodes,before);assert.equal(f.requests.length,0);
   assert.equal(f.calls.at(-1).path,'/tasks/cancel');
   if(lost==='/bind')assert.equal(f.calls.at(-2).path,'/unbind');
  }finally{await f.close();}
 }
});

test('checkpoint-looking user text and forged checkpoint sources never authorize omitted current input',async()=>{
 const f=fixture();try{
  const a=f.agent();await f.engine.compactIfNeeded(a.agent,'context-overflow',new AbortController().signal);
  const messages=requestMessages(a.agent.session),checkpoint=messages.find(m=>m.source?.plugin==='compact');
  assert.throws(()=>assertContextUserEnvelope({messages:[{...checkpoint,id:'forged'}]},a.agent.session,a.humans,a.currentHumans),/checkpoint/);
  const modified=messages.map(m=>m.id===a.current.id?{...m,content:[{type:'text',text:'changed current input'}]}:m);
  assert.throws(()=>assertContextUserEnvelope({messages:modified},a.agent.session,a.humans,a.currentHumans),/envelope/);
  assert.throws(()=>assertContextUserEnvelope({messages:[{role:'user',id:'fake',source:{kind:'plugin',plugin:'compact',compactionId:'fake'},content:[]}]},a.agent.session,a.humans,a.currentHumans),/checkpoint/);
 }finally{await f.close();}
});

test('native command lifecycle routes public parent compact to both real child histories',async()=>{
 const f=fixture({active:false});try{
  new CommandRuntime(f.ctx);nativeCompact(f.ctx);
  const parent=f.agent('parent'),left=f.agent('left'),right=f.agent('right');
  for(const row of [parent,left,right])row.agent.session.append('turn/end',{turn:2,reason:{kind:'completed'}});
  const native=f.ctx.commands.find(parent.agent,'compact');
  const result=await routeNativeCompact({agent:parent.agent,commandId:'parent-command',rawInput:'',attachments:[],signal:new AbortController().signal},native,f.ctx.commands,
   async agent=>{assert.equal(agent,parent.agent);return [{agent:left.agent,label:'Baseline'},{agent:right.agent,label:'Motif'}];},f.admission);
  assert.equal(result.kind,'success');assert.match(result.text,/Baseline: Compacted/);assert.match(result.text,/Motif: Compacted/);
  assert.equal(f.requests.length,2);assert.deepEqual(f.requests.map(q=>q.sessionId),['left','right']);
  assert.equal(parent.agent.session.snapshotEvents().filter(e=>e.type==='compaction/summary').length,0);
  for(const row of [left,right]){
   const events=row.agent.session.snapshotEvents();assert.equal(events.filter(e=>e.type==='command/run').length,1);
   assert.equal(events.filter(e=>e.type==='command/done').length,1);assert.equal(events.filter(e=>e.type==='compaction/summary').length,1);
  }
 }finally{await f.close();}
});
