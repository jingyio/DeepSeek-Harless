/** Generic operation graph retrieval; scene contracts own scope and authority. */
import {readFileSync,appendFileSync,lstatSync,existsSync} from 'node:fs';
import {resolve,dirname,sep} from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {isAgentLoopRequest} from '@deepseek-ai/dsh-llm';
import {digest,observation,syntheticToolStreamBatch} from '../motif_core/online_skill_runtime.mjs';
import {validateOperationPolicy,createOperationController,requestLane} from '../motif_core/operation_graph_policy.ts';
import {controlFlowRootApplies} from '../motif_core/control_flow_policy.ts';
import {OperationJob} from './operation_job.ts';
import {validateManagementProgram,createManagementProgramRuntime} from './management_program.ts';
import {createTemporalBarrier} from './management_temporal.ts';
import {validatePublicManagementSeed} from './management_seed.ts';
export const name='sss-operation-motif';export const inject=['agents','llm'];
const root=resolve(fileURLToPath(new URL('../../',import.meta.url)));
const raw=(p:string)=>createHash('sha256').update(readFileSync(p)).digest('hex');
const read=(p:string)=>JSON.parse(readFileSync(p,'utf8'));
function privatePath(p:string){
 const f=resolve(p),base=resolve(root,'.local');if(!f.startsWith(base+sep))throw Error('private operation binding required');
 for(let q=f;q.startsWith(base+sep);q=dirname(q))if(existsSync(q)&&lstatSync(q).isSymbolicLink())throw Error('operation symlink refused');return f;
}
function object(base:string,p:string){if(typeof p!=='string'||p.startsWith('/')||p.includes('\\')||p.split('/').some(v=>!v||v==='.'||v==='..'))throw Error('invalid immutable object');return privatePath(resolve(base,p));}
export function loadOperationEntries(b:any){
 const file=privatePath(b.registry_file);if(raw(file)!==b.registry_sha256)throw Error('library snapshot changed');
 const state=read(file);if(state.registry_digest!==digest(Object.fromEntries(Object.entries(state).filter(([k])=>k!=='registry_digest'))))throw Error('library digest changed');
 const entries=[];
 for(const e of state.entries){
  if(!['operation_graph','management_program'].includes(e.kind)||!(e.state==='active'||b.role==='certify'&&e.state==='candidate'))continue;
  if(Object.entries(e.runtime_source).some(([n,h])=>raw(resolve(root,n))!==h))continue;
  const payload=object(b.registry_root,e.payload);if(raw(payload)!==e.sha256)throw Error('operation payload mutated');
  const p=(e.kind==='management_program'?validateManagementProgram:validateOperationPolicy)(read(payload));
  if(e.certificate){
   const cfile=object(b.registry_root,e.certificate.file);if(raw(cfile)!==e.certificate.sha256)throw Error('operation certificate mutated');const c=read(cfile);
   if(c.format==='sss-management-seed-attestation-v1')validatePublicManagementSeed(p,c,e.sha256,e.runtime_source);
   else {
   if(c.status!==(p.format==='sss-operation-flow-v3'?'certified_motif_v3':p.format==='sss-operation-graph-v2'?'certified_motif_v2':'certified_motif_v1')||c.policy_digest!==p.policy_digest||c.payload_sha256!==e.sha256||c.holdout_used!==false
    ||raw(privatePath(c.candidate_lock_file))!==c.candidate_lock_sha256)throw Error('uncertified operation');
   for(const review of [c.native_review,...c.reviews])if(raw(privatePath(review.record_file))!==review.record_sha256)throw Error('operation proof mutated');
   if(e.kind==='management_program'&&(c.certification_contract!=='sss-management-program-certification-v1'||raw(privatePath(c.native_program_proof_file))!==c.native_program_proof_sha256))throw Error('native program proof changed');
   }
  }else if(b.role!=='certify')throw Error('independent operation certificate required');
  entries.push({...e,policy:p});
 }return entries;
}
export function createOperationRuntime(b:any,audit:(r:any)=>void){
 const loaded=loadOperationEntries(b),entries=loaded.filter(e=>e.kind==='operation_graph');let controller:any=null,choice:any=null,halted=false;
 const programs=b.adapter==='management_v3'?createManagementProgramRuntime(loaded.filter(e=>e.kind==='management_program'),b,read(privatePath(b.task_file)),audit):null;
 const temporal=b.adapter==='management_v3'?createTemporalBarrier(read(privatePath(b.task_file)),b.scope,audit):null;
 const executions=new Map<string,number>();let flowRuns:any[]=[],laneRuns:any[]=[];
 audit({kind:'experience_runtime_ready',entries:entries.length,catalog_sha256:digest(b.catalog),scope_sha256:digest(b.scope)});
 const fail=(reason:string,entryId?:string)=>{halted=true;controller?.fail(reason);for(const run of [...flowRuns,...laneRuns])if(!run.controller.done)run.controller.fail(reason);programs?.fail(reason);audit({kind:'experience_deferred',reason,entry_id:entryId??choice?.entry_id??null});};
 const compatible=(e:any,exec:any)=>e.policy.artifact.nodes[0].tool===exec.name&&e.policy.execution_version_sha256===b.scope.execution_version
  &&Object.entries({...e.policy.artifact.tool_contracts,...e.policy.artifact.interleaving_contracts,...e.policy.artifact.request_lane_contracts}).every(([n,t]:any)=>digest(b.catalog[n]??null)===digest(t)&&Object.entries(t.contract.scope_requirements??{}).every(([k,v])=>b.scope[k]===v));
 const rootApplies=(e:any,out:any)=>{const c=e.policy.artifact.tool_contracts[e.policy.artifact.nodes[0].tool].contract;
  return digest(out?._sss_scope??null)!==digest(b.scope)||(!c.statuses||c.statuses.includes(out?.status))&&(c.effect!=='authorized_write'||out?._sss_authorized===true)
   &&(e.policy.format!=='sss-operation-flow-v3'||controlFlowRootApplies(e.policy,out));};
 return {get halted(){return halted;},fail,
  observe(exec:any,result:any){
   if(halted)return;
   temporal?.observe(exec,result);
   if(programs?.observe(exec,result)){if(programs.halted)halted=true;return;}
   if(controller?.done){const key=choice.policy.artifact.legacy_adapter?.key??choice.entry_id;executions.set(key,(executions.get(key)??0)+1);controller=null;choice=null;}
   laneRuns=laneRuns.filter(r=>!r.controller.done);flowRuns=flowRuns.filter(r=>!r.controller.done);
   if(!controller&&!flowRuns.length){
    const out=observation(result,exec.name),lane=requestLane(exec,out,b.catalog,b.scope);
    if(lane&&!String(exec.callId).startsWith('sss-')&&!laneRuns.some(r=>r.controller.willConsume(exec))){
     const entry=entries.filter(e=>e.policy.format==='sss-operation-graph-v2'&&compatible(e,exec)&&rootApplies(e,out)
      &&e.policy.artifact.request_lane_contracts?.[exec.name]).sort((a,b)=>b.policy.artifact.nodes.length-a.policy.artifact.nodes.length||b.activated_generation-a.activated_generation)[0];
     if(entry&&!laneRuns.some(r=>r.key===lane.request_id)){
      if(laneRuns.length>=16){fail('prepared_request_pool_limit',entry.entry_id);return;}
      laneRuns.push({key:lane.request_id,entry,controller:createOperationController(entry.policy,b.scope,audit)});
      audit({kind:'experience_selected',entry_id:entry.entry_id,experience_kind:'operation_graph',activated_generation:entry.activated_generation,request_id:lane.request_id});
     }
    }
    if(laneRuns.length){for(const run of laneRuns){run.controller.observe(exec,result);if(run.controller.halted){fail('operation_guard_failed',run.entry.entry_id);return;}}return;}
   }
   if(!controller){
    flowRuns=flowRuns.filter(r=>!r.controller.done);
    const out=observation(result,exec.name),error=result?.isError===true||result?.value?.isError===true;
    if(!error&&!String(exec.callId).startsWith('sss-')&&!flowRuns.some(r=>r.controller.willConsume(exec))){
     const candidates=entries.filter(e=>e.policy.format==='sss-operation-flow-v3'&&compatible(e,exec)&&rootApplies(e,out))
       .sort((a,b)=>b.policy.artifact.nodes.length-a.policy.artifact.nodes.length||b.activated_generation-a.activated_generation);
     if(candidates.length){const entry=candidates[0],key=digest({tool:exec.name,out});
      if(flowRuns.length<16&&!flowRuns.some(r=>r.key===key)){
       flowRuns.push({key,entry,controller:createOperationController(entry.policy,b.scope,audit)});
       audit({kind:'experience_selected',entry_id:entry.entry_id,experience_kind:'operation_graph',activated_generation:entry.activated_generation});
      }
     }
    }
    if(flowRuns.length){
     for(const run of flowRuns){run.controller.observe(exec,result);if(run.controller.halted){fail('operation_guard_failed',run.entry.entry_id);return;}}
     return;
    }
    const candidates=entries.filter(e=>e.policy.format!=='sss-operation-flow-v3'&&compatible(e,exec)
     &&(e.policy.artifact.legacy_adapter?.family!=='reentry'||(executions.get(e.policy.artifact.legacy_adapter.key)??0)<2)
     &&(e.policy.artifact.legacy_adapter?.family!=='plan'||Array.isArray(exec.arguments?.actions)&&exec.arguments.actions.length<=6&&exec.arguments.actions.every((a:any)=>['copy','move','quarantine'].includes(a.op))&&observation(result,exec.name)?.risks?.length===0)
    );
    if(!candidates.length)return;
    // A rejected native call has not established a graph root. Keep its error
    // in the ordinary trajectory and let the model correct it before admission.
    if(result?.isError===true||result?.value?.isError===true){
     audit({kind:'operation_root_error_observed',tool:exec.name,call_id:exec.callId,model_request_bypassed:false});return;
    }
    const rootOutput=observation(result,exec.name);
    const applicable=candidates.filter(e=>rootApplies(e,rootOutput));
    if(!applicable.length){audit({kind:'operation_root_not_applicable',tool:exec.name,call_id:exec.callId,model_request_bypassed:false});return;}
    choice=applicable.sort((a,b)=>Number(b.policy.format==='sss-operation-flow-v3')-Number(a.policy.format==='sss-operation-flow-v3')||b.policy.artifact.nodes.length-a.policy.artifact.nodes.length||b.activated_generation-a.activated_generation)[0];
    controller=createOperationController(choice.policy,b.scope,audit);
    audit({kind:'experience_selected',entry_id:choice.entry_id,experience_kind:'operation_graph',activated_generation:choice.activated_generation});
   }
   controller.observe(exec,result);if(controller.halted)fail('operation_guard_failed');
  },propose(tools:any[],messages:any[]){
   if(halted)return [];
   if(programs?.active){if(temporal&&!temporal.ready(messages))return [];const result=programs.propose(tools,randomUUID);if(programs.halted)halted=true;return result;}
   const ids=new Set<string>();
   for(const m of messages)if(m.role==='assistant'&&m.source?.kind==='model')for(const c of m.content??[])if(c.type==='tool-call')ids.add(c.id);
   laneRuns=laneRuns.filter(r=>!r.controller.done);
   if(laneRuns.some(r=>r.controller.pending))return [];
   for(const run of laneRuns){if(temporal&&!temporal.ready(messages,run.controller.nextTool))continue;const calls=run.controller.propose(tools,randomUUID,ids);if(run.controller.halted){fail('operation_guard_failed',run.entry.entry_id);return [];}if(calls.length)return calls;}
   flowRuns=flowRuns.filter(r=>!r.controller.done);
   if(flowRuns.some(r=>r.controller.pending))return [];
   for(const run of flowRuns){if(temporal&&!temporal.ready(messages,run.controller.nextTool))continue;const calls=run.controller.propose(tools,randomUUID,ids);if(run.controller.halted){fail('operation_guard_failed',run.entry.entry_id);return [];}if(calls.length)return calls;}
   return controller&&!halted&&(!temporal||temporal.ready(messages,controller.nextTool))?controller.propose(tools,randomUUID,ids):[];
  }
 };
}
export function apply(ctx:any){
 const file=process.env.SSS_OPERATION_BINDING;if(!file)return;const b=read(privatePath(file));
 if(raw(privatePath(b.task_file))!==b.task_sha256)throw Error('operation task changed');
 for(const [n,h] of Object.entries(b.runtime_source))if(raw(resolve(root,n))!==h)throw Error('operation runtime changed');
 const audit=(v:any)=>appendFileSync(privatePath(b.audit_file),JSON.stringify({...v,session_id:b.session_id})+'\n',{mode:0o600});
 const c=createOperationRuntime(b,audit);let live=false,envelope:string|null=null;
 ctx.on('agent/created',({agent}:any)=>{if(live||agent.session.id!==b.session_id){c.fail('operation_session_changed');return;}live=true;agent.ctx.on('tools/result',c.observe);});
 ctx.on('agent/disposed',()=>{live=false;});
 ctx.on('llm/stream',(o:any,next:()=>any)=>{
  if(!live||o.sessionId!==b.session_id||!isAgentLoopRequest(o)||c.halted)return next();
  if(o.messages.some((m:any)=>m.source?.kind==='task-acceptance-repair')){c.fail('repair_requires_ordinary_harness');return next();}
  const users=o.messages.filter((m:any)=>m.role==='user'&&m.source?.kind==='user');const now=digest(users.map((m:any)=>({id:m.id,content:m.content})));
  const match=users.filter((m:any)=>m.content?.length===1&&m.content[0].type==='text'&&createHash('sha256').update(m.content[0].text).digest('hex')===b.prompt_sha256);
  if(match.length!==1||envelope!==null&&envelope!==now){c.fail('operation_user_envelope_changed');return next();}
  envelope=now;const calls=c.propose(o.tools??[],o.messages);
  if(calls.length&&b.job_file)new OperationJob(root,b.job_file).apply('motif-step');
  return calls.length?syntheticToolStreamBatch(calls):next();
 },{global:true});
}
