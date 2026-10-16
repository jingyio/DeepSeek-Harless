/** 宿主局部恢复协议诊断：真实私有PendingPlanStore文件＋受控host；不是模型或渲染效果证据。 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, mkdir, readdir, realpath, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { AdapterRejected, preflightPlan } from '../dist/delivery-adapter.js';
import { ExecutionPolicy } from '../dist/execution-policy.js';
import { PendingPlanStore } from '../dist/pending-plan.js';
import { PlanRecovery } from '../dist/plan-recovery.js';

const goodPlan=()=>({title:'Fixed source scientific deck',template:'lab',slides:[
  {title:'Non-target source',sources:[{source_id:'approved',page:1}],bullets:['Exact numeric condition: 31 people'],notes:'NON_TARGET_LONG_NOTE ' + 'stable conditions; '.repeat(150)},
  {title:'Target',sources:[{source_id:'approved',page:2}],bullets:['Metric 63.7% under fixed conditions'],notes:'Target experiment and source conditions kept'}]});
const badPlan=()=>{const plan=goodPlan();plan.slides[1].title='x'.repeat(71);return plan;};
function noFullPlan(value) {
  if(Array.isArray(value)) value.forEach(noFullPlan);
  else if(value!==null && typeof value==='object') for(const [key,child] of Object.entries(value)) {
    assert.notEqual(key,'plan','完整plan不可返回模型');noFullPlan(child);
  }
}
async function captureFailure(work,code) {
  let caught;try{await work();}catch(error){caught=error;}
  assert.ok(caught instanceof AdapterRejected);if(code)assert.equal(caught.code,code);return caught;
}
async function fixture(work,{strategy='host_delivery',allowOutput=true,createStore=true}={}) {
  const root=await realpath(await mkdtemp(join(tmpdir(),'sss-plan-recovery-'))),area=join(root,'.local','job','fixed');
  await mkdir(area,{recursive:true});const jobPath=join(area,'job.json'),raw=JSON.stringify({slides:2,allow_output:allowOutput,inputs:[]});await writeFile(jobPath,raw);
  const evidence={job_sha256:createHash('sha256').update(raw).digest('hex'),input_version:'a'.repeat(64),schema_sha256:'b'.repeat(64),
    implementation_sha256:'c'.repeat(64),permission_sha256:'d'.repeat(64)};
  const audit=[],backendCalls=[],seenPlans=[];let renderFailure,guardFailure;
  const host={
    guard:async()=>{if(guardFailure)throw guardFailure;},
    audit:async(kind,data)=>{audit.push({kind,data});},
    renderDelivery:async(plan)=>{
      if(!allowOutput)throw new AdapterRejected('output_permission_denied','explicit output permission required');
      seenPlans.push(structuredClone(plan));preflightPlan(plan,2);
      if(renderFailure){const error=renderFailure;renderFailure=undefined;throw error;}
      for(const name of ['render_deck','inspect_deck','validate_deck','deliver_deck'])backendCalls.push(name);
      return {delivered:true,deck_id:'new-copy',validation_id:'checked-version',file_sha256:'e'.repeat(64),input_version:evidence.input_version,
        editable:true,scientific_quality:'not_reviewed'};
    },
    reviseDelivery:async()=>assert.fail('不应调用revise_deck处理尚无PPT的失败计划'),
    restyleDelivery:async()=>assert.fail('不应无关重排来源PPT'),
  };
  const options={root,jobPath,expectedSlides:2,evidence,guard:()=>host.guard(),audit:(kind,data)=>host.audit(kind,data)};
  const store=createStore?await PendingPlanStore.create(options):undefined;
  const policy=new ExecutionPolicy(strategy==='legacy_model_selected'?undefined:{schema_version:1,strategy}),recovery=new PlanRecovery(store,policy,host);
  const draftCount=async()=>{try{return (await readdir(join(area,'pending-plans'))).filter(name=>name.startsWith('pending-')).length;}
    catch(error){if(error.code==='ENOENT')return 0;throw error;}};
  try{await work({root,area,jobPath,options,host,store,policy,recovery,audit,backendCalls,seenPlans,draftCount,
    failRender:error=>{renderFailure=error;},failGuard:error=>{guardFailure=error;}});}
  finally{await rm(root,{recursive:true,force:true});}
}

test('首失败自动保存draft小诊断；整稿重交在宿主前拒绝，不再调用后端',async()=>{
  await fixture(async({recovery,backendCalls,seenPlans,draftCount})=>{
    const original=badPlan(),error=await captureFailure(()=>recovery.render({plan:original}),'invalid_plan');
    const receipt=error.details.pending_plan;assert.ok(receipt.draft_id);assert.equal(receipt.preflight.valid,false);
    assert.equal(await draftCount(),1);assert.deepEqual(backendCalls,[]);assert.equal(seenPlans.length,1);noFullPlan(error.details);
    assert.ok(!JSON.stringify(error.details).includes('NON_TARGET_LONG_NOTE'));
    await assert.rejects(()=>recovery.render({plan:goodPlan()}),{code:'pending_plan_exists'});
    assert.equal(seenPlans.length,1);assert.deepEqual(backendCalls,[]);assert.equal(await draftCount(),1);
  });
});

test('错误句柄仅返回本任务最新回执，不自动改参数或执行；来源失效仍拒绝',async()=>{
 await fixture(async({recovery,store,backendCalls,failGuard})=>{
  const first=await captureFailure(()=>recovery.render({plan:badPlan()}),'invalid_plan');const receipt=first.details.pending_plan;
  const error=await captureFailure(()=>recovery.repair({draft_id:'invented',version_sha256:'b'.repeat(64),updates:[{page:2,changes:{title:'Correct'}}]}),'invalid_pending_handle');
  assert.equal(error.details.pending_plan.draft_id,receipt.draft_id);assert.equal(error.details.pending_plan.version_sha256,receipt.version_sha256);assert.deepEqual(backendCalls,[]);noFullPlan(error.details);
  const unchanged=await store.read(receipt.draft_id,receipt.version_sha256,[2]);assert.equal(unchanged.slides[0].slide.title,badPlan().slides[1].title);
  failGuard(new AdapterRejected('source_version_changed','changed'));
  const refused=await captureFailure(()=>recovery.repair({draft_id:'invented'}),'source_version_changed');assert.equal(refused.details.pending_plan,undefined);
 });
});

test('repair只传小字段patch，内部复用完整计划且非目标科学内容保持，结果不返整稿',async()=>{
  await fixture(async({recovery,backendCalls,seenPlans})=>{
    const original=badPlan(),error=await captureFailure(()=>recovery.render({plan:original}));
    const receipt=error.details.pending_plan,args={draft_id:receipt.draft_id,version_sha256:receipt.version_sha256,updates:[{page:2,changes:{title:'Corrected target title'}}]};
    assert.ok(JSON.stringify(args).length<JSON.stringify(original).length/4);
    const result=await recovery.repair(args);assert.equal(result.delivered,true);assert.equal(result.pending_plan.status,'delivered');
    assert.deepEqual(backendCalls,['render_deck','inspect_deck','validate_deck','deliver_deck']);
    assert.deepEqual(seenPlans.at(-1).slides[0],original.slides[0]);
    assert.deepEqual(seenPlans.at(-1).slides[1],{...original.slides[1],title:'Corrected target title'});
    assert.deepEqual(result.local_repair.changed_pages,[2]);assert.equal(result.execution_policy.request_tool,'repair_pending_plan');
    noFullPlan(result);assert.ok(!JSON.stringify(result).includes('NON_TARGET_LONG_NOTE'));
  });
});

test('真实缺顶层title模式通过metadata修复，无需再生成或回传任何科学页面',async()=>{
  await fixture(async({recovery,seenPlans})=>{
    const original=goodPlan();delete original.title;
    const first=(await captureFailure(()=>recovery.render({plan:original}),'invalid_arguments')).details.pending_plan;
    assert.deepEqual(first.failure.missing_fields,['title']);
    const args={draft_id:first.draft_id,version_sha256:first.version_sha256,metadata:{title:'Explicit recovered title'}};
    const result=await recovery.repair(args);assert.equal(result.delivered,true);
    assert.deepEqual(seenPlans.at(-1).slides,original.slides);assert.equal(seenPlans.at(-1).title,'Explicit recovered title');
    assert.deepEqual(result.local_repair.changed_metadata,['title']);assert.deepEqual(result.local_repair.changed_pages,[]);noFullPlan(result);
  });
});

test('页数错误只由明确删除指定多余页恢复，已正确页不重写',async()=>{
  await fixture(async({recovery,seenPlans})=>{
    const original=goodPlan();original.slides.push({title:'Extra explicitly removed page',sources:[{source_id:'approved',page:3}],bullets:['duplicate conclusion']});
    const first=(await captureFailure(()=>recovery.render({plan:original}),'slide_count_mismatch')).details.pending_plan;
    const result=await recovery.repair({draft_id:first.draft_id,version_sha256:first.version_sha256,deletions:[3]});
    assert.equal(result.delivered,true);assert.deepEqual(seenPlans.at(-1).slides,original.slides.slice(0,2));
    assert.deepEqual(result.local_repair.deleted_pages,[3]);noFullPlan(result);
  });
});

test('第一处patch已保留但其它错误仍preflight拒绝；下一patch必须用新版本且不重新输出其它页',async()=>{
  await fixture(async({recovery,backendCalls,seenPlans})=>{
    const original=badPlan();original.slides[0].takeaway='y'.repeat(91);
    const error=await captureFailure(()=>recovery.render({plan:original})),first=error.details.pending_plan;
    const result=await recovery.repair({draft_id:first.draft_id,version_sha256:first.version_sha256,updates:[{page:2,changes:{title:'Fixed second'}}]});
    assert.equal(result.ok,false);assert.equal(result.code,'pending_preflight_failed');assert.deepEqual(backendCalls,[]);assert.equal(seenPlans.length,1);
    const next=result.pending_plan;assert.notEqual(next.version_sha256,first.version_sha256);
    await assert.rejects(()=>recovery.repair({draft_id:first.draft_id,version_sha256:first.version_sha256,updates:[{page:1,changes:{takeaway:'Stale'}}]}),{code:'pending_version_changed'});
    const delivered=await recovery.repair({draft_id:next.draft_id,version_sha256:next.version_sha256,updates:[{page:1,changes:{takeaway:'Explicit correct conclusion'}}]});
    assert.equal(delivered.delivered,true);assert.equal(seenPlans.at(-1).slides[1].title,'Fixed second');
    assert.deepEqual(seenPlans.at(-1).slides[0].bullets,original.slides[0].bullets);noFullPlan(delivered);
  });
});

test('实际宿主渲染再失败有新版receipt；模型只修新错误字段，所有科学条件不自动缩短',async()=>{
  await fixture(async({recovery,failRender,seenPlans})=>{
    const original=badPlan(),first=(await captureFailure(()=>recovery.render({plan:original}))).details.pending_plan;
    failRender(new AdapterRejected('backend_tool_failed','layout rejected',{backend_report:{error:'text_overflow',page:2,field:'bullets',role:'body_1'}}));
    const error=await captureFailure(()=>recovery.repair({draft_id:first.draft_id,version_sha256:first.version_sha256,
      updates:[{page:2,changes:{title:'Repaired title'}}]}),'backend_tool_failed');
    const next=error.details.pending_plan;assert.equal(next.status,'pending');assert.notEqual(next.version_sha256,first.version_sha256);
    assert.equal(next.failure.field,'bullets');assert.equal(next.failure.role,'body_1');assert.deepEqual(next.failure.failing_pages,[2]);
    assert.deepEqual(seenPlans.at(-1).slides[1].bullets,original.slides[1].bullets);
    const result=await recovery.repair({draft_id:next.draft_id,version_sha256:next.version_sha256,
      updates:[{page:2,changes:{bullets:['63.7%; original fixed conditions retained']}}]});
    assert.equal(result.delivered,true);assert.equal(seenPlans.at(-1).slides[1].title,'Repaired title');
    assert.equal(seenPlans.at(-1).slides[1].notes,original.slides[1].notes);assert.deepEqual(seenPlans.at(-1).slides[0],original.slides[0]);noFullPlan(error.details);
  });
});

test('只读取失败页而非整稿；页号与receipt版本需真实有效',async()=>{
  await fixture(async({recovery})=>{
    const receipt=(await captureFailure(()=>recovery.render({plan:badPlan()}))).details.pending_plan;
    const result=await recovery.read({draft_id:receipt.draft_id,version_sha256:receipt.version_sha256,pages:[2]});
    assert.deepEqual(result.slides.map(row=>row.page),[2]);assert.ok(!JSON.stringify(result).includes('NON_TARGET_LONG_NOTE'));noFullPlan(result);
    await assert.rejects(()=>recovery.read({draft_id:receipt.draft_id,version_sha256:'f'.repeat(64),pages:[2]}),{code:'pending_version_changed'});
  });
});

test('baseline及legacy只读/修复工具均硬拒，不能窃用宿主优化；原普通render继续交原入口',async()=>{
  for(const strategy of ['baseline_steps','legacy_model_selected'])await fixture(async({recovery,backendCalls,draftCount,audit})=>{
    const args={draft_id:'not-real',version_sha256:'f'.repeat(64),pages:[2]};
    await assert.rejects(()=>recovery.read(args),{code:'execution_policy_tool_disabled'});
    await assert.rejects(()=>recovery.repair({...args,updates:[{page:2,changes:{title:'not allowed'}}]}),{code:'execution_policy_tool_disabled'});
    assert.equal(await recovery.render({plan:goodPlan()}),undefined);assert.equal(await draftCount(),0);assert.deepEqual(backendCalls,[]);
    assert.equal(audit.filter(row=>row.kind==='execution_policy_tool_rejected').length,2);
  },{strategy});
});

test('preview没有恢复store仍可正常派发，输出权限拒绝而非启动失败，不创建草稿',async()=>{
  await fixture(async({recovery,backendCalls,draftCount})=>{
    await assert.rejects(()=>recovery.render({plan:goodPlan()}),{code:'output_permission_denied'});
    await assert.rejects(()=>recovery.read({draft_id:'not-real',version_sha256:'f'.repeat(64),pages:[2]}),{code:'output_permission_denied'});
    await assert.rejects(()=>recovery.repair({draft_id:'not-real',version_sha256:'f'.repeat(64),updates:[{page:2,changes:{title:'denied'}}]}),{code:'output_permission_denied'});
    assert.deepEqual(backendCalls,[]);assert.equal(await draftCount(),0);
  },{allowOutput:false,createStore:false});
});

test('未知异常、版本失效及权限拒绝不保存为可修复草稿，不重试科学内容',async()=>{
  for(const error of [new Error('private stack or sensitive error'),new AdapterRejected('source_version_changed','source changed'),
    new AdapterRejected('implementation_version_changed','implementation changed'),new AdapterRejected('output_permission_denied','permission denied'),
    new AdapterRejected('backend_tool_failed','unknown backend failure'),new AdapterRejected('backend_tool_failed','unknown backend detail',{backend_report:{error:'internal_error'}})])
    await fixture(async({recovery,failRender,draftCount,backendCalls})=>{
      failRender(error);await assert.rejects(()=>recovery.render({plan:goodPlan()}),caught=>caught===error);
      assert.equal(await draftCount(),0);assert.deepEqual(backendCalls,[]);
    });
});

test('工具顶层额外/缺失参数拒绝不制造无意义恢复草稿；无法安全保存的畸形plan保原诊断',async()=>{
  await fixture(async({recovery,draftCount,backendCalls})=>{
    await assert.rejects(()=>recovery.render({plan:goodPlan(),arbitrary:'bad argument'}),{code:'invalid_arguments'});
    assert.equal(await draftCount(),0);assert.deepEqual(backendCalls,[]);
    await assert.rejects(()=>recovery.render({}),{code:'invalid_arguments'});assert.equal(await draftCount(),0);
    await assert.rejects(()=>recovery.render({plan:{title:'Not recoverable',slides:['bad slide',goodPlan().slides[1]]}}),{code:'invalid_plan'});assert.equal(await draftCount(),0);
  });
});
