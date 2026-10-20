/** Automatic, evidence-bound retrieval of certified Motifs and learned programs. */
import {readFileSync,appendFileSync,lstatSync,existsSync} from 'node:fs';
import {resolve,dirname,sep} from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {isAgentLoopRequest} from '@deepseek-ai/dsh-llm';
import {digest,observation,syntheticToolStreamBatch} from '../motif_core/online_skill_runtime.mjs';
import {terminalStream} from '../motif_core/terminal_receipt_policy.ts';
import {validateScript as validateV1,createScriptController as createV1} from './dsh_learned_script.ts';
import {validateScript as validateV2,createScriptController as createV2} from './dsh_learned_script_v2.ts';
import {createCollectionController} from '../motif_core/collection_read_policy_v2.ts';
import {createReentryController} from '../motif_core/collection_reentry_policy_v2.ts';
import {validateCollectionPolicy} from '../motif_core/collection_read_policy.ts';
import {validateReentryPolicy} from '../motif_core/collection_reentry_policy.ts';
import {validatePlanPolicy,createPlanController} from '../motif_core/authorized_plan_policy.ts';
import {createJobPlanGuard} from './dsh_job_plan_gate.ts';
export const name='sss-experience';export const inject=['agents','llm'];
const root=resolve(fileURLToPath(new URL('../../',import.meta.url))),prefix='mcp__file_management__';
const raw=(p:string)=>createHash('sha256').update(readFileSync(p)).digest('hex');
const unsigned=(v:any,k:string)=>Object.fromEntries(Object.entries(v).filter(([n])=>n!==k));
function scoped(base:string,name:string){
 if(typeof name!=='string'||name.startsWith('/')||name.includes('\\')||name.split('/').some(p=>!p||p==='.'||p==='..'))throw Error('invalid registry path');
 const file=resolve(base,name);for(let p=file;p.startsWith(base+sep);p=dirname(p))if(existsSync(p)&&lstatSync(p).isSymbolicLink())throw Error('registry symlink refused');return file;
}
export function loadExperiences(base:string,file:string,sha:string,certifying=false){
 if(raw(file)!==sha)throw Error('immutable registry version changed');
 const state=JSON.parse(readFileSync(file,'utf8'));
 if(state.schema_version!==1||state.format!=='sss-experience-registry-v1'||state.registry_digest!==digest(unsigned(state,'registry_digest'))
  ||state.automatic_selection_uses_profile_id!==false||!Array.isArray(state.entries))throw Error('invalid unified registry');
 return state.entries.filter((r:any)=>r.state==='active'||certifying&&r.state==='candidate').map((r:any)=>{
  const path=scoped(base,r.payload);if(raw(path)!==r.sha256)throw Error('experience payload changed');
  const payload=JSON.parse(readFileSync(path,'utf8'));const field=r.kind.startsWith('script_')?'script_digest':r.kind==='read_library'?'library_digest':'policy_digest';
  if(payload[field]!==r.artifact_digest||payload[field]!==digest(unsigned(payload,field)))throw Error('experience signature changed');
  if(r.kind.startsWith('script_')){
   (r.kind==='script_v1'?validateV1:validateV2)(payload);
   if(!certifying||r.state==='active'){
    if(!r.certificate)throw Error('uncertified experience');const file=scoped(base,r.certificate.file);
    if(raw(file)!==r.certificate.sha256)throw Error('certificate changed');const cert=JSON.parse(readFileSync(file,'utf8'));
    if(!['certified','certified_v2'].includes(cert.status)||cert.holdout_used!==false||!cert.scripts.some((s:any)=>s.script_digest===payload.script_digest&&s.sha256===r.sha256))throw Error('certificate payload mismatch');
    const train=new Set(payload.training.map((s:any)=>s.task_fingerprint));
    const reviews=cert.reviews.filter((s:any)=>s.actual_candidate_execution!==false).filter((s:any)=>s.script_digest?s.script_digest===payload.script_digest:s.task_id.includes(payload.workflow_id));
    if(reviews.length<2||new Set(reviews.map((s:any)=>s.task_fingerprint)).size!==reviews.length||reviews.some((s:any)=>train.has(s.task_fingerprint)||s.role&&s.role!=='certify'))throw Error('certificate role overlap');
   }
  }else if(r.kind==='collection')validateCollectionPolicy(payload);
  else if(r.kind==='reentry')validateReentryPolicy(payload);
  else if(r.kind==='plan')validatePlanPolicy(payload);
  else if(r.kind!=='read_library'||payload.status!=='certified_read_library')throw Error('unknown experience kind');
  if(!r.kind.startsWith('script_')&&r.certificate){
   const certFile=scoped(base,r.certificate.file);if(raw(certFile)!==r.certificate.sha256)throw Error('Motif certificate changed');
   const cert=JSON.parse(readFileSync(certFile,'utf8')),train=new Set(payload.artifact.source_task_fingerprints);
   const reviews=[cert.native_review,...(cert.reviews??[])];
   if(cert.status!=='certified_motif_v1'||cert.policy_digest!==payload.policy_digest||cert.payload_sha256!==r.sha256
    ||cert.holdout_used!==false||cert.quality_and_permission_required!==true||cert.reviews?.length!==2
    ||new Set(reviews.map((v:any)=>v.task_fingerprint)).size!==3||reviews.some((v:any)=>train.has(v.task_fingerprint))
    ||cert.native_review?.role!=='native_certification'||cert.reviews.some((v:any)=>v.role!=='candidate_certification'))
     throw Error('invalid independent Motif execution certificate');
  }
  const compatible=Object.entries(r.runtime_source).every(([n,h])=>existsSync(resolve(root,n))&&raw(resolve(root,n))===h);
  return {...r,payload,compatible};
 });
}
/** Match public task facts + actual MCP observations; no fixture ID or answer oracle. */
export function selectExperience(entries:any[],facts:any,tools:any[]){
 const rejected:any[]=[];const c=facts.task?.workflow_contract;
 const schemaMatch=(p:any)=>Object.entries(p.tool_schema_sha256??{}).every(([name,h])=>{const t=tools.find(t=>t.name===name);return t&&digest(t.parameters)===h;});
 const scripts:any[]=[];
 for(const r of entries){
  if(!r.compatible){rejected.push({entry_id:r.entry_id,reason:'runtime_source_changed'});continue;}
  if(!r.kind.startsWith('script_'))continue;const p=r.payload;
  const guards=r.kind==='script_v1'?[{objective_sha256:p.objective_sha256,context_text_sha256:p.context_text_sha256,destination_prefixes:p.destination_prefixes}]:p.guard_cases;
  const currentRule=facts.rule===null?null:digest(facts.rule);
  const safe=!!c&&facts.task.copy_only===true&&digest(facts.task.allowed_operations)===digest(['copy'])&&digest(c.required_reads)===digest(c.context_paths)
   &&c.context_paths.length<=1&&c.source_paths.length>0&&c.source_paths.length<=32&&c.source_paths.every((n:string)=>facts.inventory.some((r:any)=>r.path===n))
   &&p.execution_version_sha256===facts.task.workflow_execution_version_sha256&&schemaMatch(p);
  const match=safe&&guards.some((g:any)=>g.objective_sha256===digest(facts.task.objective)&&g.context_text_sha256===currentRule
   &&digest(g.destination_prefixes)===digest(c.destination_prefixes));
  if(match)scripts.push(r);else rejected.push({entry_id:r.entry_id,reason:'goal_rule_permission_state_or_schema_mismatch'});
 }
 // Equal proven programs may have different training sets; newest certified version wins.
 const signatures=new Set(scripts.map(r=>digest(r.payload.steps)));
 if(signatures.size>1)return {selected:null,rejected,reason:'ambiguous_certified_programs'};
 if(scripts.length)return {selected:scripts.sort((a,b)=>b.activated_generation-a.activated_generation)[0],rejected,reason:'verified_goal_rule_state'};
 const version=facts.task.workflow_execution_version_sha256??facts.task.report_execution_version_sha256??facts.task.collection_execution_version_sha256;
 const readable=c?c.allowed_reads.length>0&&c.required_reads.length>0:
  facts.task.copy_only===true&&digest(facts.task.allowed_operations)===digest([])&&!!facts.task.report_contract;
 const graphSchemas=(r:any)=>r.kind==='reentry'?r.payload.next_policy.artifact:r.payload.artifact;
 const motifs=entries.filter(r=>r.compatible&&['collection','reentry'].includes(r.kind)&&r.payload.execution_version_sha256===version&&schemaMatch(graphSchemas(r))&&readable);
 if(motifs.length)return {selected:motifs.sort((a,b)=>b.activated_generation-a.activated_generation)[0],rejected,reason:'model_selection_then_certified_read_graph'};
 const plans=entries.filter(r=>r.compatible&&r.kind==='plan'&&r.payload.execution_version_sha256===facts.task.execution_version_sha256&&schemaMatch(r.payload.artifact));
 if(plans.length&&facts.planBinding)return {selected:plans[0],rejected,reason:'explicit_durable_plan_composition'};
 return {selected:null,rejected,reason:'no_verified_experience'};
}
export function createExperienceController(entries:any[],binding:any,audit:(r:any)=>void){
 const spec=binding.spec;let stage='task',pending:any=null,task:any=null,inventory:any[]=[],rule:string|null=null,pin:any=null,controller:any=null,selected:any=null,halted=false,done=false,job:any=null;
 const fail=(reason:string)=>{halted=true;pending=null;controller?.fail(reason);job?.disable(reason);audit({kind:'experience_deferred',reason,entry_id:selected?.entry_id??null});};
 const dispatch=(name:string,args:any)=>{pending={callId:'sss-experience-'+randomUUID(),name:prefix+name,args};audit({kind:'experience_probe',stage,name:pending.name});return {call:{callId:pending.callId,proposal:{tool:pending.name,arguments:args}}};};
 return {get halted(){return halted;},get done(){return done;},fail,
  observe(exec:any,result:any){
   if(halted||done)return;
   if(controller){controller.observe(exec,result);if(controller.halted)fail('selected_experience_guard_failed');return;}
   if(!pending||exec.callId!==pending.callId||exec.name!==pending.name||digest(exec.arguments)!==digest(pending.args)){fail('unexpected_probe_observation');return;}
   const out=observation(result,exec.name);pending=null;if(!out){fail('failed_actual_probe');return;}
   try{
    if(stage==='task'){
     if(out.input_sha256!==digest(spec)||digest(out.objective)!==digest(spec.objective)||(!out.workflow_contract&&!out.report_contract))throw Error('actual task binding changed');
     task=out;stage='inventory';
    }else if(stage==='inventory'){
     if(!Array.isArray(out.files)||out.snapshot_sha256!==digest(spec.initial_snapshot)||out.files.some((r:any)=>spec.initial_snapshot[r.path]!==r.sha256
      ||r.file_id!=='file:local:'+digest({path:r.path,sha:r.sha256}).slice(0,24)||!Number.isSafeInteger(r.bytes)||r.bytes<0)
      ||new Set(out.files.map((r:any)=>r.path)).size!==out.files.length||out.files.length!==Object.keys(spec.initial_snapshot).filter(n=>n!=='.experiment-copy').length)throw Error('current state changed before retrieval');
     // list_files is byte metadata; the certified parser source version is established by pin_file.
     inventory=out.files.map((r:any)=>({...r,source_version:digest({path:r.path,sha:r.sha256,parser:'fm-parser-v1'})}));const c=task.workflow_contract;
     stage=c?.context_paths.length===1&&c.allowed_reads.includes(c.context_paths[0])?'pin':'select';
    }else if(stage==='pin'){
     const r=inventory.find(r=>r.path===task.workflow_contract.context_paths[0]);
     if(!r||out.file_id!==r.file_id||out.source_version!==r.source_version||typeof out.source_id!=='string')throw Error('rule source changed');pin=out;stage='read';
    }else if(stage==='read'){
     const r=inventory.find(r=>r.path===task.workflow_contract.context_paths[0]);
     if(out.source_id!==pin.source_id||out.source_version!==r.source_version||out.sha256!==r.sha256||out.status!=='readable'||out.truncated)throw Error('unverified rule read');
     rule=out.text;stage='select';
    }
    audit({kind:'experience_probe_verified',stage:exec.name,call_id:exec.callId,observation_sha256:digest(out)});
   }catch(e:any){fail(e.message);}
  },
  propose(tools:any[]){
   if(halted||done||pending)return null;
   if(controller){
    if(job&&!job.allow()){fail('original_job_limit');return null;}
    const p=selected.kind.startsWith('script_')?controller.propose(tools):{calls:controller.propose(tools,randomUUID)};
    if(controller.halted){fail('selected_experience_guard_failed');return null;}
    if(controller.done&&!selected.kind.startsWith('script_')){done=true;return null;}
    if(p?.terminal)done=true;return p;
   }
   try{
    if(stage==='task')return dispatch('read_task',{});
    if(stage==='inventory')return dispatch('list_files',{});
    if(stage==='pin')return dispatch('pin_file',{file_id:inventory.find(r=>r.path===task.workflow_contract.context_paths[0]).file_id});
    if(stage==='read')return dispatch('read_file',{source_id:pin.source_id});
    const choice=selectExperience(entries,{task,inventory,rule,planBinding:binding.plan_binding},tools);
    audit({kind:'experience_retrieval',...choice,selected:choice.selected?{entry_id:choice.selected.entry_id,kind:choice.selected.kind}:null,goal_sha256:digest(task.objective),rule_sha256:rule===null?null:digest(rule)});
    selected=choice.selected;if(!selected){fail(choice.reason);return null;}
    const scope={schema_version:1,session_id:binding.session_id,task_id:task.task_id,input_version:digest(spec),snapshot_sha256:digest(spec.initial_snapshot),initial_snapshot:spec.initial_snapshot,
     inventory,inventory_sha256:digest(inventory),execution_version_sha256:selected.payload.execution_version_sha256};
    if(selected.kind==='script_v1'||selected.kind==='script_v2')controller=(selected.kind==='script_v1'?createV1:createV2)(selected.payload,{spec,input_sha256:digest(spec),prompt_sha256:binding.prompt_sha256},audit);
    else if(selected.kind==='collection'||selected.kind==='reentry'){
     controller=(selected.kind==='collection'?createCollectionController:createReentryController)(selected.payload,scope,audit);
     if(selected.kind==='collection')audit({kind:'collection_motif_loaded',policy_digest:selected.payload.policy_digest});
    }
    else if(selected.kind==='plan'){
     const sc={...scope,grant:spec.write_grant,grant_sha256:digest(spec.write_grant)};
     job=createJobPlanGuard(root,binding.plan_binding,binding.plan_policy,sc,audit);if(!job.activate())throw Error('durable plan activation denied');controller=createPlanController(selected.payload,sc,audit);
    }else throw Error('experience has no certified executor');
    audit({kind:'experience_selected',entry_id:selected.entry_id,experience_kind:selected.kind,activated_generation:selected.activated_generation});
    if(selected.kind.startsWith('script_'))return controller.propose(tools);
    return null; // Real model supplies semantic selections / effects; Motif only follows its certified boundary.
   }catch(e:any){fail(e.message);return null;}
  }
 };
}
export function apply(ctx:any){
 const file=process.env.SSS_EXPERIENCE_BINDING;if(!file)return;
 if(!resolve(file).startsWith(resolve(root,'.local')+sep)||lstatSync(file).isSymbolicLink())throw Error('private experience binding required');
 const b=JSON.parse(readFileSync(file,'utf8'));
 if(raw(b.task_file)!==b.task_sha256||raw(fileURLToPath(import.meta.url))!==b.runtime_sha256)throw Error('experience task/runtime binding changed');
 const entries=loadExperiences(b.registry_root,b.registry_file,b.registry_sha256,b.role==='certify');
 const spec=JSON.parse(readFileSync(b.task_file,'utf8'));let session:any=null,live=false,envelope:any=null,started=false;
 const audit=(row:any)=>appendFileSync(b.audit_file,JSON.stringify({...row,session_id:session})+'\n',{mode:0o600});
 const runtimeBinding={...b,spec};const c=createExperienceController(entries,runtimeBinding,audit);
 ctx.on('agent/created',({agent}:any)=>{if(session!==null){c.fail('additional_agent');return;}session=agent.session.id;runtimeBinding.session_id=session;live=true;agent.ctx.on('tools/result',c.observe);});
 ctx.on('agent/disposed',()=>{live=false;});
 ctx.on('llm/stream',(options:any,next:()=>any)=>{
  if(!live||options.sessionId!==session||!isAgentLoopRequest(options)||c.halted||c.done)return next();
  if(options.messages.some((m:any)=>m.source?.kind==='task-acceptance-repair')){c.fail('acceptance_repair_requires_ordinary_harness');return next();}
  const human=options.messages.filter((m:any)=>m.role==='user'&&m.source?.kind==='user');
  const texts=human.map((m:any)=>m.content?.length===1&&m.content[0].type==='text'?m.content[0].text:null);
  const matching=texts.filter((s:any)=>typeof s==='string'&&createHash('sha256').update(s).digest('hex')===b.prompt_sha256);
  const reminders=texts.filter((s:any)=>typeof s==='string'&&(s.startsWith('<system-reminder>\n')||s.startsWith('Current runtime context. This snapshot supersedes')));
  const now=digest(human.map((m:any)=>({id:m.id,content:m.content})));
  if(matching.length!==1||matching.length+reminders.length!==human.length||reminders.length>2||(envelope!==null&&envelope!==now)
   ||!started&&options.messages.some((m:any)=>m.role==='assistant')){c.fail('prompt_or_start_boundary_changed');return next();}
  started=true;envelope=now;const proposal=c.propose(options.tools??[]);
  return proposal?.terminal?terminalStream({status:'experience_delivery_pending_fixed_acceptance',receipt:proposal.terminal}):proposal?.call?syntheticToolStreamBatch([proposal.call]):proposal?.calls?.length?syntheticToolStreamBatch(proposal.calls):next();
 },{global:true});
}
