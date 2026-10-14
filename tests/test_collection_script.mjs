import test from 'node:test';import assert from 'node:assert/strict';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';
import {validateCollectionScript,scriptGraph,createCollectionScriptController} from '../src/motif_core/collection_batch_script.ts';
function f(){const tools=[scriptGraph.source_tool,scriptGraph.pin_tool,scriptGraph.read_tool,scriptGraph.gather_tool];
 const s={schema_version:1,format:'sss-collection-script-v1',origin:'handwritten_no_library',graph:scriptGraph,tools,
 execution_version_sha256:'a'.repeat(64),tool_schema_sha256:Object.fromEntries(tools.map(t=>[t,digest({})]))};s.script_digest=digest(s);
 const t={schema_version:1,task_id:'t',session_id:'s',input_version:'b'.repeat(64),snapshot_sha256:'c'.repeat(64),
 execution_version_sha256:s.execution_version_sha256,inventory:[],inventory_sha256:digest([])};return {s,t};}
test('handwritten config loads without certified artifact or training witnesses',()=>{const {s,t}=f();assert.equal(validateCollectionScript(s),s);assert.equal(createCollectionScriptController(s,t,()=>{}).armed,false);});
for(const k of ['origin','graph','script_digest'])test('script rejects changed '+k,()=>{const {s}=f();s[k]=k==='graph'?{...scriptGraph,max_batch:16}:'changed';assert.throws(()=>validateCollectionScript(s));});
test('script has its own verified audit and explicit empty coverage, no Motif attribution',()=>{const {s,t}=f(),log=[],c=createCollectionScriptController(s,t,r=>log.push(r));
 const packet={collection_id:'chosen',input_sha256:t.input_version,snapshot_sha256:t.snapshot_sha256,execution_version_sha256:t.execution_version_sha256,
 files:[],count:0,selection:scriptGraph.selection};packet.collection_sha256=digest(packet);
 c.observe({name:s.tools[0],callId:'model-real',arguments:{file_ids:[]}},{value:{structuredContent:packet}});
 const call=c.propose(s.tools.map(name=>({name,parameters:{}})),()=> 'id')[0];assert.equal(call.proposal.tool,s.tools[3]);
 c.observe({name:call.proposal.tool,callId:call.callId,arguments:call.proposal.arguments},{value:{structuredContent:{status:'collection_complete',collection_id:'chosen',
 collection_sha256:packet.collection_sha256,input_sha256:t.input_version,execution_version_sha256:t.execution_version_sha256,snapshot_sha256:t.snapshot_sha256,
 count:0,files:[],coverage_sha256:digest([]),semantic_judgment_certified:false}}});
 assert.equal(c.done,true);assert.ok(log.some(r=>r.kind==='collection_script_batch_verified'));assert.ok(log.every(r=>!r.kind.includes('motif')&&!r.policy_digest&&!r.certified_digest));});
