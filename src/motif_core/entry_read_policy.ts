/** Bounded interpreter for an independently learned task-entry read frontier. */
import {digest, observation} from './online_skill_runtime.mjs';
import {validateInventoryPolicy,validateInventoryTask,createInventoryController} from './inventory_entry_policy.ts';
const hex = (v:any) => typeof v==='string' && /^[a-f0-9]{64}$/.test(v);
export function validateEntryPolicy(p:any){
  if(['sss-entry-inventory-v1','sss-entry-incremental-v1'].includes(p?.format))return validateInventoryPolicy(p);
  const a=p?.artifact,e=a?.entry;
  if(p?.schema_version!==1||p.format!=='sss-entry-read-v1'||!hex(p.policy_digest)
    ||p.policy_digest!==digest(Object.fromEntries(Object.entries(p).filter(([k])=>k!=='policy_digest')))
    ||!hex(p.source_library_digest)||!hex(p.execution_version_sha256)||!hex(a?.schema_sha256)
    ||a?.kind!=='task_entry_read_frontier'||a.status!=='trace_validated_read_only'
    ||a.certified_digest!==digest(Object.fromEntries(Object.entries(a).filter(([k])=>k!=='certified_digest')))
    ||!Array.isArray(a.source_task_fingerprints)||a.source_task_fingerprints.length<2
    ||new Set(a.source_task_fingerprints).size!==a.source_task_fingerprints.length
    ||!a.validation_task_fingerprint||a.source_task_fingerprints.includes(a.validation_task_fingerprint)
    ||e?.kind!=='foreach_frozen_targets'||e.selection!=='all_targets'||e.max_targets!==100||e.max_batch!==8
    ||e.stop!=='semantic_handoff_after_reads'||typeof e.tool!=='string'||!/^mcp__[a-zA-Z0-9_]+$/.test(e.tool)
    ||typeof e.param!=='string'||!/^\w+$/.test(e.param)||e.result_identity_field!==e.param
    ||e.result_input_field!=='input_sha256'||e.result_source_field!=='document_version_sha256')
    throw new TypeError('invalid or changed certified entry policy');
  return p;
}
export function validateEntryTask(t:any,p:any){
  if(['sss-entry-inventory-v1','sss-entry-incremental-v1'].includes(p?.format))return validateInventoryTask(t,p);
  if(t?.schema_version!==1||typeof t.session_id!=='string'||!t.session_id||typeof t.task_id!=='string'||!t.task_id
    ||!hex(t.input_version)||t.execution_version_sha256!==p.execution_version_sha256
    ||!Array.isArray(t.target_ids)||t.target_ids.length>p.artifact.entry.max_targets
    ||t.target_ids.some((x:any)=>typeof x!=='string'||!x||x.length>160)
    ||new Set(t.target_ids).size!==t.target_ids.length||t.target_ids_sha256!==digest(t.target_ids)
    ||!t.target_versions||typeof t.target_versions!=='object'||Array.isArray(t.target_versions)
    ||Object.keys(t.target_versions).length!==t.target_ids.length
    ||t.target_ids.some((x:string)=>!hex(t.target_versions[x])))throw new TypeError('invalid or stale frozen entry task');
  return t;
}
export function createEntryController(policy:any,task:any,audit:(r:any)=>void){
  if(['sss-entry-inventory-v1','sss-entry-incremental-v1'].includes(policy?.format))return createInventoryController(policy,task,audit);
  validateEntryPolicy(policy);validateEntryTask(task,policy);
  const e=policy.artifact.entry,pending=new Map<string,any>(),used=new Set<string>();
  let cursor=0,halted=false,done=task.target_ids.length===0;
  return {
    get halted(){return halted;},get done(){return done;},get pending(){return pending.size;},
    fail(reason:string){halted=true;audit({kind:'entry_motif_deferred',reason});},
    propose(tools:any[],newId:()=>string){
      if(halted||done||pending.size)return [];
      const tool=tools.find(t=>t.name===e.tool);
      if(!tool||digest(tool.parameters)!==policy.artifact.schema_sha256){this.fail('tool_schema_changed');return [];}
      const ids=task.target_ids.slice(cursor,cursor+e.max_batch),batch=newId();
      const calls=ids.map((target:string)=>({callId:'sss-entry-'+newId(),proposal:{tool:e.tool,arguments:{[e.param]:target}}}));
      for(const [i,c] of calls.entries())pending.set(c.callId,{target:ids[i],batch,args:c.proposal.arguments});
      cursor+=ids.length;
      audit({kind:'entry_motif_bypass_attempt',batch_id:batch,call_ids:calls.map(c=>c.callId),
        target_ids:ids,policy_digest:policy.policy_digest,certified_digest:policy.artifact.certified_digest,
        counterfactual_requests_saved_inferred:false});
      return calls;
    },
    observe(exec:any,result:any){
      const expected=pending.get(exec.callId);if(!expected)return;
      pending.delete(exec.callId);const out=observation(result,exec.name);
      const ok=exec.name===e.tool&&digest(exec.arguments)===digest(expected.args)&&out
        &&out[e.result_identity_field]===expected.target&&out[e.result_input_field]===task.input_version
        &&out[e.result_source_field]===task.target_versions[expected.target]&&!used.has(expected.target);
      if(!ok){this.fail('failed_or_changed_entry_result');return;}
      used.add(expected.target);
      audit({kind:'entry_motif_read_verified',call_id:exec.callId,batch_id:expected.batch,
        target_id:expected.target,observation_sha256:digest(out)});
      if(!pending.size&&!halted){
        // A verified synthetic request is not itself a measured counterfactual saving.
        audit({kind:'entry_model_request_bypassed_verified',batch_id:expected.batch,successful_read_count:used.size});
        if(cursor===task.target_ids.length){done=true;audit({kind:'entry_motif_semantic_handoff',target_count:used.size});}
      }
    }
  };
}
