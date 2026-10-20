/** Forward one high-risk decision to the existing native account UI. */
import {readFileSync,writeFileSync,existsSync,mkdirSync,renameSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {randomUUID} from 'node:crypto';
import {digest} from '../motif_core/online_skill_runtime.mjs';
export const name='file-native-approval';
export const inject=['agents'];
export function apply(ctx:any){
 const home=resolve(process.env.HARLESS_FILE_APPROVAL_HOME!);
 const delivery=resolve(process.env.FM_OUTPUT!);
 const spec=JSON.parse(readFileSync(process.env.FM_TASK_FILE!,'utf8'));
 mkdirSync(home,{recursive:true,mode:0o700});
 ctx.on('agent/created',({agent}:any)=>agent.ctx.on('tools/execute',async(exec:any,next:any)=>{
  if(!['mcp__file_management__execute_plan','mcp__file_management__restore_plan'].includes(exec.name))return next();
  const args=typeof exec.arguments==='string'?JSON.parse(exec.arguments):exec.arguments;
  const state=JSON.parse(readFileSync(join(delivery,'management-state.json'),'utf8'));
  const plan=state.plans[args.plan_id];if(!plan)throw Error('unknown current management plan');
  const restore=exec.name.endsWith('__restore_plan');
  const risks=plan.risks;
  if(!risks.length)return next();
  const planHash=restore?digest({plan_sha256:plan.plan_sha256,direction:'restore',before:state.journals[plan.plan_id]?.restore_before??state.expected_tree}):plan.plan_sha256;
  const dir=join(delivery,restore?'restore-approvals':'approvals'),target=join(dir,plan.plan_id+'.json');
  // An exact persisted decision survives an interrupted tool call. The MCP still
  // checks the original task, current tree and journal before applying effects.
  if(existsSync(target)&&JSON.parse(readFileSync(target,'utf8')).plan_sha256===planHash)return next();
  const denial=join(delivery,'denials',digest({before:plan.before,actions:plan.actions,direction:restore?'restore':'execute'})+'.json');
  if(existsSync(denial))throw Error('this file plan was denied; change the plan before requesting approval');
  const id=randomUUID(), request={id,call_id:exec.callId,task_sha256:digest(spec),plan_id:plan.plan_id,plan_sha256:planHash,direction:restore?'restore':'execute',actions:plan.actions,risks};
  writeFileSync(join(home,id+'.request.json'),JSON.stringify(request),{mode:0o600});
  const answer=join(home,id+'.decision.json');
  while(!existsSync(answer)){
   if(exec.signal.aborted)throw Error('native file approval interrupted');
   await new Promise(r=>setTimeout(r,150));
  }
  const decision=JSON.parse(readFileSync(answer,'utf8'));
  if(decision.request_digest!==digest(request)||!decision.native_asked?.data?.id||decision.native_asked.data.id!==decision.native_decided?.data?.id||decision.outcome!==decision.native_decided?.data?.outcome)throw Error('native one-plan approval proof changed');
  if(decision.outcome!=='allowed-once'){
   mkdirSync(join(delivery,'denials'),{recursive:true,mode:0o700});
   writeFileSync(denial,JSON.stringify({plan_sha256:planHash,outcome:decision.outcome,proof:decision}),{mode:0o600});
   throw Error('native one-plan approval denied');
  }
  mkdirSync(dir,{recursive:true,mode:0o700});
  const proof={...decision,task_sha256:request.task_sha256,approval_event_id:decision.native_asked.data.id};
  writeFileSync(target+'.tmp',JSON.stringify({plan_id:plan.plan_id,plan_sha256:planHash,proof}),{mode:0o600});renameSync(target+'.tmp',target);
  return next();
 }));
}
