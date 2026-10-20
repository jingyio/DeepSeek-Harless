/** Metered same-task delegation using the installed native in-process driver.
 * No new agent loop, credentials, budget account or filesystem authority.
 */
import {AsyncLocalStorage} from 'node:async_hooks';
import {isAgentLoopRequest} from '@deepseek-ai/dsh-llm';
import {parentAgentOptionsForDelegation} from '@deepseek-ai/dsh-subagent';
import {WebDeepSeekAdapter} from './harless_reasoning.ts';
import {assertContextUserEnvelope} from './geneloop_context.ts';
import {digest} from '../motif_core/online_skill_runtime.mjs';
const executionOwners=new WeakMap<object,{root:any;assert:()=>void}>();

/** Host tools resolve workspace from trusted live delegation, never lineage text. */
export function resolveExecutionAgent(ctx:any,agent=ctx.get('agents')?.currentInitiator()):any{
 if(!agent?.session)throw Error('No owning execution agent');
 const owned=executionOwners.get(agent);
 if(owned){owned.assert();if(ctx.get('agents')?.get(owned.root.id)!==owned.root)throw Error('Delegation owner is no longer live');return owned.root;}
 if(!/^(?:session-[a-f0-9-]{36}|sss-[a-f0-9]{32})$/.test(agent.session.id))throw Error('Unrecognized delegated execution agent');
 return agent;
}

export type DelegationHost={
 taskForSession:(id:string)=>any;
 isActive:(task:any)=>boolean;
 onChild?:(child:any,root:any,task:any)=>void;
 audit:(row:any,task:any)=>void;
};

