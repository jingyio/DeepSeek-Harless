/** Native plan state with public commands admitted through the existing Task owner.
 * A public comparison session is a projection, never an alternate model driver.
 */
export const PLAN_GUIDANCE=`The user selected plan mode. Investigate the request and prepare a concrete plan using read-only inspection. Do not implement changes yet. Ask focused questions when information is missing. When ready, present the complete plan through exit_plan_mode for the user's approval. Plan mode is collaboration guidance; the existing tool permissions, task meter and cancellation rules still apply.`;

export type PlanHost={
 ensureOwned:(sessionId:string)=>Promise<unknown>;
 taskForSession:(sessionId:string)=>any;
 isActive:(task:any)=>boolean;
 currentTargets:(parent:any)=>Promise<any[]>;
 ownsLane:(parentSessionId:string,lane:any,task?:any)=>boolean;
 submit:(input:{intent:any;parentSessionId:string;content:any[];signal:AbortSignal})=>Promise<any>;
 audit:(row:any,task?:any)=>void;
};

export function createPlanAdmission(ctx:any,host:PlanHost){
 const intents=new WeakMap<object,{parent:any;signal:AbortSignal;bound:WeakSet<object>}>();
 const parents=new WeakMap<object,any>(),lanes=new WeakMap<object,Set<any>>(),laneTasks=new WeakMap<object,any>();
 const live=(agent:any)=>{if(!agent?.session||ctx.agents.get(agent.id)!==agent)throw Error('Plan requires the exact live agent');};
 const lane=(parent:any,agent:any,task?:any)=>{
  live(parent);live(agent);
  if(!host.ownsLane(parent.session.id,agent,task))throw Error('Plan target does not belong to this public session');
  if(task&&(!host.isActive(task)||host.taskForSession(agent.session.id)!==task||task.request?.session_id!==agent.session.id))
   throw Error('Plan task is no longer active');
 };
 const select=(parent:any,agent:any,active:boolean,task?:any)=>{
  if(agent===parent)live(parent);else lane(parent,agent,task);
  const result=ctx.planMode.set(agent,active);
  host.audit({kind:'native_plan_selected',public_session_id:parent.session.id,session_id:agent.session.id,active,result},task);
  return result;
 };
 const track=(parent:any,agent:any,task=host.taskForSession(agent.session.id))=>{
  if(agent===parent)return;
  parents.set(agent.session,parent);let set=lanes.get(parent);if(!set)lanes.set(parent,set=new Set());
  for(const old of set){const owner=laneTasks.get(old);if(ctx.agents.get(old.id)!==old||owner&&!host.isActive(owner))set.delete(old);}
  set.add(agent);if(task)laneTasks.set(agent,task);
 };
 // An approved native exit must also clear the public selection once every
 // current lane has exited, so the next task does not re-enter plan mode.
 ctx.on('session/event',(session:any,event:any)=>{
  if(event.type!=='plan/mode'||event.data.active)return;
  const parent=parents.get(session);if(!parent||ctx.agents.get(parent.id)!==parent)return;
  const current=[...(lanes.get(parent)??[])].filter(agent=>ctx.agents.get(agent.id)===agent);
  if(current.every(agent=>{const s=ctx.planMode.get(agent);return !(s.pending??s.active);}))select(parent,parent,false);
 },{global:true});
 return {
  /** Use as the scoped public /plan handler; the native controller owns state and exit review. */
  async command(invocation:any){
   const {agent:parent,signal,attachments=[]}=invocation;live(parent);await host.ensureOwned(parent.session.id);signal.throwIfAborted();
   const message=invocation.rawInput.trim();
   if(message==='off'&&attachments.length)return {kind:'error',text:'Attachments cannot accompany /plan off.'};
   if(message==='off'||(!message&&!attachments.length)){
    const active=message!=='off',targets=await host.currentTargets(parent);signal.throwIfAborted();
    // Validate the complete set before changing any state. Parent remembers the
    // explicit selection for a later fresh lane, without steering a model.
    targets.forEach(target=>lane(parent,target));
    select(parent,parent,active);
    for(const target of new Set(targets))if(target!==parent){track(parent,target);select(parent,target,active);}
    return {kind:'success',text:active?'已进入计划模式；下一条消息会按普通任务处理。':'已退出计划模式。'};
   }
   const content=[...attachments,...message?[{type:'text',text:message}]:[]];
   const intent=Object.freeze({kind:'plan',parentSessionId:parent.session.id,commandId:invocation.commandId});
   intents.set(intent,{parent,signal,bound:new WeakSet()});
   try{
    const result=await host.submit({intent,parentSessionId:parent.session.id,content,signal});
    signal.throwIfAborted();if(result?.kind==='error'){intents.delete(intent);return result;}
    if(!lanes.get(parent)?.size)select(parent,parent,true);
    return result??{kind:'success',text:'计划请求已提交。'};
   }catch(error){intents.delete(intent);throw error;}
  },
  /** Call after ordinary admission/binding, before submitting its original user message. */
  bind(intent:any,task:any,agent:any){
   const entry=intents.get(intent);if(!entry)throw Error('Unapproved plan intent');entry.signal.throwIfAborted();
   lane(entry.parent,agent,task);
   if(entry.bound.has(agent))throw Error('Plan intent was already bound to this lane');
   entry.bound.add(agent);track(entry.parent,agent,task);select(entry.parent,entry.parent,true);select(entry.parent,agent,true,task);
  },
  /** A later admitted task inherits only the human-selected public plan state. */
  inherit(parent:any,task:any,agent:any){
   lane(parent,agent,task);track(parent,agent,task);const state=ctx.planMode.get(parent);
   return select(parent,agent,state.pending??state.active,task);
  }
 };
}
