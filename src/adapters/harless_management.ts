/** Same native Agent lifecycle; Python owns immutable materials and offline RSI. */
import {spawn} from 'node:child_process';
import {readFileSync,writeFileSync,appendFileSync,mkdirSync} from 'node:fs';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createOperationRuntime} from './dsh_operation_motif.ts';
import {createTaskObserver} from './dsh_continuous_rsi.ts';
import {createAcceptanceGuard,verifier} from './file_acceptance_guard.ts';
import {syntheticToolStreamBatch} from '../motif_core/online_skill_runtime.mjs';
import {OperationJob} from './operation_job.ts';
const helper=fileURLToPath(new URL('../../scenarios/file-management/management_web.py',import.meta.url));
const root=fileURLToPath(new URL('../../',import.meta.url));
export function managementAcceptance(task:any){
 const b=task.management.binding;
 const policy={kind:'file_management' as const,max_repairs:2,project_root:root,python:task.management.config.python,
  task_file:b.task_file,delivery_root:b.delivery,archive_root:join(task.management.config.private_root??join(root,'.local'),'management-acceptance'),job_file:b.job_file,interruptible:true as const};
 return createAcceptanceGuard(policy,verifier(policy,task.request.session_id,b.task_sha256));
}
export function managementBridge(config:any,parameters:any):Promise<any>{return new Promise((resolve,reject)=>{
 const child=spawn(config.python??'python3',[helper],{stdio:['pipe','pipe','pipe'],env:{...process.env,...(config.private_root?{HARLESS_MANAGEMENT_PRIVATE_ROOT:config.private_root}:{})}}),out:Buffer[]=[],err:Buffer[]=[];
 const timer=setTimeout(()=>{child.kill();reject(Error('management bridge timed out'));},120000);
 child.stdout.on('data',b=>out.push(b));child.stderr.on('data',b=>err.push(b));child.on('error',e=>{clearTimeout(timer);reject(e);});
 child.on('close',code=>{clearTimeout(timer);if(code)reject(Error(Buffer.concat(err).toString().slice(-3000)));else try{resolve(JSON.parse(Buffer.concat(out).toString()));}catch(e){reject(e);}});
 child.stdin.end(JSON.stringify({...config,...parameters}));
});}
export function attachManagementRuntime(task:any,rsi:any,onAudit:(r:any)=>void){
 const b=rsi.observer_binding;const observer=createTaskObserver({...b,binding_sha256:rsi.observer_binding_sha256},row=>{
  if(row.kind==='runtime_schema')writeFileSync(b.schema_file,JSON.stringify(row.schemas),{mode:0o600});
  else appendFileSync(b.event_file,JSON.stringify(row)+'\n',{mode:0o600});
 });observer.created(task.request.session_id);
 const runtime=createOperationRuntime(rsi.operation_binding,row=>{
  appendFileSync(join(task.output,'experience-audit.jsonl'),JSON.stringify({...row,session_id:task.request.session_id})+'\n',{mode:0o600});
  if(row.kind==='operation_model_request_bypassed_verified')task.stats.verified_skips++;
  onAudit(row);
 });
 return {observer,runtime,intercept(request:any,next:any){
  observer.tools(task.request.session_id,request.tools??[]);
  if(request.messages.some((m:any)=>m.source?.kind==='task-acceptance-repair')){runtime.fail('repair_requires_ordinary_harness');return next();}
  const calls=task.selection.rsi&&task.request.mode==='execute'?runtime.propose(request.tools??[],request.messages):[];
  if(calls.length)new OperationJob(root,task.management.binding.job_file).apply('motif-step');
  return calls.length?syntheticToolStreamBatch(calls):next();
 }};
}
export async function confirmManagementEffect(task:any,agent:any,exec:any){
 if(!exec.name.endsWith('__execute_plan')&&!exec.name.endsWith('__restore_plan'))return;
 const direction=exec.name.endsWith('__restore_plan')?'restore':'execute';
 const raw=exec.arguments??exec.args??{};const args=typeof raw==='string'?JSON.parse(raw):raw;
 const info=await managementBridge(task.management.config,{action:'plan',directory:task.management.binding.directory,plan_id:args.plan_id,direction});
 if(!info.risks.length||info.approved)return;
 if(info.denied)throw Error('this operation was denied; keep files unchanged and report the gap');
 const approval=agent.ctx.get('approval');if(!approval)throw Error('native confirmation channel unavailable');
 const outcome=await approval.request({agent,toolName:exec.name,callId:exec.callId,reason:'请确认本次'+(direction==='restore'?'恢复':'文件操作')+'，仅批准这一计划：'+JSON.stringify({actions:info.actions,risks:info.risks,external_paths:info.external_paths}),signal:exec.signal});
 if(outcome!=='allowed-once'){
  await managementBridge(task.management.config,{action:'deny',directory:task.management.binding.directory,plan_id:info.plan_id,outcome,direction});
  throw Error('management high-risk confirmation '+outcome);
 }
 const events=agent.session.snapshotEvents();const asked=[...events].reverse().find((e:any)=>e.type==='approval/asked'&&e.data.callId===exec.callId);
 const decision=events.find((e:any)=>e.type==='approval/decided'&&e.data.id===asked?.data.id&&e.data.outcome==='allowed-once');
 if(!asked||!decision)throw Error('actual native confirmation proof missing');
 await managementBridge(task.management.config,{action:'approve',directory:task.management.binding.directory,plan_id:info.plan_id,plan_sha256:info.plan_sha256,direction,
  proof:{outcome,approval_event_id:asked.data.id,session_id:task.request.session_id,task_sha256:info.task_sha256,call_id:exec.callId}});
}
