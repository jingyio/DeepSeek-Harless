import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync} from 'node:fs';
import {dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';
import {createOperationRuntime} from '../src/adapters/dsh_operation_motif.ts';

const root=dirname(dirname(fileURLToPath(import.meta.url)));
const obs=value=>({value:{structuredContent:value}});
function fixture(t,rootContract={}) {
  mkdirSync(join(root,'.local'),{recursive:true});
  const home=mkdtempSync(join(root,'.local','operation-root-admission-'));
  t.after(()=>rmSync(home,{recursive:true,force:true}));
  const names=['prepare','perform','inspect'].map(n=>'mcp__root_admission__'+n);
  const scope={execution_version:'a'.repeat(64),permission_sha256:'b'.repeat(64)};
  const tools=names.map((name,i)=>({name,parameters:{type:'object',properties:{[i?'handle':'intent']:{type:'string'}},required:[i?'handle':'intent']}}));
  const catalog=Object.fromEntries(tools.map((v,i)=>[v.name,{schema:v.parameters,schema_sha256:digest(v.parameters),contract:{format:'sss-mcp-learning-v1',effect:i===1?'authorized_write':'read',auto_continue:i>0,exports:i===0?['first']:i===1?['second']:[]}}]));
  Object.assign(catalog[names[0]].contract,rootContract);
  const artifact={kind:'learned_mcp_operation_dag',status:'trace_validated_effectful',execution_version:scope.execution_version,max_nodes:8,certification_contract:'sss-operation-certification-v2',
    nodes:[{tool:names[0],bindings:{}},{tool:names[1],bindings:{handle:{node:0,path:'first'}}},{tool:names[2],bindings:{handle:{node:1,path:'second'}}}],
    tool_contracts:catalog,source_task_fingerprints:['training-a','training-b'],validation_task_fingerprint:'independent-c'};
  artifact.certified_digest=digest(artifact);
  const policy={schema_version:1,format:'sss-operation-graph-v2',execution_version_sha256:scope.execution_version,artifact};policy.policy_digest=digest(policy);
  const payload=join(home,'policy.json');writeFileSync(payload,JSON.stringify(policy));
  const sha=p=>createHash('sha256').update(readFileSync(p)).digest('hex');
  const manifest={schema_version:1,format:'sss-experience-registry-v1',generation:0,entries:[{entry_id:policy.policy_digest,kind:'operation_graph',payload:'policy.json',sha256:sha(payload),runtime_source:{},state:'candidate',activated_generation:1}]};manifest.registry_digest=digest(manifest);
  const registry=join(home,'registry.json');writeFileSync(registry,JSON.stringify(manifest));
  const audit=[],runtime=createOperationRuntime({registry_file:registry,registry_sha256:sha(registry),registry_root:home,role:'certify',adapter:'file_operations_v2',scope,catalog},row=>audit.push(row));
  const messages=id=>[{role:'assistant',source:{kind:'model'},content:[{type:'tool-call',id,name:names[0],arguments:{intent:'actual new goal'}}]}];
  return {names,scope,tools,audit,runtime,messages};
}

for (const error of [{isError:true,value:{content:[{type:'text',text:'preview rejected before effects'}]}},
  {value:{isError:true,content:[{type:'text',text:'invalid native root arguments'}]}}])
  test('an ordinary root error cannot select or permanently disable a graph before admission '+(error.isError?'outer':'nested'),t=>{
    const f=fixture(t);
    f.runtime.observe({name:f.names[0],callId:'native-invalid',arguments:{intent:'invalid'}},error);
    assert.equal(f.runtime.halted,false);assert.deepEqual(f.runtime.propose(f.tools,f.messages('native-invalid')),[]);
    assert.equal(f.audit.filter(e=>e.kind==='experience_selected').length,0);
    assert.equal(f.audit.filter(e=>e.kind==='experience_deferred').length,0);
    assert.equal(f.audit.filter(e=>e.kind==='operation_root_error_observed').length,1);
    f.runtime.observe({name:f.names[0],callId:'native-corrected',arguments:{intent:'actual new goal'}},obs({first:'verified-first',_sss_scope:f.scope}));
    let next=f.runtime.propose(f.tools,f.messages('native-corrected'))[0];assert.ok(next);
    f.runtime.observe({name:next.proposal.tool,callId:next.callId,arguments:next.proposal.arguments},obs({second:'verified-second',_sss_scope:f.scope,_sss_authorized:true}));
    next=f.runtime.propose(f.tools,f.messages('native-corrected'))[0];assert.ok(next);
    f.runtime.observe({name:next.proposal.tool,callId:next.callId,arguments:next.proposal.arguments},obs({_sss_scope:f.scope}));
    assert.equal(f.audit.filter(e=>e.kind==='operation_graph_complete').length,1);
    assert.equal(f.audit.filter(e=>e.kind==='operation_model_request_bypassed_verified').length,2);
    assert.deepEqual(f.audit.filter(e=>e.kind==='operation_root_verified').map(e=>e.call_id),['native-corrected']);
  });

test('a purported successful root with another scope still stops execution',t=>{
  const f=fixture(t);f.runtime.observe({name:f.names[0],callId:'foreign',arguments:{}},obs({first:'foreign',_sss_scope:{...f.scope,permission_sha256:'c'.repeat(64)}}));
  assert.equal(f.runtime.halted,true);assert.deepEqual(f.runtime.propose(f.tools,f.messages('foreign')),[]);
});

test('a failed continuation after admission still stops the candidate permanently',t=>{
  const f=fixture(t);f.runtime.observe({name:f.names[0],callId:'native-valid',arguments:{}},obs({first:'verified-first',_sss_scope:f.scope}));
  const next=f.runtime.propose(f.tools,f.messages('native-valid'))[0];assert.ok(next);
  f.runtime.observe({name:next.proposal.tool,callId:next.callId,arguments:next.proposal.arguments},{isError:true,value:{content:[{type:'text',text:'actual generated operation failed'}]}});
  assert.equal(f.runtime.halted,true);assert.deepEqual(f.runtime.propose(f.tools,f.messages('native-valid')),[]);
  assert.equal(f.audit.filter(e=>e.kind==='operation_model_request_bypassed_verified').length,0);
});

for(const kind of ['status','authority'])test('same-scope ordinary semantic calls do not select an inapplicable root '+kind,t=>{
 const f=fixture(t,kind==='status'?{statuses:['certifiable']}:{effect:'authorized_write'});
 f.runtime.observe({name:f.names[0],callId:'ordinary-semantic',arguments:{}},obs({first:'unapproved',status:'ordinary',_sss_scope:f.scope,_sss_authorized:false}));
 assert.equal(f.runtime.halted,false);assert.equal(f.audit.some(v=>v.kind==='experience_selected'),false);
 f.runtime.observe({name:f.names[0],callId:'native-approved',arguments:{}},obs({first:'approved',status:'certifiable',_sss_scope:f.scope,_sss_authorized:true}));
 assert.ok(f.runtime.propose(f.tools,f.messages('native-approved'))[0]);
});
