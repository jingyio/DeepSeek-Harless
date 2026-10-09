import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { markAgentLoopRequest } from '@deepseek-ai/dsh-llm';

const options = { skip: !process.features?.typescript };
const toolSchemas = [{ name: 'mcp__demo__read_note', description: 'Read a versioned note',
  parameters: { type: 'object', properties: { source_id: { type: 'string' } }, required: ['source_id'] } }];

async function fixture(overrides = {}) {
  const directory = mkdtempSync(join(tmpdir(), 'sss-web-tasks-'));
  const registrations = new Map(), controlCalls = [];
  const token = 'fixture-control-authority';
  const server = createServer(async (req, res) => {
    if (req.headers['x-sss-control-token'] !== token) { res.writeHead(401); res.end('{}'); return; }
    let text = ''; for await (const part of req) text += part;
    const url = new URL(req.url, 'http://127.0.0.1');
    const value = text ? JSON.parse(text) : undefined;
    controlCalls.push({ path: url.pathname, value });
    if (url.pathname === '/tasks/register') registrations.set(value.session_id,
      { task_id: value.task_id, budget_usd: value.budget_usd });
    const session = value?.session_id ?? url.searchParams.get('session_id');
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ stats: { upstream_requests: 0, prompt_tokens: 0,
      completion_tokens: 0, estimated_cost_usd: 0, ...registrations.get(session) } }));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const policy = { output: directory, endpoint: 'http://127.0.0.1:1234/v1',
    mode: 'baseline', budget_usd: .25, allowed_tools: toolSchemas.map(row => row.name),
    capability_profile: 'example', max_output_tokens: 1000, provider_mode: 'mock',
    control_endpoint: `http://127.0.0.1:${server.address().port}`, control_token: token,
    resources: { 'source:one': { version: 'v1', text: 'Public source fixture.' } }, ...overrides };
  mkdirSync(join(directory, 'tasks'));
  const policyPath = join(directory, 'policy.json'); writeFileSync(policyPath, JSON.stringify(policy));
  const previous = process.env.SSS_WEB_POLICY; process.env.SSS_WEB_POLICY = policyPath;
  const listeners = new Map(), routes = new Map(), webRoutes = new Map(), agents = new Map();
  const promptCalls = [], queueMutations = [], adapters = [];
  const emit = (name, ...args) => { for (const listener of listeners.get(name) ?? []) listener(...args); };
  const ctx = {
    effect(factory) { factory(); },
    on(name, listener) { const rows = listeners.get(name) ?? []; rows.push(listener); listeners.set(name, rows); },
    llm: { registerAdapter(names, adapter) { adapters.push({ names, adapter }); return () => {}; } },
    connection: {
      fetch: { register(route) { routes.set(route.path, route); return async () => {}; } },
      requestRejection(request) { return request.authorized ? undefined : 401; },
    },
    webServer: {
      register(route) { webRoutes.set(route.path, route); return () => {}; },
      tapIndex(transform) { ctx.indexTransform = transform; return () => {}; },
    },
    fileUploads: {
      async uploadStream(request) { let bytes=0; for await (const part of request.data) bytes += part.length;
        return { receiptId: `receipt-${request.sessionId}-${bytes}`, file: { path: 'private-fixture' } }; },
    },
    sessionController: {
      async create(request) {
        const id = request.sessionId ?? `mock-session-${agents.size + 1}`;
        if (!agents.has(id)) {
          const guardFns = [];
          const agent = { session: { id }, guards: guardFns, events: [], ctx: {
            tools: { restrict(value) { agent.allow = value; }, guard(fn) { guardFns.push(fn); },
              schemas() { return structuredClone(toolSchemas); } },
            on() {},
          } };
          agents.set(id, agent); emit('agent/created', { agent });
        }
        return { sessionId: id, agentPreset: request.agentPreset };
      },
      async prompt(request, signal) {
        assert.ok(signal instanceof AbortSignal);
        promptCalls.push(request);
        const agent = agents.get(request.sessionId);
        const event = { type: 'user/message', data: { id: `user-${promptCalls.length}`,
          content: request.content, source: { kind: 'user', rpcId: request.requestId } } };
        agent.events.push(event); emit('session/event', agent.session, event);
        return { accepted: true };
      },
      async inspect(id) { return { meta: { id }, events: agents.get(id)?.events ?? [] }; },
      async cancel() { return { accepted: true }; },
      selectModel(request) { return request; },
      updateQueue(request) { queueMutations.push(request); return { accepted: true }; },
    },
  };
  try {
    const { apply } = await import('../src/adapters/dsh_web_tasks.ts'); apply(ctx);
  } catch (error) {
    if (previous === undefined) delete process.env.SSS_WEB_POLICY; else process.env.SSS_WEB_POLICY = previous;
    server.closeAllConnections(); await new Promise(resolve => server.close(resolve));
    rmSync(directory, { recursive: true }); throw error;
  }
  async function api(body, query = '') {
    const route = routes.get('/api/harless/tasks');
    const response = await route.fetch(new Request('http://127.0.0.1/api/harless/tasks' + query,
      body === undefined ? {} : { method: 'POST', body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' } }));
    return { status: response.status, value: await response.json() };
  }
  const preview = async request => { const result = await api({ action: 'preview', request });
    assert.equal(result.status, 200, JSON.stringify(result.value)); return result.value; };
  const submit = async task => api({ action: 'submit', task_id: task.task_id,
    confirmation_digest: task.confirmation_digest });
  function modelRequest(task, changes = {}, tagged = true) {
    const agent = agents.get(task.session_id), event = agent.events.find(row => row.type === 'user/message');
    const body = { sessionId: task.session_id, provider: 'deepseek-official', model: 'deepseek-flash',
      reasoningEffort: 'off', maxTokens: 1000, tools: structuredClone(toolSchemas),
      messages: [{ role: 'user', id: event.data.id, source: event.data.source, content: event.data.content }], ...changes };
    return tagged ? markAgentLoopRequest(body) : body;
  }
  return { ctx, api, preview, submit, agents, emit, promptCalls, queueMutations, controlCalls,
    registrations, modelRequest, routes, webRoutes,
    stream(request, next) { return listeners.get('llm/stream')[0](request, next); },
    async complete(task) { emit('agent/status', { agent: agents.get(task.session_id), status: 'idle' });
      await api(undefined, '?task_id=' + task.task_id); },
    async close() {
      if (previous === undefined) delete process.env.SSS_WEB_POLICY; else process.env.SSS_WEB_POLICY = previous;
      server.closeAllConnections(); await new Promise(resolve => server.close(resolve));
      rmSync(directory, { recursive: true });
    },
  };
}

test('DeepSeek Harless tasks use authenticated Connection API routes and protect the task panel', options, async () => {
  const f = await fixture();
  try {
    const route = f.routes.get('/api/harless/tasks');
    assert.deepEqual(route.methods, ['GET', 'POST']); assert.equal(route.requestBody, 'buffered');
    assert.equal(f.webRoutes.get('/tasks').kind, 'exact');
    const result = {};
    f.webRoutes.get('/tasks').handler({ authorized: false }, {
      writeHead(status) { result.status = status; }, end(value) { result.body = value; },
    });
    assert.equal(result.status, 401); assert.ok(!result.body.includes('<form'));
    f.webRoutes.get('/tasks').handler({ authorized: true }, {
      writeHead(status) { result.status = status; }, end(value) { result.body = value; },
    });
    assert.equal(result.status, 200); assert.match(result.body, /DeepSeek Harless 任务工作台/);
  } finally { await f.close(); }
});

test('Dynamic preview creates independent tasks, binds resource versions, and is request-id idempotent', options, async () => {
  const f = await fixture();
  try {
    const input = { instruction: '第一次任务', request_id: 'stable-first',
      inputs: [{ resource_id: 'source:one', version: 'v1' }] };
    const first = await f.preview(input), repeated = await f.preview(input);
    assert.equal(first.task_id, repeated.task_id); assert.equal(first.session_id, repeated.session_id);
    assert.equal(f.agents.size, 1); assert.equal(f.registrations.size, 1);
    assert.equal(first.sources[0].resource_id, 'source:one');
    assert.equal(first.status, 'awaiting_confirmation'); assert.equal(first.paid_calls_enabled, false);
    const second = await f.preview({ messages: [{ role: 'user', content: '另一项任务' }], mode: 'shadow' });
    assert.notEqual(second.task_id, first.task_id); assert.notEqual(second.session_id, first.session_id);
    assert.equal(second.mode, 'shadow');
    for (const [request, code] of [
      [{ ...input, instruction: '同一请求标识的另一输入' }, 'request_id_conflict'],
      [{ instruction: '任务', mode: 'queue' }, 'invalid_request'],
      [{ instruction: '任务', capability_profile: 'root-shell' }, 'profile_not_allowed'],
      [{ instruction: '任务', inputs: [{ resource_id: 'not-registered' }] }, 'resource_not_registered'],
      [{ instruction: '任务', inputs: [{ resource_id: 'source:one', version: 'v2' }] }, 'resource_version_changed'],
    ]) { const result = await f.api({ action: 'preview', request }); assert.equal(result.value.error.code, code); }
    const list = await f.api(); assert.equal(list.value.tasks.length, 2); assert.equal(list.value.aggregate.tasks, 2);
  } finally { await f.close(); }
});

test('Submit requires the current confirmation and never reruns a retry; only one task is active', options, async () => {
  const f = await fixture();
  try {
    const first = await f.preview('可执行任务一'), second = await f.preview({ instruction: '可执行任务二', mode: 'execute' });
    const denied = await f.api({ action: 'submit', task_id: first.task_id, confirmation_digest: '0'.repeat(64) });
    assert.equal(denied.status, 409); assert.equal(denied.value.error.code, 'confirmation_changed');
    assert.equal(f.promptCalls.length, 0);
    assert.equal((await f.submit(first)).status, 200); assert.equal((await f.submit(first)).status, 200);
    assert.equal(f.promptCalls.length, 1);
    const busy = await f.submit(second); assert.equal(busy.status, 409); assert.equal(busy.value.error.code, 'task_busy');
    await f.complete(first); assert.equal((await f.submit(second)).status, 200);
    assert.equal(f.promptCalls.length, 2);
    const detail = await f.api(undefined, '?task_id=' + second.task_id);
    assert.equal(detail.value.fallback_reason, 'no_certified_library');
    assert.equal(detail.value.stats.verified_skips, 0);
    await f.complete(second);
  } finally { await f.close(); }
});

test('Model admission rejects auxiliary calls, changed schemas, altered user envelopes and wrong sessions', options, async () => {
  const f = await fixture();
  try {
    const task = await f.preview('模型接缝检查'); await f.submit(task);
    const next = () => (async function* () { yield { type: 'fixture' }; })();
    assert.throws(() => f.stream(f.modelRequest(task, {}, false), next), /Unapproved/);
    assert.throws(() => f.stream(f.modelRequest(task, { sessionId: 'other-session' }), next), /Unapproved/);
    assert.throws(() => f.stream(f.modelRequest(task, { reasoningEffort: 'high' }), next), /Unapproved/);
    assert.throws(() => f.stream(f.modelRequest(task, { tools: [{ ...toolSchemas[0], description: 'changed' }] }), next), /schema/);
    const original = f.modelRequest(task);
    assert.throws(() => f.stream(f.modelRequest(task, { messages: [...original.messages,
      { role: 'user', id: 'goal-round', source: { kind: 'goal', goalId: 'unapproved-goal', revision: 1, round: 1 },
        content: [{ type: 'text', text: '未经任务确认的目标续跑' }] }] }), next), /Goal continuation/);
    assert.throws(() => f.stream(f.modelRequest(task, { messages: [{ ...original.messages[0],
      content: [{ type: 'text', text: '未经预览的新要求' }] }] }), next), /envelope/);
    const received = []; for await (const row of f.stream(f.modelRequest(task), next)) received.push(row);
    assert.equal(received.length, 1);
    const agent = f.agents.get(task.session_id);
    assert.deepEqual(agent.allow, { allow: ['mcp__demo__read_note'] });
    assert.equal(agent.guards[0]({ name: 'mcp__demo__read_note' }), undefined);
    assert.match(agent.guards[0]({ name: 'bash' }), /outside/);
    await f.complete(task);
    assert.throws(() => f.stream(f.modelRequest(task), next), /Unapproved/);
  } finally { await f.close(); }
});

test('Native mock chat admits dynamic content in a new session and records task cancellation', options, async () => {
  const f = await fixture();
  try {
    const created = await f.ctx.sessionController.create({});
    await f.ctx.sessionController.prompt({ sessionId: created.sessionId, requestId: 'native-first', mode: 'queue',
      content: [{ type: 'text', text: '网页中的自由输入' }] }, new AbortController().signal);
    assert.equal(f.promptCalls[0].content[0].text, '网页中的自由输入');
    const listing = await f.api(), first = listing.value.tasks[0];
    assert.equal(first.session_id, created.sessionId); assert.equal(first.status, 'running');
    await assert.rejects(f.ctx.sessionController.prompt({ sessionId: created.sessionId, requestId: 'native-second', mode: 'queue',
      content: [{ type: 'text', text: '应另开任务' }] }, new AbortController().signal), /already has a task/);
    await assert.rejects(f.ctx.sessionController.prompt({ sessionId: 'unknown', requestId: 'bad', mode: 'queue',
      content: [{ type: 'text', text: '未知会话' }] }, new AbortController().signal), /outside/);
    const cancelled = await f.api({ action: 'cancel', task_id: first.task_id });
    assert.equal(cancelled.value.status, 'cancelled');
    await f.api(undefined, '?task_id=' + first.task_id);
    const second = await f.preview('取消后能运行独立任务'); assert.equal((await f.submit(second)).status, 200);
    await f.complete(second);
  } finally { await f.close(); }
});

test('Real-provider native prompt cannot bypass explicit task preview and budget confirmation', options, async () => {
  const f = await fixture({ provider_mode: 'real' });
  try {
    const created = await f.ctx.sessionController.create({});
    await assert.rejects(f.ctx.sessionController.prompt({ sessionId: created.sessionId,
      requestId: 'unconfirmed-paid', mode: 'queue', content: [{ type: 'text', text: '未确认付费请求' }] },
    new AbortController().signal), /Preview and confirm/);
    assert.equal(f.promptCalls.length, 0); assert.equal(f.registrations.size, 0);
  } finally { await f.close(); }
});

test('Queued content cannot be edited or steered past an accepted confirmation', options, async () => {
  const f = await fixture();
  try {
    const task = await f.preview('经预览确认的题面'); await f.submit(task);
    for (const action of [{ kind: 'edit', content: [{ type: 'text', text: '替换已批准的任务' }] },
      { kind: 'remove' }, { kind: 'steer' }]) {
      await assert.rejects(Promise.resolve().then(() => f.ctx.sessionController.updateQueue({
        sessionId: task.session_id, itemId: 'pending-user-message', action,
      })), /preview|confirmed|queue|task|mutation/i);
    }
    assert.equal(f.queueMutations.length, 0);
    await f.complete(task);
  } finally { await f.close(); }
});
