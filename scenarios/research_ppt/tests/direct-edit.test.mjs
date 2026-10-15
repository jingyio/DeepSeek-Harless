/** 输入/合并/凭证边界的协议回归；真实 MCP+LO 交付另由服务器实验验证。 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { directEditEnvironment, executeExplicitRevision, parseDirectEditArgs, previewExplicitUpdates } from '../dist/direct-edit-cli.js';
import { ExecutionPolicy } from '../dist/execution-policy.js';

const sha='a'.repeat(64);
const args=['--job','.local/jobs/current/job.json','--deck-id','real-deck-id','--updates','.local/edit.json'];
const fixture=()=>({title:'Persisted original',template:'academic',slides:[
  {title:'Keep',bullets:['Keep fact'],sources:[{source_id:'approved',page:1}],notes:'Keep notes'},
  {title:'Change',bullets:['Explicit fact'],sources:[{source_id:'approved',page:2}],notes:'Original conditions'}]});

test('默认预览；执行必须是明确 apply 加预览版本，拒绝外部 PPT 和自然语言参数',()=>{
  assert.equal(parseDirectEditArgs(args).apply,false);
  assert.throws(()=>parseDirectEditArgs([...args,'--apply']),{code:'expected_version_required'});
  const apply=parseDirectEditArgs([...args,'--apply','--expect-sha256',sha]);
  assert.equal(apply.apply,true); assert.equal(apply.expectedSha256,sha);
  for (const extra of [['--pptx','external.pptx'],['--instruction','make it better'],['--deck-id','other'],['--apply','--apply'],['--expect-sha256','A'.repeat(64)]])
    assert.throws(()=>parseDirectEditArgs([...args,...extra]),{code:'invalid_arguments'});
});

test('只合并明确字段，原计划、来源、notes 和非目标页保持；生成准确预览',()=>{
  const original=fixture(), copy=structuredClone(original);
  const preview=previewExplicitUpdates(original,[{page:2,changes:{title:'Explicit new title'}}],2);
  assert.deepEqual(original,copy); assert.deepEqual(preview.plan.slides[0],original.slides[0]);
  assert.deepEqual(preview.plan.slides[1],{...original.slides[1],title:'Explicit new title'});
  assert.deepEqual(preview.changedPages,[2]);
  assert.deepEqual(preview.differences,[{page:2,field:'title',before:'Change',after:'Explicit new title',removed:false}]);
});

test('页号重复、错误类型、未知操作和容量溢出在写调用前拒绝',()=>{
  for (const changes of [[{page:0,changes:{title:'new'}}],[{page:'2',changes:{title:'new'}}],
    [{page:2,changes:{title:'new'}},{page:2,changes:{title:'other'}}],
    [{page:2,changes:{auto_rewrite:true}}],[{page:2,changes:{title:null}}],
    [{page:2,changes:{title:'x'.repeat(71)}}],[{page:2,changes:{notes:'bad\u0000text'}}],
    [{page:2,changes:{table:[['A','B'],['x']]}}]]) assert.throws(()=>previewExplicitUpdates(fixture(),changes,2));
  assert.throws(()=>previewExplicitUpdates(fixture(),[{page:2,changes:{title:'Change'}}],2),{code:'no_changes'});
});

test('移除媒体必须显式 null 且同步布局，不能静默删除图片',()=>{
  const plan=fixture(); plan.slides[1].layout='image'; plan.slides[1].image={source_id:'approved',image_id:'approved-image'};
  assert.throws(()=>previewExplicitUpdates(plan,[{page:2,changes:{layout:'content'}}],2));
  const preview=previewExplicitUpdates(plan,[{page:2,changes:{layout:'content',image:null}}],2);
  assert.equal(preview.plan.slides[1].image,undefined); assert.ok(plan.slides[1].image);
  assert.ok(preview.differences.find(x=>x.field==='image' && x.removed));
});

test('字体白名单跨 stdio 边界；API 凭证和任意 NODE_OPTIONS 不传入后端',()=>{
  const env=directEditEnvironment('/project/.venv/bin/python',{FONTCONFIG_FILE:'/project/fonts.conf',FONTCONFIG_PATH:'/project/fonts',
    DEEPSEEK_API_KEY:'must-not-copy',OPENAI_API_KEY:'must-not-copy',NODE_OPTIONS:'--require untrusted.js'});
  assert.equal(env.SSS_PPT_DELIVERY_PYTHON,'/project/.venv/bin/python');
  assert.equal(env.FONTCONFIG_FILE,'/project/fonts.conf'); assert.equal(env.FONTCONFIG_PATH,'/project/fonts');
  for (const key of ['DEEPSEEK_API_KEY','OPENAI_API_KEY','NODE_OPTIONS']) assert.equal(env[key],undefined);
});

test('CLI 坏参数以可解析拒绝结果退出，不启动 MCP 或打印未捕获堆栈',()=>{
  const script=fileURLToPath(new URL('../dist/direct-edit-cli.js',import.meta.url));
  const result=spawnSync(process.execPath,[script,...args,'--apply'],{encoding:'utf8'});
  assert.equal(result.status,2); const output=JSON.parse(result.stderr.trim());
  assert.equal(output.code,'expected_version_required'); assert.equal(output.model_requests,0);
  assert.equal(output.provider_called,false); assert.equal(result.stdout,'');
});

function revisionResponses() {
  const version='b'.repeat(64),audit={passed:true,non_target_slides_preserved:true,shared_styles_preserved:true,slide_count:2,changed_pages:[2]};
  const deck={deck_id:'new-copy',parent_deck_id:'original',file_sha256:sha,input_version:version,slide_count:2,
    each_slide_has_editable_text:true,revision_audit:audit};
  return {version,responses:{revise_deck:structuredClone(deck),inspect_deck:structuredClone(deck),
    validate_deck:{...structuredClone(deck),passed:true,validation_id:'actual-validation'},
    deliver_deck:{deck_id:'new-copy',validation_id:'actual-validation',file_sha256:sha,input_version:version,editable:true,artifacts:[]}}};
}

test('明确CLI遵守baseline原子步骤，不选择被禁止的组合入口，也不调用模型',async()=>{
  const {version,responses}=revisionResponses(),calls=[];
  const call=async(name,args)=>{calls.push({name,args});return structuredClone(responses[name]);};
  const updates=[{page:2,changes:{title:'Explicit'}}],result=await executeExplicitRevision(call,
    new ExecutionPolicy({schema_version:1,strategy:'baseline_steps'}),'original',updates,2,version);
  assert.deepEqual(calls.map(x=>x.name),['revise_deck','inspect_deck','validate_deck','deliver_deck']);
  assert.deepEqual(calls[0].args,{deck_id:'original',updates});
  assert.equal(result.delivered,true);assert.equal(result.parent_deck_id,'original');
  assert.equal(result.revision_audit.non_target_slides_preserved,true);
});

test('host策略明确CLI仅用revise_deck，核验实际宿主策略，不重复已完成步骤',async()=>{
  const policy=new ExecutionPolicy({schema_version:1,strategy:'host_delivery'}),{version,responses}=revisionResponses(),calls=[];
  const delivered={...responses.deliver_deck,delivered:true,parent_deck_id:'original',revision_audit:responses.revise_deck.revision_audit,
    execution_policy:{policy_sha256:policy.snapshot().policy_sha256,request_tool:'revise_deck',host_script:'revise_delivery'}};
  const call=async(name,args)=>{calls.push({name,args});return structuredClone(delivered);};
  assert.equal((await executeExplicitRevision(call,policy,'original',[{page:2,changes:{title:'Explicit'}}],2,version)).delivered,true);
  assert.deepEqual(calls.map(x=>x.name),['revise_deck']);
  for (const mutation of [row=>row.delivered=false,row=>delete row.execution_policy,row=>row.execution_policy.policy_sha256='c'.repeat(64),
    row=>row.execution_policy.host_script='other']) {
    const value=structuredClone(delivered);mutation(value);
    await assert.rejects(()=>executeExplicitRevision(async()=>value,policy,'original',[{page:2,changes:{title:'Explicit'}}],2,version),
      {code:'delivery_contract_rejected'});
  }
});

test('baseline明确CLI在修订、版本、真实渲染失败处停止，不盲目继续验收',async()=>{
  const policy=new ExecutionPolicy({schema_version:1,strategy:'baseline_steps'}),updates=[{page:2,changes:{title:'Explicit'}}];
  for (const [stage,mutate,expected] of [
    ['revise_deck',row=>row.revision_audit.non_target_slides_preserved=false,'revision_contract_rejected'],
    ['revise_deck',row=>row.input_version='c'.repeat(64),'revision_contract_rejected'],
    ['inspect_deck',row=>row.file_sha256='c'.repeat(64),'deck_contract_rejected'],
    ['validate_deck',row=>row.passed=false,'validation_contract_rejected'],
    ['validate_deck',row=>row.validation_id='','validation_contract_rejected'],
    ['deliver_deck',row=>row.validation_id='other','delivery_contract_rejected']]) {
    const {version,responses}=revisionResponses(),calls=[];mutate(responses[stage]);
    await assert.rejects(()=>executeExplicitRevision(async name=>{calls.push(name);return structuredClone(responses[name]);},
      policy,'original',updates,2,version),{code:expected});
    assert.equal(calls.at(-1),stage);
  }
});

test('没有冻结策略的历史明确CLI仍走原revise_delivery，不能把兼容路径称为host接管',async()=>{
  const calls=[];
  const result=await executeExplicitRevision(async name=>{calls.push(name);return {delivered:true};},
    new ExecutionPolicy(undefined),'original',[{page:2,changes:{title:'Explicit'}}],2,'b'.repeat(64));
  assert.deepEqual(calls,['revise_delivery']);assert.equal(result.execution_policy,undefined);
});
