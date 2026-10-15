/** Deterministic coordination/ownership diagnostics, never a model quality test. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync,readFileSync,writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve,sep} from 'node:path';
import {createHash} from 'node:crypto';
import {createComparisonService} from '../src/adapters/harless_comparison.ts';
import {REPORT_ANSWER_BINDING} from '../src/adapters/harless_report_answer.ts';
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
  assert.equal(f.service.parentFor('a-motif'),'a');assert.equal(f.service.parentFor('foreign'),null);
  await assert.rejects(f.send('a','one','changed'),/不能更改/);
  const second=await f.send('a','two','follow up');const v=await f.wait(second.comparison_id);assert.equal(f.created.length,2);assert.equal(v.lanes.baseline.session_id,'a-baseline');
  const other=await f.send('b','one');const bview=await f.wait(other.comparison_id,'b');assert.equal(bview.lanes.motif.answer,'b/motif');
  await assert.rejects(f.service.view('b',a.comparison_id),/找不到/);await assert.rejects(f.service.view('foreign',a.comparison_id),/foreign/);
  await assert.rejects(f.send('a','three','change scene',{...context,scene:'data'}),/需要新会话/);
  const uploaded = await f.service.admit('a',{requestId:'files',content:[{type:'file',receiptId:'new'}]},context);
  assert.equal((await f.wait(uploaded.comparison_id)).status,'completed');
  const stored = JSON.parse(readFileSync(join(f.root,'comparisons.json'))).turns.at(-1);
  assert.match(stored.prior_context.baseline, /a\/baseline/);
  assert.doesNotMatch(stored.prior_context.baseline, /a\/motif|b\/baseline/);
  await assert.rejects(f.service.admit('a',{requestId:'changed-files',content:[{type:'file',receiptId:'other'}]},context),/更换已绑定资料需要/);
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

test('First uploads retain historical lane protection and bounded, valid per-lane context',async()=>{
 let generation=0; const f=fixture({createLane:async(parent,scene,lane)=>parent+'-'+lane+'-'+(++generation)});
 try {
  const initial=await f.send('a','discuss','x'.repeat(40000)), before=await f.wait(initial.comparison_id);
  const admitted=await f.service.admit('a',{requestId:'upload',content:[{type:'file',receiptId:'source'}]},context);
  const after=await f.wait(admitted.comparison_id);
  assert.notEqual(before.lanes.baseline.session_id,after.lanes.baseline.session_id);
  for(const lane of Object.values(before.lanes)) {
   assert.equal(f.service.isLane(lane.session_id),true);
   assert.equal(f.service.parentFor(lane.session_id),'a');
  }
  const stored=JSON.parse(readFileSync(join(f.root,'comparisons.json'))).turns.at(-1);
  assert.ok(stored.prior_context.baseline.length<32000);
  assert.equal(JSON.parse(stored.prior_context.baseline)[0].assistant,'a/baseline');
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

test('Old budget failure recovers only verified downloads without rerunning or allowing scores',async()=>{
 const f=fixture({submit:async id=>{f.submitted.push(id);f.tasks.get(id).status='budget_exhausted';}});
 try{
  const a=await f.send(),first=await f.wait(a.comparison_id);assert.equal(first.status,'failed');
  f.service.dispose();let inspected=0;
  const host={...f.host,inspect:async(id,context)=>{inspected++;if(inspected<=2)throw Error('temporary availability failure');assert.equal(context.turn.id,a.comparison_id);return{...f.tasks.get(id),deliveries:[{id:'verified-pdf',sha256:'a'.repeat(64)}]};}};
  const resumed=createComparisonService(f.root,'account-a',host,{pollMs:1});
  await assert.rejects(resumed.view('foreign',a.comparison_id),/foreign/);assert.equal(inspected,0);
  assert.equal((await resumed.view('a',a.comparison_id)).lanes.motif.artifacts.length,0);
  const recovered=await resumed.view('a',a.comparison_id);assert.equal(recovered.status,'failed');assert.equal(recovered.scoring_available,false);
  assert.equal(recovered.lanes.motif.artifacts.length,1);assert.match(recovered.lanes.motif.failure,/交付校验/);
  await resumed.view('a',a.comparison_id);assert.equal(inspected,4);assert.equal(f.submitted.length,2);
  await assert.rejects(resumed.rate('a',a.comparison_id,'motif',5,0,recovered.lanes.motif.output_sha256),/两侧都完成/);
  resumed.dispose();
 }finally{f.close();}
});

test('Completed text without a delivered report stays explicit; old verified delivery repair invalidates stale rating',async()=>{
 const f=fixture();try{
  const a=await f.send('a','one','make a report',{...context,scene:'research-data-analysis'});
  const first=await f.wait(a.comparison_id);
  assert.equal(first.lanes.baseline.status,'completed');
  assert.equal(first.lanes.baseline.delivery_status,'not_delivered');
  assert.match(first.lanes.baseline.delivery_message,/不表示报告已成功生成/);
  await f.service.rate('a',a.comparison_id,'baseline',2,0,first.lanes.baseline.output_sha256);
  f.service.dispose();let inspected=0;
  const resumed=createComparisonService(f.root,'account-a',{...f.host,inspect:async(id,context)=>{
   inspected++;assert.equal(context.recoverMissing,true);
   return{...f.tasks.get(id),deliveries:context.lane==='baseline'?[{id:'verified-pdf',sha256:'b'.repeat(64),verification:'data-report-delivery-v1'}]:[]};
  }},{pollMs:1});
  const repaired=await resumed.view('a',a.comparison_id);
  assert.equal(repaired.status,'completed');assert.equal(repaired.lanes.baseline.failure,undefined);
  assert.equal(repaired.lanes.baseline.delivery_status,'available');
  assert.deepEqual(repaired.scores,{});assert.equal(repaired.score_revision,2);
  await assert.rejects(resumed.rate('a',a.comparison_id,'baseline',5,1,first.lanes.baseline.output_sha256),/已更新/);
  await resumed.view('a',a.comparison_id);assert.equal(inspected,2);assert.equal(f.submitted.length,2);
  resumed.dispose();
 }finally{f.close();}
});

test('Legacy data drafts fail closed during recovery outages and are removed without rerunning paid work',async()=>{
 const f=fixture();try{
  const a=await f.send('a','one','make a report',{...context,scene:'research-data-analysis'});
  await f.wait(a.comparison_id);f.service.dispose();
  const path=join(f.root,'comparisons.json'),state=JSON.parse(readFileSync(path,'utf8'));
  state.turns[0].lanes.motif.artifacts=[{id:'old-unverified-draft',sha256:'c'.repeat(64)}];
  state.turns[0].scores.motif=5;writeFileSync(path,JSON.stringify(state));
  let available=false;
  const resumed=createComparisonService(f.root,'account-a',{...f.host,inspect:async id=>{
   if(!available)throw Error('temporary budget connection loss');return{...f.tasks.get(id),deliveries:[]};
  }},{pollMs:1});
  const duringOutage=await resumed.view('a',a.comparison_id);
  assert.deepEqual(duringOutage.lanes.motif.artifacts,[],'unverified cached downloads must not leak when inspection fails');
  available=true;const repaired=await resumed.view('a',a.comparison_id);
  assert.deepEqual(repaired.lanes.motif.artifacts,[]);assert.equal(repaired.lanes.motif.delivery_status,'not_delivered');
  assert.equal(repaired.scores.motif,undefined);assert.equal(repaired.score_revision,1);
  assert.equal(JSON.parse(readFileSync(path,'utf8')).turns[0].lanes.motif.artifacts.length,0);
  assert.equal(f.submitted.length,2);resumed.dispose();
 }finally{f.close();}
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

test('Historic report display binds the exact original answer, preserving files and invalidating stale scores without reruns',async()=>{
 const raw='estimate={{estimate}}',artifact={id:'prior-verified',sha256:'f'.repeat(64),verification:'data-report-delivery-v1'};
 const f=fixture({submit:async id=>{f.submitted.push(id);Object.assign(f.tasks.get(id),{status:'completed',answer:raw,deliveries:[artifact]});}});
 try{
  const admitted=await f.send('a','one','report',{...context,scene:'research-data-analysis'}),first=await f.wait(admitted.comparison_id);
  await f.service.rate('a',admitted.comparison_id,'baseline',4,0,first.lanes.baseline.output_sha256);f.service.dispose();
  let inspected=0;
  const resumed=createComparisonService(f.root,'account-a',{...f.host,inspect:async(id,ctx)=>{
   inspected++;assert.equal(ctx.recoverMissing,true);
   // A later turn may carry a verified file; rebuilding answer presentation
   // must not replace that file using this task's strict new-delivery scan.
   return{...f.tasks.get(id),deliveries:[],answer_display:'estimate=1.34',answer_binding:{version:REPORT_ANSWER_BINDING,
    source_answer_sha256:createHash('sha256').update(ctx.lane==='baseline'?raw:'different original').digest('hex'),status:'bound'}};
  }},{pollMs:1});
  await assert.rejects(resumed.view('foreign',admitted.comparison_id),/foreign/);assert.equal(inspected,0);
  const repaired=await resumed.view('a',admitted.comparison_id);
  assert.equal(repaired.lanes.baseline.answer,raw);assert.equal(repaired.lanes.baseline.answer_display,'estimate=1.34');
  assert.deepEqual(repaired.lanes.baseline.artifacts,[artifact]);assert.notEqual(repaired.lanes.baseline.output_sha256,first.lanes.baseline.output_sha256);
  assert.equal(repaired.lanes.motif.answer_display,undefined,'display for a different raw answer is rejected');
  assert.deepEqual(repaired.scores,{});assert.equal(repaired.score_revision,2);assert.equal(f.submitted.length,2);
  await assert.rejects(resumed.rate('a',admitted.comparison_id,'baseline',5,1,first.lanes.baseline.output_sha256),/已更新/);
  await resumed.view('a',admitted.comparison_id);assert.equal(inspected,2);resumed.dispose();
  const restored=createComparisonService(f.root,'account-a',f.host);const cached=await restored.view('a',admitted.comparison_id);
  assert.equal(cached.lanes.baseline.answer_display,'estimate=1.34');assert.equal(cached.lanes.baseline.answer,raw);restored.dispose();
 }finally{f.close();}
});

test('A persisted unresolved report display is audited once at terminal recovery and ratings change only with the visible result',async()=>{
 const raw='estimate={{estimate}}',artifact={id:'verified-file',sha256:'e'.repeat(64),verification:'data-report-delivery-v1'};
 const source=createHash('sha256').update(raw).digest('hex');
 const pending={answer_display:'estimate=【未绑定：estimate】',answer_binding:{version:REPORT_ANSWER_BINDING,source_answer_sha256:source,status:'unresolved',reason:'no_verified_task_evidence'}};
 const f=fixture({submit:async id=>{f.submitted.push(id);Object.assign(f.tasks.get(id),{status:'completed',answer:raw,deliveries:[artifact],...pending});}});
 try{
  const admitted=await f.send('a','unresolved','report',{...context,scene:'research-data-analysis'}),first=await f.wait(admitted.comparison_id);
  const rated=await f.service.rate('a',admitted.comparison_id,'baseline',4,0,first.lanes.baseline.output_sha256);f.service.dispose();
  let inspected=0;
  const unchanged=createComparisonService(f.root,'account-a',{...f.host,inspect:async(id,ctx)=>{inspected++;assert.equal(ctx.recoverMissing,true);return f.tasks.get(id);}});
  const still=await unchanged.view('a',admitted.comparison_id);
  assert.equal(inspected,2,'version alone cannot suppress a terminal audit of unresolved values');
  assert.deepEqual(still.scores,{baseline:4});assert.equal(still.score_revision,rated.score_revision);
  await unchanged.view('a',admitted.comparison_id);assert.equal(inspected,2,'one audit per attempt per process');unchanged.dispose();
  const recovered=createComparisonService(f.root,'account-a',{...f.host,inspect:async(id,ctx)=>({...f.tasks.get(id),
   answer_display:'estimate=1.34',answer_binding:{version:REPORT_ANSWER_BINDING,source_answer_sha256:ctx.lane==='baseline'?source:'foreign-answer',status:'bound'}})});
  const bound=await recovered.view('a',admitted.comparison_id);
  assert.equal(bound.lanes.baseline.answer,raw);assert.equal(bound.lanes.baseline.answer_display,'estimate=1.34');
  assert.equal(bound.lanes.motif.answer_display,pending.answer_display,'mismatched raw-answer proof stays rejected');
  assert.deepEqual(bound.lanes.baseline.artifacts,[artifact]);assert.deepEqual(bound.scores,{});
  assert.equal(bound.score_revision,rated.score_revision+1);assert.equal(f.submitted.length,2,'recovery never submits new model tasks');
  recovered.dispose();
 }finally{f.close();}
});
