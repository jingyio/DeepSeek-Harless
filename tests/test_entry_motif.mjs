import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {markAgentLoopRequest} from '@deepseek-ai/dsh-llm';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';
import {createEntryController,validateEntryPolicy,validateEntryTask} from '../src/motif_core/entry_read_policy.ts';
import {createEntryGate} from '../src/adapters/dsh_entry_motif.ts';
const tool='mcp__test__read_packet',schema={type:'object',required:['id'],properties:{id:{type:'string'}}};
function fixture(n=2){
 const artifact={kind:'task_entry_read_frontier',status:'trace_validated_read_only',schema_sha256:digest(schema),
  source_task_fingerprints:['a','b'],validation_task_fingerprint:'heldout',entry:{kind:'foreach_frozen_targets',selection:'all_targets',
  tool,param:'id',max_targets:100,max_batch:8,result_identity_field:'id',result_input_field:'input_sha256',result_source_field:'document_version_sha256',stop:'semantic_handoff_after_reads'}};
 artifact.certified_digest=digest(artifact);
 const policy={schema_version:1,format:'sss-entry-read-v1',source_library_digest:'a'.repeat(64),execution_version_sha256:'b'.repeat(64),artifact};policy.policy_digest=digest(policy);
 const ids=Array.from({length:n},(_,i)=>'target'+i);
 const task={schema_version:1,session_id:'s',task_id:'t',input_version:'c'.repeat(64),execution_version_sha256:'b'.repeat(64),
  target_ids:ids,target_ids_sha256:digest(ids),target_versions:Object.fromEntries(ids.map(i=>[i,'d'.repeat(64)])),
  prompt_sha256:createHash('sha256').update('Review selected claims').digest('hex')};
 return {policy,task};
}
function result(target,task){return {value:{structuredContent:{id:target,input_sha256:task.input_version,document_version_sha256:task.target_versions[target]}}};}
test('entry spans changing counts in batches of at most eight, verified only after actual results',()=>{
 const {policy,task}=fixture(9),log=[];const c=createEntryController(policy,task,r=>log.push(r));let counter=0;
 const calls=c.propose([{name:tool,parameters:schema}],()=>String(++counter));assert.equal(calls.length,8);
 assert.equal(log.filter(r=>r.kind==='entry_model_request_bypassed_verified').length,0);
 for(const row of calls)c.observe({callId:row.callId,name:tool,arguments:row.proposal.arguments},result(row.proposal.arguments.id,task));
 const final=c.propose([{name:tool,parameters:schema}],()=>String(++counter));assert.equal(final.length,1);
 c.observe({callId:final[0].callId,name:tool,arguments:final[0].proposal.arguments},result('target8',task));
 assert.equal(c.done,true);assert.equal(log.filter(r=>r.kind==='entry_model_request_bypassed_verified').length,2);
 assert.deepEqual(c.propose([{name:tool,parameters:schema}],()=>''),[]);
});
test('failed or stale read never records a verified bypass, even if another read succeeds',()=>{
 const {policy,task}=fixture(),log=[];const c=createEntryController(policy,task,r=>log.push(r));let i=0;
 const calls=c.propose([{name:tool,parameters:schema}],()=>String(++i));
 c.observe({callId:calls[0].callId,name:tool,arguments:calls[0].proposal.arguments},{isError:true});
 c.observe({callId:calls[1].callId,name:tool,arguments:calls[1].proposal.arguments},result('target1',task));
 assert.equal(c.halted,true);assert.equal(c.done,false);assert.equal(log.filter(r=>r.kind==='entry_model_request_bypassed_verified').length,0);
});
test('changed library, task, versions or tool schema fail closed; empty target list does no work',()=>{
 const {policy,task}=fixture();const broken=structuredClone(policy);broken.artifact.entry.selection='subset';assert.throws(()=>validateEntryPolicy(broken));
 const changed=structuredClone(task);changed.target_ids.push('outside');assert.throws(()=>validateEntryTask(changed,policy));
 const version=structuredClone(task);version.execution_version_sha256='e'.repeat(64);assert.throws(()=>validateEntryTask(version,policy));
 const c=createEntryController(policy,task,()=>{});assert.deepEqual(c.propose([{name:tool,parameters:{}}],()=>''),[]);assert.equal(c.halted,true);
 const empty=fixture(0);assert.equal(createEntryController(empty.policy,empty.task,()=>{}).done,true);
});
test('only matching original agent prompt at task entry bypasses the provider',async()=>{
 const {policy,task}=fixture(1),log=[];const gate=createEntryGate(policy,task,r=>log.push(r));let calls=0;
 const next=()=>{calls++;return(async function*(){})();};
 const raw={sessionId:'s',messages:[{role:'user',source:{kind:'user'},content:[{type:'text',text:'Review selected claims'}]}],tools:[{name:tool,parameters:schema}]};
 for await(const _ of gate.intercept(raw,next,true)){}assert.equal(calls,1);
 const req=markAgentLoopRequest(Object.freeze(raw)),chunks=[];
 for await(const c of gate.intercept(req,next,true))chunks.push(c);
 assert.equal(calls,1);assert.equal(chunks.at(-1).reason.kind,'tool-calls');
 const block=chunks.find(c=>c.type==='tool-call-delta');assert.ok(block.id.startsWith('sss-entry-'));
 gate.observe({callId:block.id,name:tool,arguments:JSON.parse(block.argumentsDelta)},result('target0',task));
 for await(const _ of gate.intercept(req,next,true)){}assert.equal(calls,2);
 const altered=fixture(1),g=createEntryGate(altered.policy,altered.task,()=>{});
 for await(const _ of g.intercept(markAgentLoopRequest(Object.freeze({...raw,messages:[{role:'user',source:{kind:'user'},content:[{type:'text',text:'Another question'}]}]})),next,true)){}
 assert.equal(g.controller.halted,true);
});

