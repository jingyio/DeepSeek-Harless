import test from 'node:test';
import assert from 'node:assert/strict';
import { createTaskProgress, taskToolLabel } from '../src/adapters/harless_task_progress.ts';

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
