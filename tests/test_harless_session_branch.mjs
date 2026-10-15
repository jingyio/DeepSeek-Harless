import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { completedBranchPrefix, branchTitleRoot, sessionBranchTitle, createSessionBranchService } from '../src/adapters/harless_session_branch.ts';

const event = (type, seq, data = {}) => ({ type, seq, time: 1000 + seq, data });
function history() { return [event('turn/start', 0, { turn: 1 }),
  event('user/message', 1, { id: 'u1', source: { kind: 'user' }, content: [{ type: 'text', text: '第一轮' }] }),
  event('assistant/message', 2, { message: { content: [{ type: 'text', text: '第一轮答案' }] } }),
  event('turn/end', 3, { turn: 1 }), event('turn/start', 4, { turn: 2 }),
  event('user/message', 5, { id: 'u2', source: { kind: 'user' }, content: [{ type: 'text', text: '第二轮' }] }),
  event('assistant/message', 6, { message: { content: [{ type: 'text', text: '第二轮答案' }] } }),
  event('turn/end', 7, { turn: 2 })]; }
function fixture(t) {
  const output = mkdtempSync(join(tmpdir(), 'harless-branches-'));
  t.after(() => rmSync(output, { recursive: true, force: true }));
  const sessions = new Map([['source', { meta: { title: '实验讨论', agentPreset: 'parent-bound-preset' }, events: history() }]]);
  const created = [];
  const host = {
    async ensureOwned(id) { if (!sessions.has(id)) throw Object.assign(Error('not owned'), { status: 404 }); },
    async inspect(id) { return sessions.get(id); },
    listTitles() { return [...sessions.values()].map(row => row.meta.title); },
    async createSeeded(value) {
      created.push(value);
      sessions.set(value.sessionId, { meta: { title: value.title }, events: value.seed });
    },
  };
  return { output, host, created, sessions, service: createSessionBranchService(output, 'user-a', host) };
}

test('selected assistant anchors fork through their own completed turn, not the latest turn', () => {
  assert.equal(completedBranchPrefix(history(), 2).length, 4);
  assert.equal(completedBranchPrefix(history(), 6).length, 8);
  assert.equal(completedBranchPrefix(history()).length, 8);
  assert.equal(completedBranchPrefix(history(), 999).length, 8);
  assert.throws(() => completedBranchPrefix(history().slice(0, 7), 6), /等待/);
  assert.throws(() => completedBranchPrefix(history(), 1.2), /位置/);
  assert.throws(() => completedBranchPrefix([event('turn/end', 2)]), /完整/);
});

test('repeated and concurrent branches reserve independent sequential titles and histories', async t => {
  const f = fixture(t);
  const results = await Promise.all(Array.from({ length: 5 }, () => f.service.fork({ sessionId: 'source', atSeq: 2 })));
  assert.equal(new Set(results.map(row => row.sessionId)).size, 5);
  assert.deepEqual(f.created.map(row => row.title), ['实验讨论（1）', '实验讨论（2）', '实验讨论（3）', '实验讨论（4）', '实验讨论（5）']);
  assert.ok(f.created.every(row => row.seed.length === 4 && row.inheritedEventCount === 4 && row.sourceAtSeq === 3));
  f.created[0].seed[1].data.content[0].text = 'branch-local edit';
  f.created[0].seed.push(event('turn/start', 4));
  assert.equal(f.sessions.get('source').events[1].data.content[0].text, '第一轮');
  assert.equal(f.created[1].seed[1].data.content[0].text, '第一轮');
  assert.equal(f.created[1].seed.length, 4);
});

