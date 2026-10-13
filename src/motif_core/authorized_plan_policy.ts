/** Bounded effectful continuation; server-issued task capability required before every effect. */
import {digest,observation} from './online_skill_runtime.mjs';
const hex=(v:any)=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const unsigned=(v:any,k:string)=>Object.fromEntries(Object.entries(v??{}).filter(([n])=>n!==k));
const validPath=(p:any)=>typeof p==='string'&&p.length>0&&p.length<=180&&!p.startsWith('/')&&!p.includes('\\')&&p.split('/').every((v:string)=>v!==''&&v!=='.'&&v!=='..')&&!/[\x00-\x1f]/.test(p);
export function validatePlanPolicy(p:any){
 const a=p?.artifact,g=a?.graph,tools=a?.tools;
 if(p?.format!=='sss-authorized-plan-v1'||p.schema_version!==1||!hex(p.execution_version_sha256)||p.policy_digest!==digest(unsigned(p,'policy_digest'))
  ||a?.kind!=='authorized_copy_plan_chain'||a.status!=='trace_validated_effectful'||a.certified_digest!==digest(unsigned(a,'certified_digest'))
  ||!Array.isArray(a.source_task_fingerprints)||a.source_task_fingerprints.length<2||new Set(a.source_task_fingerprints).size!==a.source_task_fingerprints.length
  ||!a.validation_task_fingerprint||a.source_task_fingerprints.includes(a.validation_task_fingerprint)
  ||!Array.isArray(tools)||tools.length!==3||new Set(tools).size!==3||tools.some((t:any)=>typeof t!=='string'||!/^mcp__[a-zA-Z0-9_]+$/.test(t))
  ||digest(tools)!==digest([g?.preview_tool,g?.authorize_tool,g?.execute_tool])||g.max_actions!==6||digest(g.allowed_ops)!==digest(['copy','move','quarantine'])
  ||g.stop!=='after_verified_execution_or_semantic_recovery'||Object.keys(a.tool_schema_sha256??{}).length!==3||tools.some((t:string)=>!hex(a.tool_schema_sha256[t])))throw new TypeError('invalid certified authorized plan policy');
 const edges=[{from:tools[0]+'.plan_id',to:tools[1]+'.plan_id'},{from:tools[0]+'.plan_id',to:tools[2]+'.plan_id'},{from:tools[1]+'.authorization_id',to:tools[2]+'.authorization_id'}];
 if(digest(edges)!==digest(a.transfer_evidence))throw new TypeError('changed plan parameter graph');return p;
}
export function validatePlanTask(t:any,p:any){
 const grant=t?.grant,rows=t?.inventory;
 if(t?.schema_version!==1||typeof t.session_id!=='string'||typeof t.task_id!=='string'||!hex(t.input_version)||t.execution_version_sha256!==p.execution_version_sha256
  ||!t.initial_snapshot||t.snapshot_sha256!==digest(t.initial_snapshot)||!Array.isArray(rows)||!rows.length||rows.length>32
  ||rows.some((r:any)=>!validPath(r.path)||typeof r.file_id!=='string'||!hex(r.sha256)||t.initial_snapshot[r.path]!==r.sha256)
  ||new Set(rows.map((r:any)=>r.file_id)).size!==rows.length||t.inventory_sha256!==digest(rows)
  ||grant?.schema_version!==1||!Number.isInteger(grant.max_actions)||grant.max_actions<1||grant.max_actions>6||typeof grant.allow_restore!=='boolean'
  ||!Array.isArray(grant.allowed_ops)||!grant.allowed_ops.length||grant.allowed_ops.some((o:any)=>!['copy','move','quarantine'].includes(o))
  ||!Array.isArray(grant.source_paths)||!grant.source_paths.length||grant.source_paths.some((n:any)=>!rows.some((r:any)=>r.path===n))
  ||!Array.isArray(grant.destination_prefixes)||!grant.destination_prefixes.length||grant.destination_prefixes.some((d:any)=>typeof d!=='string'||!d.endsWith('/')||!validPath(d.slice(0,-1)))
  ||t.grant_sha256!==digest(grant))throw new TypeError('invalid bounded task write grant');return t;
}
export function planEffects(t:any,actions:any[]){
 const after={...t.initial_snapshot},seen=new Set(),destinations:string[]=[],scope=new Map(t.inventory.map((r:any)=>[r.file_id,r]));
 if(!Array.isArray(actions)||!actions.length||actions.length>t.grant.max_actions)throw new TypeError('action count outside grant');
 for(const a of actions){const row:any=Array.isArray(a?.file_ids)&&a.file_ids.length===1?scope.get(a.file_ids[0]):null;
  if(digest(Object.keys(a).sort())!==digest(['destination','file_ids','format','op'])||!row||seen.has(row.path)||!t.grant.source_paths.includes(row.path)
   ||!t.grant.allowed_ops.includes(a.op)||a.format!=='none'||!validPath(a.destination)||a.destination.startsWith('.experiment-copy')
   ||!t.grant.destination_prefixes.some((d:string)=>a.destination.startsWith(d))||after[a.destination]!==undefined
   ||destinations.some(d=>d.startsWith(a.destination+'/')||a.destination.startsWith(d+'/')))throw new TypeError('effect source/destination outside grant');
  seen.add(row.path);destinations.push(a.destination);after[a.destination]=row.sha256;if(a.op!=='copy')delete after[row.path];
 }return after;
}
export function createPlanController(policy:any,task:any,audit:(r:any)=>void){
 validatePlanPolicy(policy);validatePlanTask(task,policy);const g=policy.artifact.graph;
 let preview:any=null,token:any=null,effects:any=null,pending:any=null,halted=false,done=false;
 const fail=(reason:string)=>{halted=true;audit({kind:'plan_motif_deferred',reason,requires_semantic_recovery:true});};
 return {get armed(){return preview!==null;},get pending(){return pending?1:0;},get done(){return done;},get halted(){return halted;},fail,
 observe(exec:any,result:any){
  if(halted||done)return;const out=observation(result,exec.name);
  if(!pending){
   if(preview){fail('interleaved_operation');return;}if(exec.name!==g.preview_tool)return;
   try{effects=planEffects(task,out?.actions);}catch{fail('effect_outside_task_grant');return;}
   if(String(exec.callId).startsWith('sss-')||!Array.isArray(exec.arguments?.actions)||digest(Object.keys(exec.arguments))!==digest(['actions'])||digest(exec.arguments.actions.map((a:any)=>({format:'none',...a})))!==digest(out.actions)||out.status!=='validated_copy_plan'
    ||out.permission_status!=='within_task_grant'||out.copy_only!==true||typeof out.plan_id!=='string'||!hex(out.plan_sha256)
    ||out.preview_sha256!==digest(unsigned(out,'preview_sha256'))||out.input_sha256!==task.input_version||out.snapshot_sha256!==task.snapshot_sha256
    ||out.execution_version_sha256!==task.execution_version_sha256||out.grant_sha256!==task.grant_sha256){fail('changed_or_unapproved_preview');return;}
   preview=out;audit({kind:'plan_model_preview_verified',call_id:exec.callId,preview_sha256:out.preview_sha256,operation_count:out.actions.length});return;
  }
  const expected=pending;pending=null;
  if(exec.callId!==expected.callId||exec.name!==expected.tool||digest(exec.arguments)!==digest(expected.args)||!out){fail('execution_failed_manual_recovery');return;}
  const base=out.plan_id===preview.plan_id&&out.copy_only===true&&out.input_sha256===task.input_version&&out.execution_version_sha256===task.execution_version_sha256&&out.grant_sha256===task.grant_sha256;
  if(expected.stage==='authorize'){
   if(!base||out.status!=='task_grant_authorized'||out.single_plan!==true||typeof out.authorization_id!=='string'||out.snapshot_sha256!==task.snapshot_sha256
    ||out.operation_count!==preview.actions.length||out.preview_sha256!==preview.preview_sha256||out.plan_sha256!==preview.plan_sha256
    ||out.authorization_sha256!==digest(unsigned(out,'authorization_sha256'))){fail('authorization_changed_or_denied');return;}
   token=out;audit({kind:'plan_authorization_verified',authorization_id:out.authorization_id,authorization_sha256:out.authorization_sha256});
  }else{
   if(!base||out.status!=='executed_verified'||out.authorization_id!==token.authorization_id||out.authorization_sha256!==token.authorization_sha256
    ||out.plan_sha256!==preview.plan_sha256||out.operation_count!==preview.actions.length||out.snapshot_sha256!==digest(effects)||!hex(out.journal_sha256)){fail('unverified_effect_receipt');return;}
   done=true;audit({kind:'plan_execution_verified',receipt_sha256:digest(out),snapshot_sha256:out.snapshot_sha256,operation_count:out.operation_count});
  }
  audit({kind:'plan_model_request_bypassed_verified',stage:expected.stage,call_id:exec.callId});
 },
 propose(tools:any[],newId:()=>string){
  if(!preview||pending||halted||done)return [];
  for(const name of policy.artifact.tools){const t=tools.find((t:any)=>t.name===name);if(!t||digest(t.parameters)!==policy.artifact.tool_schema_sha256[name]){fail('plan_schema_changed');return [];}}
  const tool=token?g.execute_tool:g.authorize_tool,args=token?{plan_id:preview.plan_id,authorization_id:token.authorization_id}:{plan_id:preview.plan_id};
  const callId='sss-plan-'+newId();pending={callId,tool,args,stage:token?'execute':'authorize'};
  audit({kind:'plan_motif_bypass_attempt',stage:pending.stage,call_id:callId,policy_digest:policy.policy_digest});return [{callId,proposal:{tool,arguments:args}}];
 }};
}
