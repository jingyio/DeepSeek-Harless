/** Public Harness interception; never performs scientific judgments. */
import {randomUUID,createHash} from 'node:crypto';
import {readFileSync,appendFileSync,mkdirSync} from 'node:fs';
import {join} from 'node:path';
import {isAgentLoopRequest} from '@deepseek-ai/dsh-llm';
import {digest,syntheticToolStreamBatch} from '../motif_core/online_skill_runtime.mjs';
import {createEntryController,validateEntryPolicy,validateEntryTask} from '../motif_core/entry_read_policy.ts';
import {createTerminalController,validateTerminalPolicy,validateTerminalTask,terminalStream} from '../motif_core/terminal_receipt_policy.ts';
import {createCollectionController,validateCollectionPolicy,validateCollectionTask} from '../motif_core/collection_read_policy.ts';
import {createCollectionScriptController,validateCollectionScript} from '../motif_core/collection_batch_script.ts';
import {createPlanController,validatePlanPolicy,validatePlanTask} from '../motif_core/authorized_plan_policy.ts';
import {createReentryController,validateReentryPolicy,validateReentryTask} from '../motif_core/collection_reentry_policy.ts';
import {createJobPlanGuard} from './dsh_job_plan_gate.ts';
import {fileURLToPath} from 'node:url';
export const name='sss-entry-motif';
export const inject=['llm','agents'];
export function createCollectionGate(policy:any,task:any,audit:(r:any)=>void,builder:any=createCollectionController,jobGuard?:any){
  const controller=builder(policy,task,audit);let envelope:string|null=null;
  return {controller,observe:(exec:any,result:any)=>{
      controller.observe(exec,result);
      if(jobGuard&&controller.halted)jobGuard.disable('plan_controller_halted');
    },
    intercept(options:any,next:()=>any,live:boolean){
      if((options.messages??[]).some((m:any)=>m.source?.kind==='task-acceptance-repair')){controller.fail('acceptance_repair_requires_ordinary_harness');jobGuard?.disable('acceptance_repair_requires_ordinary_harness');return next();}
      if(options.sessionId!==task.session_id||!isAgentLoopRequest(options)||!live
        ||controller.done||controller.halted||controller.pending)return next();
      if(jobGuard&&!jobGuard.allow()){controller.fail('durable_plan_guard_rejected');return next();}
      const human=(options.messages??[]).filter((m:any)=>m.role==='user'&&m.source?.kind==='user');
      const texts=human.map((m:any)=>m.content?.length===1&&m.content[0].type==='text'?m.content[0].text:null);
      const matching=texts.filter((s:any)=>typeof s==='string'&&createHash('sha256').update(s).digest('hex')===task.prompt_sha256);
      const reminders=texts.filter((s:any)=>typeof s==='string'&&(s.startsWith('<system-reminder>\n')||s.startsWith('Current runtime context. This snapshot supersedes')));
      const now=digest(human.map((m:any)=>({id:m.id,content:m.content})));
      if(matching.length!==1||matching.length+reminders.length!==human.length||reminders.length>2||(envelope!==null&&envelope!==now)){
        controller.fail('collection_prompt_or_user_envelope_changed');jobGuard?.disable('prompt_or_user_envelope_changed');return next();}
      envelope=now;if(!controller.armed)return next();
      const calls=controller.propose(options.tools??[],randomUUID);
      if(controller.halted)jobGuard?.disable('plan_proposal_guard_rejected');
      return calls.length?syntheticToolStreamBatch(calls):next();
    }};
}
export function createEntryGate(policy:any,task:any,audit:(r:any)=>void){
  const controller=createEntryController(policy,task,audit);let envelope:string|null=null,started=false;
  return {controller,observe:(exec:any,result:any)=>controller.observe(exec,result),
    intercept(options:any,next:()=>any,live:boolean){
      if((options.messages??[]).some((m:any)=>m.source?.kind==='task-acceptance-repair')){controller.fail('acceptance_repair_requires_ordinary_harness');return next();}
      if(options.sessionId!==task.session_id||!isAgentLoopRequest(options)||!live)return next();
      if(controller.done||controller.halted||controller.pending)return next();
      const human=(options.messages??[]).filter((m:any)=>m.role==='user'&&m.source?.kind==='user');
      const text=human.map((m:any)=>m.content?.length===1&&m.content[0].type==='text'?m.content[0].text:null);
      const matching=text.filter((s:any)=>typeof s==='string'&&createHash('sha256').update(s).digest('hex')===task.prompt_sha256);
      const reminders=text.filter((s:any)=>typeof s==='string'&&(s.startsWith('<system-reminder>\n')||s.startsWith('Current runtime context. This snapshot supersedes')));
      const now=digest(human.map((m:any)=>({id:m.id,content:m.content})));
      if(matching.length!==1||matching.length+reminders.length!==human.length||reminders.length>2||(envelope!==null&&envelope!==now)){
        controller.fail('prompt_or_user_envelope_changed');return next();}
      // Entry interception cannot start after a real model has already made a decision.
      if(!started&&(options.messages??[]).some((m:any)=>m.role==='assistant')){controller.fail('not_task_entry');return next();}
      envelope=now;const calls=controller.propose(options.tools??[],randomUUID);
      if(!calls.length)return next();started=true;return syntheticToolStreamBatch(calls);
    }};
}
export function createTerminalGate(policy:any,task:any,audit:(r:any)=>void,verify?:any){
  const controller=createTerminalController(policy,task,audit,verify);let envelope:string|null=null;
  return {controller,observe:(exec:any,result:any)=>controller.observe(exec,result),
    intercept(options:any,next:()=>any,live:boolean){
      if((options.messages??[]).some((m:any)=>m.source?.kind==='task-acceptance-repair')){controller.fail('acceptance_repair_requires_ordinary_harness');return next();}
      if(options.sessionId!==task.session_id||!isAgentLoopRequest(options)||!live||controller.done||controller.halted)return next();
      const human=(options.messages??[]).filter((m:any)=>m.role==='user'&&m.source?.kind==='user');
      const texts=human.map((m:any)=>m.content?.length===1&&m.content[0].type==='text'?m.content[0].text:null);
      const matching=texts.filter((s:any)=>typeof s==='string'&&createHash('sha256').update(s).digest('hex')===task.prompt_sha256);
      const reminders=texts.filter((s:any)=>typeof s==='string'&&(s.startsWith('<system-reminder>\n')||s.startsWith('Current runtime context. This snapshot supersedes')));
      const now=digest(human.map((m:any)=>({id:m.id,content:m.content})));
      if(matching.length!==1||matching.length+reminders.length!==human.length||reminders.length>2||(envelope!==null&&envelope!==now)){
        controller.fail('prompt_or_user_envelope_changed');return next();}
      envelope=now;
      if(!controller.armed)return next();
      const offered=(options.tools??[]).find((t:any)=>t.name===policy.artifact.terminal.tool);
      if(!offered||digest(offered.parameters)!==policy.artifact.schema_sha256){controller.fail('terminal_tool_schema_changed');return next();}
      const messages=options.messages??[],last=messages.at(-1),results=last?.content??[];
      const assistant=messages.slice(0,-1).findLast((m:any)=>m.role==='assistant'),calls=(assistant?.content??[]).filter((b:any)=>b.type==='tool-call');
      const a=controller.armed;let argumentsSha:string|null=null,receiptSha:string|null=null;
      try{argumentsSha=digest(JSON.parse(calls[0]?.arguments));receiptSha=digest(JSON.parse(results[0]?.content?.[0]?.text));}catch{}
      if(last?.source?.kind!=='tool'||results.length!==1||results[0].type!=='tool-result'||results[0].isError
        ||results[0].toolCallId!==a.call_id||receiptSha!==a.receipt_sha256||calls.length!==1
        ||calls[0].id!==a.call_id||calls[0].name!==policy.artifact.terminal.tool||argumentsSha!==a.args_sha256){
        controller.fail('not_immediate_single_receipt_frontier');return next();}
      const summary=controller.finish();return summary?terminalStream(summary):next();
    }};
}
export function apply(ctx:any){
  const path=process.env.SSS_ENTRY_MOTIF_POLICY,taskPath=process.env.SSS_ENTRY_MOTIF_TASK;
  const terminalPath=process.env.SSS_TERMINAL_MOTIF_POLICY,terminalTask=process.env.SSS_TERMINAL_MOTIF_TASK;
  const collectionPath=process.env.SSS_COLLECTION_MOTIF_POLICY,collectionTask=process.env.SSS_COLLECTION_MOTIF_TASK;
  const scriptPath=process.env.SSS_COLLECTION_SCRIPT,scriptTask=process.env.SSS_COLLECTION_SCRIPT_TASK;
  const planPath=process.env.SSS_PLAN_MOTIF_POLICY,planTask=process.env.SSS_PLAN_MOTIF_TASK;
  const reentryPath=process.env.SSS_REENTRY_MOTIF_POLICY,reentryTask=process.env.SSS_REENTRY_MOTIF_TASK;
  if(!path&&!terminalPath&&!collectionPath&&!scriptPath&&!planPath&&!reentryPath)return;
  if([path,terminalPath,collectionPath,scriptPath,planPath,reentryPath].filter(Boolean).length>1)throw new TypeError('Motif combination needs separate certification');
  const terminal=Boolean(terminalPath);
  const collection=Boolean(collectionPath),script=Boolean(scriptPath),plan=Boolean(planPath),reentry=Boolean(reentryPath);
  const policy=(reentry?validateReentryPolicy:plan?validatePlanPolicy:script?validateCollectionScript:collection?validateCollectionPolicy:terminal?validateTerminalPolicy:validateEntryPolicy)(JSON.parse(readFileSync((reentry?reentryPath:plan?planPath:script?scriptPath:collection?collectionPath:terminal?terminalPath:path)!,'utf8')));
  const task=(reentry?validateReentryTask:plan?validatePlanTask:collection||script?validateCollectionTask:terminal?validateTerminalTask:validateEntryTask)(JSON.parse(readFileSync((reentry?reentryTask:plan?planTask:script?scriptTask:collection?collectionTask:terminal?terminalTask:taskPath)!,'utf8')),policy);
  if(!/^[a-f0-9]{64}$/.test(task.prompt_sha256??''))throw new TypeError('entry needs actual prompt digest');
  const dir=join(process.cwd(),'.local/online-motif');mkdirSync(dir,{recursive:true,mode:0o700});
  const file=join(dir,createHash('sha256').update(task.session_id).digest('hex')+'.jsonl');
  const audit=(row:any)=>appendFileSync(file,JSON.stringify({...row,session_id:task.session_id})+'\n',{mode:0o600});
  const binding=process.env.SSS_DURABLE_PLAN_BINDING;
  if(process.env.FM_JOB_FILE&&plan&&!binding)throw Error('durable plan requires explicit certified composition binding');
  if(binding&&JSON.parse(readFileSync(binding,'utf8')).job_file!==process.env.FM_JOB_FILE)throw Error('composition and MCP must use the same durable job');
  const jobGuard=plan&&binding?createJobPlanGuard(fileURLToPath(new URL('../../',import.meta.url)),binding,planPath!,task,audit):undefined;
  if(jobGuard&&!jobGuard.activate()){audit({kind:'plan_motif_disabled_before_start'});return;}
  const gate=reentry?createCollectionGate(policy,task,audit,createReentryController):plan?createCollectionGate(policy,task,audit,createPlanController,jobGuard):script?createCollectionGate(policy,task,audit,createCollectionScriptController):(collection?createCollectionGate:terminal?createTerminalGate:createEntryGate)(policy,task,audit);let live=false;
  audit({kind:reentry?'reentry_motif_loaded':plan?'plan_motif_loaded':script?'collection_script_loaded':collection?'collection_motif_loaded':terminal?'terminal_motif_loaded':'entry_motif_loaded',policy_digest:policy.policy_digest,script_digest:policy.script_digest});
  ctx.on('agent/created',({agent}:any)=>{if(agent.session.id===task.session_id){live=true;agent.ctx.on('tools/result',gate.observe);}});
  ctx.on('agent/disposed',({agent}:any)=>{if(agent.session.id===task.session_id)live=false;});
  ctx.on('llm/stream',(options:any,next:()=>any)=>gate.intercept(options,next,live),{global:true});
}
