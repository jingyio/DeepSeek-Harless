/** Certified bounded copy programs on the current workspace MCP. No code eval. */
import {digest,observation} from '../motif_core/online_skill_runtime.mjs';
const prefix='mcp__file_management__';
const unsigned=(v:any,k:string)=>Object.fromEntries(Object.entries(v).filter(([n])=>n!==k));
const path=(v:any)=>typeof v==='string'&&v.length>0&&!v.startsWith('/')&&!v.includes('\\')&&!v.split('/').some((s:string)=>['','.','..'].includes(s));
const dir=(v:any)=>typeof v==='string'&&v.endsWith('/')&&path(v.slice(0,-1));
export function validateManagementProgram(p:any){
 const a=p?.artifact,r=a?.recipe;
 if(p?.format!=='sss-management-program-v1'||p.schema_version!==1||p.policy_digest!==digest(unsigned(p,'policy_digest'))
  ||a.certified_digest!==digest(unsigned(a,'certified_digest'))||a.kind!=='learned_management_copy_program'
  ||a.certification_contract!=='sss-management-program-certification-v1'||!Array.isArray(a.source_task_fingerprints)
  ||new Set(a.source_task_fingerprints).size<2||a.source_task_fingerprints.includes(a.validation_task_fingerprint)
  ||!r||digest(r.objective)!==r.guard?.objective_sha256||!Array.isArray(r.source_prefixes)||!r.source_prefixes.length||r.source_prefixes.some((v:any)=>!dir(v))
  ||r.guard.destination_prefixes.some((v:any)=>!dir(v))||!Array.isArray(r.context_paths)||r.context_paths.length>1||r.context_paths.some((v:any)=>!path(v))
  ||r.context_paths.length!==(r.guard.context_text_sha256===null?0:1)||!Array.isArray(r.steps)||!r.steps.length||r.steps.length>3)throw Error('invalid current management program');
 let copies=0,hashed=false;
 for(const s of r.steps){
  if(s.op==='hash_representatives'&&['min','max'].includes(s.order)&&Object.keys(s).length===2&&!hashed&&!copies){hashed=true;continue;}
  if(s.op!=='copy_map'||!['task_sources','nonempty_txt_sources','hash_representatives','prior_targets'].includes(s.source)
   ||!(s.strip_prefix===''||dir(s.strip_prefix))||s.destination_slot!==copies||Object.keys(s).length!==4
   ||s.destination_slot>=r.guard.destination_prefixes.length||s.source==='hash_representatives'&&!hashed||s.source==='prior_targets'&&copies!==1)throw Error('unsupported copy instruction');copies++;
 }
 if(copies<1||copies>2)throw Error('copy stage bound');return p;
}

export function copyProgramActions(r:any,inventory:any[],groups:any,prior:string[],stage:number){
 const s=r.steps.filter((s:any)=>s.op==='copy_map')[stage];let rows=inventory.filter(v=>v.root_id==='workspace'&&r.source_prefixes.some((p:string)=>v.path.startsWith(p))&&(!r.current_source_paths||r.current_source_paths.includes(v.path)));
 if(s.source==='prior_targets')rows=prior.map(n=>{const v=inventory.find(v=>v.path===n&&v.root_id==='workspace');if(!v)throw Error('actual backup identity missing');return v;});
 else if(s.source==='nonempty_txt_sources')rows=rows.filter(v=>!(v.path.toLowerCase().endsWith('.txt')&&v.bytes===0));
 else if(s.source==='hash_representatives'){
  if(!Array.isArray(groups))throw Error('actual hash groups required');const available=new Map(rows.map(v=>[v.file_id,v])),seen:string[]=[];
  rows=groups.map(g=>{if(!g.files.length)throw Error('empty hash group');const members=g.files.map((f:any)=>{const v:any=available.get(f.file_id);
   if(!v||f.path!=='workspace/'+v.path||v.sha256!==g.sha256)throw Error('hash identity or bytes changed');seen.push(v.file_id);return v;});
   members.sort((a:any,b:any)=>a.path<b.path?-1:a.path>b.path?1:0);return members[r.steps[0].order==='min'?0:members.length-1];});
  if(new Set(seen).size!==seen.length||seen.length!==available.size)throw Error('incomplete hash roster');
 }
 if(!rows.length||rows.length>32)throw Error('copy count outside original bounds');
 return rows.map(v=>{if(!v.path.startsWith(s.strip_prefix))throw Error('source prefix changed');const target=r.guard.destination_prefixes[s.destination_slot]+v.path.slice(s.strip_prefix.length);
  if(!path(target)||inventory.some(v=>v.root_id==='workspace'&&v.path===target))throw Error('destination conflict requires ordinary confirmation');return {op:'copy',file_ids:[v.file_id],destination:target};});
}

