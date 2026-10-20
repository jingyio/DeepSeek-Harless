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

test('Data exposes verified generic code files without exposing uncertified report drafts',async()=>{
 const f=fixture({submit:async id=>{const task=f.tasks.get(id);task.status='completed';task.deliveries=[
  {id:'code',name:'outputs/code/result.json',verification:'code-output-v1'},
  {id:'draft',name:'outputs/report/draft.pdf'},
  {id:'forged',name:'outputs/report/unverified.pdf',verification:'code-output-v1'}];}});
 try{const sent=await f.send('a','code','calculate',{...context,scene:'research-data-analysis'});const result=await f.wait(sent.comparison_id);
  assert.deepEqual(result.lanes.baseline.artifacts.map(row=>row.id),['code']);assert.equal(result.lanes.baseline.delivery_status,'available');
 }finally{f.close();}
});
function fixture(overrides={}){
 const root=mkdtempSync(join(tmpdir(),'harless-comparison-')),tasks=new Map(),created=[],prepared=[],submitted=[],cancelled=[],events=[];
 const host={owns:async id=>{if(!['a','b'].includes(id))throw Error('foreign session');},
  createLane:async(parent,scene,lane)=>{const id=parent+'-'+lane;created.push(id);return id;},
  prepare:async(t,lane,requestId)=>{prepared.push({parent:t.session_id,lane,requestId});const task_id=requestId;tasks.set(task_id,{status:'queued',answer:t.session_id+'/'+lane,stats:{model_requests:0},deliveries:[]});return{task_id};},
  submit:async id=>{submitted.push(id);tasks.get(id).status='completed';},inspect:async id=>tasks.get(id),
  cancel:async id=>{cancelled.push(id);tasks.get(id).status='cancelled';},publish:async(parent,view,request)=>{
   if(request)assert.deepEqual(view,JSON.parse(JSON.stringify(view)),'initial native user/message metadata must be pure JSON');
   events.push({parent,view,request});},...overrides};
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
  const changed=await f.send('a','three','change scene',{...context,scene:'data'});
  assert.equal((await f.wait(changed.comparison_id)).scene,'data');
  const uploaded = await f.service.admit('a',{requestId:'files',content:[{type:'file',receiptId:'new'}]},context);
  assert.equal((await f.wait(uploaded.comparison_id)).status,'completed');
  const stored = JSON.parse(readFileSync(join(f.root,'comparisons.json'))).turns.at(-1);
  assert.match(stored.prior_context.baseline, /a\/baseline/);
  assert.doesNotMatch(stored.prior_context.baseline, /a\/motif|b\/baseline/);
  const replaced=await f.service.admit('a',{requestId:'changed-files',content:[{type:'file',receiptId:'other'}]},context);
  assert.equal((await f.wait(replaced.comparison_id)).status,'completed');
 }finally{f.close();}
});

test('legacy lane contexts rotate once and preserve originals, dialogue and existing observations without public leakage',async()=>{
 const f=fixture();let resumed;
 try{
  const first=await f.send();await f.wait(first.comparison_id);f.service.dispose();
  const path=join(f.root,'comparisons.json'),state=JSON.parse(readFileSync(path,'utf8'));
  delete state.threads.a.context_version;writeFileSync(path,JSON.stringify(state));
  const prepared=[];
  resumed=createComparisonService(f.root,'account-a',{...f.host,prepare:async(turn,lane,id)=>{
   prepared.push(structuredClone(turn));return f.host.prepare(turn,lane,id);
  }},{pollMs:1});
  const input={requestId:'cleaned-followup',content:[{type:'text',text:'你好'}]},evidence='Preserved exact page observation';
  const next=await resumed.admit('a',input,{...context,prior_sources:[{name:'original.pdf',sha256:'a'.repeat(64)}],
   prior_evidence_by_lane:{baseline:[evidence],motif:['Independent Motif observation']}});
  for(let i=0;i<100&&(await resumed.view('a',next.comparison_id)).status!=='completed';i++)await new Promise(r=>setTimeout(r,3));
  assert.equal(prepared.length,2);assert.deepEqual(prepared[0].input,input.content);
  assert.match(prepared[0].prior_context.baseline,/a\/baseline/);
  assert.deepEqual(prepared[0].prior_evidence.baseline,[evidence]);
  assert.deepEqual(prepared[0].prior_sources,[{name:'original.pdf',sha256:'a'.repeat(64)}]);
  assert.doesNotMatch(JSON.stringify(await resumed.view('a',next.comparison_id)),/Preserved exact page observation|original\.pdf/);
  assert.equal(JSON.parse(readFileSync(path,'utf8')).threads.a.context_version,2);
  const before=f.created.length;await resumed.admit('a',{requestId:'same-clean-lane',content:[{type:'text',text:'next'}]},context);
  assert.equal(f.created.length,before,'ordinary followups keep the repaired lane');
 }finally{resumed?.dispose();f.close();}
});

