import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { FileJob } from '../src/adapters/file_workflow_job.ts';
import { createAcceptanceGuard } from '../src/adapters/file_acceptance_guard.ts';
function fixture(limits={}) {
  const root=mkdtempSync(join(tmpdir(),'sss-file-job-'));mkdirSync(join(root,'.local'));
  const file=join(root,'.local/task.json');writeFileSync(file,'{"grant":"fixed"}');
  const path=join(root,'.local/job.json'),job=new FileJob(root,path),delivery=join(root,'.local/delivery');
  job.apply('init',{task_file:file,delivery_root:delivery,execution_version_sha256:'a'.repeat(64),
    limits:{budget_usd:1,max_requests:2,max_steps:2,max_output:4000,max_repairs:2,...limits}});
  return {root,file,path,job,delivery};
}
const reservation={model:'deepseek-flash',upper_usd:0.2,request_sha256:'b'.repeat(64)};

test('uncapped durable tasks exceed old quotas and preserve accounting across reconstruction',()=>{
  const f=fixture({budget_usd:null,max_requests:null,max_steps:null,max_output:393216,max_repairs:null});
  for(let i=0;i<105;i++){
    const job=new FileJob(f.root,f.path),r=job.apply('reserve',reservation);assert.equal(r.admitted,true);
    job.apply('settle',{request_id:r.request_id,model:'deepseek-flash',observed_usd:0.1});
  }
  const state=new FileJob(f.root,f.path).load();
  assert.equal(state.requests,105);assert.equal(state.steps,105);assert.equal(state.spent_units,10500000000);
  assert.equal(state.status,'running');assert.equal(state.limits.budget_usd,null);
  f.job.apply('cancel');assert.equal(new FileJob(f.root,f.path).apply('reserve',reservation).admitted,false);
});

