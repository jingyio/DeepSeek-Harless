import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {validateRsiRecord,bytesSha256,admissionDecision,executeRsiOperation,
 validateRsiUpdate,publishRsiUpdate,rollbackRsiUpdate} from '../src/adapters/rsi_protocol.ts';
import {fixtures,fixtureRecord,diagnosticHost} from '../examples/rsi-protocol-v1/host.mjs';

const root=fileURLToPath(new URL('../',import.meta.url));
const python=process.env.SSS_PYTHON??(process.platform==='win32'?'python':'python3');
const copy=structuredClone;
const encode=value=>JSON.stringify(value);

test('Python and TypeScript agree on all public wire fixtures, including invalid records',()=>{
 const records=[...fixtures.records,...fixtures.invalid.map(x=>x.record)];
 const actual=records.map(r=>{try{validateRsiRecord(r);return true;}catch{return false;}});
 const run=spawnSync(python,['scripts/check-rsi-wire.py'],{cwd:root,encoding:'utf8'});
 assert.equal(run.status,0,run.stderr);
 assert.deepEqual(actual,JSON.parse(run.stdout));
 assert.deepEqual(actual,[...fixtures.records.map(()=>true),...fixtures.invalid.map(()=>false)]);
});

test('fixture versions bind the actual Python operator and TypeScript admission code',()=>{
 assert.equal(fixtures.versions.motif.sha256,bytesSha256(readFileSync(new URL('../examples/rsi-protocol-v1/group_count.py',import.meta.url))));
 assert.equal(fixtures.versions.matcher.sha256,bytesSha256(readFileSync(new URL('../src/adapters/rsi_protocol.ts',import.meta.url))));
});

test('different complete tasks execute the same local Python operation on different current inputs',async()=>{
 for(const task of ['A','B']){
  const {request,host,args}=diagnosticHost(task);
  const execution=await executeRsiOperation(request,args,()=>host,async(_operation,input)=>{
   const run=spawnSync(python,['examples/rsi-protocol-v1/group_count.py'],{cwd:root,input:JSON.stringify(input),encoding:'utf8'});
   assert.equal(run.status,0,run.stderr);return JSON.parse(run.stdout);
  });
  assert.deepEqual(execution.result,fixtures.tasks[task].expected);
  assert.equal(execution.decision.payload.action,'execute');
  assert.deepEqual(execution.events.map(x=>x.payload.phase),['started','succeeded']);
  assert.equal(execution.events[0].payload.call_id,execution.events[1].payload.call_id);
  execution.events.forEach(validateRsiRecord);
 }
});

test('an unrelated intervening step does not grant or prevent a fresh local admission',()=>{
 const {request,host}=diagnosticHost();
 const unrelated={operation:'draft_title',result:'unrelated work'};
 assert.ok(unrelated.result);
 assert.equal(admissionDecision(request,host).payload.action,'execute');
 host.obligations.clear();
 assert.equal(admissionDecision(request,host).payload.reason,'semantic_obligation_missing');
});

