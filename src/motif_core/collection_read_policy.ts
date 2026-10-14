/** Certified post-selection foreach(pin, read), then complete gather. */
import {digest,observation} from './online_skill_runtime.mjs';
const hex=(v:any)=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const without=(v:any,k:string)=>Object.fromEntries(Object.entries(v).filter(([key])=>key!==k));
const id=(v:any)=>typeof v==='string'&&v.length>0&&v.length<=160&&!/[\x00-\x1f]/.test(v);
export function validateCollectionPolicy(p:any){
 const a=p?.artifact,g=a?.graph;
 if(p?.schema_version!==1||p.format!=='sss-collection-read-v1'||!hex(p.policy_digest)
  ||p.policy_digest!==digest(without(p,'policy_digest'))||!hex(p.source_library_digest)||!hex(p.execution_version_sha256)
  ||a?.kind!=='selected_collection_read_graph'||a.status!=='trace_validated_read_only'
  ||a.certified_digest!==digest(without(a,'certified_digest'))||!Array.isArray(a.source_task_fingerprints)
  ||a.source_task_fingerprints.length<2||new Set(a.source_task_fingerprints).size!==a.source_task_fingerprints.length
  ||!id(a.validation_task_fingerprint)||a.source_task_fingerprints.includes(a.validation_task_fingerprint)
  ||g?.selection!=='actual_model_selected_members'||g.max_targets!==32||g.max_batch!==8
  ||g.stop!=='semantic_handoff_after_complete_gather'||g.array_field!=='files'||g.identity_field!=='file_id'
  ||g.pin_param!=='file_id'||g.read_param!=='source_id'||g.gather_param!=='source_ids'
  ||!Array.isArray(a.tools)||a.tools.length!==4||new Set(a.tools).size!==4
  ||a.tools.some((t:any)=>typeof t!=='string'||!/^mcp__[a-zA-Z0-9_]+$/.test(t))
  ||digest(a.tools)!==digest([g.source_tool,g.pin_tool,g.read_tool,g.gather_tool])
  ||!a.tool_schema_sha256||Object.keys(a.tool_schema_sha256).length!==4
  ||a.tools.some((t:string)=>!hex(a.tool_schema_sha256[t])))throw new TypeError('invalid certified collection policy');
 const edges=[{from_tool:g.source_tool,from_field:'files[].file_id',to_tool:g.pin_tool,to_param:'file_id',mapping:'foreach_all_selected'},
  {from_tool:g.pin_tool,from_field:'source_id',to_tool:g.read_tool,to_param:'source_id',mapping:'same_iteration'},
  {from_tool:g.read_tool,from_field:'source_id',to_tool:g.gather_tool,to_param:'source_ids',mapping:'gather_complete'},
  {from_tool:g.source_tool,from_field:'collection_id',to_tool:g.gather_tool,to_param:'collection_id',mapping:'same_collection'}];
 if(digest(a.transfer_evidence)!==digest(edges))throw new TypeError('changed collection parameter graph');
 return p;
}
export function validateCollectionTask(t:any,p:any){
 const rows=t?.inventory;
 if(t?.schema_version!==1||!id(t.session_id)||!id(t.task_id)||!hex(t.input_version)||!hex(t.snapshot_sha256)
  ||t.execution_version_sha256!==p.execution_version_sha256||!Array.isArray(rows)||rows.length>32
  ||rows.some((r:any)=>!id(r?.file_id)||!id(r.path)||!hex(r.sha256)||!hex(r.source_version)||!Number.isSafeInteger(r.bytes)||r.bytes<0)
  ||new Set(rows.map((r:any)=>r.file_id)).size!==rows.length||t.inventory_sha256!==digest(rows))
  throw new TypeError('invalid current collection task scope');
 return t;
}
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
    if(selected){fail('unexpected_tool_during_collection');return;}
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
    chunk=selected.files.slice(cursor,cursor+g.max_batch);rows=chunk;tool=g.pin_tool;args=rows.map(r=>({file_id:r.file_id}));
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
