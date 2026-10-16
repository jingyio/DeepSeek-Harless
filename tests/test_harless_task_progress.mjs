import test from 'node:test';
import assert from 'node:assert/strict';
import { createTaskProgress, taskToolLabel } from '../src/adapters/harless_task_progress.ts';

test('cancelled native assistant messages remain interrupted in live and restored progress', () => {
  const progress = createTaskProgress(); progress.beginAttempt();
  progress.chunk({type:'text-delta',index:0,text:'partial'});
  progress.event({type:'assistant/message',data:{interrupted:true,message:{id:'cancelled-message',content:[{type:'text',text:'partial'}]}}});
  progress.finish('cancelled');
  const value=progress.snapshot();
  assert.equal(value.messages[0].status,'interrupted');
  assert.equal(value.trace.find(row=>row.kind==='assistant').status,'cancelled');
  assert.equal(value.trace.find(row=>row.kind==='request').status,'cancelled');
  assert.deepEqual(createTaskProgress(value).snapshot(),value);
});

test('public answer updates on each real text chunk and block end never doubles text', () => {
  const progress = createTaskProgress(); progress.beginAttempt();
  progress.chunk({ type: 'text-delta', index: 0, text: '正在' });
  assert.equal(progress.snapshot().answer, '正在');
  progress.chunk({ type: 'text-delta', index: 0, text: '回复' });
  assert.equal(progress.snapshot().answer, '正在回复');
  progress.chunk({ type: 'block-end', index: 0, block: { type: 'text', text: '正在回复' } });
  assert.equal(progress.snapshot().answer, '正在回复');
  progress.chunk({ type: 'text-delta', index: 1, text: '第二段' });
  assert.equal(progress.snapshot().answer, '正在回复\n第二段');
  progress.event({ type: 'assistant/message', data: { message: { content: [{ type: 'text', text: '最终内容' }] } } });
  assert.equal(progress.snapshot().answer, '最终内容');
});

test('real tool lifecycle exposes safe activity labels and no raw arguments or reasoning', () => {
  const progress = createTaskProgress();
  progress.chunk({ type: 'reasoning-delta', index: 0, text: 'private reasoning' });
  progress.chunk({ type: 'tool-call-delta', index: 1, name: 'mcp__report__read_data', argumentsDelta: '/home/private' });
  progress.event({ type: 'tool/call', data: { callId: 'a', name: 'mcp__report__read_data', arguments: '/home/private' } });
  assert.equal(progress.snapshot().activity[0].status, 'running');
  progress.event({ type: 'tool/result', data: { message: { source: { callId: 'a' }, content: [{ isError: false }] } } });
  assert.equal(progress.snapshot().activity[0].status, 'completed');
  assert.equal(progress.snapshot().activity[0].label, '读取资料');
  assert.doesNotMatch(JSON.stringify(progress.snapshot()), /private|reasoning|arguments/);
  assert.equal(taskToolLabel('mcp__report__layout_report'), '生成交付文件');
});

test('attempts replace their own streaming answer and failures retain an honest status', () => {
  const progress = createTaskProgress(); progress.beginAttempt();
  progress.chunk({ type: 'text-delta', index: 0, text: 'previous step' });
  progress.beginAttempt(); progress.chunk({ type: 'text-delta', index: 0, text: 'current step' });
  assert.equal(progress.snapshot().answer, 'current step');
  progress.event({ type: 'tool/call', data: { callId: 'a', name: 'analyze' } });
  progress.event({ type: 'tool/result', data: { message: { source: { callId: 'a' }, content: [{ isError: true }] } } });
  assert.equal(progress.snapshot().activity[0].status, 'failed');
  progress.finish('budget_exhausted');
  assert.equal(progress.snapshot().progress.status, 'failed');
  assert.equal(progress.snapshot().progress.label, '处理未完成');
});