test('all historical execution sources remain discoverable after more than six rotations',async()=>{
 let sequence=0;
 const f=fixture({createLane:async(parent,_scene,lane)=>parent+'-'+lane+'-'+(++sequence)});
 try{
  const native=Array.from({length:20},(_,index)=>({user:'native-'+index,assistant:'native answer '+index}));
  let latest;
  for(let round=0;round<13;round++){
   const sent=await f.send('a','long-'+round,'scene question '+round,{...context,scene:round%2?'paper':'ppt',prior_context:native});
   latest=await f.wait(sent.comparison_id);
  }
  assert.equal(f.service.contextSessions('a').baseline.length,13);
  assert.equal(f.service.contextSessions('a').motif.length,13);
  assert.deepEqual(f.service.contextSessions('b'),{baseline:[],motif:[]});
  const stored=JSON.parse(readFileSync(join(f.root,'comparisons.json'))).turns.at(-1);
  const rows=JSON.parse(stored.prior_context.baseline);
  assert.equal(rows.length,32);assert.equal(rows[0].user,'native-0');assert.equal(rows.at(-1).user,'scene question 11');
  assert.equal((stored.prior_context.baseline.match(/native-0/g)??[]).length,1);
  assert.equal(latest.status,'completed');
 }finally{f.close();}
});

test('paired lanes start together while another turn waits for both and same-chat overlap stays rejected',async()=>{
 const f=fixture({submit:async id=>{f.submitted.push(id);f.tasks.get(id).status='running';}});
 try{
  const first=await f.send();
  for(let i=0;i<50&&f.submitted.length<2;i++)await new Promise(r=>setTimeout(r,2));
  assert.equal(f.submitted.length,2,'neither lane waits for the other answer');
  assert.ok([...f.tasks.values()].every(task=>task.status==='running'));
  await assert.rejects(f.send('a','overlap'),/仍在运行/);
  const other=await f.send('b','next');
  await new Promise(r=>setTimeout(r,5));assert.equal(f.submitted.length,2);
  f.tasks.get(f.submitted[0]).status='completed';
  await new Promise(r=>setTimeout(r,5));assert.equal(f.submitted.length,2,'the next turn waits for the remaining lane');
  f.tasks.get(f.submitted[1]).status='completed';await f.wait(first.comparison_id);
  for(let i=0;i<50&&f.submitted.length<4;i++)await new Promise(r=>setTimeout(r,2));
  assert.equal(f.submitted.length,4);
  for(const task of f.tasks.values())task.status='completed';await f.wait(other.comparison_id,'b');
 }finally{f.close();}
});

test('a headerless host explicitly retains sequential execution',async()=>{
 const f=fixture({parallel:()=>false,submit:async id=>{f.submitted.push(id);f.tasks.get(id).status='running';}});
 try{
  const sent=await f.send();
  for(let i=0;i<50&&!f.submitted.length;i++)await new Promise(r=>setTimeout(r,2));
  assert.equal(f.submitted.length,1);f.tasks.get(f.submitted[0]).status='completed';
  for(let i=0;i<50&&f.submitted.length<2;i++)await new Promise(r=>setTimeout(r,2));
  assert.equal(f.submitted.length,2);f.tasks.get(f.submitted[1]).status='completed';await f.wait(sent.comparison_id);
 }finally{f.close();}
});