export function createManagementProgramRuntime(entries:any[],b:any,spec:any,audit:(r:any)=>void){
 let stage='idle',candidates:any[]=[],choice:any=null,pending:any=null,inventory:any[]=[],pin:any=null,groups:any=null,actions:any[]=[],plan:any=null,prior:string[]=[],copy=0,halted=false,done=false;
 let expected=structuredClone(spec.initial_tree??{});
 const emit=(v:any)=>audit({...v,entry_id:choice?.entry_id??null,source_kind:'management_program'});
 const fail=(reason:string)=>{if(halted||done||stage==='idle'&&!candidates.length)return;halted=true;pending=null;emit({kind:'experience_deferred',reason});};
 const scope=(out:any)=>out&&digest(out._sss_scope)===digest(b.scope);
 const recipe=(entry:any)=>{const r=entry.policy.artifact.recipe;return spec.approved_inputs?.length?{...r,current_source_paths:spec.approved_inputs.map((v:any)=>v.path)}:r;};
 const sameCatalog=(p:any)=>Object.entries(p.artifact.tool_contracts).every(([n,t])=>digest(b.catalog[n])===digest(t));
 const verifyInventory=(out:any)=>{
  const files=expected.workspace.files,all=Object.keys(files).filter(n=>!['.experiment-copy','.management-copy'].includes(n));
  if(!scope(out)||out.snapshot_sha256!==digest(expected)||!Array.isArray(out.files)||out.files.length!==all.length||new Set(out.files.map((r:any)=>r.file_id)).size!==all.length
   ||out.files.some((r:any)=>r.root_id!=='workspace'||files[r.path]!==r.sha256||r.file_id!=='file:local:'+digest({path:'workspace/'+r.path,sha:r.sha256}).slice(0,24)||!Number.isSafeInteger(r.bytes)||r.bytes<0))throw Error('actual inventory changed');
  inventory=out.files;
 };
 const select=()=>{
  const signatures=new Set(candidates.map(e=>digest(e.policy.artifact.recipe)));if(signatures.size!==1)throw Error('ambiguous certified programs');
  choice=candidates.sort((a,b)=>b.activated_generation-a.activated_generation)[0];
  emit({kind:'experience_selected',experience_kind:'management_program',activated_generation:choice.activated_generation});stage='step';
 };
 return {get active(){return stage!=='idle'&&!done&&!halted;},get halted(){return halted;},get done(){return done;},fail,
  observe(exec:any,result:any){
   if(halted||done)return false;const out=observation(result,exec.name);
   if(stage==='idle'){
    if(exec.name!==prefix+'read_task'||String(exec.callId).startsWith('sss-')||!scope(out)||digest(out.learning_scope)!==digest(b.scope)||b.scope.input_sha256!==digest(spec))return false;
    if(spec.rules?.read_only||Object.keys(spec.external_roots??{}).length||(out.recovery_state??[]).length)return false;
    candidates=entries.filter(e=>e.policy.execution_version_sha256===b.scope.execution_version&&sameCatalog(e.policy)&&e.policy.artifact.recipe.guard.objective_sha256===digest(out.objective));
    if(!candidates.length)return false;
    const contexts=new Set(candidates.map(e=>digest(e.policy.artifact.recipe.context_paths)));if(contexts.size!==1){fail('ambiguous rule scope');return false;}
    stage='inventory';return true;
   }
   let generated=!!pending;
   if(!pending&&!String(exec.callId).startsWith('sss-')){
    const r=choice?.policy.artifact.recipe??candidates[0].policy.artifact.recipe;
    let expectedName:any=null,expectedArgs:any=null;
    if(stage==='inventory'||stage==='refresh'){expectedName='list_files';expectedArgs={};}
    else if(stage==='pin_context'){expectedName='pin_file';expectedArgs={file_id:inventory.find(v=>v.path===r.context_paths[0])?.file_id};}
    else if(stage==='read_context'){expectedName='read_file';expectedArgs={source_id:pin.source_id};}
    if(expectedName&&exec.name===prefix+expectedName&&digest(exec.arguments)===digest(expectedArgs))pending={callId:exec.callId,tool:exec.name,args:exec.arguments};
   }
   if(!pending||pending.callId!==exec.callId||pending.tool!==exec.name||digest(pending.args)!==digest(exec.arguments)||!out){fail('unexpected_or_failed_program_call');return true;}
   const current=stage,probe=generated&&!choice&&['inventory','pin_context','read_context'].includes(stage);let probeEmitted=false;pending=null;
   const verifiedProbe=()=>{probeEmitted=true;emit({kind:'management_program_probe_verified',call_id:exec.callId,stage:current,tool:exec.name,
    arguments_sha256:digest(exec.arguments),result_sha256:digest(out),scope_sha256:digest(b.scope),model_request_bypassed:false});};
   try{
    if(current==='inventory'||current==='refresh'){
     verifyInventory(out);
     if(current==='inventory'){stage=candidates[0].policy.artifact.recipe.context_paths.length?'pin_context':'select';if(stage==='select')select();}
     else if(copy===choice.policy.artifact.recipe.steps.filter((s:any)=>s.op==='copy_map').length){done=true;stage='done';emit({kind:'management_program_complete',copy_stages:copy,actual_inventory_sha256:digest(out)});}
     else stage='step';
    }else if(current==='pin_context'){
     const n=candidates[0].policy.artifact.recipe.context_paths[0],r=inventory.find(r=>r.path===n);
     if(!r||!scope(out)||out.file_id!==r.file_id||out.source_version!==digest({path:'workspace/'+n,sha:r.sha256,parser:'fm-parser-v1'})||typeof out.source_id!=='string')throw Error('rule pin changed');
     pin={...out,path:'workspace/'+n,sha256:r.sha256};stage='read_context';
    }else if(current==='read_context'){
     if(!scope(out)||out.source_id!==pin.source_id||out.file_id!==pin.file_id||out.path!==pin.path||out.source_version!==pin.source_version||out.sha256!==pin.sha256||out.status!=='readable'||out.truncated)throw Error('rule read incomplete');
     if(probe)verifiedProbe();
     candidates=candidates.filter(e=>e.policy.artifact.recipe.guard.context_text_sha256===digest(out.text));if(!candidates.length)throw Error('rule changed; ordinary planning required');select();
    }else if(current==='hash'){groups=out.groups;copyProgramActions(recipe(choice),inventory,groups,prior,copy);stage='step';
    }else if(current==='preview'){
     if(!scope(out)||out.status!=='validated_management_plan'||out.risks?.length||typeof out.plan_id!=='string'||!Array.isArray(out.actions)||out.actions.length!==actions.length)throw Error('copy preview changed or requires confirmation');
     for(let i=0;i<actions.length;i++){const a=actions[i],v=out.actions[i],src=inventory.find(r=>r.file_id===a.file_ids[0]);
      if(v.op!=='copy'||v.source_root!=='workspace'||v.destination_root!=='workspace'||v.source!==src.path||v.source_sha256!==src.sha256||v.destination!==a.destination||digest(v.file_ids)!==digest(a.file_ids))throw Error('preview effects differ from learned program');}
     plan=out;stage='execute';
    }else if(current==='execute'){
     for(const a of actions){const src=inventory.find(r=>r.file_id===a.file_ids[0]);expected.workspace.files[a.destination]=src.sha256;
      const parts=a.destination.split('/');for(let i=1;i<parts.length;i++){const n=parts.slice(0,i).join('/');if(!expected.workspace.directories.includes(n))expected.workspace.directories.push(n);}}
     expected.workspace.directories.sort();
     if(!scope(out)||out._sss_authorized!==true||out.status!=='executed_verified'||out.plan_id!==plan.plan_id||out.operation_count!==actions.length||out.snapshot_sha256!==digest(expected))throw Error('actual execution receipt differs');
     prior=actions.map(a=>a.destination);copy++;stage='refresh';
    }
    if(probe){if(!probeEmitted)verifiedProbe();}
    else emit({kind:generated?'operation_model_request_bypassed_verified':'management_program_native_step_adopted',call_id:exec.callId,stage:current,model_request_bypassed:generated});
   }catch(e:any){fail(e.message);}return true;
  },
  propose(tools:any[],newId:()=>string){
   if(stage==='idle'||halted||done||pending)return [];
   try{
    let name:string,args:any;const r=recipe(choice??candidates[0]);
    if(stage==='step'){
     if(r.steps[0].op==='hash_representatives'&&copy===0&&groups===null){stage='hash';name='hash_files';args={file_ids:inventory.filter(v=>r.source_prefixes.some((p:string)=>v.path.startsWith(p))&&(!r.current_source_paths||r.current_source_paths.includes(v.path))).map(v=>v.file_id)};}
     else {actions=copyProgramActions(r,inventory,groups,prior,copy);stage='preview';name='preview_actions';args={actions};}
    }else if(stage==='inventory'||stage==='refresh'){name='list_files';args={};}
    else if(stage==='pin_context'){const v=inventory.find(v=>v.path===r.context_paths[0]);if(!v)throw Error('rule source missing');name='pin_file';args={file_id:v.file_id};}
    else if(stage==='read_context'){name='read_file';args={source_id:pin.source_id};}
    else if(stage==='execute'){name='execute_plan';args={plan_id:plan.plan_id};}
    else throw Error('unexpected program stage');
    const tc=tools.find((t:any)=>t.name===prefix+name),declared=(choice??candidates[0]).policy.artifact.tool_contracts[prefix+name];
    if(!tc||digest(tc.parameters)!==digest(declared.schema)||!sameCatalog((choice??candidates[0]).policy))throw Error('actual tool catalog changed');
    const callId='sss-program-'+newId();pending={callId,tool:prefix+name,args};emit({kind:'management_program_bypass_attempt',call_id:callId,stage});return [{callId,proposal:{tool:prefix+name,arguments:args}}];
   }catch(e:any){fail(e.message);return [];}
  }
 };
}
