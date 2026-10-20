/** Real GeneLoop public controller wrapping native AgentLoop/CommandRuntime.
 * In-memory host storage and no model calls; exercises first-create ownership order.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {randomUUID} from 'node:crypto';
import {Context} from '@deepseek-ai/cordis';
import {AgentRegistry} from '@deepseek-ai/dsh-agent';
import {AgentLoop} from '@deepseek-ai/dsh-agent-loop';
import {SessionStore} from '@deepseek-ai/dsh-session';
import {SessionProjectionRegistry} from '@deepseek-ai/dsh-session-projection';
import {SystemPrompt} from '@deepseek-ai/dsh-system-prompt';
import {ToolRuntime} from '@deepseek-ai/dsh-tools';
import {LlmRuntime} from '@deepseek-ai/dsh-llm';
import {CommandRuntime} from '@deepseek-ai/dsh-commands';
import {TokenMeter} from '@deepseek-ai/dsh-token-meter';
import {SubagentRuntime} from '@deepseek-ai/dsh-subagent';
import {apply as nativeSpawn} from '@deepseek-ai/dsh-subagent-spawn-in-process';
import {ApiSessionNotFound} from '@deepseek-ai/dsh-api-session-controller';
import {apply as nativeCompact} from '@deepseek-ai/dsh-command-compact';
import {apply as mountTasks} from '../src/adapters/dsh_web_tasks.ts';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';

async function fixture({restored=false}={}){
 const directory=mkdtempSync(join(tmpdir(),'geneloop-public-commands-')),ctx=new Context(),groups=new Map(),headers=new Map();
 const policy={output:directory,endpoint:'http://127.0.0.1:1/v1',control_endpoint:'http://127.0.0.1:1',control_token:'diagnostic-only',
  allowed_tools:[],capability_profile:'new-scene',mode:'baseline',budget_usd:null,max_output_tokens:393216,provider_mode:'mock',
  scenes:[{id:'new-scene',label:'Chat',preset:'sss-task',allowed_tools:[]}]};
 const path=join(directory,'policy.json');writeFileSync(path,JSON.stringify(policy));
 const prior=process.env.SSS_WEB_POLICY,priorHome=process.env.DSH_HOME;process.env.SSS_WEB_POLICY=path;delete process.env.DSH_HOME;
 const restoredParent='session-'+randomUUID(),restoredPrivate='session-'+randomUUID();
 if(restored){const scope=digest({output:directory,home:null});
  writeFileSync(join(directory,'session-ownership-'+scope+'.json'),JSON.stringify({scope,sessions:[restoredParent,restoredPrivate],bound:[],chat_only_sessions:[]}));
  writeFileSync(join(directory,'private-lane-sessions.json'),JSON.stringify({version:1,principal:'local-operator',sessions:{[restoredPrivate]:restoredParent}}));}
 new SessionStore(ctx);new AgentRegistry(ctx);new SessionProjectionRegistry(ctx);new SystemPrompt(ctx,{});new ToolRuntime(ctx,{});new LlmRuntime(ctx);
 new CommandRuntime(ctx);new TokenMeter(ctx);new SubagentRuntime(ctx);nativeSpawn(ctx,{providerName:'spawn'});nativeCompact(ctx);
 const loop=new AgentLoop(ctx,{agents:[]});
 ctx.agentPresets={async mount(){},async select(){}};
 ctx.attachments={async admitPromptContent(content){return content;}};
 ctx.fileUploads={bindPrompt(){return {commit(){},[Symbol.dispose](){}};},resolve(){}};
 ctx.workspaceRegistry={list:()=>[...groups.values()],get:id=>groups.get(id),archivedSessionIds:[],async create(path,title){
  const group={id:'workspace-'+randomUUID(),path,title,sessionIds:[],async attachSession(id){if(!this.sessionIds.includes(id))this.sessionIds.push(id);}};groups.set(group.id,group);return group;
 }};
 ctx.workspaceController={async *follow(){yield {type:'baseline',value:{items:[],archivedSessionIds:[]}};},
  async rename({workspaceId,title}){const workspace=groups.get(workspaceId);workspace.title=title;return {workspace};},
  async archiveSession(){return {archivedSessionIds:[]};},
  async insertSessionBefore({workspaceId,sessionId}){const workspace=groups.get(workspaceId);await workspace.attachSession(sessionId);return {workspace};}};
 ctx.connection={fetch:{register(){return()=>{};}},requestRejection(){return 401;}};
 ctx.webServer={register(){return()=>{};},tapIndex(){return()=>{};}};
 const underlying={
  async create(request){
   const id=request.sessionId??'session-'+randomUUID();let agent=ctx.agents.get(id);
   if(!agent){agent=await loop.create(id,{provider:'deepseek-official',model:'deepseek-flash',reasoningEffort:'off',maxTokens:393216});
    headers.set(id,{id,agentPreset:request.agentPreset,cwd:request.cwd??groups.get(request.workspaceId)?.path});}
   if(request.workspaceId)await groups.get(request.workspaceId).attachSession(id);
   return {sessionId:id,agentPreset:request.agentPreset};
  },
  async inspect(id){const agent=ctx.agents.get(id);if(!agent)throw new ApiSessionNotFound('Unknown diagnostic session');return {meta:headers.get(id),events:agent.session.snapshotEvents()};},
  async selectModel(request){return request;},async rename({sessionId,title}){headers.get(sessionId).title=title;return {title};},
  async prompt(){throw Error('No model work is authorized by this diagnostic');},async cancel(){return {accepted:true};},
  async list(){return {items:[...headers.keys()].map(sessionId=>({sessionId}))};},async search(){return this.list();},
  async page(){return {records:[],hasMore:false};},async *follow(){},
 };
 ctx.sessionController={...underlying};
 const nativePlan={name:'plan',description:'Global unsafe plan sentinel',input:{hint:'[message]',attachments:true},handler(){throw Error('Global plan bypassed Task admission');}};
 const nativeGoal={name:'goal',description:'Global unsafe goal sentinel',input:{hint:'[objective]',attachments:true},handler(){throw Error('Global goal bypassed Task admission');}};
 ctx.commands.register(nativePlan);ctx.commands.register(nativeGoal);
 const restoreEnv=()=>{if(prior===undefined)delete process.env.SSS_WEB_POLICY;else process.env.SSS_WEB_POLICY=prior;if(priorHome===undefined)delete process.env.DSH_HOME;else process.env.DSH_HOME=priorHome;};
 try{mountTasks(ctx);}catch(error){await ctx.fiber.dispose();restoreEnv();rmSync(directory,{recursive:true,force:true});throw error;}
 const unowned=await underlying.create({sessionId:'session-'+randomUUID()}),foreign=ctx.agents.get(unowned.sessionId);
 const globals=Object.fromEntries(['plan','goal','compact'].map(name=>[name,ctx.commands.find(foreign,name)]));
 return {ctx,directory,nativePlan,nativeGoal,globals,underlying,restoredParent,restoredPrivate,async close(){await ctx.fiber.dispose();restoreEnv();rmSync(directory,{recursive:true,force:true});}};
}

test('fresh public controller.create installs scoped native command routes after ownership admission and is idempotent',async()=>{
 const f=await fixture();try{
  const created=await f.ctx.sessionController.create({}),agent=f.ctx.agents.get(created.sessionId);assert.ok(agent);
  const plan=f.ctx.commands.find(agent,'plan'),goal=f.ctx.commands.find(agent,'goal'),compact=f.ctx.commands.find(agent,'compact');
  assert.notEqual(plan.handler,f.globals.plan.handler);assert.notEqual(goal.handler,f.globals.goal.handler);assert.notEqual(compact.handler,f.globals.compact.handler);
  const signal=new AbortController().signal;
  assert.equal((await f.ctx.commands.execute(agent,'/plan',[],signal)).result.kind,'success');assert.equal(f.ctx.planMode.get(agent).active,true);
  assert.equal((await f.ctx.commands.execute(agent,'/plan off',[],signal)).result.kind,'success');assert.equal(f.ctx.planMode.get(agent).active,false);
  assert.equal((await f.ctx.commands.execute(agent,'/goal bare inferred objective',[],signal)).result.kind,'error');assert.equal(f.ctx.goals.get(agent),undefined);
  await f.ctx.sessionController.create({sessionId:created.sessionId});assert.equal(f.ctx.commands.find(agent,'plan'),plan);
  assert.equal(f.ctx.commands.list(agent).filter(c=>['plan','goal','compact'].includes(c.name)).length,3);
  assert.equal(agent.session.snapshotEvents().filter(e=>e.type==='user/message').length,0,'control commands never drive the public parent');
 }finally{await f.close();}
});

test('cold owned public agents receive the same scoped routes while persisted private lanes keep native command scope',async()=>{
 const f=await fixture({restored:true});try{
  await f.underlying.create({sessionId:f.restoredParent});await f.underlying.create({sessionId:f.restoredPrivate});
  const parent=f.ctx.agents.get(f.restoredParent),child=f.ctx.agents.get(f.restoredPrivate);
  for(const name of ['plan','goal','compact']){
   assert.notEqual(f.ctx.commands.find(parent,name).handler,f.globals[name].handler);
   assert.equal(f.ctx.commands.find(child,name).handler,f.globals[name].handler);
  }
  await assert.rejects(f.ctx.sessionController.create({sessionId:f.restoredPrivate}),e=>e.code==='comparison_child');
 }finally{await f.close();}
});
