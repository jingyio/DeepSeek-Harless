/** Versioned prefetch-aware executor; legacy certificates keep their original validator. */
import {digest,observation} from './online_skill_runtime.mjs';
import {validateCollectionPolicy,validateCollectionTask} from './collection_read_policy.ts';
const id=(v:any)=>typeof v==='string'&&v.length>0&&v.length<=160&&!/[\x00-\x1f]/.test(v);
const without=(v:any,k:string)=>Object.fromEntries(Object.entries(v).filter(([key])=>key!==k));
export function createCollectionController(policy:any,task:any,audit:(r:any)=>void){
 validateCollectionPolicy(policy);return createGuardedCollectionExecutor(policy,task,audit);
}
/** Shared byte/version verification and batching, also used by the explicit handwritten baseline. */
export function createGuardedCollectionExecutor(policy:any,task:any,audit:(r:any)=>void){
 validateCollectionTask(task,policy);
 const g=policy.artifact.graph,pending=new Map<string,any>(),pins=new Map<string,any>(),reads=new Map<string,any>();
 let selected:any=null,cursor=0,stage='waiting',chunk:any[]=[],halted=false,done=false;
 const scope=new Map(task.inventory.map((r:any)=>[r.file_id,r]));
 const fail=(reason:string)=>{halted=true;audit({kind:'collection_motif_deferred',reason});};
 return {get halted(){return halted;},get done(){return done;},get pending(){return pending.size;},
  get armed(){return selected!==null;},fail,
  observe(exec:any,result:any){
   if(halted||done)return;
   const expected=pending.get(exec.callId);const out=observation(result,exec.name);
   if(!expected){
    if(selected){
     // A real model can emit selection + pins in one decision. Adopt only
     // already successful exact pins; never relabel them as skipped requests.
     if(stage==='pin'&&!pending.size&&cursor===0&&exec.name===g.pin_tool&&!String(exec.callId).startsWith('sss-')){
      const row=selected.files.find((r:any)=>r.file_id===exec.arguments?.file_id);
      if(!row||digest(Object.keys(exec.arguments))!==digest(['file_id'])||!out||out.file_id!==row.file_id
       ||out.source_version!==row.source_version||!id(out.source_id)||pins.has(row.file_id)
       ||[...pins.values()].some((p:any)=>p.source_id===out.source_id)){fail('invalid_native_prefetch_pin');return;}
      pins.set(row.file_id,out);audit({kind:'collection_native_pin_adopted',call_id:exec.callId,file_id:row.file_id,
       observation_sha256:digest(out),model_request_bypassed:false});return;
     }
     fail('unexpected_tool_during_collection');return;
    }
    if(exec.name!==g.source_tool)return;
    const args=exec.arguments;
    if(String(exec.callId).startsWith('sss-')||!out||!args||digest(Object.keys(args))!==digest(['file_ids'])
     ||!Array.isArray(args.file_ids)||args.file_ids.length>g.max_targets||new Set(args.file_ids).size!==args.file_ids.length
     ||out.selection!==g.selection||out.input_sha256!==task.input_version||out.snapshot_sha256!==task.snapshot_sha256
     ||out.execution_version_sha256!==task.execution_version_sha256||!id(out.collection_id)
     ||out.collection_sha256!==digest(without(out,'collection_sha256'))||!Array.isArray(out.files)
     ||out.count!==out.files.length||digest(out.files.map((r:any)=>r?.file_id))!==digest(args.file_ids)
     ||out.files.some((r:any)=>!scope.has(r.file_id)||digest(r)!==digest(scope.get(r.file_id)))){
       fail('invalid_or_changed_model_selection');return;}
    selected=out;stage=out.files.length?'pin':'gather';
    audit({kind:'collection_motif_selection_verified',call_id:exec.callId,count:out.count,
      collection_id:out.collection_id,selection_sha256:digest(out)});return;
   }
   pending.delete(exec.callId);
   if(!out||exec.name!==expected.tool||digest(exec.arguments)!==digest(expected.args)){
     fail('failed_or_changed_collection_result');return;}
   if(expected.stage==='pin'){
    const row=expected.row;
    if(out.file_id!==row.file_id||out.source_version!==row.source_version||!id(out.source_id)
      ||[...pins.values()].some((p:any)=>p.source_id===out.source_id)){fail('changed_or_duplicate_pin');return;}
    pins.set(row.file_id,out);
   }else if(expected.stage==='read'){
    const row=expected.row,pin=pins.get(row.file_id);
    if(out.file_id!==row.file_id||out.source_id!==pin.source_id||out.source_version!==row.source_version
      ||out.path!==row.path||out.sha256!==row.sha256||!['readable','unreadable','metadata_only','unsupported'].includes(out.status)){
       fail('changed_read_or_unknown_status');return;}
    reads.set(row.file_id,out);
    audit({kind:'collection_motif_read_verified',call_id:exec.callId,file_id:row.file_id,
      source_id:out.source_id,source_version:out.source_version,observation_sha256:digest(out),batch_id:expected.batch});
   }else{
    const rows=selected.files.map((r:any)=>{const read=reads.get(r.file_id);return {file_id:r.file_id,path:r.path,
      source_id:read.source_id,source_version:r.source_version,status:read.status,read_sha256:digest(read)};});
    if(out.status!=='collection_complete'||out.collection_id!==selected.collection_id
     ||out.collection_sha256!==selected.collection_sha256||out.input_sha256!==task.input_version
     ||out.execution_version_sha256!==task.execution_version_sha256||out.snapshot_sha256!==task.snapshot_sha256
     ||out.count!==rows.length||digest(out.files)!==digest(rows)||out.coverage_sha256!==digest(rows)
     ||out.semantic_judgment_certified!==false){fail('incomplete_or_changed_gather');return;}
    done=true;audit({kind:'collection_motif_complete',collection_id:selected.collection_id,count:rows.length,
      coverage_sha256:out.coverage_sha256,observation_sha256:digest(out)});
   }
   if(!pending.size&&!halted){
    audit({kind:'collection_model_request_bypassed_verified',stage:expected.stage,batch_id:expected.batch,count:expected.batchSize});
    if(expected.stage==='pin')stage='read';
    if(expected.stage==='read'){cursor+=chunk.length;stage=cursor===selected.files.length?'gather':'pin';}
   }
  },
  propose(tools:any[],newId:()=>string){
   if(!selected||halted||done||pending.size)return [];
   for(const name of policy.artifact.tools){const tool=tools.find((t:any)=>t.name===name);
    if(!tool||digest(tool.parameters)!==policy.artifact.tool_schema_sha256[name]){fail('collection_tool_schema_changed');return [];}}
   const batch=newId();let tool:string,args:any[],rows:any[];
   if(stage==='pin'){
    chunk=selected.files.slice(cursor,cursor+g.max_batch);rows=chunk.filter((r:any)=>!pins.has(r.file_id));
    if(!rows.length){stage='read';rows=chunk;tool=g.read_tool;args=rows.map(r=>({source_id:pins.get(r.file_id).source_id}));}
    else {tool=g.pin_tool;args=rows.map(r=>({file_id:r.file_id}));}
   }else if(stage==='read'){
    rows=chunk;tool=g.read_tool;args=rows.map(r=>({source_id:pins.get(r.file_id).source_id}));
   }else{
    rows=[null];tool=g.gather_tool;args=[{collection_id:selected.collection_id,source_ids:selected.files.map((r:any)=>reads.get(r.file_id).source_id)}];
   }
   const calls=args.map(arguments_=>({callId:'sss-collection-'+newId(),proposal:{tool,arguments:arguments_}}));
   calls.forEach((c,i)=>pending.set(c.callId,{tool,args:args[i],row:rows[i],stage,batch,batchSize:calls.length}));
   audit({kind:'collection_motif_bypass_attempt',stage,batch_id:batch,call_ids:calls.map(c=>c.callId),
     policy_digest:policy.policy_digest,certified_digest:policy.artifact.certified_digest,collection_id:selected.collection_id});
   return calls;
  }
 };
}
