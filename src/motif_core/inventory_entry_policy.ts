/** Source-array binding for a certified, bounded inventory preparation frontier. */
import {digest, observation} from './online_skill_runtime.mjs';
const hex=(v:any)=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const toolName=(v:any)=>typeof v==='string'&&/^mcp__[a-zA-Z0-9_]+$/.test(v);
const without=(v:any,k:string)=>Object.fromEntries(Object.entries(v).filter(([key])=>key!==k));
export function validateInventoryPolicy(p:any){
 const a=p?.artifact,e=a?.entry;
 const incremental=p?.format==='sss-entry-incremental-v1';
 if(p?.schema_version!==1||!['sss-entry-inventory-v1','sss-entry-incremental-v1'].includes(p.format)||!hex(p.policy_digest)
  ||p.policy_digest!==digest(without(p,'policy_digest'))||!hex(p.source_library_digest)||!hex(p.execution_version_sha256)
  ||a?.kind!==(incremental?'task_entry_incremental_frontier':'task_entry_inventory_frontier')||a.status!=='trace_validated_read_only'
  ||a.certified_digest!==digest(without(a,'certified_digest'))||!hex(a.schema_sha256)
  ||!Array.isArray(a.source_task_fingerprints)||a.source_task_fingerprints.length<2
  ||new Set(a.source_task_fingerprints).size!==a.source_task_fingerprints.length
  ||!a.validation_task_fingerprint||a.source_task_fingerprints.includes(a.validation_task_fingerprint)
  ||e?.kind!==(incremental?'update_plan_then_foreach':'inventory_then_foreach')||e.selection!==(incremental?'all_invalidated_work':'all_selected_inventory')||e.max_targets!==20||e.max_batch!==8
  ||e.stop!=='semantic_handoff_after_reads'||!toolName(e.source_tool)||!toolName(e.tool)||e.source_tool===e.tool
  ||digest(a.tools)!==digest([e.source_tool,e.tool])||e.param!=='paper_id'||e.array_field!==(incremental?'work':'papers')||e.identity_field!=='paper_id'
  ||(incremental&&e.plan_field!=='plan_sha256')
  ||e.input_field!=='task_sha256'||e.source_field!=='pdf_sha256'||e.result_version_field!=='document_version_sha256'
  ||e.parser_field!=='parser_profile_sha256'||digest(a.projection_excluded_fields)!==digest(['cache_stats'])
  ||!a.tool_schema_sha256||Object.keys(a.tool_schema_sha256).length!==2
  ||a.tools.some((t:string)=>!hex(a.tool_schema_sha256[t])))throw new TypeError('invalid or changed certified inventory policy');
 return p;
}
export function validateInventoryTask(t:any,p:any){
 const ps=t?.inventory_papers,ids=Array.isArray(ps)?ps.map((r:any)=>r?.paper_id):[];
 if(t?.schema_version!==1||typeof t.session_id!=='string'||!t.session_id||typeof t.task_id!=='string'||!t.task_id
  ||!hex(t.input_version)||t.execution_version_sha256!==p.execution_version_sha256||!hex(t.parser_profile_sha256)
  ||typeof t.question!=='string'||!t.question.trim()||t.question.length>4000||!Array.isArray(ps)||ps.length>20||ps.length<1
  ||ps.some((r:any)=>!r||typeof r.paper_id!=='string'||!r.paper_id||r.paper_id.length>160||!hex(r.pdf_sha256)
    ||typeof r.filename!=='string'||!Number.isSafeInteger(r.bytes)||r.bytes<=0)
  ||new Set(ids).size!==ids.length||digest(t.target_ids)!==digest(ids)||t.target_ids_sha256!==digest(ids)
  ||t.inventory_sha256!==digest(ps)||!t.target_versions||Array.isArray(t.target_versions)
  ||Object.keys(t.target_versions).length!==ids.length||ids.some((i:string)=>!hex(t.target_versions[i]))
  ||(p.format==='sss-entry-incremental-v1'&&(!hex(t.source_result_sha256)||!hex(t.plan_sha256))))
   throw new TypeError('invalid or stale frozen inventory task');
 return t;
}
export function createInventoryController(policy:any,task:any,audit:(r:any)=>void){
 validateInventoryPolicy(policy);validateInventoryTask(task,policy);
 const e=policy.artifact.entry,pending=new Map<string,any>(),used=new Set<string>();
 const incremental=policy.format==='sss-entry-incremental-v1';
 let phase='source',rows:any[]=[],cursor=0,halted=false,done=false;
 return {
  get halted(){return halted;},get done(){return done;},get pending(){return pending.size;},
  fail(reason:string){halted=true;audit({kind:'entry_motif_deferred',reason});},
  propose(tools:any[],newId:()=>string){
   if(halted||done||pending.size)return [];
   // Validate both schemas before executing the zero-argument source tool.
   for(const name of policy.artifact.tools){const t=tools.find((x:any)=>x.name===name);
    if(!t||digest(t.parameters)!==policy.artifact.tool_schema_sha256[name]){this.fail('tool_schema_changed');return [];}}
   const batch=newId(),selected=phase==='source'?[null]:rows.slice(cursor,cursor+e.max_batch);
   const calls=selected.map((r:any)=>({callId:'sss-entry-'+newId(),proposal:{tool:phase==='source'?e.source_tool:e.tool,
    arguments:phase==='source'?{}:{[e.param]:r[e.identity_field]}}}));
   for(const [i,c] of calls.entries())pending.set(c.callId,{phase,batch,args:c.proposal.arguments,row:selected[i]});
   if(phase==='prepare')cursor+=selected.length;
   audit({kind:'entry_motif_bypass_attempt',phase,batch_id:batch,call_ids:calls.map(c=>c.callId),
    target_ids:selected.filter(Boolean).map(r=>r[e.identity_field]),policy_digest:policy.policy_digest,
    certified_digest:policy.artifact.certified_digest,counterfactual_requests_saved_inferred:false});
   return calls;
  },
  observe(exec:any,result:any){
   const expected=pending.get(exec.callId);if(!expected)return;pending.delete(exec.callId);
   const out=observation(result,exec.name);
   if(!out||digest(exec.arguments)!==digest(expected.args)||exec.name!==(expected.phase==='source'?e.source_tool:e.tool)){
    this.fail('failed_or_changed_entry_result');return;}
   if(expected.phase==='source'){
    if(!Array.isArray(out[e.array_field])||out[e.input_field]!==task.input_version||out.question!==task.question
      ||(!incremental&&(digest(out[e.array_field])!==task.inventory_sha256||digest(out[e.array_field])!==digest(task.inventory_papers)))
      ||(incremental&&(digest(out)!==task.source_result_sha256||out[e.plan_field]!==task.plan_sha256
        ||digest(out[e.array_field].map((r:any)=>r?.[e.identity_field]))!==task.target_ids_sha256))){
      this.fail('inventory_or_question_changed');return;}
    // Actual tool-issued objects supply parameters; frozen task serves only as guard.
    rows=out[e.array_field];phase='prepare';
    audit({kind:'entry_motif_inventory_verified',call_id:exec.callId,batch_id:expected.batch,observation_sha256:digest(out),target_count:rows.length});
   }else{
    const pid=expected.row[e.identity_field];
    const source=incremental?task.inventory_papers.find((r:any)=>r.paper_id===pid):expected.row;
    if(out[e.identity_field]!==pid||out[e.source_field]!==source[e.source_field]
      ||out[e.result_version_field]!==task.target_versions[pid]||out[e.parser_field]!==task.parser_profile_sha256||used.has(pid)){
      this.fail('pdf_or_parser_version_changed');return;}
    used.add(pid);audit({kind:'entry_motif_read_verified',call_id:exec.callId,batch_id:expected.batch,
      target_id:pid,observation_sha256:digest(out),navigation_sha256:digest(without(out,'cache_stats'))});
   }
   if(!pending.size&&!halted){
    audit({kind:'entry_model_request_bypassed_verified',phase:expected.phase,batch_id:expected.batch,successful_read_count:used.size});
    if(phase==='prepare'&&cursor===rows.length){done=true;audit({kind:'entry_motif_semantic_handoff',target_count:used.size});}
   }
  }
 };
}
