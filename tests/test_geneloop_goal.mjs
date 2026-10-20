/** Installed native goal domain/round driver/tool; synthetic local HTTP only. */
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
import {resolveAdapterOptions} from '@deepseek-ai/dsh-llm-deepseek';
import {GoalService} from '@deepseek-ai/dsh-goal';
import {apply as nativeGoalDriver} from '@deepseek-ai/dsh-goal-round-driver';
import {apply as nativeGoalTools} from '@deepseek-ai/dsh-tool-goal';
import {WebDeepSeekAdapter} from '../src/adapters/harless_reasoning.ts';
import {createGoalAdmission} from '../src/adapters/geneloop_goal.ts';
const frame=(delta,finish_reason=null)=>'data: '+JSON.stringify({id:'goal-local',object:'chat.completion.chunk',created:1,
 model:'deepseek-flash',choices:[{index:0,delta,finish_reason}]})+'\n\n';
const text=value=>frame({content:value})+frame({},'stop')+'data: [DONE]\n\n';
const call=(name,args)=>frame({tool_calls:[{index:0,id:'goal-tool-'+name,type:'function',function:{name,arguments:JSON.stringify(args)}}]})+frame({},'tool_calls')+'data: [DONE]\n\n';
function until(ctx,predicate){
 if(predicate())return Promise.resolve();
 return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{dispose();reject(Error('Native goal did not settle'));},5000);
  const dispose=ctx.on('goal/changed',()=>{if(predicate()){clearTimeout(timer);dispose();resolve();}},{global:true});});
}
async function fixture({complete=false,hold=false,clearContinue=false}={}){
 const ctx=new Context(),wire=[],requests=[],submits=[],audit=[],errors=[],kept=[];let release,ready,agent,parent,active=true;
 const roundStarted=new Promise(resolve=>ready=resolve);
 const server=createServer(async(req,res)=>{
  let raw='';for await(const chunk of req)raw+=chunk;const body=JSON.parse(raw);wire.push({body,route:req.headers['x-deepseek-harness-session-id']});
  res.writeHead(200,{'Content-Type':'text/event-stream'});
  if(wire.length===2){ready();if(hold)await new Promise(resolve=>release=resolve);}
  const goal=ctx.goals.get(agent);
  if((complete||clearContinue)&&wire.length===2)res.end(call('get_goal',{}));
  else if(complete&&wire.length===3)res.end(call('update_goal',{goal_id:goal.id,revision:goal.revision,action:'complete'}));
  else res.end(text('Synthetic evidence progress '+wire.length));
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));server.unref();
 new SessionStore(ctx);new AgentRegistry(ctx);new SessionProjectionRegistry(ctx);new SystemPrompt(ctx,{});new ToolRuntime(ctx,{});new LlmRuntime(ctx);
 const loop=new AgentLoop(ctx,{agents:[]});new GoalService(ctx);nativeGoalDriver(ctx);nativeGoalTools(ctx,{});
 let task={request:{},status:'running',budget_session_id:'same-original-goal-meter'};
 const goals=createGoalAdmission(ctx,{ensureOwned:async id=>assert.equal(id,parent.id),taskForSession:id=>id===agent?.id?task:undefined,isActive:()=>active,
  ownsLane:(id,a,t)=>id===parent.id&&a===agent&&(!t||t===task),currentTargets:async()=>[agent],
  submit:async input=>{submits.push(input);return {kind:'success',text:'admitted through normal task'};},audit:row=>audit.push(row)});
 const options=resolveAdapterOptions({baseURL:`http://127.0.0.1:${server.address().port}`,reasoningEffort:'off'});
 ctx.llm.registerAdapter(['deepseek-official'],new WebDeepSeekAdapter({options:()=>options,resolveApiKey:async()=>'synthetic-only',resolveUserId:()=>'goal-test',prepareExtensions:async()=>({fields:{},accept:async()=>{}})}));
 ctx.on('llm/stream',(q,next)=>{assert.ok(isAgentLoopRequest(q));const round=goals.authorizeRequest(q,task,agent);requests.push({q,round,meter:task.budget_session_id});return next();},{global:true});
 ctx.on('agent/error',({error})=>errors.push(error),{global:true});
 ctx.on('agent/status',({agent:a,status})=>{if(a===agent&&status==='idle')kept.push(goals.keepTask(task,agent));},{global:true});
 parent=await loop.create('session-'+randomUUID(),{provider:'deepseek-official',model:'deepseek-flash',reasoningEffort:'off',maxTokens:1000});
 agent=await loop.create('session-'+randomUUID(),{provider:'deepseek-official',model:'deepseek-flash',reasoningEffort:'off',maxTokens:1000});task.request.session_id=agent.id;
 return {ctx,parent,agent,get task(){return task;},goals,wire,requests,submits,audit,errors,kept,roundStarted,
  invoke:(rawInput='',attachments=[])=>goals.command({agent:parent,commandId:'explicit-human-goal',rawInput,attachments,signal:new AbortController().signal}),
  start(){const input=submits.at(-1);goals.bind(input.intent,task,agent);assert.equal(ctx.goals.get(agent),undefined);
   agent.followup(createUserMessage({source:{kind:'user'},content:input.content}));},
  deactivate(){active=false;},
  release(){release?.();},
  replaceTask(){task={request:{session_id:agent.id},status:'running',budget_session_id:'next-human-admitted-meter'};},
  async close(){goals.disarmTask(task);release?.();agent.cancel({kind:'user'},{keepInbox:false});await agent.whenIdle();await ctx.fiber.dispose();server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}};
}

