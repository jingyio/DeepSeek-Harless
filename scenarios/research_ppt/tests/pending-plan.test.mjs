/** 有界失败计划恢复的协议/文件系统回归；实际模型成本与LO渲染须由服务器真实验收另证。 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, mkdir, readFile, realpath, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { AdapterRejected, digest, preflightPlan } from '../dist/delivery-adapter.js';
import { PendingPlanStore, mergePendingPatch } from '../dist/pending-plan.js';

const failure = { code: 'invalid_plan', message: '明确页标题超过容量。', details: { page: 2 } };
const valid = () => ({title:'Scientifically fixed',template:'lab',slides:[
  {title:'Untouched',sources:[{source_id:'source-approved',page:1}],bullets:['Control population = 31'],notes:'Exact conditions; no automatic change'},
  {title:'Target',sources:[{source_id:'source-approved',page:2}],bullets:['Accuracy 63.7%'],notes:'Hold measurement and unit'}]});
const broken = () => { const plan=valid(); plan.slides[1].title='x'.repeat(71); return plan; };
const sha = value => createHash('sha256').update(value).digest('hex');
async function fixture(work, overrides={}) {
  const root=await realpath(await mkdtemp(join(tmpdir(),'sss-pending-plan-'))), area=join(root,'.local','jobs','fixed');
  await mkdir(area,{recursive:true}); const jobPath=join(area,'job.json');
  const job={slides:2,allow_output:true,inputs:[]}; const raw=JSON.stringify(job); await writeFile(jobPath,raw);
  const evidence={job_sha256:sha(raw),input_version:'a'.repeat(64),schema_sha256:'b'.repeat(64),implementation_sha256:'c'.repeat(64),permission_sha256:'d'.repeat(64)};
  let sourceCurrent=true; const audit=[];
  const options={root,jobPath,expectedSlides:2,evidence,guard:async()=>{if(!sourceCurrent) throw new AdapterRejected('source_version_changed','source changed');},
    audit:async(kind,data)=>{audit.push({kind,data});},...overrides};
  try { await work({root,area,jobPath,job,evidence,options,audit,invalidateSource:()=>{sourceCurrent=false;},store:await PendingPlanStore.create(options)}); }
  finally { await rm(root,{recursive:true,force:true}); }
}

test('失败完整计划存私有句柄；局部修改保科学数值、来源、notes、非目标页，原稿字节不变',async()=>{
  await fixture(async({store,area,audit})=>{
    const original=broken(), copy=structuredClone(original), captured=await store.capture(original,failure);
    assert.equal(captured.attempts,1); assert.deepEqual(captured.failure.failing_pages,[2]);
    assert.equal(captured.preflight.valid,false); assert.equal(captured.plan,undefined);
    const initial=await readFile(join(area,'pending-plans',captured.draft_id,'revision-1.json'));
    const repaired=await store.patch(captured.draft_id,captured.version_sha256,{updates:[{page:2,changes:{title:'Exact revised title'}}]});
    assert.equal(repaired.preflight.valid,true); assert.deepEqual(repaired.changed_pages,[2]);
    const read=await store.read(repaired.draft_id,repaired.version_sha256,[1,2]);
    assert.deepEqual(read.slides[0].slide,original.slides[0]);
    assert.deepEqual(read.slides[1].slide,{...original.slides[1],title:'Exact revised title'});
    assert.deepEqual(original,copy); assert.equal(read.plan,undefined);
    assert.deepEqual(await readFile(join(area,'pending-plans',captured.draft_id,'revision-1.json')),initial);
    assert.ok(audit.some(row=>row.kind==='pending_plan_state' && row.data.automatic_content_change===false));
  });
});

test('无机械自动补页/删页/截短；必须显式插删且总页数精确，原页号稳定',()=>{
  const plan=valid(); plan.slides.splice(1,0,{title:'Explicit extra',sources:[{source_id:'source-approved',page:3}],notes:'do not silently delete'});
  const copy=structuredClone(plan);
  assert.throws(()=>mergePendingPatch(plan,{updates:[{page:2,changes:{title:'Still 3 pages'}}]},2),{code:'slide_count_mismatch'});
  const repaired=mergePendingPatch(plan,{deletions:[2]},2);
  assert.deepEqual(repaired.plan,valid()); assert.deepEqual(repaired.deleted_pages,[2]); assert.deepEqual(plan,copy);
  const short=valid(); short.slides.pop();
  const inserted=mergePendingPatch(short,{insertions:[{before_page:2,slide:valid().slides[1]}]},2);
  assert.deepEqual(inserted.plan,valid()); assert.deepEqual(inserted.inserted_before_pages,[2]);
  for (const patch of [{deletions:[2,2]},{deletions:[0]},{deletions:['2']},{deletions:[2],updates:[{page:2,changes:{title:'contradictory'}}]},
    {insertions:[{before_page:5,slide:valid().slides[1]}]},{auto_delete:true}]) assert.throws(()=>mergePendingPatch(plan,patch,2));
  assert.throws(()=>preflightPlan(plan,2),{code:'slide_count_mismatch'});
});

test('整页替换能修不支持字段；来源索引重绑不能通过省略旧证据说明逃逸',()=>{
  const malformed=valid(); malformed.slides[1].unsupported_field='malformed';
  const replacement=mergePendingPatch(malformed,{replacements:[{page:2,slide:valid().slides[1]}]},2);
  assert.equal(replacement.plan.slides[1].unsupported_field,undefined); assert.equal(malformed.slides[1].unsupported_field,'malformed');
  const plan=valid(); Object.assign(plan.slides[1],{archetype:'evidence-focus',layout:'image',image:{source_id:'source-approved',image_id:'figure-1'},
    evidence_notes:[{label:'Condition',text:'Population fixed',source_index:1}]});
  const after={...plan.slides[1],sources:[{source_id:'source-approved',page:4}]}; delete after.evidence_notes;
  assert.throws(()=>mergePendingPatch(plan,{replacements:[{page:2,slide:after}]},2),{code:'invalid_revision'});
  after.evidence_notes=[]; assert.doesNotThrow(()=>mergePendingPatch(plan,{replacements:[{page:2,slide:after}]},2));
  assert.throws(()=>mergePendingPatch(plan,{updates:[{page:2,changes:{sources:[{source_id:'source-approved',page:4}]}}]},2),{code:'invalid_revision'});
});

test('缺顶层标题/错误模板只由显式metadata修复，原科学页面保持；保精确小诊断',async()=>{
  await fixture(async({store})=>{
    const original=valid(); delete original.title; original.template='unsupported';
    const receipt=await store.capture(original,{code:'invalid_arguments',message:'missing title',details:{missing_fields:['title'],
      allowed_fields:['title','slides','template','private-arbitrary-secret'],backend_report:{page:2,role:'evidence_note_1',field:'evidence_notes',
        fields:['bullets','arbitrary-secret'],expected_slides:2,submitted_slides:2,internal_payload:'must not reflect'}}});
    assert.deepEqual(receipt.failure.missing_fields,['title']); assert.deepEqual(receipt.failure.allowed_fields,['title','slides','template']);
    assert.equal(receipt.failure.field,'evidence_notes'); assert.equal(receipt.failure.role,'evidence_note_1');
    assert.deepEqual(receipt.failure.fields,['bullets']); assert.equal(receipt.failure.internal_payload,undefined);
    const fixed=await store.patch(receipt.draft_id,receipt.version_sha256,{metadata:{title:'Explicit full title',template:'lab'}});
    assert.equal(fixed.preflight.valid,true); assert.deepEqual(fixed.changed_metadata,['title','template']);
    const read=await store.read(fixed.draft_id,fixed.version_sha256,[1,2]);
    assert.equal(read.title,'Explicit full title'); assert.equal(read.template,'lab'); assert.deepEqual(read.slides.map(row=>row.slide),original.slides);
    for(const metadata of [{},{auto_title:true},{title:null},{template:'arbitrary'}])
      await assert.rejects(()=>store.patch(fixed.draft_id,fixed.version_sha256,{metadata}),{code:'invalid_pending_patch'});
  });
});

test('媒体删除必须显式null与兼容布局，不修改其他字段或静默删除原图',async()=>{
  await fixture(async({store})=>{
    const original=broken(); Object.assign(original.slides[1],{layout:'image',image:{source_id:'source-approved',image_id:'figure-1'}});
    const receipt=await store.capture(original,failure);
    const patched=await store.patch(receipt.draft_id,receipt.version_sha256,{updates:[{page:2,changes:{title:'Fixed',layout:'content'}}]});
    assert.equal(patched.preflight.valid,false);
    const read=await store.read(patched.draft_id,patched.version_sha256,[2]); assert.deepEqual(read.slides[0].slide.image,original.slides[1].image);
    await assert.rejects(()=>store.prepareAttempt(patched.draft_id,patched.version_sha256),{code:'invalid_plan'});
    const explicit=await store.patch(patched.draft_id,patched.version_sha256,{updates:[{page:2,changes:{image:null}}]});
    assert.equal(explicit.preflight.valid,true);
    assert.throws(()=>mergePendingPatch(original,{updates:[{page:2,changes:{sources:null}}]},2),{code:'invalid_pending_patch'});
  });
});

test('跨进程重启恢复真实私有plan，schema/工具/来源/权限摘要变化拒旧draft',async()=>{
  await fixture(async({options,store})=>{
    const captured=await store.capture(broken(),failure), restarted=await PendingPlanStore.create(options);
    assert.deepEqual(await restarted.activePending(),captured);
    const read=await restarted.read(captured.draft_id,captured.version_sha256,[2]); assert.equal(read.slides[0].slide.title.length,71);
    for (const field of ['schema_sha256','implementation_sha256','input_version','permission_sha256']) {
      const changed=await PendingPlanStore.create({...options,evidence:{...options.evidence,[field]:'f'.repeat(64)}});
      await assert.rejects(()=>changed.activePending(),{code:'pending_scope_changed'});
    }
  });
});

test('任务文件权限变化和来源失效在读取/修改前停止，默认预览不能创建恢复服务',async()=>{
  await fixture(async({jobPath,job,store,invalidateSource})=>{
    const receipt=await store.capture(broken(),failure);
    invalidateSource(); await assert.rejects(()=>store.read(receipt.draft_id,receipt.version_sha256,[2]),{code:'source_version_changed'});
  });
  await fixture(async({jobPath,job,store})=>{
    const receipt=await store.capture(broken(),failure); await writeFile(jobPath,JSON.stringify({...job,allow_output:false}));
    await assert.rejects(()=>store.patch(receipt.draft_id,receipt.version_sha256,{updates:[{page:2,changes:{title:'unsafe'}}]}),{code:'job_version_changed'});
  });
  await fixture(async({options,jobPath,job})=>{
    const raw=JSON.stringify({...job,allow_output:false}); await writeFile(jobPath,raw);
    await assert.rejects(()=>PendingPlanStore.create({...options,evidence:{...options.evidence,job_sha256:sha(raw)}}),{code:'output_permission_denied'});
  });
});

test('全稿重复提交被活动draft拦截；版本变化和同计划再次执行拒绝',async()=>{
  await fixture(async({store})=>{
    const receipt=await store.capture(broken(),failure);
    await assert.rejects(()=>store.capture(valid(),failure),{code:'pending_plan_exists'});
    await assert.rejects(()=>store.prepareAttempt(receipt.draft_id,receipt.version_sha256),{code:'pending_unchanged_retry'});
    const patched=await store.patch(receipt.draft_id,receipt.version_sha256,{updates:[{page:2,changes:{title:'Fixed'}}]});
    await assert.rejects(()=>store.read(receipt.draft_id,receipt.version_sha256,[2]),{code:'pending_version_changed'});
    await assert.rejects(()=>store.patch(patched.draft_id,patched.version_sha256,{updates:[{page:2,changes:{title:'Fixed'}}]}),{code:'no_changes'});
    const attempt=await store.prepareAttempt(patched.draft_id,patched.version_sha256);
    assert.equal(attempt.plan.slides[1].title,'Fixed'); assert.equal(attempt.receipt.status,'in_flight');
    const failed=await store.recordOutcome(attempt.receipt.draft_id,attempt.receipt.version_sha256,attempt.attempt_id,{delivered:false,failure});
    await assert.rejects(()=>store.prepareAttempt(failed.draft_id,failed.version_sha256),{code:'pending_unchanged_retry'});
  });
});

test('并发修改只有一个版本成功；in-flight及重启后不猜执行结果，不重渲染',async()=>{
  await fixture(async({store,options})=>{
    const receipt=await store.capture(broken(),failure), another=await PendingPlanStore.create(options);
    const responses=await Promise.allSettled([store.patch(receipt.draft_id,receipt.version_sha256,{updates:[{page:2,changes:{title:'First'}}]}),
      another.patch(receipt.draft_id,receipt.version_sha256,{updates:[{page:2,changes:{title:'Second'}}]})]);
    assert.equal(responses.filter(x=>x.status==='fulfilled').length,1);
    assert.ok(['pending_plan_busy','pending_version_changed'].includes(responses.find(x=>x.status==='rejected').reason.code));
    const current=await store.activePending(), attempt=await store.prepareAttempt(current.draft_id,current.version_sha256);
    const restarted=await PendingPlanStore.create(options);
    await assert.rejects(()=>restarted.prepareAttempt(attempt.receipt.draft_id,attempt.receipt.version_sha256),{code:'pending_attempt_in_flight'});
    await assert.rejects(()=>restarted.recordOutcome(attempt.receipt.draft_id,attempt.receipt.version_sha256,'wrong-attempt',{delivered:true}),{code:'pending_attempt_changed'});
    const delivered=await restarted.recordOutcome(attempt.receipt.draft_id,attempt.receipt.version_sha256,attempt.attempt_id,{delivered:true});
    assert.equal(delivered.status,'delivered'); assert.equal(await restarted.activePending(),undefined);
    await assert.rejects(()=>restarted.patch(delivered.draft_id,delivered.version_sha256,{updates:[{page:2,changes:{title:'Again'}}]}),{code:'pending_already_delivered'});
  });
});

test('同job全局提交预算跨draft及重启累计，不能重发整稿绕开失败上限',async()=>{
  await fixture(async({store,options})=>{
    const first=await store.capture(broken(),failure), patch=await store.patch(first.draft_id,first.version_sha256,{updates:[{page:2,changes:{title:'Fixed'}}]});
    const attempt=await store.prepareAttempt(patch.draft_id,patch.version_sha256);
    await store.recordOutcome(attempt.receipt.draft_id,attempt.receipt.version_sha256,attempt.attempt_id,{delivered:true});
    const later=broken(); later.title='Second explicit task render'; const next=await store.capture(later,failure);
    assert.equal(next.attempts,1);
    const fixed=await store.patch(next.draft_id,next.version_sha256,{updates:[{page:2,changes:{title:'Second fixed'}}]});
    const restarted=await PendingPlanStore.create(options);
    await assert.rejects(()=>restarted.prepareAttempt(fixed.draft_id,fixed.version_sha256),{code:'pending_attempt_limit'});
    await assert.rejects(()=>restarted.capture(valid(),failure),{code:'pending_plan_exists'});
  },{maxAttempts:3});
});

test('局部修复独立有界，不能持续产生无效patch拖长模型历史',async()=>{
  await fixture(async({store})=>{
    const original=broken(), first=await store.capture(original,failure);
    const patched=await store.patch(first.draft_id,first.version_sha256,{updates:[{page:1,changes:{title:'Still has page 2 error'}}]});
    assert.equal(patched.preflight.valid,false);
    await assert.rejects(()=>store.patch(patched.draft_id,patched.version_sha256,{updates:[{page:2,changes:{title:'Too late'}}]}),{code:'pending_patch_limit'});
  },{maxPatches:1});
});

test('大JSON、深嵌套、危险对象键、任意句柄和多页批量读取拒绝',async()=>{
  await fixture(async({store})=>{
    const large=valid(); large.slides[0].notes='x'.repeat(2_000_001);
    await assert.rejects(()=>store.capture(large,failure),{code:'pending_plan_size_exceeded'});
    const deep=valid(); let nested={}; for(let i=0;i<26;i++) nested={next:nested}; deep.slides[1].extra=nested;
    await assert.rejects(()=>store.capture(deep,failure),{code:'pending_plan_size_exceeded'});
    const dangerous=JSON.parse(JSON.stringify(valid()).replace('"title":"Target"','"__proto__":{"escaped":true},"title":"Target"'));
    await assert.rejects(()=>store.capture(dangerous,failure),{code:'invalid_pending_plan'});
    const receipt=await store.capture(broken(),failure);
    await assert.rejects(()=>store.read('../../outside',receipt.version_sha256,[1]),{code:'invalid_pending_handle'});
    await assert.rejects(()=>store.read(receipt.draft_id,receipt.version_sha256,[1,1]),{code:'invalid_pending_pages'});
    await assert.rejects(()=>store.read(receipt.draft_id,receipt.version_sha256,[1,2,3,4,5,6]),{code:'invalid_pending_pages'});
    await assert.rejects(()=>store.read(receipt.draft_id,receipt.version_sha256,[0]),{code:'invalid_pending_patch'});
    assert.equal({}.escaped,undefined);
  });
});

test('固定目录及记录符号链接不能跳出私有job；外部文件保持',async()=>{
  await fixture(async({store,area,root,options})=>{
    const receipt=await store.capture(broken(),failure), external=join(root,'outside.txt'); await writeFile(external,'original outside');
    const head=join(area,'pending-plans',receipt.draft_id,'head.json'); await rm(head);
    await symlink(external,head);
    await assert.rejects(()=>store.read(receipt.draft_id,receipt.version_sha256,[2]),{code:'pending_storage_rejected'});
    assert.equal(await readFile(external,'utf8'),'original outside');
    await rm(join(area,'pending-plans'),{recursive:true}); await symlink(root,join(area,'pending-plans'),'dir');
    await assert.rejects(()=>PendingPlanStore.create(options),{code:'path_scope_rejected'});
    assert.equal(await readFile(external,'utf8'),'original outside');
  });
});

test('校验摘要/头记录篡改均fail closed；不会返回未经版本认证的计划',async()=>{
  await fixture(async({store,area})=>{
    const receipt=await store.capture(broken(),failure), path=join(area,'pending-plans',receipt.draft_id,'revision-1.json');
    const record=JSON.parse(await readFile(path,'utf8')); record.plan.slides[0].bullets=['Forged 99%']; await writeFile(path,JSON.stringify(record));
    await assert.rejects(()=>store.activePending(),{code:'pending_scope_changed'});
    assert.notEqual(digest(record),receipt.version_sha256);
  });
});