test('header-routed independent conversations run concurrently and cancellation affects only its own lanes',async()=>{
 const f=fixture({concurrent:()=>true,submit:async id=>{f.submitted.push(id);f.tasks.get(id).status='running';}});
 try{
  const first=await f.send('a','parallel-a'),second=await f.send('b','parallel-b');
  for(let i=0;i<100&&f.submitted.length<4;i++)await new Promise(r=>setTimeout(r,2));
  assert.equal(f.submitted.length,4,'a second conversation does not wait for either first-conversation lane');
  assert.deepEqual(await f.send('b','parallel-b'),second,'retry cannot create extra runs');
  await assert.rejects(f.send('a','overlap'),/仍在运行/);
  await f.service.cancel('a',first.comparison_id);
  const other=await f.service.view('b',second.comparison_id);
  assert.ok(Object.values(other.lanes).every(l=>f.tasks.get(l.task_id).status==='running'));
  for(const task of f.tasks.values())if(task.status==='running')task.status='completed';
  assert.equal((await f.wait(second.comparison_id,'b')).status,'completed');
 }finally{f.close();}
});

test('a lost readiness hint retries preparation without creating a failed lane or duplicate submission',async()=>{
 let attempts=0;
 const f=fixture({prepare:async(t,lane,requestId)=>{
  attempts++;if(attempts<4)return{deferred:true};
  f.prepared.push({lane,requestId});f.tasks.set(requestId,{status:'queued',answer:'ready',deliveries:[]});return{task_id:requestId};
 }});
 try{const sent=await f.send();const done=await f.wait(sent.comparison_id);
  assert.equal(done.status,'completed');assert.equal(f.prepared.length,2);assert.equal(f.submitted.length,2);
  assert.equal(new Set(f.submitted).size,2);assert.equal(attempts,5);
 }finally{f.close();}
});

test('durable ratings return without waiting for native publication and complete snapshots need no cold backend inspection',async()=>{
 let block=false,release;const gate=new Promise(resolve=>release=resolve);
 const f=fixture({publish:async()=>{if(block)await gate;},submit:async id=>{f.submitted.push(id);Object.assign(f.tasks.get(id),{status:'completed',trace:[],messages:[]});}});
 let restored;
 try{
  const sent=await f.send(),done=await f.wait(sent.comparison_id);block=true;
  let response;const rate=f.service.rate('a',sent.comparison_id,'baseline',4,0,done.lanes.baseline.output_sha256).then(value=>response=value);
  for(let i=0;i<50&&!response;i++)await new Promise(r=>setTimeout(r,2));
  assert.equal(response?.scores.baseline,4,'native UI publication cannot block the score response');await rate;
  assert.equal(JSON.parse(readFileSync(join(f.root,'comparisons.json'),'utf8')).turns[0].scores.baseline,4);
  f.service.dispose();restored=createComparisonService(f.root,'account-a',{...f.host,inspect:async()=>{throw Error('complete snapshot must not read a budget service');}});
  assert.equal((await restored.view('a',sent.comparison_id)).scores.baseline,4);
 }finally{release();restored?.dispose();f.close();}
});

