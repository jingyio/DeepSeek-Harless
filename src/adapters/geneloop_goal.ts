/** Human-selected finite native goal rounds remain inside one admitted Task.
 * Native GoalService and goal-round-driver own the durable state and loop.
 */
import {isAgentLoopRequest} from '@deepseek-ai/dsh-llm';
import {renderGoalRoundPrompt} from '@deepseek-ai/dsh-goal-round-driver';
import {digest} from '../motif_core/online_skill_runtime.mjs';
import {assertContextUserEnvelope} from './geneloop_context.ts';

export const GOAL_GUIDANCE=`A goal can be created or rearmed only by an explicit human /goal command with a positive integer round count. Do not infer permission to create a goal or change its objective or round count. During an admitted goal, use get_goal and update_goal to mark verified completion or a concrete persistent blocker under the native goal policy. All continuation rounds use this same task, workspace, tool permissions and meter. The chosen round count is finite; it is not an unlimited run.`;
export type GoalHost={
 ensureOwned:(id:string)=>Promise<unknown>;
 taskForSession:(id:string)=>any;
 isActive:(task:any)=>boolean;
 ownsLane:(parentSessionId:string,agent:any,task?:any)=>boolean;
 currentTargets:(parent:any)=>Promise<any[]>;
 submit:(input:{intent:any;parentSessionId:string;content:any[];signal:AbortSignal;resumeTargets?:any[]})=>Promise<any>;
 audit:(row:any,task?:any)=>void;
};
const ref=(goal:any)=>({id:goal.id,revision:goal.revision});

