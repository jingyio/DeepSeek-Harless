/** 确定性权限/恢复诊断；不替代服务器上的真实 DeepSeek 连续反馈验收。 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { Readable } from 'node:stream';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { explicitFeedbackPages, feedbackRunDirectory } from '../dist/feedback-runner.js';
import { createHash } from 'node:crypto';
import { assertRevisionScope } from '../dist/feedback-mcp.js';
import { installPptWeb } from '../dist/web-tasks.js';

test('反馈支持单页、多页、范围、全稿；范围未知不扩大，越界拒绝',()=>{
  assert.deepEqual(explicitFeedbackPages('第4页精简',15),[4]);
  assert.deepEqual(explicitFeedbackPages('第4、5页，及第7页',15),[4,5,7]);
  assert.deepEqual(explicitFeedbackPages('第4到6页',15),[4,5,6]);
  assert.deepEqual(explicitFeedbackPages('全部页面',3),[1,2,3]);
  assert.deepEqual(explicitFeedbackPages('方法页精简',15),[]);
  assert.deepEqual(explicitFeedbackPages('为什么N=6？',15),[]);
  for(const text of ['第0页','第16页','第5至4页'])assert.throws(()=>explicitFeedbackPages(text,15));
});
test('修订工具拒绝其他稿件、未授权页、空范围和额外控制参数',()=>{
  const update={page:4,changes:{title:'允许的修改'}};
  assert.doesNotThrow(()=>assertRevisionScope({deck_id:'original',updates:[update]},'original',[4]));
  for(const args of [{deck_id:'other',updates:[update]},{deck_id:'original',updates:[{...update,page:5}]},
    {deck_id:'original',updates:[update],command:'override'},{deck_id:'original',updates:[]}])
    assert.throws(()=>assertRevisionScope(args,'original',[4]));
  assert.throws(()=>assertRevisionScope({deck_id:'original',updates:[update]},'original',[]));
});

const root=fileURLToPath(new URL('../../../',import.meta.url));
test('真实Harness运行目录接缝接受目录但核验manifest；文件、目录越界和错任务拒绝',async t=>{
  const parent=join(root,'.local/runs');mkdirSync(parent,{recursive:true});
  const area=mkdtempSync(join(parent,'feedback-regression-'));t.after(()=>rmSync(area,{recursive:true,force:true}));
  const scenario=join(area,'scenario.json');writeFileSync(scenario,'{}');
  const sha=s=>createHash('sha256').update(s).digest('hex');
  writeFileSync(join(area,'manifest.json'),JSON.stringify({config_sha256:sha('{}'),prompt_sha256:sha('actual prompt')}));
  assert.equal(await feedbackRunDirectory(area,scenario,'actual prompt'),resolve(area));
  await assert.rejects(()=>feedbackRunDirectory(area,scenario,'other prompt'));
  await assert.rejects(()=>feedbackRunDirectory(scenario,scenario,'actual prompt'));
  await assert.rejects(()=>feedbackRunDirectory(root,scenario,'actual prompt'));
});
const account=(fee=.01)=>({usage_complete:true,unsettled_request_count:0,observed_proxy_usd:fee,upstream_requests:2});
function fixture(t,feedback=[],accounting=account()) {
  const parent=join(root,'.local','feedback-regression');mkdirSync(parent,{recursive:true});
  const area=mkdtempSync(join(parent,'case-'));t.after(()=>rmSync(area,{recursive:true,force:true}));
  const trial=join(area,'trial.json');writeFileSync(trial,JSON.stringify({groups:{baseline:{job:'unused'},optimized:{job:'unused'}}}));
  const delivery=(group,version)=>({deck_id:group+'-'+version,files:[{kind:'pptx',path:join(area,group+'-'+version+'.pptx'),sha256:'a'.repeat(64)}]});
  writeFileSync(join(area,'comparison.json'),JSON.stringify({results:Object.fromEntries(['baseline','optimized'].map(g=>[g,{status:'completed',mechanical_delivery_verified:true,accounting,deliveries:[delivery(g,0)]}]))}));
  const task={id:'task',status:'completed',version:'current',trial,budget_usd:.5,files:[],instruction:'test',feedback};
  const dir=join(area,'state');mkdirSync(dir);writeFileSync(join(dir,'state.json'),JSON.stringify({receipts:[],tasks:[task],reserved_usd:.5}));
  const routes=new Map();installPptWeb({connection:{requestRejection:()=>null},effect:(fn)=>fn(),webServer:{register:({path,handler})=>{routes.set(path,handler);return()=>{};}}},{output:area,ppt_state_directory:dir,provider_mode:'real',ppt_run_budget_usd:.1});
  async function call(body) {
    const req=Readable.from(body?[Buffer.from(JSON.stringify(body))]:[]);req.method=body?'POST':'GET';req.url='/api/harless/ppt?task_id=task';req.headers={host:'localhost'};
    let status,payload;await routes.get('/api/harless/ppt')(req,{writeHead:s=>{status=s;},end:b=>{payload=JSON.parse(b);}});return{status,payload};
  }
  return{call,dir,delivery};
}
test('只在双方账本完整时释放未用预算；旧版本/无权限字段/预算不足拒绝，不启动模型',async t=>{
  const f=fixture(t),initial=await f.call();assert.equal(initial.status,200);
  assert.equal(initial.payload.budget_scope.reserved_usd,.02);
  const base={action:'message',task_id:'task',message:'第4页修改',request_id:'unique-id',expected_version:'current'};
  for(const raw of [{...base,expected_version:'stale'},{...base,tenant:'other'},{...base,path:'/external'},base]){
    const result=await f.call(raw);assert.equal(result.status,400);
  }
  assert.equal(JSON.parse(readFileSync(join(f.dir,'state.json'))).tasks[0].feedback.length,0);
});
test('费用未知不释放额度，不冒充零费用',async t=>{
  const f=fixture(t,[],{...account(),usage_complete:false}),r=await f.call();
  assert.equal(r.payload.budget_scope.reserved_usd,.5);assert.equal(r.payload.cumulative.proxy_model_usd,null);
});
test('重启恢复最新稿和旧稿；同请求ID幂等，改变同ID消息拒绝，不重付费',async t=>{
  const f=fixture(t,[{id:'turn',request_id:'same-request',message:'第4页精简',parent_version:'old',status:'completed',budget_usd:.5,
    results:{baseline:{status:'delivered',accounting:account(),deliveries:[]},optimized:{status:'delivered',accounting:account(),deliveries:[]}}}]);
  // 持久化回执是当前稿来源，不由浏览器提供路径。
  const saved=JSON.parse(readFileSync(join(f.dir,'state.json')));saved.tasks[0].feedback[0].results.optimized.deliveries=[f.delivery('optimized',1)];
  writeFileSync(join(f.dir,'state.json'),JSON.stringify(saved));
  const recovered=fixture(t,saved.tasks[0].feedback),r=await recovered.call();
  assert.equal(r.payload.current_decks.optimized.deck_id,'optimized-1');
  assert.equal(r.payload.artifacts.filter(a=>a.group==='optimized').length,2);
  const raw={action:'message',task_id:'task',request_id:'same-request',message:'第4页精简',expected_version:'old'};
  const duplicate=await recovered.call(raw);assert.equal(duplicate.status,200);assert.equal(duplicate.payload.feedback.length,1);
  assert.equal((await recovered.call({...raw,message:'第5页修改'})).status,400);
});
test('重启中的反馈标为interrupted，取消/中断产物不得升级当前稿',async t=>{
  const f=fixture(t,[{id:'turn',request_id:'running-request',message:'第4页精简',parent_version:'old',status:'running',budget_usd:.5,
    results:{optimized:{status:'delivered',accounting:account(),deliveries:[{deck_id:'must-not-apply',files:[]}]}}}]);
  const r=await f.call();assert.equal(r.payload.feedback[0].status,'interrupted');assert.equal(r.payload.current_decks.optimized.deck_id,'optimized-0');
});
test('失败和仅回答不占稿件版本号，按实际修订次数递增',async t=>{
  const original=fixture(t),turns=[
    {id:'failed',status:'failed',budget_usd:.5,results:{baseline:{status:'failed',accounting:account()},optimized:{status:'failed',accounting:account()}}},
    {id:'answer',status:'completed',budget_usd:.5,results:{baseline:{status:'answered',accounting:account()},optimized:{status:'answered',accounting:account()}}},
    {id:'revision',status:'completed',budget_usd:.5,results:{baseline:{status:'delivered',accounting:account(),deliveries:[original.delivery('baseline',1)]},optimized:{status:'delivered',accounting:account(),deliveries:[original.delivery('optimized',1)]}}}
  ];
  const recovered=fixture(t,turns),r=await recovered.call();
  assert.equal(r.payload.current_decks.optimized.version,1);
  assert.equal(r.payload.current_decks.baseline.version,1);
});