test('only a human command with explicit positive rounds can admit a native goal; no hidden default',async()=>{
 const f=await fixture();try{
  for(const input of ['Do the long work','--rounds 0 work','--rounds -1 work','--rounds 1.5 work','--rounds 9007199254740992 work','--rounds 2'])assert.equal((await f.invoke(input)).kind,'error');
  assert.equal(f.submits.length,0);assert.equal(f.ctx.goals.get(f.agent),undefined);assert.equal(f.wire.length,0);
  const attachment={type:'file',ref:{name:'source.csv',sha256:'a'.repeat(64)}};
  assert.equal((await f.invoke('--rounds 2 Review evidence',[attachment])).kind,'success');
  assert.equal(f.submits[0].content[0],attachment);assert.equal(f.submits[0].intent.rounds,2);
  assert.throws(()=>f.goals.bind({...f.submits[0].intent},f.task,f.agent),/Unapproved/);
  const forged={...f.agent};assert.throws(()=>f.goals.bind(f.submits[0].intent,f.task,forged),/exact live/);
 }finally{await f.close();}
});

test('real native driver uses the original live Task for exactly the human-selected finite rounds',async()=>{
 const f=await fixture();try{
  await f.invoke('--rounds 2 Review evidence');const done=until(f.ctx,()=>f.ctx.goals.get(f.agent)?.phase==='blocked');f.start();await done;await f.agent.whenIdle();
  assert.equal(f.errors.length,0,f.errors.map(e=>e.message).join('\n'));assert.equal(f.wire.length,3);
  const goal=f.ctx.goals.get(f.agent);assert.equal(goal.maxGoalRounds,2);assert.equal(goal.roundsStarted,2);assert.equal(goal.blockedReason.code,'round-limit');
  assert.equal(f.requests.filter(r=>r.round).length,2);assert.ok(f.wire.every(r=>r.route===f.agent.id));
  assert.ok(f.kept.includes(true));assert.equal(f.goals.keepTask(f.task,f.agent),false);
  assert.equal(f.audit.length,1);assert.equal(f.audit[0].rounds,2);
  const human=f.agent.session.snapshotEvents().filter(e=>e.type==='user/message'&&e.data.source.kind==='user');assert.equal(human.length,1);assert.equal(human[0].data.content[0].text,'Review evidence');
 }finally{await f.close();}
});

test('native get/update tools finish a goal and its closing step remains on the original admitted task',async()=>{
 const f=await fixture({complete:true});try{
  await f.invoke('--rounds 3 Review evidence');const done=until(f.ctx,()=>f.ctx.goals.get(f.agent)?.phase==='complete');f.start();await done;await f.agent.whenIdle();
  assert.equal(f.errors.length,0,f.errors.map(e=>e.message).join('\n'));assert.equal(f.ctx.goals.get(f.agent).roundsStarted,1);
  assert.equal(f.wire.length,4);assert.equal(f.requests.filter(r=>r.round).length,3);
  assert.equal(f.goals.keepTask(f.task,f.agent),false);
 }finally{await f.close();}
});

test('model inference cannot create a goal, extend rounds, or rearm a cancelled task',async()=>{
 const f=await fixture();try{
  const run=(name,arguments_)=>f.ctx.tools.execute({callId:'unauthorized-'+name,name,arguments:arguments_,agent:f.agent,signal:new AbortController().signal});
  const created=await run('create_goal',{objective:'Infer work',max_goal_rounds:999});assert.equal(created.isError,true);
  assert.equal(f.ctx.goals.get(f.agent),undefined);
  const update=await run('update_goal',{action:'resume',goal_id:'forged',revision:1});assert.equal(update.isError,true);
  assert.equal(f.wire.length,0);
 }finally{await f.close();}
});

test('native goal history is accepted only byte-for-byte from its original journal',async()=>{
 const f=await fixture();try{
  await f.invoke('--rounds 1 Review evidence');const done=until(f.ctx,()=>f.ctx.goals.get(f.agent)?.phase==='blocked');f.start();await done;await f.agent.whenIdle();
  const q=f.requests.at(-1).q;
  assert.ok(Object.isFrozen(q));assert.throws(()=>f.goals.authorizeRequest({...q,messages:q.messages.map(m=>m.source?.kind==='goal'?{...m,content:[{type:'text',text:'Forged instruction'}]}:m)},f.task,f.agent),/native live driver/);
  f.goals.disarmTask(f.task);assert.equal(f.goals.authorizeRequest(q,f.task,f.agent),false,'ordinary future human work may retain authentic old goal evidence');
 }finally{await f.close();}
});