export function createGoalAdmission(ctx:any,host:GoalHost){
 const intents=new WeakMap<object,any>(),bindings=new Map<any,any>(),retiring=new Map<any,any>();
 const live=(agent:any)=>{if(!agent?.session||ctx.agents.get(agent.id)!==agent)throw Error('Goal requires the exact live agent');};
 const assertLane=(parent:any,agent:any,task?:any)=>{
  live(parent);live(agent);
  if(!host.ownsLane(parent.session.id,agent,task))throw Error('Goal lane does not belong to this public session');
  if(task&&(!host.isActive(task)||host.taskForSession(agent.session.id)!==task||task.request?.session_id!==agent.session.id))throw Error('Goal task is no longer active');
 };
 const assertBinding=(b:any)=>{
  assertLane(b.parent,b.agent,b.task);
  const goal=ctx.goals.get(b.agent);
  if(!goal||goal.id!==b.goalId||goal.objective!==b.objective||goal.maxGoalRounds!==b.rounds)throw Error('Approved goal definition changed');
  return goal;
 };
 ctx.on('agent/pre-step',async({agent,signal}:any,next:any)=>{
  const decision=await next(),b=bindings.get(agent);
  if(!b||b.started||decision.kind==='reject'||signal.aborted)return decision;
  assertLane(b.parent,agent,b.task);
  const human=decision.messages.find((m:any)=>m.source?.kind==='user'&&digest(m.content)===b.contentDigest);
  if(!human)throw Error('Goal requires the original admitted human objective');
  b.initialId=human.id;
  const current=ctx.goals.get(agent);
  let goal;
  if(b.resume){
   if(!current||current.id!==b.expected.id||current.revision!==b.expected.revision||current.objective!==b.objective||current.maxGoalRounds!==b.rounds)
    throw Error('Goal changed before admitted resume');
   goal=ctx.goals.resume(agent,ref(current));
  }else goal=ctx.goals.create(agent,{objective:b.objective,maxGoalRounds:b.rounds});
  b.goalId=goal.id;b.started=true;
  host.audit({kind:'native_goal_admitted',session_id:agent.session.id,public_session_id:b.parent.session.id,
   goal_id:goal.id,rounds:b.rounds,operation:b.resume?'resume':'create'},b.task);
  return decision;
 },{global:true});
 // Native model goal mutations cannot mint a new Task, change the selected
 // objective/cap, or rearm after cancellation. The native tool still performs
 // its own live-driver, CAS and consecutive-blocker checks after this gate.
 ctx.on('tools/pre-execute',(exec:any,next:any)=>{
  if(exec.name==='create_goal')return {kind:'deny',reason:'Create a goal with an explicit human /goal --rounds command.'};
  if(exec.name==='update_goal'){
   const b=bindings.get(exec.agent);if(!b?.started)return {kind:'deny',reason:'No active human-admitted goal owns this task.'};
   assertBinding(b);
   if(!['complete','blocked'].includes(exec.arguments?.action))return {kind:'deny',reason:'Goal definition and activation require an explicit human command.'};
  }
  return next();
 },{global:true});
 return {
  async command(invocation:any){
   const {agent:parent,signal,attachments=[]}=invocation;live(parent);await host.ensureOwned(parent.session.id);signal.throwIfAborted();
   const raw=invocation.rawInput.trim(),control=['','pause','clear','resume'].includes(raw);
   if(control&&attachments.length)return {kind:'error',text:'目标状态命令不能携带附件。'};
   let entry:any,resumeTargets:any[]|undefined;
   if(control){
    const targets=await host.currentTargets(parent);signal.throwIfAborted();targets.forEach(agent=>assertLane(parent,agent));
    const rows=targets.map(agent=>({agent,goal:ctx.goals.get(agent)}));
    if(raw==='')return {kind:'success',text:rows.filter(r=>r.goal).map(({goal:g},i)=>`目标 ${i+1}: ${g.phase}，已启动 ${g.roundsStarted}/${g.maxGoalRounds} 轮；${g.objective}`).join('\n')||'当前没有目标。用 /goal --rounds <正整数> <目标> 明确开始。'};
    if(raw==='pause'||raw==='clear'){
     for(const {agent,goal} of rows){
      if(raw==='clear'){
       const b=bindings.get(agent),boundary=ctx.sessionProjections.stateOf(agent.session,'turnBoundary');
       // Clearing removes continuation authority immediately. The already
       // accepted round may finish its current turn under the original Task;
       // this exact turn fence cannot authorize another autonomous round.
       if(b?.started&&goal&&boundary&&boundary.openTurnStartSeq!==null){
        const round=agent.session.snapshotEvents().findLast((e:any)=>e.seq>boundary.openTurnStartSeq&&e.type==='user/message'&&
         e.data.source?.kind==='goal'&&e.data.source.goalId===b.goalId);
        if(round)retiring.set(agent,{...b,turnSeq:boundary.openTurnStartSeq,round:round.data.source.round});
       }
       bindings.delete(agent);
       if(goal)ctx.goals.clear(agent,ref(goal));
      }else if(goal?.phase==='active')ctx.goals.pause(agent,ref(goal));
     }
     return {kind:'success',text:raw==='clear'?'目标已清除；历史记录保留。':'目标已暂停。'};
    }
    if(!rows.length||rows.some(r=>!r.goal||r.goal.phase==='complete'||r.goal.roundsStarted>=r.goal.maxGoalRounds))
     return {kind:'error',text:'当前没有可恢复且仍有剩余轮次的目标。'};
    if(new Set(rows.map(r=>digest({objective:r.goal.objective,rounds:r.goal.maxGoalRounds}))).size!==1)
     return {kind:'error',text:'两个执行侧的目标定义不同，请分别处理。'};
    const g=rows[0].goal;resumeTargets=targets;
    entry={parent,signal,objective:g.objective,rounds:g.maxGoalRounds,resume:true,
     expected:new Map(rows.map(r=>[r.agent,{id:r.goal.id,revision:r.goal.revision}])),bound:new WeakSet()};
   }else{
    const match=/^--rounds\s+([1-9]\d*)\s+([\s\S]+)$/.exec(raw),rounds=match?Number(match[1]):NaN;
    if(!match||!Number.isSafeInteger(rounds)||!match[2].trim())return {kind:'error',text:'请明确指定有限轮次：/goal --rounds <正整数> <目标>。'};
    entry={parent,signal,objective:match[2].trim(),rounds,resume:false,bound:new WeakSet()};
   }
   const content=[...attachments,{type:'text',text:entry.resume?`请恢复此前明确授权的目标：${entry.objective}`:entry.objective}];
   entry.contentDigest=digest(content);
   const intent=Object.freeze({kind:'goal',parentSessionId:parent.session.id,commandId:invocation.commandId,rounds:entry.rounds,resume:entry.resume});
   intents.set(intent,entry);
   try{const result=await host.submit({intent,parentSessionId:parent.session.id,content,signal,...resumeTargets?{resumeTargets}:{}});
    signal.throwIfAborted();if(result?.kind==='error')intents.delete(intent);
    return result??{kind:'success',text:`目标已提交，明确选择 ${entry.rounds} 轮。`};
   }catch(error){intents.delete(intent);throw error;}
  },
  /** Register before ordinary input submission; arm only after its accepted native pre-step. */
  bind(intent:any,task:any,agent:any,nativeUserContent?:readonly any[]){
   const e=intents.get(intent);if(!e)throw Error('Unapproved goal intent');e.signal.throwIfAborted();assertLane(e.parent,agent,task);
   if(e.bound.has(agent)||bindings.has(agent)||retiring.has(agent))throw Error('Goal lane already has an admitted owner');
   if(e.resume&&!e.expected.has(agent))throw Error('Resume must use its existing real execution lane');
   // The ordinary Task owner may normalize durable attachment refs before
   // submission. This is a host-only attestation, never a browser argument.
   const expectedText=e.resume?`请恢复此前明确授权的目标：${e.objective}`:e.objective;
   if(nativeUserContent&&!nativeUserContent.some(p=>p.type==='text'&&p.text===expectedText))throw Error('Normalized goal input lost the explicit objective');
   e.bound.add(agent);bindings.set(agent,{...e,agent,task,contentDigest:nativeUserContent?digest(nativeUserContent):e.contentDigest,
    started:false,expected:e.resume?e.expected.get(agent):undefined});
  },
  /** Check every source against its own immutable journal. Only current
   * native rounds additionally need the still-active original Task binding.
   * Historical, authenticated goal input does not arm an ordinary new task.
   */
  authorizeRequest(request:any,task:any,agent:any){
   live(agent);if(request.sessionId!==agent.session.id||!isAgentLoopRequest(request))throw Error('Goal requests require the native live driver');
   const events=agent.session.snapshotEvents(),users=new Map(events.filter((e:any)=>e.type==='user/message').map((e:any)=>[e.data.id,e]));
   for(const message of request.messages){if(message.source?.kind!=='goal')continue;
    const event:any=users.get(message.id),s=message.source;
    if(!event||digest(event.data)!==digest(message)||!Number.isSafeInteger(s.round)||s.round<1)throw Error('Untrusted goal round source');
    const definition=events.findLast((e:any)=>e.seq<event.seq&&e.type==='goal/change'&&e.data.goal?.id===s.goalId&&e.data.goal.revision===s.revision)?.data.goal;
    if(!definition||definition.phase!=='active'||s.round>definition.maxGoalRounds||digest(message.content)!==digest(renderGoalRoundPrompt(definition,s.round)))
     throw Error('Goal source does not match the native admitted round prompt');
   }
   const boundary=ctx.sessionProjections.stateOf(agent.session,'turnBoundary');
   if(!boundary||boundary.openTurnStartSeq===null)return false;
   const current=events.filter((e:any)=>e.seq>boundary.openTurnStartSeq&&e.type==='user/message'&&e.data.source?.kind==='goal');
   if(!current.length)return false;
   const active=bindings.get(agent),b=active??retiring.get(agent);if(!b?.started||b.task!==task)throw Error('Goal continuation has no admitted Task');
   let goal;
   if(active)goal=assertBinding(b);
   else{
    assertLane(b.parent,agent,task);
    if(boundary.openTurnStartSeq!==b.turnSeq||ctx.goals.get(agent)!==undefined)throw Error('Cleared goal cannot authorize another turn');
    goal={id:b.goalId,roundsStarted:b.round};
   }
   if(current.length!==1||current[0].data.source.goalId!==goal.id||current[0].data.source.round!==goal.roundsStarted||
    current[0].data.source.round>b.rounds)throw Error('Goal round does not match its admitted definition');
   const humans=new Map<string,string>(events.filter((e:any)=>e.type==='user/message'&&e.data.source?.kind==='user').map((e:any)=>[e.data.id,digest(e.data.content)]));
   assertContextUserEnvelope(request,agent.session,humans,new Set([b.initialId]));
   return true;
  },
  keepTask(task:any,agent:any){
   const b=bindings.get(agent);if(!b||b.task!==task)return false;
   if(!b.started){assertLane(b.parent,agent,task);return true;}
   const g=assertBinding(b);return g.phase==='active'&&g.activation==='armed';
  },
  /** Call before cancelling/unbinding the original meter. No durable status is forged. */
  disarmTask(task:any){
   for(const [agent,b] of [...bindings,...retiring]){if(b.task!==task)continue;
    if(ctx.agents.get(agent.id)===agent)ctx.goals.disarm(agent);
    bindings.delete(agent);retiring.delete(agent);
   }
  }
 };
}
