import assert from 'node:assert/strict';
import test from 'node:test';
import {createTaskObserver} from '../src/adapters/dsh_continuous_rsi.ts';
import {selectExperience} from '../src/adapters/dsh_experience.ts';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';

test('task lifecycle sends a notification once, never claims task acceptance',()=>{
 const emitted=[],o=createTaskObserver({session_id:'task',allowed_tools:['mcp__file_management__select_files'],task_sha256:'a',binding_sha256:'b'},r=>emitted.push(r));
 o.created('task');o.tools('task',[{name:'mcp__file_management__select_files',parameters:{type:'object'}}]);o.result();o.disposed();o.disposed();
 assert.equal(emitted.length,2);assert.equal(emitted[1].tool_results,1);assert.equal(emitted[1].event,'agent_disposed');
 assert.equal(emitted[1].accepted,undefined);
});
test('wrong sessions and changing schema cannot enter the learning notification',()=>{
 const o=createTaskObserver({session_id:'t',allowed_tools:['a']},()=>{});
 assert.throws(()=>o.created('other'));o.created('t');o.tools('t',[{name:'a',parameters:{type:'object'}}]);
 assert.throws(()=>o.tools('t',[{name:'a',parameters:{type:'array'}}]));
});
test('Web terminal lifecycle is distinct from disposal and emits only once',()=>{
 const rows=[],o=createTaskObserver({session_id:'web',allowed_tools:['a']},r=>rows.push(r));
 o.created('web');o.tools('web',[{name:'a',parameters:{}}]);o.result();o.taskFinalized();o.disposed();o.taskFinalized();
 assert.equal(rows.length,2);assert.equal(rows[1].event,'web_task_terminal');assert.equal(rows[1].tool_results,1);
 assert.equal(rows[1].accepted,undefined);
});
test('plain read-only report task can retrieve a witnessed collection without a workflow/profile ID',()=>{
 const tool={name:'mcp__file_management__select_files',parameters:{type:'object'}},version='e'.repeat(64);
 const entry={kind:'collection',compatible:true,activated_generation:1,entry_id:'c',payload:{execution_version_sha256:version,
  artifact:{tool_schema_sha256:{[tool.name]:digest(tool.parameters)}}}};
 const facts={task:{copy_only:true,allowed_operations:[],report_contract:{kind:'inspection'},report_execution_version_sha256:version},inventory:[],rule:null};
 assert.equal(selectExperience([entry],facts,[tool]).selected,entry);
 facts.task.allowed_operations=['move'];assert.equal(selectExperience([entry],facts,[tool]).selected,null);
});
test('reentry checks both version and actual child schemas before retrieval',()=>{
 const tool={name:'mcp__file_management__select_files',parameters:{}},version='d'.repeat(64);
 const entry={kind:'reentry',compatible:true,activated_generation:2,payload:{execution_version_sha256:version,
  next_policy:{artifact:{tool_schema_sha256:{[tool.name]:digest({})}}}}};
 const facts={task:{copy_only:true,allowed_operations:[],report_contract:{kind:'inspection'},report_execution_version_sha256:version}};
 assert.equal(selectExperience([entry],facts,[tool]).selected,entry);
 tool.parameters={changed:true};assert.equal(selectExperience([entry],facts,[tool]).selected,null);
});
