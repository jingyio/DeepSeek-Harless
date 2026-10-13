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
      { task_id: value.task_id, budget_usd: value.budget_usd, model: value.model });
    const session = value?.session_id ?? url.searchParams.get('session_id');
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ stats: { global_budget_usd: .25, upstream_requests: 0, prompt_tokens: 0,
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
  const promptCalls = [], queueMutations = [], adapters = [], commands = new Map(), presetCalls = [];
  const emit = (name, ...args) => { for (const listener of listeners.get(name) ?? []) listener(...args); };
  const ctx = {
    commands: { register(definition) { commands.set(definition.name, definition); return () => commands.delete(definition.name); } },
    agentPresets: { async select(agent, preset) { presetCalls.push({ session_id: agent.session.id, preset }); agent.preset = preset; } },
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
          const agent = { preset: request.agentPreset, session: { id }, guards: guardFns, events: [], ctx: {
            tools: { restrict(value) { agent.allow = value; return () => {}; }, guard(fn) { guardFns.push(fn); return () => guardFns.splice(guardFns.indexOf(fn), 1); },
              schemas() { return structuredClone(toolSchemas.map(row => ({ ...row, name: agent.allow.allow[0] }))); } },
            systemPrompt: { section() { return () => {}; } },
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
  return { ctx, api, preview, submit, agents, emit, commands, presetCalls,
    async settings(body, query='') { const response = await routes.get('/api/harless/settings').fetch(new Request('http://127.0.0.1/api/harless/settings'+query, body === undefined ? {} : { method: 'POST', body: JSON.stringify(body) })); return { status: response.status, value: await response.json() }; },
    async command(session, rawInput) { return commands.get('harless').handler({ agent: agents.get(session), rawInput, signal: new AbortController().signal }); },
    promptCalls, queueMutations, controlCalls,
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

test('Harless task APIs remain available without separate workbench or settings pages', options, async () => {
  const f = await fixture();
  try {
    const route = f.routes.get('/api/harless/tasks');
    assert.deepEqual(route.methods, ['GET', 'POST']); assert.equal(route.requestBody, 'buffered');
    assert.equal(f.routes.has('/api/harless/settings'), true);
    for (const path of ['/tasks', '/sss', '/harless']) {
      const page = f.webRoutes.get(path);
      assert.equal(page.kind, 'exact');
      const response = { writeHead(status, headers) { this.status = status; this.headers = headers; }, end() {} };
      page.handler({}, response);
      assert.equal(response.status, 302); assert.equal(response.headers.Location, '/');
    }
    assert.equal(f.ctx.indexTransform, undefined);
    const settings = await f.settings();
    assert.equal(settings.status, 200); assert.equal('panels' in settings.value, false);
    const listing = await f.api();
    assert.deepEqual(listing.value.model_options, [{ provider: 'deepseek-official', model: 'deepseek-flash', label: 'DeepSeek Flash', available: true }]);
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
    assert.equal(first.provider, 'deepseek-official'); assert.equal(first.model, 'deepseek-flash');
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

test('GLM selection binds the preview, task budget, and model admission', options, async () => {
  const models = [{ provider: 'deepseek-official', model: 'deepseek-flash', label: 'DeepSeek Flash', available: true },
    { provider: 'harless-glm', model: 'glm-4.6', label: 'GLM 4.6', available: true }];
  const f = await fixture({ models });
  try {
    assert.deepEqual((await f.api()).value.model_options, models);
    const task = await f.preview({ instruction: '检查材料', model: 'glm-4.6' });
    assert.equal(task.provider, 'harless-glm'); assert.equal(task.model, 'glm-4.6');
    assert.equal(f.registrations.get(task.session_id).model, 'glm-4.6');
    assert.equal((await f.api({ action: 'preview', request: { instruction: '错误模型', model: 'unlisted' } })).status, 400);
    await assert.rejects(f.ctx.sessionController.selectModel({ sessionId: task.session_id,
      provider: 'deepseek-official', model: 'deepseek-flash' }), /outside the approved task/);
    assert.equal((await f.submit(task)).status, 200);
    const glmRequest = f.modelRequest(task, { provider: 'harless-glm', model: 'glm-4.6' });
    delete glmRequest.reasoningEffort;
    assert.doesNotThrow(() => f.stream(glmRequest, async function* () {}));
    assert.throws(() => f.stream(f.modelRequest(task), async function* () {}), /Unapproved task model/);
  } finally { await f.close(); }
});

test('Native model picker selection is used by the next chat task', options, async () => {
  const f = await fixture({ models: [
    { provider: 'deepseek-official', model: 'deepseek-flash', label: 'DeepSeek Flash', available: true },
    { provider: 'harless-glm', model: 'glm-4.6', label: 'GLM 4.6', available: true },
  ] });
  try {
    const { sessionId } = await f.ctx.sessionController.create({});
    await f.ctx.sessionController.selectModel({ sessionId, provider: 'harless-glm', model: 'glm-4.6' },
      new AbortController().signal);
    await f.ctx.sessionController.prompt({ sessionId, requestId: 'native-glm', mode: 'queue',
      content: [{ type: 'text', text: 'Check this paper' }] }, new AbortController().signal);
    const task = (await f.api()).value.tasks[0];
    assert.equal(task.provider, 'harless-glm');
    assert.equal(task.model, 'glm-4.6');
    assert.equal(task.status, 'running');
    assert.equal(f.registrations.get(sessionId).model, 'glm-4.6');
    await f.complete(task);
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

test('Real-provider native prompt runs immediately with budget admission and no confirmation dialog', options, async () => {
  const f = await fixture({ provider_mode: 'real' });
  try {
    const created = await f.ctx.sessionController.create({});
    const request = { sessionId: created.sessionId, requestId: 'native-paid', mode: 'queue',
      content: [{ type: 'text', text: '直接执行的请求' }] };
    assert.deepEqual(await f.ctx.sessionController.prompt(request, new AbortController().signal), { accepted: true });
    await f.ctx.sessionController.prompt(request, new AbortController().signal);
    const listing = await f.api(), task = listing.value.tasks[0];
    assert.equal(listing.value.tasks.length, 1); assert.equal(task.entrypoint, 'native_chat');
    assert.equal(task.session_id, created.sessionId); assert.equal(task.status, 'running');
    assert.equal(task.input_preview, '直接执行的请求');
    assert.equal(f.promptCalls.length, 1); assert.equal(f.registrations.size, 1);
    assert.equal(f.controlCalls.filter(call => call.path === '/tasks/activate').length, 1);
    assert.deepEqual(f.promptCalls[0].content, request.content);
    assert.equal(f.ctx.indexTransform, undefined);
    assert.equal((await f.submit(task)).status, 200); assert.equal(f.promptCalls.length, 1);
    await f.complete(task);
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


const multiScenes = [
  { id: 'example', label: '资料', preset: 'sss-task', allowed_tools: ['mcp__demo__read_note'], config_sha256: 'a'.repeat(64) },
  { id: 'other', label: '另一场景', preset: 'sss-scene-other', allowed_tools: ['mcp__other__read'], config_sha256: 'b'.repeat(64) },
];
test('Native /harless commands and settings menu select without admitting a model task; malformed commands fail', options, async () => {
  const f=await fixture({ scenes: multiScenes, mode: 'shadow' });
  try {
    const {sessionId:id}=await f.ctx.sessionController.create({});
    for(const raw of ['', 'list', 'status', 'mode', 'rsi']) assert.equal((await f.command(id,raw)).kind,'success');
    assert.match((await f.command(id,'')).text,/\/harless picker/);
    assert.equal((await f.command(id,'mode baseline')).kind,'success');
    assert.equal((await f.command(id,'rsi on')).kind,'success');
    let value=(await f.settings(undefined,'?session_id='+id)).value;
    assert.equal(value.selection.mode,'baseline'); assert.equal(value.selection.rsi,true);
    assert.equal((await f.command(id,'other')).kind,'success');
    value=(await f.settings(undefined,'?session_id='+id)).value;
    assert.equal(value.selection.scene,'other'); assert.equal(f.presetCalls.length,1);
    assert.deepEqual(f.agents.get(id).allow.allow,['mcp__other__read']);
    assert.equal(f.agents.get(id).guards.length,1);
    assert.match(f.agents.get(id).guards[0]({name:'mcp__demo__read_note'}),/outside/);
    for(const raw of ['off','mode queue','rsi perhaps','missing','other extra','mode shadow extra']) assert.equal((await f.command(id,raw)).kind,'error');
    assert.equal((await f.settings({action:'select',session_id:id,selection:{mode:'execute'}})).value.error.code,'execute_unavailable');
    assert.equal((await f.settings({action:'select',session_id:'foreign',selection:{rsi:false}})).status,404);
    assert.equal((await f.api()).value.tasks.length,0); assert.equal(f.registrations.size,0); assert.equal(f.promptCalls.length,0);
  } finally {await f.close();}
});
test('Preview-only product scenes are selectable but cannot silently run the sample runtime', options, async () => {
  const f = await fixture();
  try {
    const { sessionId } = await f.ctx.sessionController.create({});
    let result = await f.settings({ action: 'select_preview_scene', session_id: sessionId, scene_id: 'ppt' });
    assert.equal(result.status, 200);
    assert.equal(result.value.preview_scene, 'ppt');
    assert.deepEqual(result.value.preview_scenes.map(scene => scene.label),
      ['PPT', 'Paper Proofreading', 'Research Data Analysis', 'New Scene']);
    await assert.rejects(f.ctx.sessionController.prompt({ sessionId, requestId: 'preview-only', mode: 'queue',
      content: [{ type: 'text', text: 'Make a slide' }] }, new AbortController().signal), /UI preview/);
    assert.equal((await f.api()).value.tasks.length, 0);
    assert.equal(f.promptCalls.length, 0);
    result = await f.settings({ action: 'clear_preview_scene', session_id: sessionId });
    assert.equal(result.value.preview_scene, null);
    assert.equal((await f.settings({ action: 'select_preview_scene', session_id: sessionId, scene_id: 'unknown' })).status, 400);
    result = await f.settings({ action: 'select_preview_scene', session_id: sessionId, scene_id: 'new-scene' });
    assert.equal(result.value.preview_scene, 'new-scene');
    const draft = await f.api({ action: 'preview', session_id: sessionId, request: 'Explore a new topic' });
    assert.equal(draft.status, 200);
    assert.equal(draft.value.scene, 'example');
  } finally { await f.close(); }
});
test('Running task keeps frozen tools and mode while next-task choices are inherited by a fresh Session', options, async()=>{
  const f=await fixture({ scenes: multiScenes, mode:'shadow', provider_mode:'real' });
  try {
    const first=await f.preview('首项任务');await f.submit(first);
    const next=await f.settings({action:'select',session_id:first.session_id,selection:{scene:'other',rsi:false}});
    assert.equal(next.value.applies_to,'next_task');assert.equal(next.value.current_task.scene,'example');assert.equal(next.value.current_task.mode,'shadow');
    assert.deepEqual(f.agents.get(first.session_id).allow.allow,['mcp__demo__read_note']);
    assert.equal(f.presetCalls.length,0);
    const second=(await f.settings({action:'new_session',inherit_session:first.session_id})).value;
    assert.notEqual(second.session_id,first.session_id); assert.equal(second.selection.scene,'other');assert.equal(second.selection.mode,'shadow');
    await f.complete(first);
    const draft=await f.api({action:'preview',session_id:second.session_id,request:'独立任务'});
    assert.equal(draft.value.scene,'other');assert.equal(draft.value.mode,'baseline');assert.equal(draft.value.rsi,false);
    assert.equal(f.registrations.size,2);
    assert.equal((await f.submit(draft.value)).status,200);await f.complete(draft.value);
  }finally{await f.close();}
});
test('Changing next-task selection after preview cannot change that preview or its confirmation',options,async()=>{
  const f=await fixture({scenes:multiScenes,mode:'shadow'});
  try{
    const draft=await f.preview('待确认的首项任务');
    await f.settings({action:'select',session_id:draft.session_id,selection:{scene:'other',mode:'baseline'}});
    const current=(await f.api(undefined,'?task_id='+draft.task_id)).value;
    assert.equal(current.confirmation_digest,draft.confirmation_digest);assert.equal(current.mode,'shadow');assert.equal(current.scene,'example');
    assert.equal((await f.submit(draft)).status,200);await f.complete(draft);
  }finally{await f.close();}
});

test('Preview-bound library bytes cannot change before confirmation even if the requested input stays identical',options,async()=>{
 const directory=mkdtempSync(join(tmpdir(),'harless-library-'));
 const manifest=join(directory,'manifest.json'), binding=join(directory,'task.json');
 writeFileSync(manifest,'{}');writeFileSync(binding,'{}');
 const f=await fixture({manifest,task:binding});
 try{
  const draft=await f.preview('同一输入');writeFileSync(manifest,'{"changed":true}');
  const result=await f.submit(draft);assert.equal(result.status,409);assert.equal(result.value.error.code,'confirmation_changed');assert.equal(f.promptCalls.length,0);
 }finally{await f.close();rmSync(directory,{recursive:true});}
});