export function installTaskDelegation(ctx:any,host:DelegationHost,
 {nativeProvider='spawn',providerName='geneloop-task'}={}){
 const native=ctx.subagents.getProvider(nativeProvider);
 if(!native)throw Error('Native spawn subagent provider must be loaded first');
 const starts=new AsyncLocalStorage<any>(),bindings=new Map<string,any>(),slots=new Map<any,Set<any>>();
 const assertActive=(task:any,root:any)=>{
  if(!task||ctx.agents.get(root.id)!==root||host.taskForSession(root.session.id)!==task||!host.isActive(task))
   throw Error('Original delegated task is no longer active');
 };
 const ownedParent=(parent:any)=>{
  if(ctx.agents.get(parent.id)!==parent)throw Error('Delegation requires the exact live parent');
  const prior=bindings.get(parent.session.id);
  if(prior){if(prior.child!==parent)throw Error('Delegation parent identity changed');assertActive(prior.task,prior.root);return prior;}
  const task=host.taskForSession(parent.session.id);assertActive(task,parent);
  return {task,root:parent};
 };
 const created=ctx.on('agent/created',({agent}:any)=>{
  const start=starts.getStore();if(!start)return;
  if(start.bound||agent.session.header.parentSession!==start.parent.session.id)throw Error('Unexpected native child publication');
  assertActive(start.task,start.root);start.bound=agent;
  const binding={child:agent,parent:start.parent,root:start.root,task:start.task,prompt:digest(start.request.prompt),
   route:parentAgentOptionsForDelegation(start.root),humans:new Map<string,string>(),current:new Set<string>(),tools:undefined};
  bindings.set(agent.session.id,binding);
  executionOwners.set(agent,{root:start.root,assert:()=>assertActive(start.task,start.root)});
  host.onChild?.(agent,start.root,start.task);
  host.audit({kind:'native_subagent_created',session_id:agent.session.id,parent_session_id:start.parent.session.id,
   execution_session_id:start.root.session.id,budget_session_id:start.task.budget_session_id},start.task);
 },{global:true});
 const remove=(slot:any)=>{
  if(slot.bound){bindings.delete(slot.bound.session.id);executionOwners.delete(slot.bound);}
  slots.get(slot.task)?.delete(slot);if(!slots.get(slot.task)?.size)slots.delete(slot.task);
 };
 const disposeProvider=ctx.subagents.registerProvider({name:providerName,capabilities:{...native.capabilities,outputSchema:false},
  inheritsParentContext:native.inheritsParentContext,
  async start(request:any){
   const {task,root}=ownedParent(request.parent),expected=parentAgentOptionsForDelegation(root);
   for(const field of ['provider','model','reasoningEffort','maxTokens'])
    if(request.agentOptions?.[field]!==undefined&&request.agentOptions[field]!==expected[field])throw Error('Delegated model route cannot exceed its parent task');
   const abort=new AbortController(),slot:any={task,root,parent:request.parent,request,abort,ready:Promise.withResolvers()};
   const signal=AbortSignal.any([request.signal,abort.signal]);signal.throwIfAborted();
   if(!slots.has(task))slots.set(task,new Set());slots.get(task)!.add(slot);
   let published:any;
   try{
    const run=published=await starts.run(slot,()=>native.start({...request,signal}));
    if(!slot.bound||run.localAgent!==slot.bound||run.id!==slot.bound.id)throw Error('Native child identity was not admitted');
    let closed:Promise<void>|undefined;
    const wrapped={...run,dispose(){return closed??=Promise.resolve().then(()=>run.dispose()).finally(()=>remove(slot));}};
    slot.ready.resolve(wrapped);return wrapped;
   }catch(error){slot.abort.abort(error);try{await published?.dispose();}finally{remove(slot);slot.ready.resolve(null);}throw error;}
  },
  // No prepareContinuable: cross-task background continuation needs a separate
  // durable task lifecycle owner; it must not outlive this task's allowance.
 });
 const provider={
  providerName,
  isChild:(id:string)=>bindings.has(id),
  taskForChild:(id:string)=>bindings.get(id)?.task,
  rootForChild:(id:string)=>{const row=bindings.get(id);if(!row)return;assertActive(row.task,row.root);return row.root;},
  transportSession:(id:string)=>{const row=bindings.get(id);if(!row)return;assertActive(row.task,row.root);return row.root.session.id;},
  authorizeRequest(q:any){
   const row=bindings.get(q.sessionId);if(!row)return undefined;
   assertActive(row.task,row.root);
   if(ctx.agents.get(row.child.id)!==row.child||!isAgentLoopRequest(q))throw Error('Unapproved native child request');
   for(const field of ['provider','model','reasoningEffort','maxTokens'])if(q[field]!==row.route[field])throw Error('Delegated model route changed');
   if(q.messages.some((message:any)=>message.source?.kind==='goal'))throw Error('Delegated goals require their own lifecycle admission');
   for(const event of row.child.session.snapshotEvents())if(event.type==='user/message'&&event.data.source?.kind==='user'){
    if(digest(event.data.content)!==row.prompt)throw Error('Delegated user envelope changed');
    row.humans.set(event.data.id,digest(event.data.content));row.current.add(event.data.id);
   }
   assertContextUserEnvelope(q,row.child.session,row.humans,row.current);
   const tools=q.tools??[],allowed=new Map(row.task.tools.map((tool:any)=>[tool.name,digest(tool)]));
   if(tools.some((tool:any)=>allowed.get(tool.name)!==digest(tool)))throw Error('Delegated tool schema exceeds parent task');
   if(row.tools===undefined)row.tools=digest(tools);else if(row.tools!==digest(tools))throw Error('Delegated tool schema changed');
   host.audit({kind:'native_subagent_model_request',session_id:row.child.id,execution_session_id:row.root.id,
    budget_session_id:row.task.budget_session_id,tools_sha256:row.tools},row.task);
   return row;
  },
  async drain(task:any){
   const current=[...(slots.get(task)??[])];for(const slot of current)slot.abort.abort(new Error('Parent task ended'));
   await Promise.all(current.map(async slot=>{const run=await slot.ready.promise;if(run)await run.dispose();}));
  },
  async close(){disposeProvider();created();await Promise.all([...slots.keys()].map(task=>provider.drain(task)));},
 };
 return provider;
}

/** Rewrite only the final provider transport header, after the immutable native
 * child request has passed the host guard. Its native history keeps its own id.
 */
export class TaskDelegationAdapter extends WebDeepSeekAdapter{
 private delegation:any;
 constructor(config:any,models:any[],delegation:any){super(config,models);this.delegation=delegation;}
 private transport(q:any){const owner=this.delegation.transportSession(q.sessionId);return owner?{...q,sessionId:owner}:q;}
 override async prepareCall(...args:Parameters<WebDeepSeekAdapter['prepareCall']>){
  const prepared=await super.prepareCall(...args);return {...prepared,stream:(q:any)=>prepared.stream(this.transport(q))};
 }
 override stream(q:any){return super.stream(this.transport(q));}
}