test('numbering survives restart, existing siblings, nested branches, and failed admission', async t => {
  const f = fixture(t);
  f.sessions.set('existing', { meta: { title: '实验讨论（4）' }, events: history() });
  const first = await f.service.fork({ sessionId: 'source' });
  assert.equal(f.created[0].title, '实验讨论（5）');
  const resumed = createSessionBranchService(f.output, 'user-a', f.host);
  await resumed.fork({ sessionId: first.sessionId });
  assert.equal(f.created[1].title, '实验讨论（6）');
  const failure = createSessionBranchService(f.output, 'user-a', { ...f.host, async createSeeded() { throw Error('mount failed'); } });
  await assert.rejects(failure.fork({ sessionId: 'source' }), /mount failed/);
  await createSessionBranchService(f.output, 'user-a', f.host).fork({ sessionId: 'source' });
  assert.equal(f.created.at(-1).title, '实验讨论（8）');
});

test('ownership precedes history reads, projections, numbering and creation', async t => {
  const f = fixture(t);
  await assert.rejects(f.service.fork({ sessionId: 'foreign' }), error => error.status === 404);
  assert.equal(f.created.length, 0);
  await f.service.fork({ sessionId: 'source' });
  assert.equal(f.created[0].title, '实验讨论（1）');
  assert.throws(() => createSessionBranchService(f.output, 'user-b', f.host), /校验/);
});

test('comparison branches detach task, ratings and budget identity while preserving projected history', async t => {
  const f = fixture(t);
  f.sessions.get('source').events[1].data.harless_comparison = { id: 'original-task', score: 5, budget: 'original-budget' };
  f.host.projectEvents = (_id, events) => {
    events[2].data.message.content[0].text = 'Baseline：第一轮结果\nMotif：第一轮结果';
    return events;
  };
  await createSessionBranchService(f.output, 'user-a', f.host).fork({ sessionId: 'source', atSeq: 2 });
  const seed = f.created[0].seed;
  assert.equal(seed[1].data.harless_comparison, undefined);
  assert.match(seed[2].data.message.content[0].text, /Baseline/);
  assert.equal(f.sessions.get('source').events[1].data.harless_comparison.score, 5);
  const durable = JSON.parse(readFileSync(join(f.output, 'conversation-branches.json'), 'utf8'));
  assert.equal(JSON.stringify(durable).includes('original-task'), false);
});

test('titles normalize blank and existing numbered names without prototype-key confusion', async t => {
  assert.equal(branchTitleRoot(''), '新会话');
  assert.equal(branchTitleRoot('实验（2）'), '实验');
  assert.equal(branchTitleRoot('实验 (2)'), '实验');
  const f = fixture(t); f.sessions.get('source').meta.title = '__proto__';
  await f.service.fork({ sessionId: 'source' });
  await createSessionBranchService(f.output, 'user-a', f.host).fork({ sessionId: 'source' });
  assert.deepEqual(f.created.map(row => row.title), ['__proto__（1）', '__proto__（2）']);
});

test('missing metadata title uses native logged title or first human prompt with sequential numbering', async t => {
  const f = fixture(t); delete f.sessions.get('source').meta.title;
  await f.service.fork({ sessionId: 'source' });
  await f.service.fork({ sessionId: 'source' });
  assert.deepEqual(f.created.map(row => row.title), ['第一轮（1）', '第一轮（2）']);
  const source = f.sessions.get('source');
  source.events.push(event('session/title', 8, { title: '已重命名的原对话' }));
  source.meta.title = 'stale metadata';
  await f.service.fork({ sessionId: 'source' });
  assert.equal(f.created.at(-1).title, '已重命名的原对话（1）');
  assert.equal(sessionBranchTitle({}, [event('user/message', 0, { source: { kind: 'user' },
    content: [{ type: 'text', text: 'one\ntwo three four five six' }] })]), 'one two three four five');
});

test('long Unicode titles reserve native byte space for the visible branch number', async t => {
  const f = fixture(t); f.sessions.get('source').meta.title = '科研数据分析讨论'.repeat(10);
  await f.service.fork({ sessionId: 'source' });
  await f.service.fork({ sessionId: 'source' });
  assert.ok(f.created.every(row => Buffer.byteLength(row.title) <= 80 && !row.title.includes('\ufffd')));
  assert.match(f.created[0].title, /（1）$/);
  assert.match(f.created[1].title, /（2）$/);
});
