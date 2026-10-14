/** Deterministic coordination/ownership diagnostics, never a model quality test. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync,readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve,sep} from 'node:path';
import {createComparisonService} from '../src/adapters/harless_comparison.ts';
const context={scene:'ppt',options:{slides:2},model:{model:'fixture'},input_sha256:'a'.repeat(64)};
function fixture(overrides={}){
 const root=mkdtempSync(join(tmpdir(),'harless-comparison-')),tasks=new Map(),created=[],prepared=[],submitted=[],cancelled=[],events=[];
 const host={owns:async id=>{if(!['a','b'].includes(id))throw Error('foreign session');},
  createLane:async(parent,scene,lane)=>{const id=parent+'-'+lane;created.push(id);return id;},
  prepare:async(t,lane,requestId)=>{prepared.push({parent:t.session_id,lane,requestId});const task_id=requestId;tasks.set(task_id,{status:'queued',answer:t.session_id+'/'+lane,stats:{model_requests:0},deliveries:[]});return{task_id};},
  submit:async id=>{submitted.push(id);tasks.get(id).status='completed';},inspect:async id=>tasks.get(id),
  cancel:async id=>{cancelled.push(id);tasks.get(id).status='cancelled';},publish:async(parent,view,request)=>events.push({parent,view,request}),...overrides};
 const service=createComparisonService(root,'account-a',host,{pollMs:1});
 const send=(session='a',requestId='one',text='question',ctx=context)=>service.admit(session,{requestId,content:[{type:'text',text}]},ctx);
 const wait=async(id,session='a')=>{for(let i=0;i<200;i++){const value=await service.view(session,id);if(['completed','failed','cancelled'].includes(value.status)){await new Promise(r=>setTimeout(r,3));return value;}await new Promise(r=>setTimeout(r,3));}throw Error('fixture timed out');};
 return{root,host,service,tasks,created,prepared,submitted,cancelled,events,send,wait,close(){service.dispose();const path=resolve(root);assert.ok(path.startsWith(resolve(tmpdir())+sep)&&path.includes('harless-comparison-'));rmSync(path,{recursive:true,force:true});}};
}
test('Concurrent send is idempotent; each user/chat and lane keeps a distinct multi-turn history',async()=>{
 const f=fixture();try{
  const [a,b]=await Promise.all([f.send(),f.send()]);assert.equal(a.comparison_id,b.comparison_id);await f.wait(a.comparison_id);
  assert.equal(f.submitted.length,2);assert.deepEqual(f.created,['a-baseline','a-motif']);
  await assert.rejects(f.send('a','one','changed'),/不能更改/);
  const second=await f.send('a','two','follow up');const v=await f.wait(second.comparison_id);assert.equal(f.created.length,2);assert.equal(v.lanes.baseline.session_id,'a-baseline');
  const other=await f.send('b','one');const bview=await f.wait(other.comparison_id,'b');assert.equal(bview.lanes.motif.answer,'b/motif');
  await assert.rejects(f.service.view('b',a.comparison_id),/找不到/);await assert.rejects(f.service.view('foreign',a.comparison_id),/foreign/);
  await assert.rejects(f.send('a','three','change scene',{...context,scene:'data'}),/需要新会话/);
  await assert.rejects(f.service.admit('a',{requestId:'files',content:[{type:'file',receiptId:'new'}]},context),/新增资料需要/);
 }finally{f.close();}
});
test('Partial failure retry preserves the successful lane; scores bind output and revision and survive restart',async()=>{
 let fail=true;const f=fixture({submit:async id=>{f.submitted.push(id);if(fail&&f.prepared.find(p=>p.requestId===id).lane==='motif')throw Error('injected');f.tasks.get(id).status='completed';}});
 try{
  const a=await f.send(),v=await f.wait(a.comparison_id);assert.equal(v.lanes.baseline.status,'completed');assert.equal(v.lanes.motif.status,'failed');
  await assert.rejects(f.service.rate('a',a.comparison_id,'baseline',5,0,v.lanes.baseline.output_sha256),/两侧都完成/);
  await assert.rejects(f.service.retry('a',a.comparison_id,'baseline'),/成功结果/);fail=false;
  await f.service.retry('a',a.comparison_id,'motif');const done=await f.wait(a.comparison_id);assert.equal(f.submitted.length,3);
  const rated=await f.service.rate('a',a.comparison_id,'baseline',4,0,done.lanes.baseline.output_sha256);assert.equal(rated.scores.baseline,4);
  await assert.rejects(f.service.rate('a',a.comparison_id,'motif',3,0,done.lanes.motif.output_sha256),/已更新/);
  await assert.rejects(f.service.rate('a',a.comparison_id,'motif',6,1,done.lanes.motif.output_sha256),/1–5/);
  await assert.rejects(f.service.rate('a',a.comparison_id,'motif',3,1,'foreign'),/已更新/);
  const final=await f.service.rate('a',a.comparison_id,'motif',3,1,done.lanes.motif.output_sha256);assert.equal(final.score_revision,2);
  f.service.dispose();const resumed=createComparisonService(f.root,'account-a',f.host,{pollMs:1});assert.deepEqual((await resumed.view('a',a.comparison_id)).scores,{baseline:4,motif:3});assert.equal(f.submitted.length,3);resumed.dispose();
  assert.throws(()=>createComparisonService(f.root,'another-account',f.host),/scope_mismatch/);
  assert.equal(readFileSync(join(f.root,'comparison-ratings.jsonl'),'utf8').trim().split('\n').length,2);
 }finally{f.close();}
});
test('Cancelling during asynchronous preparation never submits a late task or revives a queued lane',async()=>{
 let release;const gate=new Promise(r=>release=r);const f=fixture({prepare:async(t,lane,id)=>{await gate;f.tasks.set(id,{status:'queued'});return{task_id:id};}});
 try{const a=await f.send();await f.service.cancel('a',a.comparison_id);release();await new Promise(r=>setTimeout(r,20));const v=await f.service.view('a',a.comparison_id);assert.equal(v.status,'cancelled');assert.equal(f.submitted.length,0);assert.equal(f.cancelled.length,1);}finally{f.close();}
});
test('Initial publication failure makes no model submission and the same request can recover',async()=>{
 let fail=true;const f=fixture({publish:async(_parent,_view,request)=>{if(request&&fail)throw Error('injected persistence failure');}});
 try{await assert.rejects(f.send(),/persistence failure/);assert.equal(f.submitted.length,0);fail=false;const retry=await f.send();assert.equal((await f.wait(retry.comparison_id)).status,'completed');assert.equal(f.submitted.length,2);}finally{f.close();}
});
test('Budget exhaustion is terminal and never leaves the other lane polling indefinitely',async()=>{
 const f=fixture({submit:async id=>{f.submitted.push(id);f.tasks.get(id).status='budget_exhausted';}});
 try{const a=await f.send();const v=await f.wait(a.comparison_id);assert.equal(v.status,'failed');assert.equal(f.submitted.length,2);assert.match(v.lanes.baseline.failure,/预算/);assert.equal(v.scoring_available,false);}finally{f.close();}
});

test('Admitted upload references survive receipt retirement without being exposed or crossing requests',async()=>{
 const f=fixture();try{
  const file={name:'study.csv',bytes:12,sha256:'diagnostic-source'};
  const request={requestId:'uploaded',content:[{type:'text',text:'inspect'},{type:'file',receiptId:'receipt'}]};
  const a=await f.service.admit('a',request,{...context,source_files:{receipt:file}});
  await f.wait(a.comparison_id);
  assert.deepEqual(f.service.sourceFor('a','uploaded','receipt'),file);
  assert.equal(f.service.sourceFor('b','uploaded','receipt'),undefined);
  assert.equal(f.service.sourceFor('a','another-request','receipt'),undefined);
  assert.equal('source_files' in await f.service.view('a',a.comparison_id),false);
  const before=f.submitted.length;
  assert.equal((await f.service.admit('a',request,context)).comparison_id,a.comparison_id);
  assert.equal(f.submitted.length,before);
  f.service.dispose();const restored=createComparisonService(f.root,'account-a',f.host);
  assert.deepEqual(restored.sourceFor('a','uploaded','receipt'),file);restored.dispose();
 }finally{f.close();}
});
