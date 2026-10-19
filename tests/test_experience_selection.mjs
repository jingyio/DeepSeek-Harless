import assert from 'node:assert/strict';
import test from 'node:test';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';
import {selectExperience,createExperienceController} from '../src/adapters/dsh_experience.ts';

const hex=n=>String(n).repeat(64);
function fixture(){
 const names=['read_task','list_files','pin_file','read_file','hash_files','preview_actions','execute_plan','submit_report'];
 const tools=names.map(n=>({name:'mcp__file_management__'+n,parameters:{type:'object',properties:{}}}));
 const rule='Known actual public merge rule';
 const contract={workflow_id:'FM05',source_paths:['source/a.txt'],destination_prefixes:['merged/'],context_paths:['rules/r.txt'],required_reads:['rules/r.txt'],allowed_reads:['rules/r.txt']};
 const inventory=['source/a.txt','rules/r.txt'].map((path,i)=>({path,bytes:1,extension:'.txt',sha256:digest(i),file_id:'file:local:'+digest({path,sha:digest(i)}).slice(0,24),source_version:digest(['v',i])}));
 const spec={objective:'Merge the actual sources',report_contract:{kind:'task_result'},workflow_contract:contract,initial_snapshot:Object.fromEntries(inventory.map(r=>[r.path,r.sha256]))};
 const task={...spec,input_sha256:digest(spec),allowed_operations:['copy'],copy_only:true,workflow_execution_version_sha256:hex('c')};
 const payload={workflow_id:'FM05',schema_version:2,format:'sss-learned-copy-script-v2',execution_version_sha256:hex('c'),
  steps:[{op:'hash_representatives',order:'min'},{op:'copy_map',source:'hash_representatives',strip_prefix:'',destination_slot:0}],
  guard_cases:[{objective_sha256:digest(task.objective),context_text_sha256:digest(rule),destination_prefixes:['merged/']}],
  training:[{role:'explore',task_fingerprint:hex('a'),events_sha256:hex('d')},{role:'explore',task_fingerprint:hex('b'),events_sha256:hex('e')}],
  runtime_source:Object.fromEntries(['src/adapters/dsh_learned_script_v2.ts','src/motif_core/online_skill_runtime.mjs','src/motif_core/terminal_receipt_policy.ts'].map(n=>[n,hex('f')])),
  tool_schema_sha256:Object.fromEntries(tools.map(t=>[t.name,digest(t.parameters)]))};payload.script_digest=digest(payload);
 const entry={entry_id:payload.script_digest,kind:'script_v2',payload,compatible:true,activated_generation:2};
 return {tools,spec,task,rule,inventory,entry,facts:{task,rule,inventory},binding:{spec,prompt_sha256:hex('a'),session_id:'s'}};
}
test('automatic selection uses observed facts even when unrelated profile labels lie',()=>{
 const f=fixture();f.task.profile_id='wrong-template';f.entry.payload.profile_id='another-wrong-label';
 assert.equal(selectExperience([f.entry],f.facts,f.tools).selected.entry_id,f.entry.entry_id);
});
for(const damage of ['goal','rule','permission','schema','version','current_sources','source_runtime'])test('selection rejects '+damage,()=>{
 const f=fixture();
 if(damage==='goal')f.task.objective+=' new user instruction';
 if(damage==='rule')f.facts.rule+=' changed';
 if(damage==='permission')f.task.allowed_operations=['move'];
 if(damage==='schema')f.tools[3].parameters.extra='changed';
 if(damage==='version')f.task.workflow_execution_version_sha256=hex('f');
 if(damage==='current_sources')f.task.workflow_contract.source_paths=['outside/private.txt'];
 if(damage==='source_runtime')f.entry.compatible=false;
 assert.equal(selectExperience([f.entry],f.facts,f.tools).selected,null);
});
test('conflicting valid instructions return to semantics rather than arbitrary template choice',()=>{
 const f=fixture(),other=structuredClone(f.entry);other.payload.steps[0].order='max';
 assert.equal(selectExperience([f.entry,other],f.facts,f.tools).reason,'ambiguous_certified_programs');
});
test('bootstrap changed current bytes stop before any effect or rule read',()=>{
 const f=fixture(),audit=[],c=createExperienceController([f.entry],f.binding,r=>audit.push(r));
 function respond(call,out){c.observe({name:call.proposal.tool,callId:call.callId,arguments:call.proposal.arguments},{value:{structuredContent:out}});}
 let next=c.propose(f.tools);respond(next.call,f.task);next=c.propose(f.tools);
 respond(next.call,{snapshot_sha256:hex('f'),files:f.inventory});
 assert.equal(c.halted,true);assert.equal(c.propose(f.tools),null);
 assert.equal(audit.some(r=>r.kind==='experience_selected'),false);
});
test('rule bootstrap does not read a path outside the actual read permission',()=>{
 const f=fixture();f.task.workflow_contract.allowed_reads=[];f.spec.workflow_contract=f.task.workflow_contract;f.task.input_sha256=digest(f.spec);
 const calls=[],c=createExperienceController([f.entry],f.binding,()=>{});
 for(const out of [f.task,{files:f.inventory,snapshot_sha256:digest(f.spec.initial_snapshot)}]){
  const call=c.propose(f.tools).call;calls.push(call.proposal.tool);c.observe({name:call.proposal.tool,callId:call.callId,arguments:call.proposal.arguments},{value:{structuredContent:out}});
 }
 assert.equal(c.propose(f.tools),null);assert.equal(c.halted,true);
 assert.deepEqual(calls,['mcp__file_management__read_task','mcp__file_management__list_files']);
});
test('explicit repair disables retrieval permanently for this session',()=>{
 const f=fixture(),c=createExperienceController([f.entry],f.binding,()=>{});c.fail('acceptance_repair_requires_ordinary_harness');
 assert.equal(c.propose(f.tools),null);assert.equal(c.halted,true);
});
