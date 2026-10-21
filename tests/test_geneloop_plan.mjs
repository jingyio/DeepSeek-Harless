/** Real installed native plan state/command/review, no paid provider. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {createServer} from 'node:http';
import {Context} from '@deepseek-ai/cordis';
import {AgentRegistry} from '@deepseek-ai/dsh-agent';
import {AgentLoop} from '@deepseek-ai/dsh-agent-loop';
import {SessionStore} from '@deepseek-ai/dsh-session';
import {SessionProjectionRegistry} from '@deepseek-ai/dsh-session-projection';
import {SystemPrompt} from '@deepseek-ai/dsh-system-prompt';
import {ToolRuntime} from '@deepseek-ai/dsh-tools';
import {LlmRuntime,createUserMessage} from '@deepseek-ai/dsh-llm';
import {resolveAdapterOptions} from '@deepseek-ai/dsh-llm-deepseek';
import {WebDeepSeekAdapter} from '../src/adapters/harless_reasoning.ts';
import {CommandRuntime} from '@deepseek-ai/dsh-commands';
import {PlanModeController} from '@deepseek-ai/dsh-plan-mode';
import {UserQuestionService} from '@deepseek-ai/dsh-user-questions';
import {createPlanAdmission,PLAN_GUIDANCE} from '../src/adapters/geneloop_plan.ts';

async function fixture(){
 const ctx=new Context(),tasks=new Map(),submits=[],audit=[],questions=[];let targets=[],accept=true;
 new SessionStore(ctx);new AgentRegistry(ctx);new SessionProjectionRegistry(ctx);new SystemPrompt(ctx,{});
 new ToolRuntime(ctx,{});new LlmRuntime(ctx);new CommandRuntime(ctx);new UserQuestionService(ctx);
 const loop=new AgentLoop(ctx,{agents:[]});new PlanModeController(ctx,{section:PLAN_GUIDANCE});
 const make=()=>loop.create('session-'+randomUUID(),{provider:'deepseek-official',model:'deepseek-flash'});
 const parent=await make(),left=await make(),right=await make(),foreign=await make();targets=[left,right];
 for(const agent of targets)tasks.set(agent.id,{request:{session_id:agent.id},status:'running',parent:parent.id});
 const plan=createPlanAdmission(ctx,{ensureOwned:async id=>assert.equal(id,parent.id),taskForSession:id=>tasks.get(id),isActive:t=>t.status==='running',
  currentTargets:async()=>targets,ownsLane:(id,a,t)=>id===parent.id&&[left,right].includes(a)&&(!t||t.parent===id),
  submit:async input=>{submits.push(input);return accept?{kind:'success',text:'admitted'}:{kind:'error',text:'busy'};},audit:row=>audit.push(row)});
 ctx.on('user-questions/request',async q=>{questions.push(q);return {answers:[{id:'plan-review',selected:['Approve']}]};},{global:true});
 // Shadow native direct-steer only on the public projection; native service/tool remain unchanged.
 parent.ctx.inject(['commands'],c=>c.commands.register({name:'plan',description:'Plan through ordinary Task admission',input:{hint:'[off|message]',attachments:true},handler:plan.command}));
 return {ctx,parent,left,right,foreign,tasks,plan,submits,audit,questions,setTargets:t=>targets=t,deny:()=>accept=false,
  invoke:(rawInput='',attachments=[],signal=new AbortController().signal)=>plan.command({agent:parent,commandId:'human-plan',rawInput,attachments,signal}),
  async close(){await ctx.fiber.dispose();}};
}

test('public /plan text uses ordinary admission without steering the projection and binds only admitted real lanes',async()=>{
 const f=await fixture();try{
  const result=await f.ctx.commands.execute(f.parent,'/plan inspect the uploaded source',[],new AbortController().signal);
  assert.equal(result.result.kind,'success');assert.equal(f.submits.length,1);const input=f.submits[0];
  assert.deepEqual(input.content,[{type:'text',text:'inspect the uploaded source'}]);
  assert.equal(f.parent.session.snapshotEvents().filter(e=>e.type==='user/message').length,0);
  assert.equal(f.parent.status,'idle');assert.equal(f.ctx.planMode.get(f.left).active,false);
  for(const agent of [f.left,f.right])f.plan.bind(input.intent,f.tasks.get(agent.id),agent);
  assert.equal(f.ctx.planMode.get(f.left).active,true);assert.equal(f.ctx.planMode.get(f.right).active,true);
  assert.equal(f.parent.session.snapshotEvents().filter(e=>e.type==='command/run').length,1);
  assert.equal(f.parent.session.snapshotEvents().filter(e=>e.type==='command/done').length,1);
  assert.throws(()=>f.plan.bind({...input.intent},f.tasks.get(f.left.id),f.left),/Unapproved/);
  assert.throws(()=>f.plan.bind(input.intent,f.tasks.get(f.left.id),f.left),/already bound/);
 }finally{await f.close();}
});

test('attachments retain native identity, rejected admission and cancellation never create work',async()=>{
 const f=await fixture();try{
  const attachment={type:'file',ref:{id:'source-receipt',sha256:'a'.repeat(64),name:'study.pdf'}};
  await f.invoke(' examine source',[attachment]);assert.equal(f.submits[0].content[0],attachment);
  f.deny();assert.equal((await f.invoke('blocked')).kind,'error');
  assert.throws(()=>f.plan.bind(f.submits[1].intent,f.tasks.get(f.left.id),f.left),/Unapproved/);
  const abort=new AbortController();abort.abort();await assert.rejects(f.invoke('cancelled',[],abort.signal),/abort/i);
  assert.equal(f.submits.length,2);assert.equal((await f.invoke('off',[attachment])).kind,'error');
  assert.equal(f.left.status,'idle');assert.equal(f.right.status,'idle');
 }finally{await f.close();}
});

test('mode-only controls validate every lane before mutation and later admitted lanes inherit native selection',async()=>{
 const f=await fixture();try{
  f.setTargets([f.left,f.foreign]);await assert.rejects(f.invoke(''),/does not belong/);
  assert.equal(f.ctx.planMode.get(f.left).active,false);assert.equal(f.ctx.planMode.get(f.parent).active,false);
  f.setTargets([]);await f.invoke('');assert.equal(f.submits.length,0);
  f.plan.inherit(f.parent,f.tasks.get(f.left.id),f.left);assert.equal(f.ctx.planMode.get(f.left).active,true);
  f.tasks.get(f.right.id).status='cancelled';assert.throws(()=>f.plan.inherit(f.parent,f.tasks.get(f.right.id),f.right),/no longer active/);
  f.setTargets([f.left]);await f.invoke('off');assert.equal(f.ctx.planMode.get(f.left).active,false);
  assert.equal(f.ctx.planMode.get(f.parent).active,false);
 }finally{await f.close();}
});

test('a completed historical lane cannot keep a later admitted plan stuck on the public parent',async()=>{
 const f=await fixture();try{
  await f.invoke('');f.tasks.get(f.left.id).status='completed';
  f.plan.inherit(f.parent,f.tasks.get(f.right.id),f.right);
  f.ctx.planMode.set(f.right,false);
  assert.equal(f.ctx.planMode.get(f.left).active,true,'immutable previous lane state is left intact');
  assert.equal(f.ctx.planMode.get(f.parent).active,false,'only the current admitted lane owns the remaining public selection');
 }finally{await f.close();}
});

test('native exit tool asks actual user approval and clears public selection after both lanes exit',async()=>{
 const f=await fixture(),wire=[];
 const frame=(delta,finish_reason=null)=>'data: '+JSON.stringify({id:'plan-local',object:'chat.completion.chunk',created:1,model:'deepseek-flash',choices:[{index:0,delta,finish_reason}]})+'\n\n';
 const server=createServer(async(req,res)=>{
  let raw='';for await(const part of req)raw+=part;const body=JSON.parse(raw);wire.push(body);
  const delta=body.messages.some(m=>m.role==='tool')?{content:'Approved plan is ready.'}:{tool_calls:[{index:0,id:'review-plan',type:'function',function:{name:'exit_plan_mode',arguments:JSON.stringify({plan:'# Source analysis\nRead evidence, then implement after approval.'})}}]};
  res.writeHead(200,{'Content-Type':'text/event-stream'});res.end(frame(delta)+frame({},delta.tool_calls?'tool_calls':'stop')+'data: [DONE]\n\n');
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));server.unref();
 const options=resolveAdapterOptions({baseURL:`http://127.0.0.1:${server.address().port}`,reasoningEffort:'off'});
 f.ctx.llm.registerAdapter(['deepseek-official'],new WebDeepSeekAdapter({options:()=>options,resolveApiKey:async()=>'synthetic-only',resolveUserId:()=>'plan-test',prepareExtensions:async()=>({fields:{},accept:async()=>{}})}));
 try{
  await f.invoke('');const schemaBefore=f.ctx.tools.schemas().map(t=>t.name);
  const tool=f.ctx.tools.get('exit_plan_mode');assert.ok(tool);
  for(const agent of [f.left,f.right]){
   agent.followup(createUserMessage({source:{kind:'user'},content:[{type:'text',text:'Plan the exact source analysis.'}]}));await agent.whenIdle();
   assert.equal(f.questions.at(-1).agent,agent);assert.equal(f.ctx.planMode.get(agent).active,false);
  }
  assert.equal(f.questions.length,2);assert.equal(wire.length,4);assert.equal(f.ctx.planMode.get(f.parent).active,false);
  assert.ok(wire[0].messages.some(m=>JSON.stringify(m.content).includes(PLAN_GUIDANCE)),'native model assembly includes deployment plan policy');
  assert.deepEqual(f.ctx.tools.schemas().map(t=>t.name),schemaBefore,'enter/exit keeps native tool catalog stable');
 }finally{await f.close();server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
});
