import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,rmSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {createHash} from 'node:crypto';
const enabled={skip:!process.features?.typescript};

async function fixture(change=()=>{}){
 const {fileCostMetadata}=await import('../src/adapters/harless_file_scene.ts');
 const home=mkdtempSync(join(tmpdir(),'file-cost-metadata-')),session='original-file-run';
 const root=join(home,'state'),file=join(root,'records',session+'.json'),out=join(home,'runs',session);
 mkdirSync(join(root,'records'),{recursive:true});mkdirSync(out,{recursive:true});
 const metrics={upstream_requests:4,budget_accounted_usd:.125,session_id:session};
 const record={session_id:session,run_dir:out,metrics:{...metrics},upstream_requests:4,cost_usd:.125,
  accounting_complete:true,observed_usage_complete:true,
  cost_accounting:{requests:4,cost_upper_usd:.125,accounting_complete:true,observed_usage_complete:true,missing_observed_usage_requests:0}};
 change(record);const raw=Buffer.from(JSON.stringify(record));writeFileSync(file,raw);
 const task={out,metrics:{...metrics,continuous_rsi:{record_file:file,state_root:root,
  record_sha256:createHash('sha256').update(raw).digest('hex')}}};
 return {home,file,task,record,project:()=>fileCostMetadata(task,home),fileCostMetadata,
  close:()=>rmSync(home,{recursive:true,force:true})};
}

test('File public fee uses a scoped sealed complete observed-usage record',enabled,async()=>{
 const f=await fixture();try{
  assert.deepEqual(f.project(),{upstream_requests:4,cost_usd:.125,budget_accounted_usd:.125,cost_upper_usd:.125,
   usage_complete:true,missing_observed_usage_requests:0,cost_basis:'observed_usage'});
 }finally{f.close();}
});

test('retained unknown reservation stays visible as an upper amount, never a fee',enabled,async()=>{
 const f=await fixture(r=>{r.observed_usage_complete=false;r.cost_accounting.observed_usage_complete=false;r.cost_accounting.missing_observed_usage_requests=1;});
 try{const value=f.project();assert.equal(value.cost_usd,null);assert.equal(value.cost_upper_usd,.125);
  assert.equal(value.budget_accounted_usd,.125);assert.equal(value.usage_complete,false);
  assert.equal(value.missing_observed_usage_requests,1);assert.equal(value.cost_basis,'conservative_reservation');
 }finally{f.close();}
});

test('old metrics without an accounting record do not default to complete',enabled,async()=>{
 const f=await fixture();try{
  delete f.task.metrics.continuous_rsi;const value=f.project();
  assert.equal(value.cost_usd,null);assert.equal(value.usage_complete,false);assert.equal(value.missing_observed_usage_requests,null);
  assert.equal(value.cost_upper_usd,.125);
 }finally{f.close();}
});

test('zero requests and a zero accounted amount are a valid observed zero',enabled,async()=>{
 const f=await fixture();try{
  assert.equal(f.fileCostMetadata({metrics:{upstream_requests:0,budget_accounted_usd:0}},f.home).cost_usd,0);
  assert.equal(f.fileCostMetadata({metrics:{upstream_requests:0,budget_accounted_usd:0}},f.home).usage_complete,true);
  for(const metrics of [{upstream_requests:0,budget_accounted_usd:.1},{upstream_requests:0},{budget_accounted_usd:0}]){
   const value=f.fileCostMetadata({metrics},f.home);assert.equal(value.cost_usd,null);assert.equal(value.usage_complete,false);
  }
 }finally{f.close();}
});

for(const amount of [NaN,Infinity,-.1,true,'0.125'])test(`invalid File fee ${String(amount)} stays unknown`,enabled,async()=>{
 const f=await fixture();try{f.task.metrics.budget_accounted_usd=amount;const value=f.project();
  assert.equal(value.cost_usd,null);assert.equal(value.cost_upper_usd,null);assert.equal(value.usage_complete,false);
 }finally{f.close();}
});
for(const requests of [NaN,Infinity,-1,true,'4',1.5])test(`invalid request count ${String(requests)} cannot prove fee`,enabled,async()=>{
 const f=await fixture();try{f.task.metrics.upstream_requests=requests;const value=f.project();
  assert.equal(value.upstream_requests,null);assert.equal(value.cost_usd,null);assert.equal(value.usage_complete,false);
 }finally{f.close();}
});

for(const [name,change] of [
 ['missing observed flag',r=>{delete r.cost_accounting.observed_usage_complete;}],
 ['missing completeness flag',r=>{delete r.accounting_complete;}],
 ['foreign session',r=>{r.session_id='another-run';}],
 ['foreign output',r=>{r.run_dir=join(r.run_dir,'other');}],
 ['wrong request count',r=>{r.cost_accounting.requests=3;}],
 ['invalid missing count',r=>{r.cost_accounting.missing_observed_usage_requests=-1;}],
 ['inconsistent cost',r=>{r.cost_accounting.cost_upper_usd=.2;}],
])test(`unverified sealed File accounting: ${name}`,enabled,async()=>{
 const f=await fixture(change);try{assert.equal(f.project().cost_usd,null);assert.equal(f.project().usage_complete,false);}finally{f.close();}
});

test('changed sealed bytes, wrong scope and absent files remain unknown without paths in API',enabled,async()=>{
 const f=await fixture();try{
  const foreign=f.fileCostMetadata(f.task,join(f.home,'different-account'));
  assert.equal(foreign.cost_usd,null);assert.equal(foreign.usage_complete,false);
  writeFileSync(f.file,'{}');assert.equal(f.project().cost_usd,null);
  rmSync(f.file);const absent=f.project();assert.equal(absent.cost_usd,null);
  assert.equal(JSON.stringify(absent).includes(f.home),false);assert.equal(JSON.stringify(absent).includes('record_file'),false);
 }finally{f.close();}
});
