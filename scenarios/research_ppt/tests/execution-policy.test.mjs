/** 策略与调用协议诊断；有限脚本真实渲染/费用须另在服务器任务中验证。 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { AdapterRejected, digest } from '../dist/delivery-adapter.js';
import { COMPOSED_TOOL_NAMES, ExecutionPolicy } from '../dist/execution-policy.js';

function hostFixture() {
  const calls=[], audits=[];
  const response={delivered:true,deck_id:'actual-deck',validation_id:'actual-validation',file_sha256:'a'.repeat(64)};
  return {calls,audits,response,
    guard:async()=>{ calls.push(['guard']); },
    audit:async(kind,row)=>{ audits.push({kind,...row}); },
    renderDelivery:async plan=>{ calls.push(['renderDelivery',plan]);return structuredClone(response); },
    reviseDelivery:async(deck,updates)=>{ calls.push(['reviseDelivery',deck,updates]);return structuredClone(response); },
    restyleDelivery:async(source,template)=>{ calls.push(['restyleDelivery',source,template]);return structuredClone(response); },
  };
}

test('新的对照必须显式版本/策略，拒绝自报禁用列表和任意路由；缺省保留旧任务兼容',()=>{
  for (const config of [null,{},[],{schema_version:2,strategy:'baseline_steps'},
    {schema_version:1,strategy:'legacy_model_selected'},{schema_version:1,strategy:'host_delivery',script:'arbitrary'},
    {schema_version:1,strategy:['host_delivery']},{schema_version:1,strategy:['baseline_steps']},
    {schema_version:1,strategy:'host_delivery',disabled_tools:[]},{schema_version:1,strategy:'unknown'}])
    assert.throws(()=>new ExecutionPolicy(config),{code:'invalid_execution_policy'});
  assert.equal(new ExecutionPolicy(undefined).snapshot().strategy,'legacy_model_selected');
});

test('策略hash稳定且模式不同；快照不能反向改变生效规则',()=>{
  const first=new ExecutionPolicy({schema_version:1,strategy:'host_delivery'});
  const second=new ExecutionPolicy({strategy:'host_delivery',schema_version:1});
  assert.equal(first.snapshot().policy_sha256,second.snapshot().policy_sha256);
  assert.notEqual(first.snapshot().policy_sha256,new ExecutionPolicy({schema_version:1,strategy:'baseline_steps'}).snapshot().policy_sha256);
  const snapshot=first.snapshot(); snapshot.disabled_tools.length=0;snapshot.host_routes[0].backend_steps.length=0;
  assert.deepEqual(first.snapshot().disabled_tools,[...COMPOSED_TOOL_NAMES]);
  const evidence=first.snapshot(), hash=evidence.policy_sha256;delete evidence.policy_sha256;
  assert.equal(digest(evidence),hash);
});

test('两组禁止全部旧组合入口，实际拒绝发生在后端调用前，并记录策略证据',async()=>{
  for (const strategy of ['baseline_steps','host_delivery']) {
    const policy=new ExecutionPolicy({schema_version:1,strategy}),host=hostFixture();
    for (const name of COMPOSED_TOOL_NAMES) await assert.rejects(()=>policy.dispatch(host,name,{plan:{}}),{code:'execution_policy_tool_disabled'});
    assert.deepEqual(host.calls,[]);assert.equal(host.audits.length,3);
    assert.ok(host.audits.every(row=>row.kind==='execution_policy_tool_rejected' && row.backend_called===false
      && row.policy_sha256===policy.snapshot().policy_sha256));
  }
});

test('baseline保留primitive原调用；legacy仍保留历史组合兼容',async()=>{
  for (const config of [{schema_version:1,strategy:'baseline_steps'},undefined]) {
    const policy=new ExecutionPolicy(config),host=hostFixture();
    for (const name of ['render_deck','revise_deck','inspect_deck','validate_deck','deliver_deck','read_source'])
      assert.equal(await policy.dispatch(host,name,{}),undefined);
    if (config===undefined) assert.equal(await policy.dispatch(host,'build_delivery',{}),undefined);
    assert.deepEqual(host.calls,[]); assert.deepEqual(host.audits,[]);
  }
});

test('Ours收到原primitive计划时必调用既有宿主脚本，返回真实回执，原计划不变',async()=>{
  const policy=new ExecutionPolicy({schema_version:1,strategy:'host_delivery'}),host=hostFixture();
  const plan={title:'Semantic decision retained',slides:[{title:'Actual source',sources:[{source_id:'approved',page:1}]}]},copy=structuredClone(plan);
  const result=await policy.dispatch(host,'render_deck',{plan});
  assert.deepEqual(plan,copy);assert.deepEqual(host.calls,[['guard'],['renderDelivery',plan],['guard']]);
  assert.equal(result.delivered,true);assert.equal(result.deck_id,host.response.deck_id);
  assert.equal(result.execution_policy.host_script,'render_delivery');
  assert.equal(result.execution_policy.model_selected_script,false);
  assert.deepEqual(host.audits.map(row=>row.kind),['host_script_started','host_script_completed']);
  assert.equal(host.audits[0].script_execution_id,host.audits[1].script_execution_id);
  assert.equal(host.audits[1].result_sha256,digest(host.response));assert.equal(host.audits[1].fallback_required,false);
});

test('明确修订通过同一已有脚本；不自动选择页面、生成变化或转成别的工具',async()=>{
  const policy=new ExecutionPolicy({schema_version:1,strategy:'host_delivery'}),host=hostFixture();
  const updates=[{page:3,changes:{title:'Explicit new title'}}],copy=structuredClone(updates);
  const result=await policy.dispatch(host,'revise_deck',{deck_id:'persisted-deck',updates});
  assert.deepEqual(updates,copy);assert.deepEqual(host.calls,[['guard'],['reviseDelivery','persisted-deck',updates],['guard']]);
  assert.equal(result.execution_policy.host_script,'revise_delivery');
  assert.equal(host.calls.length,3);
});

test('风格转换由相同宿主finish核验，明确合法来源模板，拒绝语义重写和隐式模板',async()=>{
  const policy=new ExecutionPolicy({schema_version:1,strategy:'host_delivery'}),host=hostFixture();
  for (const args of [{source_id:'actual'},{source_id:'actual',template:'other'},
    {source_id:4,template:'lab'},{source_id:'actual',template:['lab']},{source_id:'actual',template:'lab',rewrite:true}])
    await assert.rejects(()=>policy.dispatch(host,'restyle_deck',args),{code:'invalid_arguments'});
  assert.deepEqual(host.calls,[]);
  const result=await policy.dispatch(host,'restyle_deck',{source_id:'actual',template:'lab'});
  assert.deepEqual(host.calls,[['guard'],['restyleDelivery','actual','lab'],['guard']]);
  assert.equal(result.execution_policy.host_script,'restyle_delivery');
  assert.deepEqual(result.execution_policy.backend_steps,['restyle_deck','inspect_deck','validate_deck','deliver_deck']);
});

test('脚本失败与验证不合格明确回退，没有重试或内容修订',async()=>{
  const policy=new ExecutionPolicy({schema_version:1,strategy:'host_delivery'}),failed=hostFixture();
  failed.renderDelivery=async()=>{failed.calls.push(['failure']);throw new AdapterRejected('backend_tool_failed','Actual rejection.');};
  await assert.rejects(()=>policy.dispatch(failed,'render_deck',{plan:{}}),{code:'backend_tool_failed'});
  assert.equal(failed.calls.filter(row=>row[0]==='failure').length,1);
  assert.deepEqual(failed.audits.map(row=>row.kind),['host_script_started','host_script_failed']);
  assert.equal(failed.audits[1].automatic_retry,false);
  const incomplete=hostFixture();incomplete.renderDelivery=async()=>({delivered:false,passed:false,automatic_retry:false});
  const result=await policy.dispatch(incomplete,'render_deck',{plan:{}});
  assert.equal(result.delivered,false);assert.equal(incomplete.audits[1].fallback_required,true);
});

test('参数和版本拒绝发生在宿主脚本前；未执行不伪造completed证据',async()=>{
  const policy=new ExecutionPolicy({schema_version:1,strategy:'host_delivery'}),host=hostFixture();
  for (const [name,args] of [['render_deck',{}],['render_deck',{plan:{},retry:true}],
    ['revise_deck',{deck_id:4,updates:[]}],['revise_deck',{deck_id:'bad\u0000',updates:[]}],
    ['revise_deck',{deck_id:'ok',updates:[],rewrite:'all'}]])
    await assert.rejects(()=>policy.dispatch(host,name,args),{code:'invalid_arguments'});
  assert.deepEqual(host.calls,[]); assert.deepEqual(host.audits,[]);
  host.guard=async()=>{throw new AdapterRejected('source_version_changed','Source changed.');};
  await assert.rejects(()=>policy.dispatch(host,'render_deck',{plan:{}}),{code:'source_version_changed'});
  assert.deepEqual(host.calls,[]);assert.deepEqual(host.audits,[]);
});
