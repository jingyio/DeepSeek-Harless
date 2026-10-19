import test from 'node:test';import assert from 'node:assert/strict';import {execFileSync} from 'node:child_process';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';
import {validateOperationPolicy,createOperationController} from '../src/motif_core/operation_graph_policy.ts';
import {createOperationRuntime} from '../src/adapters/dsh_operation_motif.ts';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,rmSync} from 'node:fs';
import {resolve,join} from 'node:path';import {createHash} from 'node:crypto';
// Compile with the actual Python learner, then execute its IR in TypeScript.
const compiled=JSON.parse(execFileSync(process.env.SSS_PURE_CODE_PYTHON??'python3',['-c',
 'import json,runpy; m=runpy.run_path("tests/test_control_flow.py");f=m["frames"]();c=m["discover_flows"](f[:2])[0][0];b=m["branch_frames"]();bc=m["discover_flows"](b[:2])[0][0];i=m["frames"]();[(t["contract"].update(flow_interleaving=True)) for a in i for t in a["tools"].values()];ic=m["discover_flows"](i[:2])[0][0]; print(json.dumps({"policy":m["certify_flow"](c["compiled"],f[2]),"frame":f[2],"branch_policy":m["certify_flow"](bc["compiled"],b[2]),"branch_frame":b[2],"interleaved_policy":m["certify_flow"](ic["compiled"],i[2]),"interleaved_frame":i[2]}))'],{encoding:'utf8'}));