test('uncapped repair continues past two failures while cancellation and acceptance still govern it',async()=>{
  const f=fixture({budget_usd:null,max_requests:null,max_steps:null,max_repairs:null});
  const policy={kind:'file_management',max_repairs:null,project_root:f.root,python:'python3',task_file:f.file,delivery_root:f.delivery,archive_root:join(f.root,'.local/acceptance'),job_file:f.path};
  const signal=new AbortController().signal;
  for(let i=1;i<=4;i++)assert.equal((await createAcceptanceGuard(policy,async()=>({passed:false,errors:['repairable'],repairable:true})).stop([],signal)).repair,i);
  await createAcceptanceGuard(policy,async()=>({passed:true,errors:[]})).stop([],signal);
  assert.equal(f.job.load().status,'completed');assert.equal(f.job.load().repairs,4);
});
test('pending reservation and request limit survive cold reconstruction without reset',()=>{
  const f=fixture();f.job.apply('reserve',reservation);
  const restarted=new FileJob(f.root,f.path);assert.equal(restarted.load().spent_units,200000000);
  assert.equal(Object.keys(restarted.load().pending).length,1);restarted.apply('reserve',reservation);
  assert.equal(new FileJob(f.root,f.path).apply('reserve',reservation).admitted,false);
  assert.equal(restarted.load().status,'limit_exhausted');assert.throws(()=>restarted.apply('init',{}),/already exists/);
});
test('only complete settlement releases reservations and duplicate settlement fails',()=>{
  const f=fixture();const a=f.job.apply('reserve',reservation);
  f.job.apply('settle',{request_id:a.request_id,model:'deepseek-flash',observed_usd:null});
  assert.equal(f.job.load().spent_units,200000000);
  const b=f.job.apply('reserve',reservation);f.job.apply('settle',{request_id:b.request_id,model:'deepseek-flash',observed_usd:0.1});
  assert.equal(f.job.load().spent_units,300000000);
  assert.throws(()=>f.job.apply('settle',{request_id:b.request_id,model:'deepseek-flash',observed_usd:0}),/settled/);
});
test('cancel, revoke and execution changes cannot silently resume',()=>{
  for(const op of ['cancel','revoke']){const f=fixture();f.job.apply(op);assert.equal(f.job.apply('reserve',reservation).admitted,false);assert.throws(()=>f.job.apply('resume',{execution_version_sha256:'a'.repeat(64)}),/paused/);}
  const f=fixture();f.job.apply('pause');assert.throws(()=>f.job.apply('resume',{execution_version_sha256:'c'.repeat(64)}),/version/);
  f.job.apply('resume',{execution_version_sha256:'a'.repeat(64)});assert.equal(f.job.load().status,'running');
});
test('changed task grant and modified event chain are rejected; state cache cannot reset limits',()=>{
  const f=fixture();f.job.apply('reserve',reservation);writeFileSync(f.path,'{}');assert.equal(f.job.load().requests,1);
  writeFileSync(f.file,'{"grant":"expanded"}');assert.throws(()=>f.job.apply('reserve',reservation),/permission changed/);
  const event=join(f.path+'.events','000002.json');const row=JSON.parse(readFileSync(event));row.state.requests=0;writeFileSync(event,JSON.stringify(row));assert.throws(()=>f.job.load(),/integrity/);
});
test('two acceptance repair rounds survive reconstructed guards; third failure persists terminal status',async()=>{
  const f=fixture({max_requests:96,max_steps:96});const policy={kind:'file_management',max_repairs:2,project_root:f.root,python:'python3',task_file:f.file,delivery_root:f.delivery,archive_root:join(f.root,'.local/acceptance'),job_file:f.path};
  const evaluate=async()=>({passed:false,errors:['bad output'],repairable:true});const signal=new AbortController().signal;
  assert.equal((await createAcceptanceGuard(policy,evaluate).stop([],signal)).repair,1);
  assert.equal((await createAcceptanceGuard(policy,evaluate).stop([],signal)).repair,2);
  await assert.rejects(createAcceptanceGuard(policy,evaluate).stop([],signal),/bounded repair exhausted/);
  assert.equal(f.job.load().repairs,2);assert.equal(f.job.load().checks,3);assert.equal(f.job.load().status,'failed');
});
test('acceptance completion and aborted tasks persist lifecycle facts',async()=>{
  for(const cancelled of [false,true]){
    const f=fixture();const policy={kind:'file_management',max_repairs:2,project_root:f.root,python:'python3',task_file:f.file,delivery_root:f.delivery,archive_root:join(f.root,'.local/acceptance'),job_file:f.path};
    const controller=new AbortController();if(cancelled)controller.abort();
    await createAcceptanceGuard(policy,async()=>({passed:true,errors:[]})).stop([],controller.signal);
    assert.equal(f.job.load().status,cancelled?'cancelled':'completed');
  }
});
test('recorded MCP crash hands back one allocated repair; cold guard keeps the original round and limits',async()=>{
  const f=fixture({max_requests:96,max_steps:96});const policy={kind:'file_management',max_repairs:2,project_root:f.root,python:'python3',task_file:f.file,delivery_root:f.delivery,archive_root:join(f.root,'.local/acceptance'),job_file:f.path};
  const signal=new AbortController().signal;
  await assert.rejects(createAcceptanceGuard(policy,async()=>({passed:false,errors:['interrupted effect'],repairable:true,restart_required:true})).stop([],signal),/TASK_RECOVERY_RESTART_REQUIRED/);
  assert.equal(f.job.load().status,'running');assert.equal(f.job.load().repairs,1);assert.equal(f.job.load().checks,1);
  let round=-1;await createAcceptanceGuard(policy,async value=>{round=value;return {passed:true,errors:[]};}).stop([],signal);
  assert.equal(round,1);assert.equal(f.job.load().checks,2);assert.equal(f.job.load().repairs,1);assert.equal(f.job.load().status,'completed');
});