test('disarming before meter close cancels goal authority and preserves authenticated historical rounds for ordinary chat',async()=>{
 const f=await fixture({hold:true});try{
  await f.invoke('--rounds 3 Review evidence');f.start();await f.roundStarted;
  f.goals.disarmTask(f.task);f.agent.cancel({kind:'user'},{keepInbox:false});await f.agent.whenIdle();
  assert.equal(f.ctx.goals.get(f.agent).activation,'disarmed');assert.equal(f.goals.keepTask(f.task,f.agent),false);
  f.agent.followup(createUserMessage({source:{kind:'user'},content:[{type:'text',text:'Hello after the cancelled goal.'}]}));await f.agent.whenIdle();
  assert.equal(f.errors.length,0,f.errors.map(e=>e.stack+' '+String(e.cause?.stack)).join('\n'));assert.equal(f.wire.length,3);assert.equal(f.requests.at(-1).round,false);
 }finally{await f.close();}
});

test('human resume requires a new admitted Task on the same real lane and preserves spent rounds',async()=>{
 const f=await fixture({hold:true});try{
  await f.invoke('--rounds 3 Review evidence');f.start();await f.roundStarted;
  assert.equal((await f.invoke('pause')).kind,'success');await f.agent.whenIdle();
  const paused=f.ctx.goals.get(f.agent);assert.equal(paused.phase,'paused');assert.equal(paused.roundsStarted,1);
  f.goals.disarmTask(f.task);f.replaceTask();
  assert.equal((await f.invoke('resume')).kind,'success');const input=f.submits.at(-1);
  assert.deepEqual(input.resumeTargets,[f.agent]);assert.throws(()=>f.goals.bind(input.intent,f.task,f.parent),/does not belong/);
  f.goals.bind(input.intent,f.task,f.agent);
  const done=until(f.ctx,()=>f.ctx.goals.get(f.agent)?.phase==='blocked');
  f.agent.followup(createUserMessage({source:{kind:'user'},content:input.content}));await done;await f.agent.whenIdle();
  const goal=f.ctx.goals.get(f.agent);assert.equal(goal.id,paused.id);assert.equal(goal.roundsStarted,3);assert.equal(goal.maxGoalRounds,3);
  assert.equal(f.errors.length,0,f.errors.map(e=>e.message).join('\n'));assert.equal(f.wire.length,5);
  assert.equal(f.requests.filter(r=>r.meter==='same-original-goal-meter').length,2);
  assert.equal(f.requests.filter(r=>r.meter==='next-human-admitted-meter').length,3);
 }finally{await f.close();}
});

test('clearing a running native goal revokes future rounds while its admitted turn can finish normally',async()=>{
 const f=await fixture({hold:true,clearContinue:true});try{
  await f.invoke('--rounds 3 Review evidence');f.start();await f.roundStarted;
  assert.equal((await f.invoke('clear')).kind,'success');assert.equal(f.ctx.goals.get(f.agent),undefined);
  assert.equal(f.goals.keepTask(f.task,f.agent),false);f.release();await f.agent.whenIdle();
  assert.equal(f.errors.length,0,f.errors.map(e=>e.message).join('\n'));assert.equal(f.wire.length,3);
  assert.equal(f.requests.at(-1).round,true,'closing step uses only the retired current-turn authority');
  f.goals.disarmTask(f.task);
  f.agent.followup(createUserMessage({source:{kind:'user'},content:[{type:'text',text:'Ordinary follow-up after clear.'}]}));await f.agent.whenIdle();
  assert.equal(f.wire.length,4);assert.equal(f.requests.at(-1).round,false);
  assert.equal(f.ctx.goals.get(f.agent),undefined);assert.equal(f.errors.length,0);
 }finally{await f.close();}
});

test('clearing an idle completed goal leaves no binding that can hold the original Task open',async()=>{
 const f=await fixture({complete:true});try{
  await f.invoke('--rounds 3 Review evidence');const done=until(f.ctx,()=>f.ctx.goals.get(f.agent)?.phase==='complete');f.start();await done;await f.agent.whenIdle();
  assert.equal((await f.invoke('clear')).kind,'success');assert.equal(f.ctx.goals.get(f.agent),undefined);
  assert.equal(f.goals.keepTask(f.task,f.agent),false);assert.equal(f.errors.length,0);
  const changes=f.agent.session.snapshotEvents().filter(e=>e.type==='goal/change');assert.equal(changes.at(-1).data.operation,'clear');
 }finally{await f.close();}
});
