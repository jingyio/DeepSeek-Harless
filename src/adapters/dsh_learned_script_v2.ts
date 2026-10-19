/** Version 2 bounded copy programs; version 1 and its certificates stay frozen. */
import {readFileSync,appendFileSync,existsSync,lstatSync} from 'node:fs';
import {resolve,sep} from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {isAgentLoopRequest} from '@deepseek-ai/dsh-llm';
import {digest,observation,syntheticToolStreamBatch} from '../motif_core/online_skill_runtime.mjs';
import {terminalStream} from '../motif_core/terminal_receipt_policy.ts';
export const name='sss-learned-copy-script-v2';export const inject=['agents','llm'];
const root=resolve(fileURLToPath(new URL('../../',import.meta.url))),prefix='mcp__file_management__';
const hex=(v:any)=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const unsigned=(v:any,k:string)=>Object.fromEntries(Object.entries(v).filter(([n])=>n!==k));
const path=(v:any)=>typeof v==='string'&&v.length>0&&!v.startsWith('/')&&!v.includes('\\')&&!v.split('/').some((s:string)=>['','.','..'].includes(s));
const dir=(v:any)=>typeof v==='string'&&v.endsWith('/')&&path(v.slice(0,-1));
const names=['read_task','list_files','pin_file','read_file','hash_files','preview_actions','execute_plan','submit_report'];
export const eligibleBackupSources=(rows:any[])=>rows.filter(r=>!(r.extension==='.txt'&&r.bytes===0));
export const hashRepresentatives=(groups:any[],order:string)=>groups.map(g=>[...g.files].sort((a:any,b:any)=>a.path<b.path?-1:a.path>b.path?1:0)[order==='min'?0:g.files.length-1]);
export const runtimeFiles=['src/adapters/dsh_learned_script_v2.ts','src/motif_core/online_skill_runtime.mjs','src/motif_core/terminal_receipt_policy.ts'];
export function validateScript(s:any){
 if(s?.format!=='sss-learned-copy-script-v2'||s.schema_version!==2||s.script_digest!==digest(unsigned(s,'script_digest'))
  ||!hex(s.execution_version_sha256)||!Array.isArray(s.guard_cases)||!s.guard_cases.length||s.guard_cases.length>4
  ||s.guard_cases.some((g:any)=>!hex(g.objective_sha256)||!(g.context_text_sha256===null||hex(g.context_text_sha256))||!Array.isArray(g.destination_prefixes)||g.destination_prefixes.some((p:any)=>!dir(p)))
  ||!Array.isArray(s.steps)||s.steps.length<1||s.steps.length>4||!Array.isArray(s.training)||s.training.length<2
  ||new Set(s.training.map((r:any)=>r.task_fingerprint)).size!==s.training.length
  ||s.training.some((r:any)=>r.role!=='explore'||!hex(r.events_sha256)||!hex(r.task_fingerprint))
  ||digest(Object.keys(s.runtime_source??{}).sort())!==digest([...runtimeFiles].sort())||runtimeFiles.some(n=>!hex(s.runtime_source[n]))
  ||names.some(n=>!hex(s.tool_schema_sha256?.[prefix+n])))throw Error('invalid version 2 trace-derived program');
 let copies=0,hashed=false;
 for(const v of s.steps){
  if(v.op==='hash_representatives'&&!hashed&&!copies&&['min','max'].includes(v.order)&&Object.keys(v).length===2){hashed=true;continue;}
  if(v.op!=='copy_map'||!['task_sources','nonempty_txt_sources','hash_representatives','prior_targets'].includes(v.source)
   ||!(v.strip_prefix===''||dir(v.strip_prefix))||!Number.isSafeInteger(v.destination_slot)||v.destination_slot<0||v.destination_slot>1
   ||Object.keys(v).length!==4||s.guard_cases.some((g:any)=>v.destination_slot>=g.destination_prefixes.length)
   ||(v.source==='hash_representatives'&&!hashed)||(v.source==='prior_targets'&&copies!==1))throw Error('unsupported version 2 instruction');copies++;
 }
 if(copies<1||copies>2)throw Error('version 2 copy limit');return s;
}
export function createScriptController(script:any,binding:any,audit:(r:any)=>void){
 validateScript(script);const spec=binding.spec;
 if(!spec||binding.input_sha256!==digest(spec)||spec.report_contract?.kind!=='task_result'||!hex(binding.prompt_sha256))throw Error('invalid current script binding');
 let stage='task',step=0,halted=false,done=false,pending:any=null,task:any=null,inventory:any[]=[],sources:any[]=[],representatives:any[]=[],targets:string[]=[],actions:any[]=[],plan:any=null,receipt:any=null,guards:any[]=[];
 let context=0,pin:any=null,expected={...spec.initial_snapshot};
 const fail=(reason:string)=>{halted=true;pending=null;audit({kind:'script_v2_deferred',reason,script_digest:script.script_digest});};
 const current=(n:string)=>{const r=inventory.find(r=>r.path===n);if(!r)throw Error('missing actual inventory member');return r;};
 function copyActions(v:any){
  const all=task.workflow_contract.source_paths.map(current);
  const rows=v.source==='task_sources'?all:v.source==='nonempty_txt_sources'?eligibleBackupSources(all):v.source==='hash_representatives'?representatives:targets.map(current);
  const destinationPrefix=task.workflow_contract.destination_prefixes[v.destination_slot];
  if(!rows.length||rows.length>32||new Set(rows.map((r:any)=>r.path)).size!==rows.length)throw Error('copy count or source changed');
  return rows.map((r:any)=>{
   if(!r.path.startsWith(v.strip_prefix))throw Error('source prefix changed');
   const d=destinationPrefix+r.path.slice(v.strip_prefix.length);
   if(!path(d)||expected[d]!==undefined||!task.workflow_contract.destination_prefixes.some((p:string)=>d.startsWith(p)))throw Error('destination conflict or permission changed');
   return {op:'copy',file_ids:[r.file_id],destination:d,format:'none'};
  });
 }
 return {get halted(){return halted;},get done(){return done;},get receipt(){return receipt;},fail,
  observe(exec:any,result:any){
   if(halted||done)return;const out=observation(result,exec.name);
   if(!pending||exec.callId!==pending.callId||exec.name!==pending.name||digest(exec.arguments)!==digest(pending.args)||!out){fail('unexpected_or_failed_actual_tool');return;}
   const at=stage;pending=null;
   try{
    if(at==='task'){
     const c=out.workflow_contract;
     guards=script.guard_cases.filter((g:any)=>g.objective_sha256===digest(out.objective)&&digest(g.destination_prefixes)===digest(c?.destination_prefixes));
     if(out.input_sha256!==binding.input_sha256||out.copy_only!==true||out.workflow_execution_version_sha256!==script.execution_version_sha256
      ||!guards.length||c.workflow_id!==script.workflow_id||digest(out.allowed_operations)!==digest(['copy'])
      ||digest(c.required_reads)!==digest(c.context_paths)||c.context_paths.length>1||!c.source_paths.length||c.source_paths.length>32
      ||guards.every((g:any)=>c.context_paths.length!==(g.context_text_sha256===null?0:1)))throw Error('version 2 goal, rule scope, version or permission changed');
     task=out;stage='inventory';
    }else if(at==='inventory'||at==='refresh'||at==='final_inventory'){
     if(!Array.isArray(out.files)||out.snapshot_sha256!==digest(expected)||out.files.length!==Object.keys(expected).filter(n=>n!=='.experiment-copy').length
      ||new Set(out.files.map((r:any)=>r.path)).size!==out.files.length||out.files.some((r:any)=>!Number.isSafeInteger(r.bytes)||r.bytes<0||typeof r.extension!=='string'||expected[r.path]!==r.sha256||r.file_id!=='file:local:'+digest({path:r.path,sha:r.sha256}).slice(0,24)))throw Error('current inventory or bytes changed');
     inventory=out.files;sources=task.workflow_contract.source_paths.map(current);
     stage=at==='final_inventory'?'publish':at==='refresh'?'step':task.workflow_contract.context_paths.length?'pin_context':'step';
    }else if(at==='pin_context'){
     const r=current(task.workflow_contract.context_paths[context]);
     if(out.file_id!==r.file_id||out.source_version!==digest({path:r.path,sha:r.sha256,parser:'fm-parser-v1'})||typeof out.source_id!=='string')throw Error('context pin changed');
     pin=out;stage='read_context';
    }else if(at==='read_context'){
     const r=current(task.workflow_contract.context_paths[context]);
     if(out.source_id!==pin.source_id||out.file_id!==r.file_id||out.sha256!==r.sha256||out.status!=='readable'||out.truncated||!guards.some((g:any)=>g.context_text_sha256===digest(out.text)))throw Error('context rule changed; ordinary semantics required');
     context++;stage=context===task.workflow_contract.context_paths.length?'step':'pin_context';
    }else if(at==='hash'){
     if(!Array.isArray(out.groups))throw Error('invalid actual hash groups');
     const rows=out.groups.flatMap((g:any)=>g.files);
     if(rows.length!==sources.length||new Set(rows.map((r:any)=>r.file_id)).size!==sources.length||rows.some((r:any)=>!sources.some(s=>s.file_id===r.file_id&&s.path===r.path))
      ||out.groups.some((g:any)=>!g.files.length||g.files.some((r:any)=>current(r.path).sha256!==g.sha256)))throw Error('hash group scope changed');
     const order=script.steps[step].order;representatives=hashRepresentatives(out.groups,order);step++;stage='step';
    }else if(at==='preview'){
     if(out.status!=='validated_copy_plan'||digest(out.actions)!==digest(actions)||typeof out.plan_id!=='string')throw Error('actual preview differs');
     plan=out;stage='execute';
    }else if(at==='execute'){
     const after={...expected};actions.forEach((a:any)=>after[a.destination]=inventory.find(r=>r.file_id===a.file_ids[0]).sha256);
     if(out.status!=='executed_verified'||out.plan_id!==plan.plan_id||out.snapshot_sha256!==digest(after)||out.operation_count!==actions.length)throw Error('execution receipt or footprint differs');
     expected=after;targets=actions.map(a=>a.destination);step++;stage='refresh';
    }else if(at==='publish'){
     if(!['delivered','delivered_with_gaps'].includes(out.status)||out.input_sha256!==binding.input_sha256||!hex(out.artifact_sha256))throw Error('report receipt differs');
     receipt=out;stage='terminal';
    }
    audit({kind:'script_v2_step_verified',stage:at,call_id:exec.callId,observation_sha256:digest(out),script_digest:script.script_digest});
   }catch(e:any){fail(e.message);}
  },
  propose(tools:any[]){
   if(halted||done||pending)return null;
   for(const n of names){const t=tools.find((t:any)=>t.name===prefix+n);if(!t||!t.parameters||typeof t.parameters!=='object'||Array.isArray(t.parameters)||digest(t.parameters)!==script.tool_schema_sha256[prefix+n]){fail('tool_schema_changed');return null;}}
   try{
    if(stage==='terminal'){
     // The ordinary fixed acceptance guard still checks the actual report and all bytes.
     done=true;audit({kind:'script_v2_program_finished',script_digest:script.script_digest,receipt_sha256:digest(receipt)});return {terminal:receipt};
    }
    if(stage==='step'){
     if(step===script.steps.length)stage='final_inventory';
     else if(script.steps[step].op==='hash_representatives')stage='hash';
     else{actions=copyActions(script.steps[step]);stage='preview';}
    }
    const n=stage==='task'?'read_task':['inventory','refresh','final_inventory'].includes(stage)?'list_files':stage==='pin_context'?'pin_file':stage==='read_context'?'read_file':stage==='hash'?'hash_files':stage==='preview'?'preview_actions':stage==='execute'?'execute_plan':'submit_report';
    const args=stage==='pin_context'?{file_id:current(task.workflow_contract.context_paths[context]).file_id}:stage==='read_context'?{source_id:pin.source_id}:stage==='hash'?{file_ids:sources.map(r=>r.file_id)}:stage==='preview'?{actions}:stage==='execute'?{plan_id:plan.plan_id}:stage==='publish'?{summary:'Trace-derived bounded copy script; verified actual inventory, hashes and receipts.',file_ids:inventory.map(r=>r.file_id),gaps:[],report_kind:'task_result'}:{};
    pending={callId:'sss-script-v2-'+randomUUID(),name:prefix+n,args};
    audit({kind:'script_v2_dispatch',stage,call_id:pending.callId,arguments_sha256:digest(args)});
    return {call:{callId:pending.callId,proposal:{tool:pending.name,arguments:args}}};
   }catch(e:any){fail(e.message);return null;}
  }
 };
}
export function apply(ctx:any){
 const file=process.env.SSS_LEARNED_SCRIPT_V2_BINDING;if(!file)return;
 if(!resolve(file).startsWith(resolve(root,'.local')+sep)||lstatSync(file).isSymbolicLink())throw Error('private explicit script binding required');
 const b=JSON.parse(readFileSync(file,'utf8')),s=JSON.parse(readFileSync(b.script_file,'utf8'));
 const raw=(p:string)=>createHash('sha256').update(readFileSync(p)).digest('hex');
 if(raw(b.script_file)!==b.script_file_sha256||raw(b.task_file)!==b.task_file_sha256||b.runtime_sha256!==raw(fileURLToPath(import.meta.url))
  ||runtimeFiles.some(n=>raw(resolve(root,n))!==s.runtime_source?.[n]))throw Error('version 2 source binding changed');
 if(!['certify','holdout','free'].includes(b.role))throw Error('explicit script execution role required');
 if(b.role==='holdout'){
  const cert=JSON.parse(readFileSync(b.certificate_file,'utf8'));
  if(raw(b.certificate_file)!==b.certificate_sha256||cert.status!=='certified_v2'||digest(cert.runtime_source)!==digest(s.runtime_source)||!cert.scripts.some((r:any)=>r.script_digest===s.script_digest&&r.sha256===b.script_file_sha256))throw Error('independent script certification required');
 }
 const spec=JSON.parse(readFileSync(b.task_file,'utf8'));let live=false,session:string|null=null,envelope:string|null=null,started=false;
 const audit=(r:any)=>appendFileSync(b.audit_file,JSON.stringify({...r,session_id:session})+'\n',{mode:0o600});
 const c=createScriptController(s,{spec,input_sha256:digest(spec),prompt_sha256:b.prompt_sha256},audit);
 ctx.on('agent/created',({agent}:any)=>{if(session!==null){c.fail('additional_agent');return;}session=agent.session.id;live=true;agent.ctx.on('tools/result',c.observe);});
 ctx.on('agent/disposed',()=>{live=false;});
 ctx.on('llm/stream',(options:any,next:()=>any)=>{
  if(!live||options.sessionId!==session||!isAgentLoopRequest(options)||c.halted||c.done)return next();
  if(options.messages.some((m:any)=>m.source?.kind==='task-acceptance-repair')){c.fail('acceptance_repair_requires_ordinary_harness');return next();}
  const human=options.messages.filter((m:any)=>m.role==='user'&&m.source?.kind==='user');
  const texts=human.map((m:any)=>m.content.length===1&&m.content[0].type==='text'?m.content[0].text:null);
  const matching=texts.filter((s:any)=>typeof s==='string'&&createHash('sha256').update(s).digest('hex')===b.prompt_sha256);
  const reminders=texts.filter((s:any)=>typeof s==='string'&&(s.startsWith('<system-reminder>\n')||s.startsWith('Current runtime context. This snapshot supersedes')));
  const now=digest(human.map((m:any)=>({id:m.id,content:m.content})));
  if(matching.length!==1||matching.length+reminders.length!==human.length||reminders.length>2||(envelope!==null&&envelope!==now)
   ||(!started&&options.messages.some((m:any)=>m.role==='assistant'))){c.fail('prompt_or_start_boundary_changed');return next();}
  envelope=now;started=true;const proposal=c.propose(options.tools??[]);
  return proposal?.terminal?terminalStream({status:'script_delivery_pending_fixed_acceptance',receipt:proposal.terminal}):proposal?.call?syntheticToolStreamBatch([proposal.call]):next();
 },{global:true});
}