test('snapshot mutation, duplicate tool events, and simultaneous tasks remain isolated', () => {
  const a = createTaskProgress(), b = createTaskProgress();
  const call = { type: 'tool/call', data: { callId: 'one', name: 'read_file' } };
  a.event(call); a.event(call);
  assert.equal(a.snapshot().activity.length, 1);
  a.snapshot().activity[0].status = 'failed';
  assert.equal(a.snapshot().activity[0].status, 'running');
  assert.equal(b.snapshot().activity.length, 0);
  a.finish('cancelled'); assert.equal(a.snapshot().activity[0].status, 'cancelled');
  assert.equal(b.snapshot().progress.status, 'running');
});

test('saved progress restores without erasing completed tool activity after restart', () => {
  const first = createTaskProgress();
  first.event({ type: 'tool/call', data: { callId: 'call', name: 'read_data' } });
  first.event({ type: 'tool/result', data: { message: { source: { callId: 'call' }, content: [] } } });
  first.finish('completed');
  const saved = first.snapshot(), restored = createTaskProgress(saved);
  assert.deepEqual(restored.snapshot(), saved);
  saved.activity[0].status = 'failed';
  assert.equal(restored.snapshot().activity[0].status, 'completed');
});

test('separate native assistant explanations survive tools and later model attempts',()=>{
  const p=createTaskProgress(undefined,()=> '2026-10-15T12:00:00.000Z');
  p.beginAttempt();p.chunk({type:'text-delta',index:0,text:'我先读取'});p.chunk({type:'text-delta',index:0,text:'资料。'});
  p.event({type:'assistant/message',data:{message:{id:'a',content:[{type:'text',text:'我先读取资料。'}]}}});
  p.event({type:'tool/call',data:{callId:'read',name:'mcp__report__read_data'}});
  p.event({type:'tool/result',data:{message:{source:{callId:'read'},content:[]}}});
  p.beginAttempt();p.chunk({type:'reasoning-delta',index:0,text:'private internal thought'});
  p.chunk({type:'text-delta',index:1,text:'根据实际数据'});
  assert.deepEqual(p.snapshot().messages.map(row=>row.text),['我先读取资料。','根据实际数据']);
  assert.equal(p.snapshot().messages[1].status,'streaming');
  p.event({type:'assistant/message',data:{message:{id:'b',content:[{type:'text',text:'根据实际数据，结论如下。'}]}}});
  p.event({type:'assistant/message',data:{message:{id:'b',content:[{type:'text',text:'duplicate'}]}}});
  p.finish('completed');
  assert.equal(p.snapshot().messages.length,2);assert.equal(p.snapshot().answer,'根据实际数据，结论如下。');
  assert.ok(p.snapshot().trace.some(row=>row.kind==='thinking'));
  assert.doesNotMatch(JSON.stringify(p.snapshot()),/private internal thought/);
  assert.deepEqual(createTaskProgress(p.snapshot()).snapshot(),p.snapshot());
});

test('only a verified skip audit gets an optimized marker, failed tool errors remain failures',()=>{
  const p=createTaskProgress();
  p.audit({kind:'shadow_candidate',arguments:{path:'/home/private'}});
  p.audit({kind:'motif_bypass_attempt'});
  assert.ok(p.snapshot().trace.every(row=>!row.optimized&&!row.verified_skip));
  p.audit({kind:'model_request_skipped_verified',at:'2026-10-15T12:00:00.000Z'});
  assert.equal(p.snapshot().trace.filter(row=>row.optimized&&row.verified_skip).length,1);
  p.event({type:'tool/call',data:{callId:'exec',name:'exec_command'}});
  p.event({type:'tool/result',data:{error:'private stack',message:{source:{callId:'exec'},content:[]}}});
  assert.equal(p.snapshot().trace.at(-1).status,'failed');assert.equal(p.snapshot().trace.at(-1).label,'运行命令');
  assert.doesNotMatch(JSON.stringify(p.snapshot()),/private|arguments/);
});

test('PPT repair shows real work without claiming a Motif skip',()=>{
 const p=createTaskProgress();p.recovery();
 assert.equal(p.snapshot().progress.label,'正在修正演示文稿');
 assert.equal(p.snapshot().trace.at(-1).kind,'request');
 assert.equal(p.snapshot().trace.at(-1).optimized,false);
 p.beginAttempt();assert.equal(p.snapshot().progress.label,'正在组织回复');
});