const refusals=[
 ['task mismatch',(x)=>{x.request.payload.task_id='other-task';},'reject','task_mismatch'],
 ['state changed',(x)=>{x.host.stateVersion='new-state';},'handoff','state_changed'],
 ['component changed',(x)=>{x.host.versions.matcher.id='new-matcher';},'reject','component_version_changed'],
 ['no operator',(x)=>{x.host.operators.clear();},'handoff','no_applicable_operator'],
 ['uncertified operator',(x)=>{x.host.operators.get('group-count').certified=false;},'reject','operator_not_certified'],
 ['code changed',(x)=>{x.host.currentCodeSha256.set('group-count','0'.repeat(64));},'reject','operator_code_changed'],
 ['permission revoked',(x)=>{x.host.grant.revoked=true;},'reject','permission_denied'],
 ['wrong permission task',(x)=>{x.host.grant.taskId='other-task';},'reject','permission_denied'],
 ['semantic similarity alone',(x)=>{x.host.obligations.clear();},'handoff','semantic_obligation_missing'],
 ['different selected arguments',(x)=>{x.host.obligations.get(x.request.payload.obligation_ref).argumentsSha256='0'.repeat(64);},'handoff','semantic_obligation_changed'],
 ['dropped dependency',(x)=>{x.request.payload.dependencies=[];},'reject','dependency_binding_mismatch'],
 ['duplicate dependency',(x)=>{x.request.payload.dependencies.push(copy(x.request.payload.dependencies[0]));},'reject','dependency_binding_mismatch'],
 ['missing current evidence',(x)=>{x.host.currentEvidence.clear();},'handoff','current_evidence_missing'],
 ['historical evidence',(x)=>{x.host.currentEvidence.get('current-table').payload.role='training';},'reject','evidence_scope_mismatch'],
 ['evidence changed',(x)=>{x.host.currentEvidence.get('current-table').payload.sha256='0'.repeat(64);},'handoff','evidence_invalidated'],
 ['new counterevidence',(x)=>{x.host.currentEvidence.get('current-table').payload.status='invalidated';},'handoff','evidence_invalidated'],
 ['opaque Bash',(x)=>{const op=fixtureRecord('operator','opaque-bash');x.request.payload.operator_id=op.payload.id;x.host.operators.set(op.payload.id,{record:op,certified:true});},'handoff','opaque_operation'],
 ['external write',(x)=>{x.host.operators.get('group-count').record.payload.effect='external_write';},'reject','external_write_not_enabled'],
];
for(const [name,mutate,action,reason]of refusals)test(`${name}: no dispatch and an explicit reason`,async()=>{
 const x=diagnosticHost();mutate(x);let dispatches=0;
 const out=await executeRsiOperation(x.request,x.args,()=>x.host,async()=>{dispatches++;return {};});
 assert.equal(dispatches,0);assert.equal(out.events.length,0);
 assert.equal(out.decision.payload.action,action);assert.equal(out.decision.payload.reason,reason);
});

test('admission is rechecked after an earlier decision; mutated arguments never dispatch',async()=>{
 const x=diagnosticHost();assert.equal(admissionDecision(x.request,x.host).payload.action,'execute');
 x.host.grant.revoked=true;let dispatched=false;
 const denied=await executeRsiOperation(x.request,x.args,()=>x.host,async()=>{dispatched=true;});
 assert.equal(denied.decision.payload.reason,'permission_denied');assert.equal(dispatched,false);
 x.host.grant.revoked=false;
 const changed=await executeRsiOperation(x.request,{rows:[]},()=>x.host,async()=>{dispatched=true;});
 assert.equal(changed.decision.payload.reason,'arguments_changed');
 assert.equal(dispatched,false);
});

test('missing columns fail input validation before dispatch; tool failures preserve failed receipts',async()=>{
 const x=diagnosticHost(),args={rows:[{wrong_column:'x'}]},hash=bytesSha256(JSON.stringify(args));
 x.request.payload.arguments_sha256=hash;
 x.host.obligations.get(x.request.payload.obligation_ref).argumentsSha256=hash;
 let dispatched=false;
 const missing=await executeRsiOperation(x.request,args,()=>x.host,async()=>{dispatched=true;});
 assert.equal(missing.decision.payload.reason,'input_schema_invalid');
 assert.equal(dispatched,false);
 const y=diagnosticHost();
 for(const dispatch of [async()=>{throw Error('diagnostic failure');},async()=>({unexpected:true})]){
  const out=await executeRsiOperation(y.request,y.args,()=>y.host,dispatch);
  assert.equal(out.decision.payload.reason,'tool_execution_failed');
  assert.deepEqual(out.events.map(x=>x.payload.phase),['started','failed']);
  assert.equal(out.result,null);
 }
});

function updateContext(kind='rule_revision'){
 const c=fixtureRecord('candidate_patch','candidate-'+kind),r=fixtureRecord('validation_report');
 const candidateBytes=encode(c),candidateSha256=bytesSha256(candidateBytes);
 r.payload.candidate_id=c.payload.id;r.payload.candidate_sha256=candidateSha256;r.payload.base_version=copy(c.payload.base_version);
 const reportBytes=encode(r),reportSha256=bytesSha256(reportBytes);
 const host={versions:copy(fixtures.versions),candidateSha256,payloadSha256:c.payload.payload_sha256,
  reportSha256,approvedReports:new Map([[r.payload.id,reportSha256]]),
  evidence:new Map(['training-failure','validation-run'].map(id=>[id,fixtureRecord('evidence',id)])),
  diagnoses:new Map(['motif','matcher'].map(component=>['diagnosis-'+component,fixtureRecord('diagnosis','diagnosis-'+component)]))};
 return {c,r,candidateBytes,reportBytes,host};
}