const source='mcp__test__list',prepare='mcp__test__prepare';
const listSchema={type:'object',properties:{}},prepareSchema={type:'object',properties:{paper_id:{type:'string'}},required:['paper_id']};
function inventoryFixture(n=2){
 const {task}=fixture(n);const rows=task.target_ids.map((id,i)=>({paper_id:id,pdf_sha256:'e'.repeat(64),filename:i+'.pdf',bytes:20}));
 Object.assign(task,{inventory_papers:rows,inventory_sha256:digest(rows),question:'Review selected claims',parser_profile_sha256:'f'.repeat(64)});
 const artifact={kind:'task_entry_inventory_frontier',status:'trace_validated_read_only',schema_sha256:'a'.repeat(64),
  source_task_fingerprints:['one','two'],validation_task_fingerprint:'new',tools:[source,prepare],
  tool_schema_sha256:{[source]:digest(listSchema),[prepare]:digest(prepareSchema)},projection_excluded_fields:['cache_stats'],
  entry:{kind:'inventory_then_foreach',selection:'all_selected_inventory',source_tool:source,tool:prepare,param:'paper_id',array_field:'papers',
   identity_field:'paper_id',input_field:'task_sha256',source_field:'pdf_sha256',result_version_field:'document_version_sha256',
   parser_field:'parser_profile_sha256',max_targets:20,max_batch:8,stop:'semantic_handoff_after_reads'}};
 artifact.certified_digest=digest(artifact);
 const policy={schema_version:1,format:'sss-entry-inventory-v1',source_library_digest:'a'.repeat(64),execution_version_sha256:task.execution_version_sha256,artifact};policy.policy_digest=digest(policy);
 return {task,policy};
}
const inventoryTools=[{name:source,parameters:listSchema},{name:prepare,parameters:prepareSchema}];
function observed(out){return {value:{structuredContent:out}};}
function listResult(t){return {task_sha256:t.input_version,question:t.question,papers:t.inventory_papers};}
function navResult(t,id){return {paper_id:id,pdf_sha256:t.inventory_papers.find(r=>r.paper_id===id).pdf_sha256,
 document_version_sha256:t.target_versions[id],parser_profile_sha256:t.parser_profile_sha256,pages:[{status:'low_text_needs_review'}]};}