test('a crash before the delta checkpoint recovers in a durable newer epoch even with a lower revision',async()=>{
 const listeners=new Map();let resumed;
 const f=fixture({submit:async id=>{f.submitted.push(id);f.tasks.get(id).status='running';},
  subscribe:(id,listener)=>{listeners.set(id,listener);return()=>listeners.delete(id);}});
 try{
  const sent=await f.send();
  for(let i=0;i<50&&listeners.size<2;i++)await new Promise(r=>setTimeout(r,2));
  assert.equal(listeners.size,2);
  const path=join(f.root,'comparisons.json'),lastDurable=readFileSync(path,'utf8');
  const [id,notify]=[...listeners][0];
  for(let i=0;i<12;i++)notify({...f.tasks.get(id),answer:'a'.repeat(i+1)});
  const before=f.service.snapshot('a',sent.comparison_id);
  assert.ok(before.snapshot_revision>JSON.parse(lastDurable).revision);
  // Disposal flushes intentionally, so restore the pre-crash disk bytes to
  // model abrupt termination before the pending 250 ms checkpoint was written.
  f.service.dispose();await new Promise(r=>setTimeout(r,5));writeFileSync(path,lastDurable);
  resumed=createComparisonService(f.root,'account-a',f.host,{pollMs:1});
  const after=resumed.snapshot('a',sent.comparison_id),persisted=JSON.parse(readFileSync(path,'utf8'));
  assert.equal(after.status,'failed');assert.equal(after.snapshot_epoch,before.snapshot_epoch+1);
  assert.ok(after.snapshot_revision<before.snapshot_revision);
  assert.equal(persisted.snapshot_epoch,after.snapshot_epoch,'the new epoch must be on disk before any snapshot can be emitted');
  assert.equal(f.submitted.length,2,'recovery never retries paid execution');
 }finally{resumed?.dispose();f.close();}
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

for(const effort of ['off','low','high','max'])test(`reasoning ${effort} is immutable for both lanes and the same request cannot change its strength`, async () => {
 const seen=[]; const f=fixture({prepare:async(t,lane,requestId)=>{
  seen.push({lane,effort:t.reasoning_effort});f.tasks.set(requestId,{status:'queued',answer:lane,deliveries:[]});return{task_id:requestId};
 }});
 try {
  const sent=await f.send('a','reasoning','question',{...context,reasoning_effort:effort});
  await f.wait(sent.comparison_id);
  assert.deepEqual(seen,[{lane:'baseline',effort},{lane:'motif',effort}]);
  const stored=JSON.parse(readFileSync(join(f.root,'comparisons.json'),'utf8')).turns[0];
  assert.equal(stored.reasoning_effort,effort);
  await assert.rejects(f.send('a','reasoning','question',{...context,reasoning_effort:effort==='off'?'high':'off'}),/不能更改/);
  assert.equal((await f.send('a','reasoning','question',{...context,reasoning_effort:effort})).comparison_id,sent.comparison_id);
  assert.equal(f.submitted.length,2);
 }finally{f.close();}
});

test('legacy Off admissions remain idempotent after restart and cannot be upgraded to On', async () => {
 const f=fixture(); let resumed;
 try {
  const sent=await f.send();await f.wait(sent.comparison_id);f.service.dispose();
  const path=join(f.root,'comparisons.json'),state=JSON.parse(readFileSync(path,'utf8'));
  delete state.turns[0].reasoning_effort;
  const content=[{type:'text',text:'question'}];
  state.turns[0].fingerprint=createHash('sha256').update(JSON.stringify([content,context.scene,context.options,context.model])).digest('hex');
  writeFileSync(path,JSON.stringify(state));resumed=createComparisonService(f.root,'account-a',f.host,{pollMs:1});
  assert.equal((await resumed.admit('a',{requestId:'one',content},context)).comparison_id,sent.comparison_id);
  await assert.rejects(resumed.admit('a',{requestId:'one',content},{...context,reasoning_effort:'high'}),/不能更改/);
  assert.equal(f.submitted.length,2);
 }finally{resumed?.dispose();f.close();}
});

test('known preparation errors give safe actionable messages and are not report delivery failures', async () => {
 for (const [code, expected] of [
  ['data_input_format_unsupported', /未能读取附件，请重新发送/],
  ['data_requires_csv_or_tsv', /未能读取附件，请重新发送/],
  ['data_text_requires_utf8', /另存为 UTF-8/],
  ['scene_input_limit', /本轮和继承的历史附件/],
  ['file_bytes_changed', /重新上传当前版本/],
 ]) {
  const error = code === 'scene_input_limit' ? Object.assign(Error('/home/private/secret'), {code}) : Error(code);
  const f = fixture({prepare:async()=>{throw error;}});
  try {
   const sent=await f.send('a','one','report',{...context,scene:'research-data-analysis'}),view=await f.wait(sent.comparison_id);
   assert.equal(view.status,'failed');assert.equal(view.scoring_available,false);assert.equal(f.submitted.length,0);
   for(const lane of Object.values(view.lanes)) {
    assert.match(lane.failure,expected);assert.equal(lane.failure_stage,'preparation');assert.equal(lane.delivery_status,'not_started');
    assert.match(lane.delivery_message,/尚未开始执行/);assert.doesNotMatch(JSON.stringify(lane),/private|secret|交付校验|另一侧结果已保留/);
   }
  }finally{f.close();}
 }
});

test('unknown preparation diagnostics stay private while successful opposite results survive', async () => {
 const secret='data_requires_csv_or_tsv /home/private/source.csv\nstack: connection failure';
 const f=fixture({prepare:async(t,lane,id)=>{
  if(lane==='baseline')throw Object.assign(Error(secret),{code:'__proto__'});
  f.tasks.set(id,{status:'queued',answer:'另一侧已完成',deliveries:[]});return{task_id:id};
 }});
 try {
  const sent=await f.send(),view=await f.wait(sent.comparison_id);
  assert.equal(view.lanes.baseline.delivery_status,'not_started');assert.match(view.lanes.baseline.failure,/任务未能启动/);
  assert.doesNotMatch(JSON.stringify(view),/private|stack|source.csv|data_requires|__proto__|另一侧结果已保留/);
  assert.equal(view.lanes.motif.status,'completed');assert.equal(view.lanes.motif.answer,'另一侧已完成');assert.equal(f.submitted.length,1);
  assert.match(readFileSync(join(f.root,'comparison-errors.jsonl'),'utf8'),/private/,'private diagnostics remain available to the operator');
 }finally{f.close();}
});

test('historic unadmitted failures render as not started without rewriting results or inventing delivery checks', async () => {
 const f=fixture({prepare:async()=>{throw Error('old_unknown');}});let resumed;
 try {
  const sent=await f.send('a','one','report',{...context,scene:'research-data-analysis'});await f.wait(sent.comparison_id);f.service.dispose();
  const path=join(f.root,'comparisons.json'),state=JSON.parse(readFileSync(path,'utf8'));
  for(const lane of Object.values(state.turns[0].lanes)){delete lane.failure_stage;lane.task_id=null;lane.failure='这一路未完成，请重试；另一侧结果已保留。';}
  writeFileSync(path,JSON.stringify(state));resumed=createComparisonService(f.root,'account-a',f.host,{pollMs:1});
  const view=await resumed.view('a',sent.comparison_id);
  for(const lane of Object.values(view.lanes)){assert.equal(lane.delivery_status,'not_started');assert.doesNotMatch(lane.failure,/另一侧/);}
  assert.equal(f.submitted.length,0);
 }finally{resumed?.dispose();f.close();}
});

test('First uploads retain historical lane protection and full text within recent per-lane context',async()=>{
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
  assert.equal(JSON.parse(stored.prior_context.baseline)[0].user,'x'.repeat(40000));
  assert.equal(JSON.parse(stored.prior_context.baseline)[0].assistant,'a/baseline');
  await f.service.rate('a',admitted.comparison_id,'baseline',4,0,after.lanes.baseline.output_sha256);
  const another=await f.service.admit('a',{requestId:'replacement',content:[{type:'file',receiptId:'new-source'}]},context);
  const replaced=await f.wait(another.comparison_id);
  assert.notEqual(replaced.lanes.baseline.session_id,after.lanes.baseline.session_id);
  assert.equal((await f.service.view('a',admitted.comparison_id)).scores.baseline,4);
  assert.equal(f.service.isLane(after.lanes.baseline.session_id),true);
  const followup=await f.send('a','after-upload','explain');
  assert.equal((await f.wait(followup.comparison_id)).lanes.baseline.session_id,replaced.lanes.baseline.session_id);
 }finally{f.close();}
});

test('Scene and chat transitions preserve the parent, isolated lanes, files and scores across restart',async()=>{
 let counter=0;const f=fixture({createLane:async(parent,scene,lane)=>`${parent}-${scene}-${lane}-${++counter}`});
 try {
  const a=await f.send('a','data','analyze',{...context,scene:'research-data-analysis'}),first=await f.wait(a.comparison_id);
  for (const name of ['baseline','motif']) f.tasks.get(first.lanes[name].task_id).deliveries=[{id:name+'-report',name:'report.pdf',sha256:name,verification:'data-report-delivery-v1'}];
  // A cold read performs the bounded immutable delivery reconciliation.
  f.service.dispose();const fresh=createComparisonService(f.root,'account-a',f.host,{pollMs:1});
  const repaired=await fresh.view('a',a.comparison_id);
  await fresh.rate('a',a.comparison_id,'baseline',5,repaired.score_revision,repaired.lanes.baseline.output_sha256);
  const request=(requestId,text)=>({requestId,content:[{type:'text',text}]});
  const wait=async(id)=>{for(let i=0;i<200;i++){const value=await fresh.view('a',id);if(['completed','failed'].includes(value.status))return value;await new Promise(r=>setTimeout(r,3));}throw Error('timeout');};
  const ppt=await fresh.admit('a',request('ppt','make slides'),{...context,scene:'ppt',prior_context:[{user:'Earlier ordinary question',assistant:'Earlier ordinary answer'}]});
  const second=await wait(ppt.comparison_id);
  assert.equal(second.session_id,'a');assert.notEqual(first.lanes.baseline.session_id,second.lanes.baseline.session_id);
  const stored=JSON.parse(readFileSync(join(f.root,'comparisons.json'))).turns.at(-1);
  assert.match(stored.prior_context.baseline,/Earlier ordinary answer/);
  assert.match(stored.prior_context.baseline,/a\/baseline/);assert.doesNotMatch(stored.prior_context.baseline,/a\/motif/);
  assert.deepEqual(stored.prior_artifacts.baseline.map(v=>v.row.id),['baseline-report']);
  assert.deepEqual(stored.prior_artifacts.motif.map(v=>v.row.id),['motif-report']);
  const chat=await fresh.admit('a',request('chat','explain'),{...context,scene:'new-scene',presentation:'single'}),third=await wait(chat.comparison_id);
  assert.equal(third.session_id,'a');assert.equal(third.presentation,'single');assert.deepEqual(Object.keys(third.lanes),['baseline']);assert.equal(third.scoring_available,false);
  assert.equal(f.submitted.length,5,'ordinary chat executes only once');
  assert.equal(fresh.snapshot('b',ppt.comparison_id),undefined);
  assert.equal((await fresh.view('a',a.comparison_id)).scores.baseline,5);
  fresh.dispose();const resumed=createComparisonService(f.root,'account-a',f.host,{pollMs:1});
  assert.equal((await resumed.view('a',chat.comparison_id)).presentation,'single');resumed.dispose();
 }finally{f.close();}
});

test('Scoped subscriptions emit incremental answer and real progress then detach',async()=>{
 const f=fixture({submit:async id=>{f.submitted.push(id);Object.assign(f.tasks.get(id),{status:'running',answer:'first',progress:{label:'正在生成回复',status:'running'}});}});
 try {
  const a=await f.send(),seen=[];
  const stop=await f.service.subscribe('a',a.comparison_id,value=>seen.push(value));
  await assert.rejects(f.service.subscribe('b',a.comparison_id,()=>{}),/找不到/);
  for(let i=0;i<30&&!seen.some(v=>v.lanes.baseline.answer==='first');i++)await new Promise(r=>setTimeout(r,3));
  assert.ok(seen.some(v=>v.lanes.baseline.answer==='first'&&v.lanes.baseline.progress.label==='正在生成回复'));
  const baseline=[...f.tasks.keys()][0];Object.assign(f.tasks.get(baseline),{answer:'first second',status:'completed'});
  for(let i=0;i<30&&f.tasks.size<2;i++)await new Promise(r=>setTimeout(r,3));
  const count=seen.length;stop();
  for(const task of f.tasks.values())task.status='completed';await f.wait(a.comparison_id);
  assert.equal(seen.length,count);
 }finally{f.close();}
});

test('native task notifications publish all assistant steps without waiting for the next inspection',async()=>{
 const listeners=new Map();
 const f=fixture({submit:async id=>{f.submitted.push(id);f.tasks.get(id).status='running';},subscribe:(id,fn)=>{listeners.set(id,fn);return()=>listeners.delete(id);}});
 try{
  const sent=await f.send(),seen=[],stop=await f.service.subscribe('a',sent.comparison_id,value=>seen.push(value));
  for(let i=0;i<50&&!listeners.size;i++)await new Promise(r=>setTimeout(r,2));
  const id=[...listeners.keys()][0],task=f.tasks.get(id);
  task.answer='中间说明';task.messages=[{id:'assistant-1',text:'中间说明',status:'streaming'}];task.trace=[{id:'trace-1',kind:'assistant',text:'中间说明'}];
  listeners.get(id)(task);
  assert.equal(seen.at(-1).lanes.baseline.messages[0].text,'中间说明');
  assert.equal(seen.at(-1).lanes.baseline.trace[0].id,'trace-1');
  task.status='completed';
  for(let i=0;i<100;i++){for(const current of f.tasks.values())current.status='completed';if(f.service.snapshot('a',sent.comparison_id).status==='completed')break;await new Promise(r=>setTimeout(r,2));}
  stop();await f.wait(sent.comparison_id);assert.equal(listeners.size,0);
 }finally{f.close();}
});

test('lane trace pagination and feedback retain ownership, output versions and restart durability',async()=>{
 const f=fixture({inspect:async id=>({...f.tasks.get(id),trace:[{id:'trace-1',kind:'tool',label:'读取资料'},{id:'trace-2',kind:'motif',verified_skip:true,optimized:true}]})});
 try{
  const sent=await f.send(),done=await f.wait(sent.comparison_id);
  const first=await f.service.trace('a',sent.comparison_id,'motif',-1,1);
  assert.equal(first.items[0].id,'trace-1');assert.equal(first.next_cursor,0);assert.equal(first.has_more,true);
  const next=await f.service.trace('a',sent.comparison_id,'motif',first.next_cursor,1);assert.equal(next.items[0].verified_skip,true);assert.equal(next.has_more,false);
  await assert.rejects(f.service.trace('b',sent.comparison_id,'motif'),/找不到/);
  await assert.rejects(f.service.trace('a',sent.comparison_id,'foreign'),/轨迹/);
  await assert.rejects(f.service.trace('a',sent.comparison_id,'motif',NaN),/分页/);
  await assert.rejects(f.service.feedback('a',sent.comparison_id,'motif','up','stale'),/已更新/);
  const saved=await f.service.feedback('a',sent.comparison_id,'motif','up',done.lanes.motif.output_sha256);
  assert.equal(saved.lanes.motif.feedback,'up');assert.equal(saved.lanes.baseline.feedback,undefined);
  assert.deepEqual(saved.scores,done.scores);f.service.dispose();
  const restored=createComparisonService(f.root,'account-a',f.host);assert.equal((await restored.view('a',sent.comparison_id)).lanes.motif.feedback,'up');restored.dispose();
 }finally{f.close();}
});
test('Cancelling during asynchronous preparation never submits a late task or revives a queued lane',async()=>{
 let release;const gate=new Promise(r=>release=r);const f=fixture({prepare:async(t,lane,id)=>{await gate;f.tasks.set(id,{status:'queued'});return{task_id:id};}});
 try{const a=await f.send();await f.service.cancel('a',a.comparison_id);release();await new Promise(r=>setTimeout(r,20));const v=await f.service.view('a',a.comparison_id);assert.equal(v.status,'cancelled');assert.equal(f.submitted.length,0);assert.equal(f.cancelled.length,2);assert.equal(new Set(f.cancelled).size,2);}finally{f.close();}
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