test('all three patch kinds validate and publish/rollback only after successful adapter commits',async()=>{
 for(const kind of ['rule_revision','motif_split','matcher_code_patch']){
  const x=updateContext(kind);let current=copy(x.host.versions),commits=0;
  const adapter=async({expected,next})=>{assert.deepEqual(current,expected);current=copy(next);commits++;return {versions:current,manifestSha256:'a'.repeat(64)};};
  const receipt=await publishRsiUpdate(x.candidateBytes,x.reportBytes,()=>x.host,adapter);
  assert.equal(commits,1);assert.deepEqual(receipt.payload.next_versions,current);
  const publication=encode(receipt);
  const rollback=await rollbackRsiUpdate(publication,{current,publicationSha256:bytesSha256(publication)},'diagnostic regression',adapter);
  assert.equal(commits,2);assert.deepEqual(rollback.payload.restored_versions,x.host.versions);
 }
});

test('mutating bytes, stale parents, unapproved reports and evidence violations prevent publication',async()=>{
 const cases=[
  [x=>{x.candidateBytes+=' ';},'candidate_bytes_changed'],
  [x=>{x.reportBytes+=' ';},'report_bytes_changed'],
  [x=>{x.host.versions.motif.id='other-parent';},'stale_parent'],
  [x=>{x.host.versions.matcher.id='other-matcher';},'incompatible_components'],
  [x=>{x.host.payloadSha256='0'.repeat(64);},'patch_payload_changed'],
  [x=>{x.host.approvedReports.clear();},'not_independently_approved'],
  [x=>{x.host.diagnoses.clear();},'diagnosis_missing'],
  [x=>{x.host.diagnoses.get('diagnosis-motif').payload.component='matcher';},'diagnosis_binding_mismatch'],
  [x=>{x.host.evidence.get('training-failure').payload.role='test';},'frozen_test_prohibited'],
  [x=>{x.host.evidence.get('validation-run').payload.status='invalidated';},'evidence_changed'],
  [x=>{x.host.evidence.get('validation-run').payload.task_id='train-A';},'validation_evidence_scope'],
 ];
 for(const [change,reason]of cases){
  const x=updateContext();change(x);let commits=0;
  await assert.rejects(publishRsiUpdate(x.candidateBytes,x.reportBytes,()=>x.host,async()=>{commits++;}),new RegExp(reason));
  assert.equal(commits,0);
 }
});

test('validation cannot approve itself or substitute overlapping training tasks',()=>{
 const x=updateContext();x.r.payload.independent_task_ids=['train-A'];
 x.reportBytes=encode(x.r);x.host.reportSha256=bytesSha256(x.reportBytes);
 x.host.approvedReports.set(x.r.payload.id,x.host.reportSha256);
 assert.throws(()=>validateRsiUpdate(x.candidateBytes,x.reportBytes,x.host),/validation_task_overlap/);
});

test('failed compare-and-swap emits no success receipt; rollback requires the actual current version',async()=>{
 const x=updateContext();
 await assert.rejects(publishRsiUpdate(x.candidateBytes,x.reportBytes,()=>x.host,async()=>{throw Error('compare_and_swap_failed');}),/compare_and_swap_failed/);
 const receipt=await publishRsiUpdate(x.candidateBytes,x.reportBytes,()=>x.host,async({next})=>({versions:next,manifestSha256:'a'.repeat(64)}));
 let restore=false;
 const publication=encode(receipt),rollbackHost={current:x.host.versions,publicationSha256:bytesSha256(publication)};
 await assert.rejects(rollbackRsiUpdate(publication,rollbackHost,'wrong state',async()=>{restore=true;}),/current_version_mismatch/);
 assert.equal(restore,false);
 rollbackHost.current=receipt.payload.next_versions;
 receipt.payload.previous_versions.motif.id='unapproved-target';
 await assert.rejects(rollbackRsiUpdate(encode(receipt),rollbackHost,'forged target',async()=>{restore=true;}),/publication_changed/);
 assert.equal(restore,false);
});