function feed(c,call,out){c.observe({callId:call.callId,name:call.proposal.tool,arguments:call.proposal.arguments},observed(out));}
test('inventory binds actual source objects, then batches all PDFs, leaving OCR and semantics to provider',()=>{
 const {policy,task}=inventoryFixture(9),log=[],c=createEntryController(policy,task,r=>log.push(r));let i=0;
 const one=c.propose(inventoryTools,()=>String(++i));assert.equal(one.length,1);assert.equal(one[0].proposal.tool,source);
 assert.deepEqual(c.propose(inventoryTools,()=>''),[]);feed(c,one[0],listResult(task));
 const batch=c.propose(inventoryTools,()=>String(++i));assert.equal(batch.length,8);
 for(const call of batch)feed(c,call,navResult(task,call.proposal.arguments.paper_id));
 const last=c.propose(inventoryTools,()=>String(++i));feed(c,last[0],navResult(task,'target8'));
 assert.equal(c.done,true);assert.equal(log.filter(r=>r.kind==='entry_model_request_bypassed_verified').length,3);
 assert.equal(log.filter(r=>r.kind==='entry_motif_read_verified').length,9);
});
for(const reason of ['selection','question','input','pdf','parser','failure','schema'])test('inventory fallback on '+reason,()=>{
 const {policy,task}=inventoryFixture(),log=[],c=createEntryController(policy,task,r=>log.push(r));let i=0;
 const tools=reason==='schema'?[{name:source,parameters:{}},{name:prepare,parameters:prepareSchema}]:inventoryTools;
 const list=c.propose(tools,()=>String(++i));
 if(reason==='schema'){assert.equal(c.halted,true);return;}
 const out=listResult(task);if(reason==='selection')out.papers=out.papers.slice(0,1);
 if(reason==='question')out.question='altered';if(reason==='input')out.task_sha256='x';feed(c,list[0],out);
 if(!c.halted){const batch=c.propose(tools,()=>String(++i));const nav=navResult(task,'target0');
  if(reason==='pdf')nav.pdf_sha256='a'.repeat(64);if(reason==='parser')nav.parser_profile_sha256='a'.repeat(64);
  if(reason==='failure')c.observe({callId:batch[0].callId,name:prepare,arguments:batch[0].proposal.arguments},{isError:true});else feed(c,batch[0],nav);
  feed(c,batch[1],navResult(task,'target1'));
 }
 assert.equal(c.halted,true);assert.equal(c.done,false);assert.equal(log.filter(r=>r.kind==='entry_motif_read_verified').length,reason==='pdf'||reason==='parser'||reason==='failure'?1:0);
 assert.equal(log.filter(r=>r.kind==='entry_model_request_bypassed_verified'&&r.phase==='prepare').length,0);
});

function incrementalFixture(n=2){
 const {task,policy}=inventoryFixture(n),a=policy.artifact;
 policy.format='sss-entry-incremental-v1';a.kind='task_entry_incremental_frontier';
 Object.assign(a.entry,{kind:'update_plan_then_foreach',selection:'all_invalidated_work',array_field:'work',plan_field:'plan_sha256'});
 delete a.certified_digest;a.certified_digest=digest(a);delete policy.policy_digest;policy.policy_digest=digest(policy);
 const plan={question:task.question,task_sha256:task.input_version,plan_sha256:'a'.repeat(64),
  retained_claim_ids:['claim:untouched:method'],work:task.target_ids.map(paper_id=>({paper_id,fields_to_review:['method']})),synthesis_requires_review:true};
 task.plan_sha256=plan.plan_sha256;task.source_result_sha256=digest(plan);
 return {task,policy,plan};
}
test('incremental prepares only actual invalidated work, then hands off; retained PDFs are excluded',()=>{
 const {task,policy,plan}=incrementalFixture(),log=[],c=createEntryController(policy,task,r=>log.push(r));let i=0;
 feed(c,c.propose(inventoryTools,()=>String(++i))[0],plan);
 const calls=c.propose(inventoryTools,()=>String(++i));assert.deepEqual(calls.map(x=>x.proposal.arguments.paper_id),task.target_ids);
 assert.ok(calls.every(x=>x.proposal.arguments.paper_id!=='untouched'));
 for(const call of calls)feed(c,call,navResult(task,call.proposal.arguments.paper_id));
 assert.equal(c.done,true);assert.equal(log.filter(x=>x.kind==='entry_model_request_bypassed_verified').length,2);
});
for(const key of ['retained_claim_ids','plan_sha256','work','synthesis_requires_review'])test('incremental exact plan fallback on '+key,()=>{
 const {task,policy,plan}=incrementalFixture(),log=[],c=createEntryController(policy,task,r=>log.push(r));
 const call=c.propose(inventoryTools,()=>Math.random().toString())[0];
 if(key==='plan_sha256')plan[key]='b'.repeat(64);else if(key==='synthesis_requires_review')plan[key]=false;else plan[key]=[];
 feed(c,call,plan);assert.equal(c.halted,true);assert.equal(log.filter(x=>x.kind==='entry_model_request_bypassed_verified').length,0);
 assert.deepEqual(c.propose(inventoryTools,()=>''),[]);
});
