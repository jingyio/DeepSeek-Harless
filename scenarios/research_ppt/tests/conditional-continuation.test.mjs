/** 纯协议正反例夹具，不是正常模型轨迹、真实认证或费用收益证据。 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { conditionalDigest as digest, validateConditionalCandidate, validateConditionalGuard,
  proposeConditionalContinuation as propose, verifyConditionalResult as verify, REQUIRED_NEGATIVE_CASES }
  from '../dist/conditional-continuation.js';

const PIN='mcp__ppt__pin_deck_pages', READ='mcp__ppt__read_pinned_deck_pages', INSPECT='mcp__ppt__inspect_deck';
const h=x=>x.repeat(64), copy=x=>structuredClone(x);
function seal(x,key) { const body=Object.fromEntries(Object.entries(x).filter(([k])=>k!==key)); return {...body,[key]:digest(body)}; }
const str={type:'string',minLength:1,maxLength:500};
const schema=(properties,required)=>({type:'object',properties,required,additionalProperties:false});
function fixture() {
  const candidate=seal({schema_version:1,primitive_version:'ppt-conditional-read-v1',candidate_id:'protocol-fixture',origin:'learned',
    anchor:{tool:INSPECT,input_version_field:'input_version',predicate:{op:'field_equals',field:'each_slide_has_editable_text',value:true}},
    branches:{on_equal:[{id:'pin',tool:PIN,bindings:{deck_id:{from:'task',field:'deck_id'},pages_csv:{from:'task',field:'pages_csv'}},output_contract:'pinned_pages'},
      {id:'read',tool:READ,bindings:{source_id:{from:'node',node_id:'pin',field:'source_id'}},output_contract:'read_pages'}],on_unequal:[]},
    contracts:{[INSPECT]:{read_only:true,replay_stable:true,input_schema:schema({deck_id:str},['deck_id'])},
      [PIN]:{read_only:true,replay_stable:true,input_schema:schema({deck_id:str,pages_csv:{type:'string',minLength:1,maxLength:89,
        pattern:'^[1-9][0-9]?(?:,[1-9][0-9]?){0,29}$'}},['deck_id','pages_csv'])},
      [READ]:{read_only:true,replay_stable:true,input_schema:schema({source_id:str},['source_id'])}},
    dependencies:{backend:h('b'),protocol:h('c')},training:{task_fingerprints:['train-one','train-two'],trace_sha256:[h('1'),h('2')]}},'candidate_digest');
  const task={schema_version:1,session_id:'session-one',task_fingerprint:'heldout-new-task',input_version:h('d'),deck_id:'deck-real',
    deck_sha256:h('e'),pages_csv:'2,5',job_sha256:h('f'),permission_sha256:h('a'),dependencies:copy(candidate.dependencies),
    allowed_tools:[INSPECT,PIN,READ]};
  const admission=seal({schema_version:1,certifier:'python-independent-v1',status:'passed',candidate_digest:candidate.candidate_digest,
    training_task_fingerprints:copy(candidate.training.task_fingerprints),validation_task_fingerprints:['independent-certification'],
    validation_evidence_sha256:[h('3')],branches_tested:['on_equal','on_unequal'],negative_cases:[...REQUIRED_NEGATIVE_CASES]},'certificate_digest');
  const history=[{name:INSPECT,callId:'anchor-one',ok:true,arguments:{deck_id:task.deck_id},inputVersion:task.input_version,
    output:{deck_id:task.deck_id,file_sha256:task.deck_sha256,input_version:task.input_version,each_slide_has_editable_text:true}}];
  const availableTools=new Map(Object.entries(candidate.contracts).map(([name,c])=>[name,{parameters:copy(c.input_schema),annotations:{readOnlyHint:true}}]));
  return {candidate,task,liveGuard:copy(task),admission,history,availableTools,mode:'execute'};
}
function pinned(f,source='actual-returned-handle') { return {source_id:source,deck_id:f.task.deck_id,file_sha256:f.task.deck_sha256,
  version_sha256:f.task.input_version,pages_csv:f.task.pages_csv,scope:'explicit_pages_from_current_persisted_plan'}; }
function read(f,source='actual-returned-handle') { return {source_id:source,deck_id:f.task.deck_id,file_sha256:f.task.deck_sha256,
  version_sha256:f.task.input_version,total_slides:6,slides:[{page:2,slide:{title:'Second'}},{page:5,slide:{title:'Fifth'}}],
  scope:'explicit_pages_only_no_semantic_selection'}; }
function witnessPin(f,output=pinned(f)) { f.history.push({name:PIN,callId:'pin-one',ok:true,
  arguments:{deck_id:f.task.deck_id,pages_csv:f.task.pages_csv},output,inputVersion:f.task.input_version}); }

test('默认关闭；候选自称 learned 不授权执行；无证书只能 shadow',()=>{
  const f=fixture(); assert.equal(propose({...f,mode:undefined}).reason,'disabled');
  assert.equal(propose({...f,admission:undefined}).reason,'independent_admission_required');
  const shadow=propose({...f,admission:undefined,mode:'shadow'});
  assert.equal(shadow.kind,'shadow'); assert.equal(shadow.reason,'uncertified_shadow');
  assert.equal(shadow.proposals[0].validation_task_fingerprint,'uncertified-shadow');
});
test('两个分支：可编辑时只提出 pin；不满足条件时交回语义层',()=>{
  const f=fixture(); const p=propose(f);
  assert.equal(p.kind,'propose'); assert.equal(p.proposals.length,1); assert.equal(p.proposals[0].tool,PIN);
  assert.deepEqual(p.proposals[0].arguments,{deck_id:'deck-real',pages_csv:'2,5'});
  f.history[0].output.each_slide_has_editable_text=false;
  assert.deepEqual(propose(f),{kind:'abstain',reason:'condition_deferred'});
});
test('缺少/错误类型状态不能视作 false；错误 deck 或冲突页范围不能择分支',()=>{
  for(const change of [x=>delete x.history[0].output.each_slide_has_editable_text,
    x=>x.history[0].output.each_slide_has_editable_text='true',x=>x.history[0].output.deck_id='foreign',
    x=>x.history[0].arguments.deck_id='foreign',x=>x.history[0].arguments.pages_csv='2,6']) {
    const f=fixture();change(f);assert.equal(propose(f).kind,'abstain');
  }
});
test('依赖来自实际观察，只在 pin 返回后绑定 source_id，完成后不伪造空请求',()=>{
  const f=fixture(); witnessPin(f);const p=propose(f);
  assert.equal(p.proposals[0].tool,READ); assert.deepEqual(p.proposals[0].arguments,{source_id:'actual-returned-handle'});
  f.history.push({name:READ,callId:'read-one',ok:true,arguments:p.proposals[0].arguments,output:read(f)});
  assert.deepEqual(propose(f),{kind:'abstain',reason:'branch_complete'});
});
test('实际结果核验要求相同来源、页序、句柄、版本与授权快照',()=>{
  const f=fixture();witnessPin(f);const p=propose(f).proposals[0], exec={name:p.tool,arguments:p.arguments};
  assert.equal(verify(p,exec,read(f),f.liveGuard).verified,true);
  for(const mutate of [o=>o.deck_id='foreign',o=>o.file_sha256=h('0'),o=>o.version_sha256=h('0'),
    o=>o.source_id='other-handle',o=>o.slides.reverse(),o=>o.slides.pop(),o=>o.isError=true]) {
    const output=read(f);mutate(output);assert.equal(verify(p,exec,output,f.liveGuard).verified,false);
  }
  assert.equal(verify(p,{...exec,arguments:{source_id:'foreign'}},read(f),f.liveGuard).verified,false);
  assert.equal(verify(p,exec,read(f),{...f.liveGuard,permission_sha256:h('0')}).verified,false);
});
test('pin 结果错误或冲突时停止子图，不重读不完整句柄',()=>{
  for(const alter of [o=>delete o.source_id,o=>o.pages_csv='2,6',o=>o.file_sha256=h('0'),o=>o.scope='full_document']) {
    const f=fixture(),output=pinned(f);alter(output);witnessPin(f,output);
    assert.equal(propose(f).reason,'conflicting_or_failed_result');
  }
  const f=fixture();witnessPin(f);witnessPin(f,pinned(f,'different-handle'));
  assert.equal(propose(f).reason,'conflicting_or_failed_result');
});
test('权限、job、隐藏实现依赖、文件版本变化全部弃权',()=>{
  for(const mutate of [g=>g.permission_sha256=h('0'),g=>g.job_sha256=h('0'),g=>g.deck_sha256=h('0'),
    g=>g.dependencies.backend=h('0'),g=>g.allowed_tools.pop(),g=>g.pages_csv='2,6']) {
    const f=fixture();mutate(f.liveGuard);assert.equal(propose(f).reason,'live_guard_changed');
  }
  const f=fixture();f.task.dependencies.backend=h('0');f.liveGuard=copy(f.task);
  assert.equal(propose(f).reason,'dependency_changed');
});
test('实际 schema 变化/权限移除不得只凭工具名称旁路',()=>{
  const f=fixture();f.availableTools.get(PIN).parameters.properties.pages_csv.maxLength=88;
  assert.equal(propose(f).reason,'permission_or_schema_changed');
  const g=fixture();g.task.allowed_tools=g.task.allowed_tools.filter(x=>x!==READ);g.liveGuard=copy(g.task);
  assert.equal(propose(g).reason,'permission_or_schema_changed');
  const j=fixture();j.availableTools.get(PIN).annotations.readOnlyHint=false;
  assert.equal(propose(j).reason,'permission_or_schema_changed');
});
test('工具失败和写操作屏障不跨越；相同前缀不重复提出',()=>{
  const f=fixture();const p=propose(f).proposals[0];
  assert.equal(propose({...f,usedPrefixes:new Set([p.prefix_key])}).reason,'already_attempted');
  f.history.push({name:'mcp__ppt__revise_delivery',ok:true,barrier:true,arguments:{},output:{}});
  assert.equal(propose(f).reason,'missing_anchor');
  const g=fixture();g.history[0].ok=false; assert.equal(propose(g).reason,'anchor_scope_conflict');
});
test('候选写调用、前向依赖、额外字段及篡改摘要被协议拒绝',()=>{
  for(const mutate of [c=>c.branches.on_equal[0].tool='mcp__ppt__revise_delivery',
    c=>c.branches.on_equal[1].bindings.source_id.node_id='future',c=>c.code='arbitrary()',
    c=>c.training.task_fingerprints=['one'],c=>c.branches.on_equal.push(copy(c.branches.on_equal[0]))]) {
    const f=fixture();mutate(f.candidate);f.candidate=seal(f.candidate,'candidate_digest');
    assert.throws(()=>validateConditionalCandidate(f.candidate));
  }
  const f=fixture();f.candidate.anchor.predicate.value=false;assert.throws(()=>validateConditionalCandidate(f.candidate));
  assert.throws(()=>validateConditionalGuard({...f.task,pages_csv:'2,2'}));
});
test('训练不充当独立认证；一条留出边不充当条件图认证',()=>{
  for(const mutate of [a=>a.validation_task_fingerprints=['train-one'],a=>a.branches_tested=['on_equal'],
    a=>a.negative_cases.pop(),a=>a.training_task_fingerprints=['other-training'],a=>a.validation_evidence_sha256=[]]) {
    const f=fixture();mutate(f.admission);f.admission=seal(f.admission,'certificate_digest');
    assert.equal(propose(f).reason,'independent_admission_required');
  }
  const f=fixture();f.admission.status='failed';assert.equal(propose(f).reason,'independent_admission_required');
});
test('manual B1 使用相同协议，工程来源与学得来源可明确区分',()=>{
  const f=fixture();f.candidate.origin='manual';f.candidate.training={task_fingerprints:[],trace_sha256:[]};
  f.candidate=seal(f.candidate,'candidate_digest');f.admission.candidate_digest=f.candidate.candidate_digest;
  f.admission.training_task_fingerprints=[];f.admission=seal(f.admission,'certificate_digest');
  validateConditionalCandidate(f.candidate);assert.equal(propose(f).kind,'propose');
  assert.equal(propose(f).proposals[0].supporting_task_count,0);
});