const obs=v=>({value:{structuredContent:v}});
function fresh(){const f=structuredClone(compiled);return {...f,tools:Object.entries(f.frame.tools).map(([name,t])=>({name,parameters:t.schema}))};}
test('Python learned nested conditions and loops execute across MCP names and different lengths',()=>{
 const {policy,frame,tools}=fresh(),audit=[];validateOperationPolicy(policy);
 for(const length of [2,5,19]){
  const c=createOperationController(policy,frame.scope,v=>audit.push(v));const [root,chunk,coverage]=[frame.rows[0].name,frame.rows[1].name,frame.rows[4].name];
  c.observe({name:root,callId:'real-root',arguments:{source_id:'fresh-source'}},obs({request_id:'q0',document_id:'doc',_sss_scope:frame.scope}));
  let i=0;while(!c.done&&!c.halted){const proposal=c.propose(tools,()=>String(i),new Set(['real-root']))[0];assert.ok(proposal);
   const name=proposal.proposal.tool;let value;
   if(name===chunk){const request=proposal.proposal.arguments.request_id;assert.equal(request,'q'+i);value={document_id:'doc',next_request_id:++i<length?'q'+i:null,empty_text:i===2||i===length&&length%2===0};}
   else{assert.equal(name,coverage);assert.deepEqual(proposal.proposal.arguments,{document_id:'doc'});value={complete:true};}
   c.observe({name,callId:proposal.callId,arguments:proposal.proposal.arguments},obs({...value,_sss_scope:frame.scope}));
  }
  assert.equal(c.done,true);assert.equal(c.halted,false);
 }
 assert.ok(audit.filter(v=>v.kind==='operation_model_request_bypassed_verified').length>20);
});
for(const damage of ['missing_control','scope','schema','no_progress','native_root','version','unseen_exit'])test('flow guard defers '+damage,()=>{
 const {policy,frame,tools}=fresh(),c=createOperationController(policy,frame.scope,()=>{}),[root,chunk]=[frame.rows[0].name,frame.rows[1].name];
 c.observe({name:root,callId:'real',arguments:{source_id:'s'}},obs({request_id:'q',document_id:'d',_sss_scope:frame.scope}));
 if(damage==='schema')tools[1].parameters={};
 if(damage==='version')frame.scope.execution_version='changed';
 let call=c.propose(tools,()=> '1',new Set(damage==='native_root'?[]:['real']))[0];
 if(call){let value={document_id:'d',next_request_id:damage==='no_progress'?'q':null,empty_text:false,_sss_scope:damage==='scope'?{}:frame.scope};
  if(damage==='missing_control')delete value.empty_text;
  c.observe({name:chunk,callId:call.callId,arguments:call.proposal.arguments},obs(value));
  call=c.propose(tools,()=> '2',new Set(['real']))[0];
  if(damage==='unseen_exit'&&call)c.observe({name:call.proposal.tool,callId:call.callId,arguments:call.proposal.arguments},obs({complete:false,_sss_scope:frame.scope}));
 }
 assert.equal(c.halted,true);assert.deepEqual(c.propose(tools,()=> '3',new Set(['real'])),[]);
});
test('re-signed branch ambiguity, invented semantics and unbounded loops remain invalid',()=>{
 for(const change of [a=>a.edges.push(a.edges[0]),a=>a.max_steps=100000,a=>a.edges[0].guard={meaning:'important'},a=>a.branch_evidence={}]){
  const {policy}=fresh();change(policy.artifact);delete policy.artifact.certified_digest;policy.artifact.certified_digest=digest(policy.artifact);delete policy.policy_digest;policy.policy_digest=digest(policy);
  assert.throws(()=>validateOperationPolicy(policy));
 }
});
test('loop step limit stops before another tool effect',()=>{
 const {policy,frame,tools}=fresh(),c=createOperationController(policy,frame.scope,()=>{}),root=frame.rows[0].name;
 c.observe({name:root,callId:'model',arguments:{source_id:'s'}},obs({request_id:'q0',document_id:'d',_sss_scope:frame.scope}));
 let steps=0;
 while(!c.halted){const call=c.propose(tools,()=>String(steps),new Set(['model']))[0];if(!call)break;
  steps++;c.observe({name:call.proposal.tool,callId:call.callId,arguments:call.proposal.arguments},obs({document_id:'d',next_request_id:'q'+steps,empty_text:false,_sss_scope:frame.scope}));}
 assert.equal(c.halted,true);assert.equal(steps,63);assert.equal(c.done,false);
});
test('original observations reconstruct a pending loop without repeating delivered chunks',()=>{
 const {policy,frame,tools}=fresh(),c=createOperationController(policy,frame.scope,()=>{});
 c.observe({name:frame.rows[0].name,callId:'model',arguments:{source_id:'s'}},obs({request_id:'q0',document_id:'d',_sss_scope:frame.scope}));
 c.observe({name:frame.rows[1].name,callId:'old-verified-call',arguments:{request_id:'q0'}},obs({document_id:'d',next_request_id:'q1',empty_text:false,_sss_scope:frame.scope}));
 assert.deepEqual(c.propose(tools,()=> 'resume',new Set(['model']))[0].proposal.arguments,{request_id:'q1'});
});
test('nested observed cases choose separate providers without model-supplied expressions',()=>{
 const f=structuredClone(compiled),policy=f.branch_policy,frame=f.branch_frame,tools=Object.entries(frame.tools).map(([name,t])=>({name,parameters:t.schema}));
 for(let i=0;i<frame.rows.length;i+=2){const c=createOperationController(policy,frame.scope,()=>{}),r=frame.rows[i],leaf=frame.rows[i+1];
  c.observe({name:r.name,callId:'model-root',arguments:r.args},obs(r.out));
  const call=c.propose(tools,()=>String(i),new Set(['model-root']))[0];assert.equal(call.proposal.tool,leaf.name);assert.deepEqual(call.proposal.arguments,leaf.args);
  c.observe({name:leaf.name,callId:call.callId,arguments:call.proposal.arguments},obs(leaf.out));assert.equal(c.done,true);
 }
});
test('native parallel document roots keep separate cursors and complete both observed exits',t=>{
 const f=structuredClone(compiled),policy=f.interleaved_policy,frame=f.interleaved_frame;
 const memoName='mcp__file_management__read_file',memoSchema={type:'object',properties:{source_id:{type:'string'}},required:['source_id']};
 const memoContract={schema:memoSchema,schema_sha256:digest(memoSchema),contract:{format:'sss-mcp-learning-v1',effect:'read',auto_continue:true,exports:[],statuses:['readable'],flow_interleaving:true}};
 frame.tools[memoName]=memoContract;policy.artifact.interleaving_contracts[memoName]=memoContract;
 delete policy.artifact.certified_digest;policy.artifact.certified_digest=digest(policy.artifact);delete policy.policy_digest;policy.policy_digest=digest(policy);
 const root=resolve('.'),home=mkdtempSync(join(root,'.local','flow-pool-'));t.after(()=>rmSync(home,{recursive:true,force:true}));
 const payload=join(home,'policy.json');writeFileSync(payload,JSON.stringify(policy));const sha=p=>createHash('sha256').update(readFileSync(p)).digest('hex');
 const manifest={schema_version:1,format:'sss-experience-registry-v1',generation:0,entries:[{entry_id:policy.policy_digest,kind:'operation_graph',payload:'policy.json',sha256:sha(payload),runtime_source:{},state:'candidate',activated_generation:1}]};manifest.registry_digest=digest(manifest);
 const registry=join(home,'registry.json');writeFileSync(registry,JSON.stringify(manifest));const audit=[];
 const runtime=createOperationRuntime({registry_file:registry,registry_sha256:sha(registry),registry_root:home,role:'certify',adapter:'file_operations_v2',scope:frame.scope,catalog:frame.tools},v=>audit.push(v));
 const tools=Object.entries(frame.tools).map(([name,v])=>({name,parameters:v.schema})),[open,chunk,coverage]=[frame.rows[0].name,frame.rows[1].name,frame.rows[4].name];
 const models=['root-a','root-b','chunk-a','chunk-b'],messages=[{role:'assistant',source:{kind:'model'},content:models.map(id=>({type:'tool-call',id}))}];
 for(const key of ['a','b'])runtime.observe({name:open,callId:'root-'+key,arguments:{source_id:key}},obs({request_id:key+'1',document_id:key,_sss_scope:frame.scope}));
 runtime.observe({name:memoName,callId:'native-memo-read',arguments:{source_id:'memo-source'}},obs({status:'readable',text:'memo reference',_sss_scope:frame.scope}));
 assert.equal(runtime.halted,false);
 for(const key of ['a','b'])runtime.observe({name:chunk,callId:'chunk-'+key,arguments:{request_id:key+'1'}},obs({document_id:key,next_request_id:key+'2',empty_text:false,_sss_scope:frame.scope}));
 const pages={a:1,b:1};let count=0;
 while(count++<20){const call=runtime.propose(tools,messages)[0];if(!call)break;let value;
  if(call.proposal.tool===chunk){const key=call.proposal.arguments.request_id[0],page=++pages[key],last=key==='a'?3:4;value={document_id:key,next_request_id:page<last?key+String(page+1):null,empty_text:page===2||key==='b'&&page===last};}
  else{assert.equal(call.proposal.tool,coverage);value={complete:true};}
  runtime.observe({name:call.proposal.tool,callId:call.callId,arguments:call.proposal.arguments},obs({...value,_sss_scope:frame.scope}));
 }
 assert.equal(runtime.halted,false);const completed=audit.filter(v=>v.kind==='operation_graph_complete');assert.equal(completed.length,2);
 assert.equal(new Set(completed.flatMap(v=>v.control_call_ids)).size,completed.flatMap(v=>v.control_call_ids).length);
});
