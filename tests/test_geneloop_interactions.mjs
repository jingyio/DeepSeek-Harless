import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {Context} from '@deepseek-ai/cordis';
import {AgentRegistry} from '@deepseek-ai/dsh-agent';
import {AgentLoop} from '@deepseek-ai/dsh-agent-loop';
import {SessionStore} from '@deepseek-ai/dsh-session';
import {SessionProjectionRegistry} from '@deepseek-ai/dsh-session-projection';
import {SystemPrompt} from '@deepseek-ai/dsh-system-prompt';
import {ToolRuntime} from '@deepseek-ai/dsh-tools';
import {LlmRuntime} from '@deepseek-ai/dsh-llm';
import {PlanModeController} from '@deepseek-ai/dsh-plan-mode';
import {UserQuestionService} from '@deepseek-ai/dsh-user-questions';
import {createInteractionBridge} from '../src/adapters/geneloop_interactions.ts';
test('native questions preserve pending human choice and exact public parent/lane ownership',async()=>{
 const agent={},owner={session:'parent',task:'active',lane:'motif'};let live=true;
 const bridge=createInteractionBridge(caller=>caller===agent&&live?owner:undefined),abort=new AbortController();
 const request={agent,signal:abort.signal,questions:[{id:'q',question:'Which?',options:[{label:'A'},{label:'B'}]}]};
 const result=bridge.ask(request,()=>{throw Error('not native fallback');}),row=bridge.list('parent')[0];
 assert.equal(row.lane,'motif');assert.deepEqual(bridge.list('foreign'),[]);
 assert.throws(()=>bridge.answer('foreign',row.id,[{id:'q',selected:['A']}]),e=>e.status===404);
 assert.throws(()=>bridge.answer('parent',row.id,[{id:'q',selected:['invented']}]),e=>e.status===400);
 assert.throws(()=>bridge.answer('parent',row.id,[{id:'q',selected:['A','B']}]),e=>e.status===400);
 bridge.answer('parent',row.id,[{id:'q',selected:['B'],custom:'中文补充'}]);
 assert.deepEqual(await result,{answers:[{id:'q',selected:['B'],custom:'中文补充'}]});
 assert.equal(bridge.list('parent').length,0);assert.throws(()=>bridge.answer('parent',row.id,[]));
});
test('cancel, task replacement and foreign callers cannot resolve an old human question',async()=>{
 const agent={};let owner={session:'p',task:'a',lane:'baseline'};
 const bridge=createInteractionBridge(caller=>caller===agent?owner:undefined),abort=new AbortController();
 const promise=bridge.ask({agent,signal:abort.signal,questions:[{id:'q',question:'Input'}]},()=>{});
 const id=bridge.list('p')[0].id;owner={...owner,task:'new'};
 assert.throws(()=>bridge.answer('p',id,[{id:'q',selected:[],custom:'yes'}]),e=>e.status===409);
 abort.abort();await assert.rejects(promise,{name:'AbortError'});assert.deepEqual(bridge.list('p'),[]);
 assert.equal(await bridge.ask({agent:{},questions:[]},async()=>42),42);
});

test('browser-shaped blank custom answers reach real native plan approval as an actual selection',async()=>{
 const ctx=new Context();new SessionStore(ctx);new AgentRegistry(ctx);new SessionProjectionRegistry(ctx);
 new SystemPrompt(ctx,{});new ToolRuntime(ctx,{});new LlmRuntime(ctx);new UserQuestionService(ctx);
 const loop=new AgentLoop(ctx,{agents:[]});new PlanModeController(ctx,{section:'Investigate and present the plan for explicit approval.'});
 const agent=await loop.create('session-'+randomUUID(),{provider:'deepseek-official',model:'deepseek-flash'});
 const bridge=createInteractionBridge(caller=>caller===agent?{session:'public-parent',task:'original-live-task',lane:'motif'}:undefined);
 ctx.on('user-questions/request',(q,next)=>bridge.ask(q,next),{global:true});
 try{
  for(const custom of ['', ' \n ']){
   ctx.planMode.set(agent,true);
   const result=ctx.tools.get('exit_plan_mode').execute({plan:'# Approved evidence plan\nInspect the source and preserve its SHA.'},{agent,signal:new AbortController().signal});
   await Promise.resolve();const [row]=bridge.list('public-parent');assert.equal(row.lane,'motif');
   assert.equal(row.questions[0].intent.kind,'plan-review');
   bridge.answer('public-parent',row.id,[{id:'plan-review',selected:['Approve'],custom}]);
   assert.deepEqual(await result,{approved:true});assert.equal(ctx.planMode.get(agent).pending,false);
   assert.equal(bridge.list('public-parent').length,0);
  }
 }finally{bridge.dispose();await ctx.fiber.dispose();}
});
