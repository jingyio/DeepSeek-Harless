import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {markAgentLoopRequest} from '@deepseek-ai/dsh-llm';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';
import {createCollectionController,validateCollectionPolicy,validateCollectionTask} from '../src/motif_core/collection_read_policy.ts';
import {createCollectionGate} from '../src/adapters/dsh_entry_motif.ts';
const names=['select','pin','read','gather'].map(n=>'mcp__test__'+n);
function fixture(n=13){
 const [source,pin,read,gather]=names;
 const schemas=[['file_ids'],['file_id'],['source_id'],['collection_id','source_ids']].map(required=>({type:'object',required,
  properties:Object.fromEntries(required.map(k=>[k,k.endsWith('_ids')?{type:'array',items:{type:'string'}}:{type:'string'}]))}));
 const tools=names.map((name,i)=>({name,parameters:schemas[i]}));
 const graph={source_tool:source,pin_tool:pin,read_tool:read,gather_tool:gather,selection:'actual_model_selected_members',
  array_field:'files',identity_field:'file_id',pin_param:'file_id',read_param:'source_id',gather_param:'source_ids',
  max_targets:32,max_batch:8,stop:'semantic_handoff_after_complete_gather'};
 const edges=[{from_tool:source,from_field:'files[].file_id',to_tool:pin,to_param:'file_id',mapping:'foreach_all_selected'},
  {from_tool:pin,from_field:'source_id',to_tool:read,to_param:'source_id',mapping:'same_iteration'},
  {from_tool:read,from_field:'source_id',to_tool:gather,to_param:'source_ids',mapping:'gather_complete'},
  {from_tool:source,from_field:'collection_id',to_tool:gather,to_param:'collection_id',mapping:'same_collection'}];
 const artifact={kind:'selected_collection_read_graph',status:'trace_validated_read_only',tools:names,
  source_task_fingerprints:['a','b'],validation_task_fingerprint:'c',graph,transfer_evidence:edges,
  tool_schema_sha256:Object.fromEntries(tools.map(t=>[t.name,digest(t.parameters)]))};artifact.certified_digest=digest(artifact);
 const policy={schema_version:1,format:'sss-collection-read-v1',source_library_digest:'a'.repeat(64),execution_version_sha256:'b'.repeat(64),artifact};policy.policy_digest=digest(policy);
 const inventory=Array.from({length:n},(_,i)=>({file_id:'file-'+i,path:i+'.txt',bytes:10,sha256:digest(i),source_version:digest(['v',i])}));
 const task={schema_version:1,session_id:'s',task_id:'t',input_version:'c'.repeat(64),snapshot_sha256:'d'.repeat(64),
  execution_version_sha256:policy.execution_version_sha256,inventory,inventory_sha256:digest(inventory),
  prompt_sha256:createHash('sha256').update('Read my selected files').digest('hex')};
 const packet={collection_id:'collection-opaque',input_sha256:task.input_version,snapshot_sha256:task.snapshot_sha256,
  execution_version_sha256:task.execution_version_sha256,files:inventory,selection:graph.selection,count:n};packet.collection_sha256=digest(packet);
 return {policy,task,tools,packet};
}
const observed=out=>({value:{structuredContent:out}});
function select(c,f,packet=f.packet){c.observe({name:names[0],callId:'model-selection',arguments:{file_ids:f.packet.files.map(r=>r.file_id)}},observed(packet));}
function response(f,call,reads){
 const args=call.proposal.arguments;
 if(call.proposal.tool===names[1]){const row=f.packet.files.find(r=>r.file_id===args.file_id);return {file_id:row.file_id,source_version:row.source_version,source_id:'handle-'+row.file_id};}
 if(call.proposal.tool===names[2]){const row=f.packet.files.find(r=>'handle-'+r.file_id===args.source_id);
  const out={...row,source_id:args.source_id,status:row.file_id.endsWith('1')?'unreadable':'readable',text:'actual'};reads.set(row.file_id,out);return out;}
 const rows=f.packet.files.map(r=>{const read=reads.get(r.file_id);return {file_id:r.file_id,path:r.path,source_id:read.source_id,
  source_version:r.source_version,status:read.status,read_sha256:digest(read)};});
 return {status:'collection_complete',collection_id:f.packet.collection_id,collection_sha256:f.packet.collection_sha256,
  input_sha256:f.task.input_version,execution_version_sha256:f.task.execution_version_sha256,snapshot_sha256:f.task.snapshot_sha256,
  files:rows,count:rows.length,coverage_sha256:digest(rows),semantic_judgment_certified:false};
}
test('post-selection foreach preserves 13 actual identities, failures-as-diagnostics and complete gather',()=>{
 const f=fixture(),log=[],c=createCollectionController(f.policy,f.task,r=>log.push(r));let i=0;const reads=new Map();
 assert.deepEqual(c.propose(f.tools,()=>String(++i)),[]);select(c,f);
 while(!c.done){const calls=c.propose(f.tools,()=>String(++i));assert.ok(calls.length>0&&calls.length<=8);
  assert.deepEqual(c.propose(f.tools,()=>''),[]);
  for(const call of calls)c.observe({name:call.proposal.tool,callId:call.callId,arguments:call.proposal.arguments},observed(response(f,call,reads)));}
 assert.equal(reads.size,13);assert.equal(log.filter(r=>r.kind==='collection_model_request_bypassed_verified').length,5);
 assert.equal(log.filter(r=>r.kind==='collection_motif_read_verified').length,13);
 assert.deepEqual(c.propose(f.tools,()=>''),[]);
});
for(const damage of ['scope','version','digest','snapshot','schema','failure','interleaving','gather'])test('collection defers on '+damage,()=>{
 const f=fixture(2),log=[],c=createCollectionController(f.policy,f.task,r=>log.push(r));let i=0;const reads=new Map();
 if(['scope','version','digest','snapshot'].includes(damage)){
  const packet=structuredClone(f.packet);
  if(damage==='scope')packet.files[0].path='outside.txt';
  if(damage==='version')packet.execution_version_sha256='e'.repeat(64);
  if(damage==='snapshot')packet.snapshot_sha256='e'.repeat(64);
  if(damage!=='digest'){delete packet.collection_sha256;packet.collection_sha256=digest(packet);}else packet.collection_sha256='e'.repeat(64);
  select(c,f,packet);
 }else{
  select(c,f);
  if(damage==='interleaving')c.observe({name:'mcp__test__write',callId:'model-write',arguments:{}},observed({}));
  else if(damage==='schema')c.propose(f.tools.map(t=>({...t,parameters:{}})),()=>String(++i));
  else{
   while(!c.halted&&!c.done){const calls=c.propose(f.tools,()=>String(++i));
    for(const call of calls){let out=response(f,call,reads);
     if(damage==='failure'){c.observe({name:call.proposal.tool,callId:call.callId,arguments:call.proposal.arguments},{isError:true});break;}
     if(damage==='gather'&&call.proposal.tool===names[3])out={...out,files:[]};
     c.observe({name:call.proposal.tool,callId:call.callId,arguments:call.proposal.arguments},observed(out));}
   }
  }
 }
 assert.equal(c.halted,true);assert.equal(c.done,false);assert.deepEqual(c.propose(f.tools,()=>''),[]);
});
test('empty selected set gathers explicit zero coverage, and policy/task changes reject',()=>{
 const f=fixture(0),c=createCollectionController(f.policy,f.task,()=>{});select(c,f);const call=c.propose(f.tools,()=> 'id')[0];
 assert.equal(call.proposal.tool,names[3]);c.observe({name:call.proposal.tool,callId:call.callId,arguments:call.proposal.arguments},observed(response(f,call,new Map())));
 assert.equal(c.done,true);const changed=structuredClone(f.policy);changed.artifact.graph.max_targets=100;assert.throws(()=>validateCollectionPolicy(changed));
 const task={...f.task,execution_version_sha256:'f'.repeat(64)};assert.throws(()=>validateCollectionTask(task,f.policy));
});
test('matching prompt after a real model selection can bypass, while new user input returns to model',async()=>{
 const f=fixture(1),gate=createCollectionGate(f.policy,f.task,()=>{});let fallback=0;
 const next=()=>{fallback++;return(async function*(){})();};
 const request=markAgentLoopRequest({sessionId:'s',tools:f.tools,messages:[{id:'u',role:'user',source:{kind:'user'},content:[{type:'text',text:'Read my selected files'}]},
  {role:'assistant',content:[{type:'text',text:'I selected a file'}]}]});
 for await(const _ of gate.intercept(request,next,true)){}assert.equal(fallback,1);
 select(gate.controller,f);const chunks=[];for await(const c of gate.intercept(request,next,true))chunks.push(c);
 assert.ok(chunks.some(c=>c.type==='tool-call-delta'&&c.name===names[1]));assert.equal(fallback,1);
 const other=createCollectionGate(f.policy,f.task,()=>{});select(other.controller,f);
 const changed=markAgentLoopRequest({...request,messages:[...request.messages,{id:'extra',role:'user',source:{kind:'user'},content:[{type:'text',text:'Use another set'}]}]});
 for await(const _ of other.intercept(changed,next,true)){}assert.equal(other.controller.halted,true);
});
