import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {installNativePptChat,nativePptOptions,publicPptTurn} from '../dist/native-chat.js';
const digest=value=>createHash('sha256').update(JSON.stringify(value)).digest('hex');
function fixture(t){
  const output=mkdtempSync(join(tmpdir(),'ppt-native-')),events=[],effects=[],calls=[];
  const agent={session:{id:'owner',append:(type,data)=>events.push({type,data}),snapshotEvents:()=>events}};
  const row={task_id:'ppt',status:'awaiting_confirmation',confirmation_digest:'frozen',current_version:'v0',
    current_decks:{},results:{},feedback:[],artifacts:[],budget_usd_total:3};
  const refs=new Map([['file',{name:'paper.pdf',bytes:3}]]);
  const ctx={agents:{get:id=>id==='owner'?agent:undefined},sessionController:{},
    fileUploads:{resolve:(a,id)=>a===agent?refs.get(id):undefined,bindPrompt:()=>({commit(){},[Symbol.dispose](){}})},
    attachments:{readFileStream:async function*(){yield Buffer.from('pdf');},admitPromptContent:async c=>c},
    effect:fn=>effects.push(fn()),connection:{fetch:{register:r=>{ctx.route=r;return()=>{};}}}};
  const service={busy:()=>Boolean(row.execution_busy),view:async()=>structuredClone(row),importFile:async(name,stream,bytes)=>{for await(const _ of stream){}return{id:'imported',name,bytes};},
    command:async raw=>{calls.push(raw);if(raw.action==='submit')row.status='running';if(raw.action==='message')row.feedback.push({request_id:raw.request_id,status:'running'});return structuredClone(row);}};
  const api=installNativePptChat(ctx,{output},service,id=>id==='owner');
  t.after(()=>{for(const f of effects)if(typeof f==='function')f();rmSync(output,{recursive:true,force:true});});
  return{api,ctx,agent,row,events,calls,service,output};
}
const prompt=(text='生成科研PPT',file=true,id='request-1')=>({requestId:id,content:[{type:'text',text},...(file?[{type:'file',receiptId:'file'}]:[])]});
test('默认15页和单PPTX复用；不同页数或越界拒绝',()=>{
  assert.equal(nativePptOptions('生成PPT',['x.pdf']).slides,15);
  assert.equal(nativePptOptions('做成18页',['x.pdf']).slides,18);
  assert.equal(nativePptOptions('做成18页，第4页讲方法',['x.pdf']).slides,18);
  assert.equal(nativePptOptions('改风格',['x.pptx']).operation,'restyle');
  assert.throws(()=>nativePptOptions('生成31页',['x.pdf']));assert.throws(()=>nativePptOptions('15页或20页',['x.pdf']));
});
test('发送即自动执行；内部冻结与重复请求守卫保留',async t=>{
  const f=fixture(t);await f.api.start(f.agent,prompt());await f.api.start(f.agent,prompt());
  assert.deepEqual(f.calls.map(x=>x.action),['preview','submit']);assert.equal(f.events.filter(e=>e.type==='user/message').length,1);
  const v=await f.api.view('owner');await assert.rejects(f.api.confirm('owner',v.id,'changed'));
  await f.api.confirm('owner',v.id,digest(v.preview));await f.api.confirm('owner',v.id,digest(v.preview));
  assert.deepEqual(f.calls.map(x=>x.action),['preview','submit']);
  await assert.rejects(f.api.start(f.agent,prompt('换需求',true,'request-1')));
  await assert.rejects(f.api.start(f.agent,prompt('继续',false,'request-2')));
});
test('官方回执必须属于当前会话；外来会话和任务拒绝',async t=>{
  const f=fixture(t);await assert.rejects(f.api.start(f.agent,{requestId:'foreign',content:[{type:'file',receiptId:'foreign'}]}));
  await assert.rejects(f.api.view('other'));assert.equal(f.calls.length,0);assert.equal(f.events.length,0);
});
test('同稿反馈发送即执行，携带版本；对照失败不阻断优化稿',async t=>{
  const f=fixture(t);await f.api.start(f.agent,prompt());
  f.row.status='failed';f.row.results.optimized={mechanical_delivery_verified:true};f.row.current_decks={optimized:{sha256:'o'}};await f.api.view('owner');
  await f.api.start(f.agent,prompt('第4页简洁一些',false,'feedback-1'));const v=await f.api.view('owner');
  assert.equal(v.kind,'feedback');assert.equal(v.parent_version,'v0');assert.equal(f.calls.length,3);
  await f.api.confirm('owner',v.id,digest(v.preview));assert.equal(f.calls.at(-1).action,'message');assert.equal(f.calls.at(-1).expected_version,'v0');
  await assert.rejects(f.api.start(f.agent,prompt('生成另一篇',true,'new-1')));
});
test('取消等待中的生成不会提交；未交付稿不能改页',async t=>{
  const f=fixture(t);f.row.execution_busy=true;await f.api.start(f.agent,prompt());let v=await f.api.view('owner');await f.api.cancel('owner',v.id);
  assert.equal(f.api.hasSession('owner'),false);assert.equal(f.calls.some(x=>x.action==='submit'),false);
  f.row.execution_busy=false;await f.api.start(f.agent,prompt('重试',true,'new-request'));v=await f.api.view('owner');
  f.row.status='failed';await f.api.view('owner');await f.api.start(f.agent,prompt('第4页修改',false,'failed-feedback'));
  assert.equal((await f.api.view('owner')).status,'failed');assert.equal(f.calls.some(x=>x.action==='message'),false);
});
test('持久映射恢复不会重复执行；其他Session仍不能认领',async t=>{
  const f=fixture(t);await f.api.start(f.agent,prompt());const before=await f.api.view('owner');
  const restored=installNativePptChat(f.ctx,{output:f.output},f.service,id=>id==='owner');
  assert.equal(restored.hasSession('owner'),true);assert.equal((await restored.view('owner')).id,before.id);
  await assert.rejects(restored.view('other',before.id));assert.equal(f.calls.length,2);
});

