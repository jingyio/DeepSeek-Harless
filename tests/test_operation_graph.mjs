import test from 'node:test';import assert from 'node:assert/strict';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';
import {createOperationController,validateOperationPolicy} from '../src/motif_core/operation_graph_policy.ts';
function fixture(){
 const names=['prepare','perform','inspect'].map(n=>'mcp__other__'+n),scope={execution_version:'a'.repeat(64)};
 const tools=names.map((name,i)=>({name,parameters:{type:'object',required:[i?'handle':'intent']}}));
 const contracts=Object.fromEntries(tools.map((t,i)=>[t.name,{schema:t.parameters,schema_sha256:digest(t.parameters),contract:{
  format:'sss-mcp-learning-v1',effect:i===1?'authorized_write':'read',auto_continue:i>0,exports:i===0?['first','branch']:i===1?['second']:[]}}]));
 const a={kind:'learned_mcp_operation_dag',status:'trace_validated_effectful',execution_version:scope.execution_version,max_nodes:8,
  nodes:[{tool:names[0],bindings:{}},{tool:names[1],bindings:{handle:{node:0,path:'first'}}},{tool:names[2],bindings:{handle:{node:1,path:'second'}}}],
  tool_contracts:contracts,source_task_fingerprints:['a','b'],validation_task_fingerprint:'c'};a.certified_digest=digest(a);
 const p={schema_version:1,format:'sss-operation-graph-v1',execution_version_sha256:scope.execution_version,artifact:a};p.policy_digest=digest(p);
 return {p,tools,scope,names};
}
const obs=v=>({value:{structuredContent:v}});
const resign=p=>{delete p.artifact.certified_digest;p.artifact.certified_digest=digest(p.artifact);delete p.policy_digest;p.policy_digest=digest(p);};
test('new MCP names execute witnessed bindings and preserve native semantic root',()=>{
 const f=fixture(),log=[],c=createOperationController(f.p,f.scope,v=>log.push(v));let i=0;
 c.observe({name:f.names[0],callId:'native',arguments:{intent:'new goal'}},obs({first:'actual-a',_sss_scope:f.scope}));
 let call=c.propose(f.tools,()=>String(++i),new Set(['native']))[0];assert.equal(call.proposal.arguments.handle,'actual-a');
 c.observe({name:call.proposal.tool,callId:call.callId,arguments:call.proposal.arguments},obs({second:'actual-b',_sss_scope:f.scope,_sss_authorized:true}));
 call=c.propose(f.tools,()=>String(++i),new Set(['native']))[0];assert.equal(call.proposal.arguments.handle,'actual-b');
 c.observe({name:call.proposal.tool,callId:call.callId,arguments:call.proposal.arguments},obs({_sss_scope:f.scope}));
 assert.equal(c.done,true);assert.equal(log.filter(v=>v.kind==='operation_model_request_bypassed_verified').length,2);
});
for(const damage of ['authority','scope','schema','root','binding'])test('operation guard stops on '+damage,()=>{
 const f=fixture(),c=createOperationController(f.p,f.scope,()=>{});let i=0;
 c.observe({name:f.names[0],callId:'native',arguments:{}},obs({first:'actual',_sss_scope:f.scope}));
 if(damage==='root'){c.propose(f.tools,()=>String(++i),new Set());assert.equal(c.halted,true);return;}
 if(damage==='schema'){f.tools[1].parameters={};c.propose(f.tools,()=>String(++i),new Set(['native']));assert.equal(c.halted,true);return;}
 const call=c.propose(f.tools,()=>String(++i),new Set(['native']))[0];
 c.observe({name:call.proposal.tool,callId:call.callId,arguments:damage==='binding'?{handle:'guessed'}:call.proposal.arguments},
  obs({second:'next',_sss_scope:damage==='scope'?{}:f.scope,_sss_authorized:damage!=='authority'}));
 assert.equal(c.halted,true);assert.deepEqual(c.propose(f.tools,()=>String(++i),new Set(['native'])),[]);
});
test('native prefetch is adopted, never counted as a skipped model request',()=>{
 const f=fixture(),log=[],c=createOperationController(f.p,f.scope,v=>log.push(v));
 c.observe({name:f.names[0],callId:'root',arguments:{}},obs({first:'actual',_sss_scope:f.scope}));
 c.observe({name:f.names[1],callId:'model-prefetch',arguments:{handle:'actual'}},obs({second:'next',_sss_scope:f.scope,_sss_authorized:true}));
 assert.equal(log.filter(v=>v.kind==='operation_model_request_bypassed_verified').length,0);
 assert.equal(c.propose(f.tools,()=> 'id',new Set(['root']))[0].proposal.arguments.handle,'next');
});
test('resigned cyclic or semantic constants remain invalid',()=>{
 for(const mutate of [p=>p.artifact.nodes[1].bindings.handle.node=2,p=>p.artifact.nodes[1].bindings.handle={literal:'unsafe'}]){
  const f=fixture();mutate(f.p);delete f.p.artifact.certified_digest;f.p.artifact.certified_digest=digest(f.p.artifact);delete f.p.policy_digest;f.p.policy_digest=digest(f.p);
  assert.throws(()=>validateOperationPolicy(f.p));
 }
});
test('declared safe read interleaving is preserved and never counted as bypass',()=>{
 const f=fixture(),name='mcp__other__listing',parameters={type:'object',required:[]},log=[];
 f.tools.push({name,parameters});f.p.artifact.interleaving_contracts={[name]:{schema:parameters,schema_sha256:digest(parameters),
  contract:{format:'sss-mcp-learning-v1',effect:'read',safe_interleaving:true,exports:[]}}};resign(f.p);
 const c=createOperationController(f.p,f.scope,r=>log.push(r));
 c.observe({name:f.names[0],callId:'root',arguments:{}},obs({first:'actual',_sss_scope:f.scope}));
 c.observe({name,callId:'native-read',arguments:{}},obs({_sss_scope:f.scope}));
 assert.equal(c.halted,false);assert.equal(log.at(-1).model_request_bypassed,false);
 assert.equal(c.propose(f.tools,()=> 'id',new Set(['root']))[0].proposal.arguments.handle,'actual');
 assert.equal(log.filter(r=>r.kind==='operation_model_request_bypassed_verified').length,0);
 f.p.artifact.interleaving_contracts[name].contract.effect='authorized_write';resign(f.p);
 assert.throws(()=>validateOperationPolicy(f.p));
});
test('read-result continuation requires its original task intent',()=>{
 const f=fixture(),scope={...f.scope,result_read_allowed:false};f.p.artifact.tool_contracts[f.names[2]].contract.scope_requirements={result_read_allowed:true};resign(f.p);
 const c=createOperationController(f.p,scope,()=>{});
 c.observe({name:f.names[0],callId:'root',arguments:{}},obs({first:'actual',_sss_scope:scope}));
 c.observe({name:f.names[1],callId:'native-perform',arguments:{handle:'actual'}},obs({second:'next',_sss_scope:scope,_sss_authorized:true}));
 assert.deepEqual(c.propose(f.tools,()=> 'id',new Set(['root'])),[]);assert.equal(c.halted,true);
});
test('fan-out uses an earlier root export rather than the most recent output',()=>{
 const f=fixture();f.p.artifact.nodes[2].bindings.handle={node:0,path:'branch'};resign(f.p);
 const c=createOperationController(f.p,f.scope,()=>{});
 c.observe({name:f.names[0],callId:'root',arguments:{}},obs({first:'actual',branch:'other',_sss_scope:f.scope}));
 c.observe({name:f.names[1],callId:'native',arguments:{handle:'actual'}},obs({second:'next',_sss_scope:f.scope,_sss_authorized:true}));
 assert.equal(c.propose(f.tools,()=> 'id',new Set(['root']))[0].proposal.arguments.handle,'other');
});
function arrayFixture(){
 const f=fixture();f.p.format='sss-operation-graph-v2';f.p.artifact.certification_contract='sss-operation-certification-v2';
 f.p.artifact.nodes=f.p.artifact.nodes.slice(0,2);f.p.artifact.nodes[1].bindings={handle:{node:0,path:'files[].id'}};
 const params={type:'object',required:['handle'],properties:{handle:{type:'array',items:{type:'string'},minItems:1,maxItems:3}}};
 f.tools[1].parameters=params;Object.assign(f.p.artifact.tool_contracts[f.names[1]],{schema:params,schema_sha256:digest(params)});
 f.p.artifact.tool_contracts[f.names[0]].contract.exports=['files[].id'];resign(f.p);return f;
}
test('v2 binds every real output ID with one bounded array projection',()=>{
 const f=arrayFixture(),c=createOperationController(f.p,f.scope,()=>{});
 c.observe({name:f.names[0],callId:'native-root',arguments:{}},obs({files:[{id:'a'},{id:'b'}],_sss_scope:f.scope}));
 const next=c.propose(f.tools,()=> 'batch',new Set(['native-root']))[0];assert.deepEqual(next.proposal.arguments.handle,['a','b']);
 c.observe({name:f.names[1],callId:next.callId,arguments:next.proposal.arguments},obs({_sss_scope:f.scope,_sss_authorized:true}));assert.equal(c.done,true);
});
for(const values of [[],['a','a'],['a','b','c','d'],['a',null]])test('v2 rejects incomplete, duplicate or schema-bounded batch '+JSON.stringify(values),()=>{
 const f=arrayFixture(),c=createOperationController(f.p,f.scope,()=>{});
 c.observe({name:f.names[0],callId:'native-root',arguments:{}},obs({files:values.map(id=>({id})),_sss_scope:f.scope}));
 assert.deepEqual(c.propose(f.tools,()=> 'batch',new Set(['native-root'])),[]);assert.equal(c.halted,true);
});
