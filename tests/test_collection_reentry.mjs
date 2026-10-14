import test from 'node:test';import assert from 'node:assert/strict';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';
import {validateReentryPolicy,createReentryController} from '../src/motif_core/collection_reentry_policy.ts';
const names=['select','pin','read','gather'].map(n=>'mcp__test__'+n),obs=v=>({value:{structuredContent:v}});
function fixture(){
 const [s,p,r,g]=names,tools=names.map(name=>({name,parameters:{}}));const graph={source_tool:s,pin_tool:p,read_tool:r,gather_tool:g,selection:'actual_model_selected_members',array_field:'files',identity_field:'file_id',pin_param:'file_id',read_param:'source_id',gather_param:'source_ids',max_targets:32,max_batch:8,stop:'semantic_handoff_after_complete_gather'};
 const edges=[{from_tool:s,from_field:'files[].file_id',to_tool:p,to_param:'file_id',mapping:'foreach_all_selected'},{from_tool:p,from_field:'source_id',to_tool:r,to_param:'source_id',mapping:'same_iteration'},{from_tool:r,from_field:'source_id',to_tool:g,to_param:'source_ids',mapping:'gather_complete'},{from_tool:s,from_field:'collection_id',to_tool:g,to_param:'collection_id',mapping:'same_collection'}];
 const witness=n=>({task_fingerprint:n,references:[{call_id:'model-'+n,message_seq:20}],trace_id:n});
 const child=(tag,ws)=>{const a={kind:'selected_collection_read_graph',status:'trace_validated_read_only',tools:names,graph,transfer_evidence:edges,tool_schema_sha256:Object.fromEntries(names.map(n=>[n,digest({})])),source_task_fingerprints:[tag+'a',tag+'b'],validation_task_fingerprint:tag+'c',training_witnesses:ws.slice(0,2),validation_witness:ws[2]};a.certified_digest=digest(a);const p={schema_version:1,format:'sss-collection-read-v1',source_library_digest:'a'.repeat(64),execution_version_sha256:'b'.repeat(64),artifact:a};p.policy_digest=digest(p);return p;};
 const ws=['newa','newb','newc'].map(witness),parent=child('old',[]),next=child('new',ws);
 const ep=w=>({parent_policy_digest:parent.policy_digest,parent_boundary:{call_id:'sss-inherited-'+w.trace_id,result_seq:10,selection_call_id:'model-old-'+w.trace_id},residual_witness:w,runtime_nodes_used_for_new_parameter_discovery:false});
 const artifact={kind:'certified_collection_reentry',status:'trace_validated_read_only',training_episodes:ws.slice(0,2).map(ep),validation_episode:ep(ws[2]),source_task_fingerprints:['newa','newb'],validation_task_fingerprint:'newc',max_episodes:2,trigger:'fresh_model_selection_after_verified_gather',auto_select:false,parent_boundary_is_execution_evidence_only:true,runtime_nodes_used_for_new_parameter_discovery:false};artifact.certified_digest=digest(artifact);
 const policy={schema_version:1,format:'sss-collection-reentry-v1',parent_policy:parent,next_policy:next,artifact,execution_version_sha256:'b'.repeat(64)};policy.policy_digest=digest(policy);
 const inventory=[0,1].map(i=>({file_id:'f'+i,path:i+'.txt',bytes:10,sha256:digest(i),source_version:digest(['v',i])}));
 const task={schema_version:1,task_id:'t',session_id:'s',input_version:'c'.repeat(64),snapshot_sha256:'d'.repeat(64),execution_version_sha256:policy.execution_version_sha256,inventory,inventory_sha256:digest(inventory)};return {policy,task,tools};
}
function episode(c,f,k,log){
 const row=f.task.inventory[k];const packet={collection_id:'collection-'+k,input_sha256:f.task.input_version,snapshot_sha256:f.task.snapshot_sha256,execution_version_sha256:f.task.execution_version_sha256,files:[row],count:1,selection:'actual_model_selected_members'};packet.collection_sha256=digest(packet);
 c.observe({callId:'model-'+k,name:names[0],arguments:{file_ids:[row.file_id]}},obs(packet));let i=0,read;
 for(let step=0;step<3;step++){
  const call=c.propose(f.tools,()=> k+'-'+(++i))[0];assert.ok(call);let out;
  if(call.proposal.tool===names[1])out={file_id:row.file_id,source_version:row.source_version,source_id:'source-'+k};
  else if(call.proposal.tool===names[2])out=read={...row,source_id:'source-'+k,status:'readable',text:'actual'};
  else{const rows=[{file_id:row.file_id,path:row.path,source_id:read.source_id,source_version:row.source_version,status:read.status,read_sha256:digest(read)}];out={status:'collection_complete',collection_id:packet.collection_id,collection_sha256:packet.collection_sha256,input_sha256:f.task.input_version,execution_version_sha256:f.task.execution_version_sha256,snapshot_sha256:f.task.snapshot_sha256,files:rows,count:1,coverage_sha256:digest(rows),semantic_judgment_certified:false};}
  c.observe({callId:call.callId,name:call.proposal.tool,arguments:call.proposal.arguments},obs(out));
 }
}
test('L2 waits for a fresh model choice, reenters once, and records second epoch separately',()=>{const f=fixture(),log=[],c=createReentryController(f.policy,f.task,r=>log.push(r));assert.deepEqual(c.propose(f.tools,()=>''),[]);episode(c,f,0,log);assert.equal(c.done,false);assert.deepEqual(c.propose(f.tools,()=>''),[]);c.observe({name:'mcp__test__semantic',callId:'model-decision'},obs({}));episode(c,f,1,log);assert.equal(c.done,true);assert.equal(log.filter(r=>r.kind==='reentry_epoch_batch_verified').length,3);assert.equal(log.filter(r=>r.kind==='collection_model_request_bypassed_verified').length,6);});
test('a failed L1 does not enable second-epoch execution',()=>{const f=fixture(),c=createReentryController(f.policy,f.task,()=>{});c.fail('parent failed');assert.equal(c.halted,true);assert.deepEqual(c.propose(f.tools,()=>''),[]);});
for(const field of ['parent','evidence','scope'])test('L2 rejects changed '+field,()=>{const f=fixture();if(field==='parent')f.policy.parent_policy.policy_digest='wrong';else if(field==='evidence')f.policy.artifact.training_episodes[0].residual_witness.references[0].call_id='sss-forged';else f.policy.artifact.max_episodes=8;assert.throws(()=>validateReentryPolicy(f.policy));});