test('优化稿先交付，后续反馈等待内部收尾；并发轮询只提交一次',async t=>{
  const f=fixture(t);await f.api.start(f.agent,prompt());
  f.row.execution_busy=true;f.row.results.optimized={mechanical_delivery_verified:true};f.row.current_decks={optimized:{sha256:'o'}};
  assert.equal((await f.api.view('owner')).status,'completed');
  await f.api.start(f.agent,prompt('第4页精简',false,'feedback-early'));assert.equal((await f.api.view('owner')).status,'queued');
  assert.equal(f.calls.filter(c=>c.action==='message').length,0);
  f.row.execution_busy=false;f.row.status='completed';f.row.current_version='v1';
  await Promise.all([f.api.view('owner'),f.api.view('owner')]);
  assert.equal(f.calls.filter(c=>c.action==='message').length,1);assert.equal(f.calls.at(-1).expected_version,'v1');
});

test('等待期间优化稿变化会拒绝执行，避免改错版本',async t=>{
  const f=fixture(t);await f.api.start(f.agent,prompt());f.row.execution_busy=true;
  f.row.results.optimized={mechanical_delivery_verified:true};f.row.current_decks={optimized:{sha256:'o'}};await f.api.view('owner');
  await f.api.start(f.agent,prompt('第4页改标题',false,'feedback-stale'));f.row.current_decks.optimized.sha256='changed';f.row.execution_busy=false;
  assert.equal((await f.api.view('owner')).status,'failed');assert.equal(f.calls.filter(c=>c.action==='message').length,0);
});

test('用户投影没有对照、费用、原始日志与脚本；只显示当前优化稿',()=>{
  const result=publicPptTurn({id:'turn',kind:'feedback',status:'completed',preview:{budget_usd_total:3},task:{slides:15,
    current_decks:{optimized:{version:1},baseline:{version:0}},cumulative:{proxy_model_usd:1},
    artifacts:[{id:'o',group:'optimized',version:1,kind:'pptx',name:'deck.pptx',download_url:'/download/o',path:'/private'},
      {id:'old',group:'optimized',version:0,kind:'pptx'}, {id:'b',group:'baseline',version:0,kind:'pptx'}],
    feedback:[{request_id:'turn',results:{optimized:{reply:'第4页已修改。\n使用 mcp__ppt__revise_deck\n费用 $0.01',accounting:{upstream_requests:2}},baseline:{reply:'内部结果'}}}]}});
  assert.equal(result.reply,'第4页已修改。');assert.deepEqual(result.delivery.artifacts.map(a=>a.id),['o']);
  for(const word of ['baseline','accounting','budget','proxy','private','mcp__'])assert.equal(JSON.stringify(result).includes(word),false);
});
