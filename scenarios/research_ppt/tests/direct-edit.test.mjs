/** 输入/合并/凭证边界的协议回归；真实 MCP+LO 交付另由服务器实验验证。 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { directEditEnvironment, parseDirectEditArgs, previewExplicitUpdates } from '../dist/direct-edit-cli.js';

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
