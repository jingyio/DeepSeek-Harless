/** L1 is immutable; only certified fresh model reentry can invoke the learned next episode. */
import {digest} from './online_skill_runtime.mjs';
import {validateCollectionPolicy,validateCollectionTask,createCollectionController} from './collection_read_policy.ts';
const unsigned=(v:any,k:string)=>Object.fromEntries(Object.entries(v??{}).filter(([n])=>n!==k));
export function validateReentryPolicy(p:any){
 if(p?.format!=='sss-collection-reentry-v1'||p.schema_version!==1||p.policy_digest!==digest(unsigned(p,'policy_digest')))throw new TypeError('invalid L2 policy');
 validateCollectionPolicy(p.parent_policy);validateCollectionPolicy(p.next_policy);const a=p.artifact;
 if(a?.kind!=='certified_collection_reentry'||a.status!=='trace_validated_read_only'||a.certified_digest!==digest(unsigned(a,'certified_digest'))
  ||a.max_episodes!==2||a.trigger!=='fresh_model_selection_after_verified_gather'||a.auto_select!==false
  ||a.parent_boundary_is_execution_evidence_only!==true||a.runtime_nodes_used_for_new_parameter_discovery!==false
  ||p.execution_version_sha256!==p.parent_policy.execution_version_sha256||p.execution_version_sha256!==p.next_policy.execution_version_sha256
  ||digest(p.parent_policy.artifact.graph)!==digest(p.next_policy.artifact.graph)
  ||digest(p.parent_policy.artifact.tool_schema_sha256)!==digest(p.next_policy.artifact.tool_schema_sha256)
  ||!Array.isArray(a.source_task_fingerprints)||a.source_task_fingerprints.length<2||new Set(a.source_task_fingerprints).size!==a.source_task_fingerprints.length
  ||a.source_task_fingerprints.includes(a.validation_task_fingerprint)
  ||digest(a.source_task_fingerprints)!==digest(p.next_policy.artifact.source_task_fingerprints)
  ||a.validation_task_fingerprint!==p.next_policy.artifact.validation_task_fingerprint
  ||!Array.isArray(a.training_episodes)||a.training_episodes.length!==a.source_task_fingerprints.length
  ||digest(a.training_episodes.map((e:any)=>e.residual_witness))!==digest(p.next_policy.artifact.training_witnesses)
  ||digest(a.validation_episode?.residual_witness)!==digest(p.next_policy.artifact.validation_witness))throw new TypeError('changed L1/L2 certification');
 for(const e of [...a.training_episodes,a.validation_episode]){
  if(!Number.isSafeInteger(e?.parent_boundary?.result_seq)||e.parent_boundary.result_seq<0
   ||typeof e.parent_boundary.selection_call_id!=='string'||e.parent_boundary.selection_call_id.startsWith('sss-')
   ||e?.parent_policy_digest!==p.parent_policy.policy_digest||e.runtime_nodes_used_for_new_parameter_discovery!==false
   ||!e.parent_boundary?.call_id?.startsWith('sss-')||e.residual_witness?.references?.[0]?.message_seq<=e.parent_boundary.result_seq
   ||e.residual_witness?.references?.some((r:any)=>r.call_id.startsWith('sss-')))throw new TypeError('Runtime is not new model evidence');
 }
 return p;
}
export function validateReentryTask(t:any,p:any){return validateCollectionTask(t,p);}
export function createReentryController(policy:any,task:any,audit:(r:any)=>void){
 validateReentryPolicy(policy);validateReentryTask(task,policy);let epoch=1,halted=false;
 const make=(p:any)=>createCollectionController(p,task,(row:any)=>{
  audit({...row,library_epoch:epoch,library_role:epoch===1?'frozen_L1':'learned_L2_residual'});
  if(row.kind==='collection_model_request_bypassed_verified'&&epoch===2)audit({kind:'reentry_epoch_batch_verified',stage:row.stage,batch_id:row.batch_id,count:row.count});
 });
 let child=make(policy.parent_policy);
 const fail=(reason:string)=>{halted=true;child.fail(reason);audit({kind:'reentry_deferred',reason});};
 return {get armed(){return child.armed&&!child.done;},get done(){return epoch===2&&child.done;},get halted(){return halted||child.halted;},get pending(){return child.pending;},fail,
  observe(exec:any,result:any){
   if(halted||child.halted||epoch===2&&child.done)return;
   if(child.done){
    if(exec.name!==policy.next_policy.artifact.graph.source_tool)return;
    if(String(exec.callId).startsWith('sss-')){fail('reentry_requires_actual_model_selection');return;}
    epoch=2;child=make(policy.next_policy);
    audit({kind:'reentry_model_frontier_observed',call_id:exec.callId,parent_policy_digest:policy.parent_policy.policy_digest,next_policy_digest:policy.next_policy.policy_digest});
   }
   child.observe(exec,result);
  },propose(tools:any[],newId:()=>string){if(halted)return [];return child.propose(tools,newId);}
 };
}
