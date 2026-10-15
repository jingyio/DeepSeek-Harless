import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, readdirSync, rmSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { randomUUID } from 'node:crypto';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
import { markAgentLoopRequest } from '@deepseek-ai/dsh-llm';
import { ApiSessionNotFound } from '@deepseek-ai/dsh-api-session-controller';
import {comparisonArtifacts} from '../src/adapters/harless_comparison_artifacts.ts';
import { digest } from '../src/motif_core/online_skill_runtime.mjs';
import {renderPrompt} from '@deepseek-ai/dsh-system-prompt';

test('Scene instructions preserve report value tokens without treating them as Harness variables',()=>{
 const text='Bind {{estimate}} and {{ci_low}} to verified report results.';
 assert.equal(renderPrompt({sections:[{name:'harless-scene',order:10210,text:'{{harless_scene_literal}}'}],
  variables:{harless_scene_literal:text},contexts:[],tools:[]}),text);
});

const options = { skip: !process.features?.typescript };
const toolSchemas = [{ name: 'mcp__demo__read_note', description: 'Read a versioned note',
  parameters: { type: 'object', properties: { source_id: { type: 'string' } }, required: ['source_id'] } }];

async function fixture({ broker = false, dshHome = false, fixtureSchemas: schemaOverride, fixture_schemas, ...overrides } = {}) {
  const fixtureSchemas = schemaOverride ?? fixture_schemas ?? toolSchemas;
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
    if (url.pathname === '/tasks/stats' && !registrations.has(session)) {
      res.writeHead(404, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ error: 'Task session not found' })); return;
    }
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ stats: { global_budget_usd: .25, upstream_requests: 0, prompt_tokens: 0,
      completion_tokens: 0, estimated_cost_usd: 0, ...registrations.get(session) } }));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const brokerCalls = [], brokerRoutes = new Map();
  const brokerServer = broker ? createServer(async (req, res) => {
    if (req.headers['x-sss-control-token'] !== token) { res.writeHead(401); res.end('{}'); return; }
    let raw = ''; for await (const part of req) raw += part;
    const value = JSON.parse(raw); brokerCalls.push({ path: req.url, value });
    if (req.url === '/bind') brokerRoutes.set(value.session_id, value.budget_session_id);
    if (req.url === '/unbind') brokerRoutes.delete(value.session_id);
    res.writeHead(200, { 'Content-Type': 'application/json' }); res.end('{}');
  }) : undefined;
  if (brokerServer) await new Promise(resolve => brokerServer.listen(0, '127.0.0.1', resolve));
  const policy = { output: directory, endpoint: 'http://127.0.0.1:1234/v1',
    mode: 'baseline', budget_usd: .25, allowed_tools: fixtureSchemas.map(row => row.name),
    capability_profile: 'example', max_output_tokens: 1000, provider_mode: 'mock',
    control_endpoint: `http://127.0.0.1:${server.address().port}`, control_token: token,
    resources: { 'source:one': { version: 'v1', text: 'Public source fixture.' } },
    ...(brokerServer ? { budget_broker_endpoint: `http://127.0.0.1:${brokerServer.address().port}` } : {}), ...overrides };
  mkdirSync(join(directory, 'tasks'));
  const policyPath = join(directory, 'policy.json'); writeFileSync(policyPath, JSON.stringify(policy));
  const previous = process.env.SSS_WEB_POLICY; process.env.SSS_WEB_POLICY = policyPath;
  const previousHome = process.env.DSH_HOME;
  if (dshHome) { mkdirSync(join(directory, 'dsh')); process.env.DSH_HOME = join(directory, 'dsh'); }
  else delete process.env.DSH_HOME;
  const listeners = new Map(), routes = new Map(), webRoutes = new Map(), agents = new Map(), workspaceGroups = new Map();
  const receipts = new Map();
  const storedSessions = new Map();
  const storedHeaders = new Map();
  const promptCalls = [], queueMutations = [], adapters = [], commands = new Map(), presetCalls = [];
  const emit = (name, ...args) => { for (const listener of listeners.get(name) ?? []) listener(...args); };
  const ctx = {
    workspaceRegistry: { list: () => [...workspaceGroups.values()], get: id => workspaceGroups.get(id),
      async create(path, title) { const old = [...workspaceGroups.values()].find(row => row.path === path); if (old) return old;
        const row = { id:'workspace-' + randomUUID(), path, title, sessionIds:[], async attachSession(id) { if(!this.sessionIds.includes(id)) this.sessionIds.push(id); } }; workspaceGroups.set(row.id,row); return row; } },
    commands: { register(definition) { commands.set(definition.name, definition); return () => commands.delete(definition.name); } },
    agentPresets: { async mount() {}, async select(agent, preset) { presetCalls.push({ session_id: agent.session.id, preset }); agent.preset = preset; } },
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
    attachments: { async admitPromptContent(content) { return content; }, async *readFileStream(ref) { yield receipts.get(ref.attachmentId).data; } },
    fileUploads: {
      bindPrompt() { return { commit() {}, [Symbol.dispose]() {} }; },
      resolve(agent, receipt) { const row = receipts.get(receipt); return row?.session === agent.session.id ? row.ref : undefined; },
      async uploadStream(request) { let bytes=0; const chunks=[]; for await (const part of request.data) {bytes += part.length;chunks.push(Buffer.from(part));}
        const receiptId = `receipt-${request.sessionId}-${bytes}-${receipts.size}`;
        const ref = { name: request.name, bytes, attachmentId: receiptId };
        receipts.set(receiptId, { session: request.sessionId, ref, data: Buffer.concat(chunks) });
        return { receiptId, file: ref };  },
    },
    sessionController: {
      async create(request) {
        assert.ok(request.cwd === undefined || request.workspaceId === undefined, 'native create rejects workspaceId together with cwd');
        const id = request.sessionId ?? `mock-session-${agents.size + 1}`;
        if (request.workspaceId) { const group = workspaceGroups.get(request.workspaceId); assert.ok(group); if (!group.sessionIds.includes(id)) group.sessionIds.push(id); }
        if (!agents.has(id)) {
          const guardFns = [];
          const events = storedSessions.get(id) ?? []; storedSessions.set(id, events);
          if (!storedHeaders.has(id)) storedHeaders.set(id, { id, agentPreset: request.agentPreset,
            cwd: request.workspaceId ? workspaceGroups.get(request.workspaceId).path : request.cwd });
          const agent = { preset: request.agentPreset, session: { id, snapshotEvents: () => events, append(type,data,extra={}) { const event={type,data,seq:events.length,time:Date.now(),...extra};events.push(event);emit('session/event',agent.session,event);return event;} }, guards: guardFns, events, ctx: {
            tools: { restrict(value) { agent.allow = value; return () => {}; },
              guard(fn) { guardFns.push(fn); return () => guardFns.splice(guardFns.indexOf(fn), 1); },
              schemas() { return structuredClone(fixtureSchemas.length === 1 && agent.allow.allow.length === 1 ? [{ ...fixtureSchemas[0], name: agent.allow.allow[0] }] : fixtureSchemas.filter(row => agent.allow?.allow.includes(row.name))); } },
            systemPrompt: { variable(name,fn) { agent.variables??=new Map();agent.variables.set(name,fn);return()=>agent.variables.delete(name); },
              section(row) { agent.instruction = row.text==='{{harless_scene_literal}}'?agent.variables.get('harless_scene_literal')():row.text; return () => {}; } },
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
      async inspect(id) {
        if (!storedSessions.has(id)) throw new ApiSessionNotFound(`Unknown session ${id}`);
        return { meta: storedHeaders.get(id), events: storedSessions.get(id) };
      },
      async cancel() { return { accepted: true }; },
      async rename({ sessionId, title }) { storedHeaders.get(sessionId).title = title; return { title }; },
      async selectModel(request) { await originalController.create({ sessionId: request.sessionId }); return request; },
      updateQueue(request) { queueMutations.push(request); return { accepted: true }; },
    },
  };
  const originalController = { ...ctx.sessionController };
  ctx.agents = { async create(request) { const result = await originalController.create({sessionId:request.sessionId,cwd:request.meta.cwd,agentPreset:request.meta.agentPreset});
    const agent=agents.get(result.sessionId);agent.events.push(...structuredClone(request.seed));Object.assign(storedHeaders.get(result.sessionId),request.meta);
    await request.setup(agent.ctx,agent);return agent; } };
  try {
    const { apply } = await import('../src/adapters/dsh_web_tasks.ts'); apply(ctx);
  } catch (error) {
    if (previous === undefined) delete process.env.SSS_WEB_POLICY; else process.env.SSS_WEB_POLICY = previous;
    if (previousHome === undefined) delete process.env.DSH_HOME; else process.env.DSH_HOME = previousHome;
    server.closeAllConnections(); await new Promise(resolve => server.close(resolve));
    if (brokerServer) { brokerServer.closeAllConnections(); await new Promise(resolve => brokerServer.close(resolve)); }
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
    const agent = agents.get(task.session_id), events = agent.events.filter(row => row.type === 'user/message');
    const body = { sessionId: task.session_id, provider: 'deepseek-official', model: 'deepseek-flash',
      reasoningEffort: 'off', maxTokens: 1000, tools: structuredClone(fixtureSchemas),
      messages: events.map(event => ({ role: 'user', id: event.data.id, source: event.data.source,
        content: event.data.content })), ...changes };
    return tagged ? markAgentLoopRequest(body) : body;
  }
  return { ctx, api, preview, submit, agents, emit, commands, presetCalls, directory, receipts, policy, policyPath,
    async settings(body, query='') { const response = await routes.get('/api/harless/settings').fetch(new Request('http://127.0.0.1/api/harless/settings'+query, body === undefined ? {} : { method: 'POST', body: JSON.stringify(body) })); return { status: response.status, value: await response.json() }; },
    async command(session, rawInput) { return commands.get('harless').handler({ agent: agents.get(session), rawInput, signal: new AbortController().signal }); },
    promptCalls, queueMutations, controlCalls, directory,
    registrations, brokerCalls, brokerRoutes, modelRequest, routes, webRoutes,
    async stopControl() { server.closeAllConnections(); await new Promise(resolve=>server.close(resolve)); },
    originalController,
    async restart() {
      Object.assign(ctx.sessionController, originalController);
      listeners.clear(); routes.clear(); webRoutes.clear(); agents.clear();
      const { apply } = await import('../src/adapters/dsh_web_tasks.ts'); apply(ctx);
    },
    stream(request, next) { return listeners.get('llm/stream')[0](request, next); },
    async complete(task) { emit('agent/status', { agent: agents.get(task.session_id), status: 'idle' });
      await api(undefined, '?task_id=' + task.task_id); },
    async close() {
      if (previous === undefined) delete process.env.SSS_WEB_POLICY; else process.env.SSS_WEB_POLICY = previous;
      if (previousHome === undefined) delete process.env.DSH_HOME; else process.env.DSH_HOME = previousHome;
      server.closeAllConnections(); await new Promise(resolve => server.close(resolve));
      if (brokerServer) { brokerServer.closeAllConnections(); await new Promise(resolve => brokerServer.close(resolve)); }
      rmSync(directory, { recursive: true });
    },
  };
}

function assertProductPresentationOnly(ctx) {
  assert.equal(typeof ctx.indexTransform, 'function');
  const body = '<main id="native-harness-root"></main><script type="module" src="/native-client.js"></script>';
  const html = ctx.indexTransform('<!doctype html><html><head><title>DeepSeek Harness</title></head><body>' + body + '</body></html>');
  const brand = '<script>' + readFileSync(new URL('../src/adapters/geneloop_brand.js', import.meta.url), 'utf8') + '</script>';
  const account = process.env.HARLESS_GATEWAY_ENABLED === '1' ?
    '<script>' + readFileSync(new URL('../src/adapters/harless_account_link.js', import.meta.url), 'utf8') + '</script>' : '';
  // Product branding must be ready before the native client boots. It may not
  // reintroduce the separate workbench or intercept sending with a dialog.
  assert.ok(html.indexOf(brand) > html.indexOf('<head>'));
  assert.ok(html.indexOf(brand) < html.indexOf('</head>'));
  assert.match(html, /<title>GeneLoop<\/title>/);
  assert.equal(html.slice(html.indexOf('<body>') + 6, html.indexOf('</body>')), body + account);
  assert.doesNotMatch(html, /sss-native-confirmation|DeepSeek Harless 任务工作台/);
}

test('Completed task usage survives a missing or offline budget route while active tasks fail closed',options,async()=>{
 const f=await fixture({broker:true});try{
  const task=await f.preview('Preserve historical usage');await f.submit(task);
  Object.assign([...f.registrations.values()][0],{upstream_requests:7,estimated_cost_usd:0.12,prompt_tokens:1234});
  await f.complete(task);await f.restart();f.registrations.clear();
  let result=await f.api(undefined,'?task_id='+task.task_id);assert.equal(result.status,200);assert.equal(result.value.stats.upstream_requests,7);assert.equal(result.value.stats.estimated_cost_usd,0.12);
  const next=await f.preview('New active task');await f.submit(next);f.registrations.clear();
  result=await f.api(undefined,'?task_id='+next.task_id);assert.equal(result.status,409);assert.equal(result.value.error.code,'budget_control_failed');
  await f.stopControl();
  result=await f.api(undefined,'?task_id='+task.task_id);assert.equal(result.status,200);assert.equal(result.value.stats.prompt_tokens,1234);assert.equal(result.value.stats.estimated_cost_usd,0.12);
  result=await f.api(undefined,'?task_id='+next.task_id);assert.notEqual(result.status,200);
 }finally{await f.close();}
});

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
    assertProductPresentationOnly(f.ctx);
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

test('Selected model and empty session survive a Web process restart', options, async () => {
  const f = await fixture({ models: [
    { provider: 'deepseek-official', model: 'deepseek-flash', label: 'DeepSeek Flash', available: true },
    { provider: 'harless-glm', model: 'glm-4.6', label: 'GLM 4.6', available: true },
  ] });
  try {
    const { sessionId } = await f.ctx.sessionController.create({});
    await f.ctx.sessionController.selectModel({ sessionId, provider: 'harless-glm', model: 'glm-4.6' },
      new AbortController().signal);
    await f.restart();
    await f.ctx.sessionController.prompt({ sessionId, requestId: 'after-restart', mode: 'queue',
      content: [{ type: 'text', text: 'Continue with selected model' }] }, new AbortController().signal);
    const task = (await f.api()).value.tasks[0];
    assert.equal(task.model, 'glm-4.6'); assert.equal(task.provider, 'harless-glm');
    assert.equal(task.status, 'running');
    await f.complete(task);
  } finally { await f.close(); }
});

test('Submit requires the current confirmation and never reruns a retry; only one task is active', options, async () => {
  const f = await fixture();
  try {
    const first = await f.preview('可执行任务一'), second = await f.preview({ instruction: '可执行任务二', mode: 'shadow' });
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

test('Model admission accepts a no-tool agent whose wire request omits tools', options, async () => {
  const f = await fixture({ fixtureSchemas: [] });
  try {
    const task = await f.preview('无工具对话');
    assert.equal((await f.submit(task)).status, 200);
    const next = () => (async function* () { yield { type: 'fixture' }; })();
    const request = f.modelRequest(task);
    delete request.tools;
    const received = [];
    for await (const row of f.stream(request, next)) received.push(row);
    assert.equal(received.length, 1);
    const recorded = JSON.parse(readFileSync(join(f.directory, 'tasks', task.task_id, 'model-request-config.json')));
    assert.deepEqual(recorded.tools_order, []);
    await f.complete(task);
  } finally { await f.close(); }
});

test('Browser-generated session IDs are admitted, foreign sessions and storage failures are denied', options, async () => {
  const f = await fixture();
  try {
    const request = { sessionId: 'browser-new-id' };
    const results = await Promise.all([f.ctx.sessionController.create(request), f.ctx.sessionController.create(request)]);
    assert.equal(results[0].sessionId, request.sessionId);
    assert.deepEqual(results[0], results[1]); assert.equal(f.agents.size, 1);
    await f.originalController.create({ sessionId: 'foreign-existing' });
    await assert.rejects(f.ctx.sessionController.create({ sessionId: 'foreign-existing' }), /outside/);
    const inspect = f.ctx.sessionController.inspect;
    f.ctx.sessionController.inspect = async () => { throw Error('storage unavailable'); };
    await assert.rejects(f.ctx.sessionController.create({ sessionId: 'unproven-id' }), /storage unavailable/);
    f.ctx.sessionController.inspect = inspect;
    assert.equal(f.agents.has('unproven-id'), false);
    assert.equal(f.promptCalls.length, 0); assert.equal(f.registrations.size, 0);
  } finally { await f.close(); }
});

test('Legacy blank preset sessions resume only when history and budget registration are absent', options, async () => {
  const f = await fixture({ provider_mode: 'real' });
  try {
    await f.originalController.create({ sessionId: 'legacy-empty', agentPreset: 'sss-task' });
    await f.originalController.create({ sessionId: 'legacy-used', agentPreset: 'sss-task' });
    f.agents.get('legacy-used').events.push({ type: 'user/message', data: { content: [] } });
    await f.originalController.create({ sessionId: 'legacy-budget', agentPreset: 'sss-task' });
    f.registrations.set('legacy-budget', { task_id: 'previous-task', budget_usd: .25 });
    await f.originalController.create({ sessionId: 'other-preset' });
    await f.restart();
    const prompt = id => f.ctx.sessionController.prompt({ sessionId: id, requestId: 'request-' + id,
      mode: 'queue', content: [{ type: 'text', text: 'Blank session upgrade' }] }, new AbortController().signal);
    await assert.rejects(prompt('legacy-used'), /outside/);
    await assert.rejects(prompt('other-preset'), /outside/);
    await assert.rejects(prompt('legacy-budget'), /already has a task/);
    await prompt('legacy-empty');
    assert.equal((await f.ctx.sessionController.inspect('legacy-empty')).meta.title,'新会话');
    assert.equal(f.controlCalls.filter(row => row.path === '/tasks/register').length, 1);
    assert.equal(f.controlCalls.filter(row => row.path === '/tasks/activate').length, 1);
    assert.equal(f.promptCalls.length, 1);
  } finally { await f.close(); }
});

test('Owned empty sessions survive restart while bound task identities cannot get a fresh budget', options, async () => {
  const f = await fixture({ provider_mode: 'real' });
  try {
    const created = await f.ctx.sessionController.create({ sessionId: 'restart-empty' });
    await f.originalController.create({ sessionId: 'restart-foreign' });
    await f.restart();
    await assert.rejects(f.ctx.sessionController.create({ sessionId: 'restart-foreign' }), /outside/);
    const request = { sessionId: created.sessionId, requestId: 'persisted-budget', mode: 'queue',
      content: [{ type: 'text', text: 'Restart must retain this task binding' }] };
    await f.ctx.sessionController.prompt(request, new AbortController().signal);
    assert.equal(f.agents.size, 1);
    assert.deepEqual(f.agents.get(created.sessionId).allow, { allow: toolSchemas.map(row => row.name) });
    assert.equal(f.registrations.size, 1); assert.equal(f.promptCalls.length, 1);
    await f.restart();
    await f.ctx.sessionController.create({ sessionId: created.sessionId });
    await assert.rejects(f.ctx.sessionController.prompt({ ...request, requestId: 'budget-reset-attempt' },
      new AbortController().signal), /already has a task/);
    assert.equal(f.controlCalls.filter(row => row.path === '/tasks/register').length, 1);
    assert.equal(f.controlCalls.filter(row => row.path === '/tasks/activate').length, 1);
  } finally { await f.close(); }
});

test('Completed chat survives a Web output change without adopting another user session or reusing its budget', options, async () => {
  const f = await fixture({ broker: true, dshHome: true, provider_mode: 'real' });
  try {
    const home = process.env.DSH_HOME;
    const { sessionId: id } = await f.ctx.sessionController.create({});
    await f.ctx.sessionController.prompt({ sessionId: id, requestId: 'old-turn', mode: 'queue',
      content: [{ type: 'text', text: '第一轮' }] }, new AbortController().signal);
    const first = (await f.api()).value.tasks[0];
    await f.complete(first);
    await f.originalController.create({ sessionId: 'foreign-used', agentPreset: 'sss-task' });
    f.agents.get('foreign-used').events.push({ type: 'user/message', data: { content: [] } });

    // Simulate the old release: ownership lived only in the previous run output.
    const stable = join(home, readdirSync(home).find(name => name.startsWith('harless-web-ownership-')));
    const saved = JSON.parse(readFileSync(stable, 'utf8'));
    const oldScope = digest({ output: f.directory, home });
    writeFileSync(join(f.directory, 'session-ownership-' + oldScope + '.json'),
      JSON.stringify({ ...saved, scope: oldScope }));
    rmSync(stable);
    const nextOutput = join(f.directory, 'next-run');
    mkdirSync(join(nextOutput, 'tasks'), { recursive: true });
    writeFileSync(f.policyPath, JSON.stringify({ ...f.policy, output: nextOutput,
      ownership_legacy_outputs: [f.directory] }));
    await f.restart();
    assert.equal((await f.settings(undefined, '?session_id=' + id)).status, 200);
    await assert.rejects(f.ctx.sessionController.prompt({ sessionId: 'foreign-used', requestId: 'foreign',
      mode: 'queue', content: [{ type: 'text', text: '拒绝' }] }, new AbortController().signal), /outside/);
    await f.ctx.sessionController.prompt({ sessionId: id, requestId: 'second-turn', mode: 'queue',
      content: [{ type: 'text', text: '继续' }] }, new AbortController().signal);
    const second = (await f.api()).value.tasks[0];
    assert.equal(second.session_id, id);
    assert.notEqual(second.task_id, first.task_id);
    assert.equal(f.controlCalls.filter(row => row.path === '/tasks/register').length, 2);
    await f.complete(second);

    // Future deployments use the stable per-home record without old output paths.
    const laterOutput = join(f.directory, 'later-run');
    mkdirSync(join(laterOutput, 'tasks'), { recursive: true });
    writeFileSync(f.policyPath, JSON.stringify({ ...f.policy, output: laterOutput }));
    await f.restart();
    await f.ctx.sessionController.prompt({ sessionId: id, requestId: 'third-turn', mode: 'queue',
      content: [{ type: 'text', text: '再次继续' }] }, new AbortController().signal);
    const third = (await f.api()).value.tasks[0];
    assert.equal(third.session_id, id);
    assert.equal(f.controlCalls.filter(row => row.path === '/tasks/register').length, 3);
    await f.complete(third);

    process.env.DSH_HOME = join(f.directory, 'other-user-dsh');
    mkdirSync(process.env.DSH_HOME);
    await f.restart();
    await assert.rejects(f.ctx.sessionController.prompt({ sessionId: id, requestId: 'cross-user',
      mode: 'queue', content: [{ type: 'text', text: '拒绝' }] }, new AbortController().signal), /outside/);
    assert.equal(f.controlCalls.filter(row => row.path === '/tasks/register').length, 3);
  } finally { await f.close(); }
});

test('Imported legacy history continues without changing its locked preset or gaining new workspace tools', options, async () => {
  const scene = { id: 'new-scene', label: 'Workspace', preset: 'sss-task', adapter: 'workspace',
    mcp_rows: [], allowed_tools: ['mcp__workspace__read_file'], config_sha256: 'a'.repeat(64) };
  const f = await fixture({ broker: true, dshHome: true, fixtureSchemas: [],
    allowed_tools: scene.allowed_tools, scenes: [scene], capability_profile: scene.id });
  try {
    const id = 'session-11111111-1111-4111-8111-111111111111';
    await f.originalController.create({ sessionId: id, agentPreset: 'sss-task' });
    f.agents.get(id).events.push({ type: 'user/message', data: { id: 'legacy-human',
      source: { kind: 'user' }, content: [{ type: 'text', text: '旧版第一轮' }] } });
    const legacyOutput = join(f.directory, 'old-run'); mkdirSync(legacyOutput);
    const scope = digest({ output: legacyOutput, home: process.env.DSH_HOME });
    writeFileSync(join(legacyOutput, 'session-ownership-' + scope + '.json'), JSON.stringify({
      scope, sessions: [id], bound: [id] }));
    writeFileSync(f.policyPath, JSON.stringify({ ...f.policy, ownership_legacy_outputs: [legacyOutput] }));
    // Official Harness locks the preset once a turn exists.
    f.ctx.agentPresets.select = async () => { throw Error('preset is locked'); };
    await f.restart();
    assert.equal((await f.settings(undefined, '?session_id=' + id)).value.conversation_only, true);
    for (let turn = 1; turn <= 2; turn++) {
      await f.ctx.sessionController.prompt({ sessionId: id, requestId: 'legacy-followup-' + turn,
        mode: 'queue', content: [{ type: 'text', text: '继续文字对话' }] }, new AbortController().signal);
      const task = (await f.api()).value.tasks.find(row => row.request_id === 'legacy-followup-' + turn);
      assert.deepEqual(f.agents.get(id).allow.allow, []);
      const next = () => (async function* () { yield { type: 'fixture' }; })();
      for await (const row of f.stream(f.modelRequest(task, { tools: [] }), next)) assert.equal(row.type, 'fixture');
      await f.complete(task); await f.restart();
    }
    assert.equal(f.promptCalls.length, 2);
    assert.equal(f.presetCalls.length, 0);
    const denied = await f.api({ action: 'preview', session_id: id,
      request: { content: [{ type: 'file', receiptId: 'some-receipt' }] } });
    assert.equal(denied.value.error.code, 'new_session_required');
    assert.equal(f.registrations.size, 2);
  } finally { await f.close(); }
});

test('Real native chat keeps one DSH session across confirmed turns with distinct budget routes', options, async () => {
  const f = await fixture({ broker: true, provider_mode: 'real' });
  try {
    const { sessionId: id } = await f.ctx.sessionController.create({});
    assert.match(id, /^session-[a-f0-9-]{36}$/);
    const prompt = (requestId, text) => f.ctx.sessionController.prompt({ sessionId: id,
      requestId, mode: 'queue', content: [{ type: 'text', text }] }, new AbortController().signal);
    await prompt('first-turn', '你好');
    const first = (await f.api()).value.tasks[0];
    assert.equal(first.status, 'running'); assert.equal(f.promptCalls.length, 1);
    assert.equal(f.brokerRoutes.get(id), 'turn-' + first.task_id);
    assert.equal(f.registrations.get('turn-' + first.task_id).task_id, first.task_id);
    await f.complete(first);
    assert.equal(f.brokerRoutes.has(id), false);
    rmSync(join(f.directory, readdirSync(f.directory).find(name => name.startsWith('task-index-'))));
    rmSync(join(f.directory, 'tasks', first.task_id, 'budget-route.json'));
    f.registrations.set(id, { task_id: first.task_id, budget_usd: .25 });
    await f.restart();
    await prompt('second-turn', '继续回答');
    const tasks = (await f.api()).value.tasks;
    assert.equal(tasks.length, 2);
    assert.equal(tasks.find(task => task.task_id === first.task_id).status, 'completed');
    const second = tasks.find(task => task.task_id !== first.task_id);
    assert.equal(second.session_id, id); assert.notEqual(second.task_id, first.task_id);
    assert.equal(second.status, 'running'); assert.equal(f.promptCalls.length, 2);
    assert.equal(f.brokerRoutes.get(id), 'turn-' + second.task_id);
    assert.equal(f.registrations.get('turn-' + second.task_id).task_id, second.task_id);
    assert.equal(f.promptCalls.length, 2);
    const next = () => (async function* () { yield { type: 'fixture' }; })();
    const model = f.modelRequest(second);
    assert.equal(model.messages.length, 2);
    const received = []; for await (const row of f.stream(model, next)) received.push(row);
    assert.equal(received.length, 1);
    assert.throws(() => f.stream(f.modelRequest(second, { messages: [model.messages[0]] }), next), /envelope/);
    assert.throws(() => f.stream(f.modelRequest(second, { messages: [{ ...model.messages[0],
      content: [{ type: 'text', text: 'changed old user turn' }] }, model.messages[1]] }), next), /envelope/);
    await f.complete(second);
    assert.equal(f.brokerRoutes.has(id), false);
    assert.equal(f.controlCalls.filter(row => row.path === '/tasks/register').length, 2);
    assert.equal(f.controlCalls.filter(row => row.path === '/tasks/cancel').length, 2);
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
      content: [{ type: 'text', text: '应等待当前轮' }] }, new AbortController().signal), /等待本轮完成/);
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
    assertProductPresentationOnly(f.ctx);
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
const productScenes = [
  { ...multiScenes[0], id: 'new-scene', label: 'New Scene' },
  { ...multiScenes[1], id: 'ppt', label: 'PPT', instructions: 'PPT task instructions' },
  { id: 'paper-proofreading', label: 'Paper Proofreading', preset: 'sss-paper', allowed_tools: [], unavailable_reason: 'paper_backend_missing' },
  { id: 'research-data-analysis', label: 'Research Data Analysis', preset: 'sss-data', allowed_tools: [], unavailable_reason: 'data_backend_missing' },
];
test('Four product scenes x three modes x RSI: effective mode, missing backend and Execute admission', options, async () => {
  const f = await fixture({ scenes: productScenes, capability_profile: 'new-scene' });
  try {
    for (const scene of productScenes) for (const mode of ['baseline', 'shadow', 'execute']) for (const rsi of [false, true]) {
      const { sessionId } = await f.ctx.sessionController.create({});
      const selected = await f.settings({ action: 'select', session_id: sessionId, selection: { scene: scene.id, mode, rsi } });
      if (mode === 'execute' && rsi) { assert.equal(selected.value.error.code, 'execute_unavailable'); continue; }
      if (scene.unavailable_reason) { assert.equal(selected.value.error.code, 'scene_not_connected');
        assert.equal((await f.settings(undefined, '?session_id=' + sessionId)).value.selection.scene, 'new-scene'); continue; }
      assert.equal(selected.status, 200); assert.equal(selected.value.selection.scene, scene.id);
      const draft = await f.api({ action: 'preview', session_id: sessionId, request: 'Bound task' });
      if (scene.unavailable_reason) { assert.equal(draft.value.error.code, 'scene_not_connected'); continue; }
      assert.equal(draft.status, 200); assert.equal(draft.value.scene, scene.id);
      assert.equal(draft.value.mode, rsi ? mode : 'baseline'); assert.equal(draft.value.selected_mode, mode);
      const snapshot = JSON.parse(readFileSync(join(f.directory, 'tasks', draft.value.task_id, 'effective-config.json')));
      assert.equal(snapshot.selection.mode, mode); assert.deepEqual(snapshot.allowed_tools, scene.allowed_tools);
      assert.equal(snapshot.instructions, scene.instructions);
    }
    assert.equal(f.promptCalls.length, 0); // all menu/preview operations are model-free
    const denied = await f.api({ action: 'preview', request: { instruction: 'No library', mode: 'execute' } });
    assert.equal(denied.value.error.code, 'execute_unavailable');
    assert.equal((await f.settings({ action: 'select_preview_scene', scene_id: 'unknown' })).status, 400);
  } finally { await f.close(); }
});

test('Running task keeps frozen tools and mode while next-task choices are inherited by a fresh Session', options, async()=>{
  const f=await fixture({ scenes: multiScenes, mode:'shadow', provider_mode:'real' });
  try {
    const first=await f.preview('首项任务');await f.submit(first);
    const next=await f.settings({action:'select',session_id:first.session_id,selection:{scene:'other',rsi:false}});
    assert.equal(next.value.error.code,'session_busy');
    const unchanged = (await f.settings(undefined, '?session_id=' + first.session_id)).value;
    assert.equal(unchanged.selection.scene,'example');assert.equal(unchanged.current_task.mode,'shadow');
    assert.deepEqual(f.agents.get(first.session_id).allow.allow,['mcp__demo__read_note']);
    assert.equal(f.presetCalls.length,0);
    const second=(await f.settings({action:'new_session',inherit_session:first.session_id,selection:{scene:'other',rsi:false}})).value;
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


test('Two server-owned principals have independent settings, task/session identities and workspaces', options, async () => {
  const first = await fixture({ user_id: 'alice', scenes: productScenes, capability_profile: 'new-scene' });
  const second = await fixture({ user_id: 'bob', scenes: productScenes, capability_profile: 'new-scene' });
  try {
    await second.settings({ action: 'select', selection: { scene: 'ppt', rsi: false, mode: 'execute' } });
    const [a, b] = await Promise.all([first.preview('Alice task'), second.preview('Bob task')]);
    assert.equal(a.user_id, 'alice'); assert.equal(b.user_id, 'bob');
    assert.equal(a.scene, 'new-scene'); assert.equal(b.scene, 'ppt');
    assert.equal(b.mode, 'baseline'); assert.equal(b.selected_mode, 'execute');
    assert.equal((await first.api(undefined, '?task_id=' + b.task_id)).status, 404);
    assert.equal((await second.settings(undefined, '?session_id=' + a.session_id)).status, 404);
    await Promise.all([first.submit(a), second.submit(b)]);
    assert.equal(first.promptCalls.length, 1); assert.equal(second.promptCalls.length, 1);
    await Promise.all([first.complete(a), second.complete(b)]);
    await assert.rejects(first.ctx.sessionController.create({ cwd: second.directory }), /private Session/);
  } finally { await second.close(); await first.close(); }
});

test('Session adapter binds private presets and rejects foreign file receipts before model admission', options, async () => {
  const scene = { ...multiScenes[0], id: 'new-scene', adapter: 'workspace',
    mcp_rows: [{ id: 'mcp', name: 'mcp-client', config: { cwd: '__HARLESS_SESSION_WORKSPACE__' } }] };
  const f = await fixture({ scenes: [scene], capability_profile: 'new-scene' });
  try {
    const a = await f.ctx.sessionController.create({}); const b = await f.ctx.sessionController.create({});
    const uploaded = await f.ctx.fileUploads.uploadStream({ sessionId: a.sessionId, name: 'alice.txt',
      data: (async function* () { yield Buffer.from('AAA'); })() });
    const content = [{ type: 'file', receiptId: uploaded.receiptId }];
    const rejected = await f.api({ action: 'preview', session_id: b.sessionId, request: { content } });
    assert.equal(rejected.status, 400); assert.equal(f.registrations.size, 0); assert.equal(f.promptCalls.length, 0);
    const accepted = await f.api({ action: 'preview', session_id: a.sessionId, request: { content } });
    assert.equal(accepted.status, 200); assert.equal(accepted.value.scene_inputs[0].name, 'alice.txt');
    const snapshot = JSON.parse(readFileSync(join(f.directory, 'tasks', accepted.value.task_id, 'effective-config.json')));
    assert.ok(snapshot.workspace.includes(a.sessionId)); assert.ok(!snapshot.workspace.includes(b.sessionId));
    assert.equal(readFileSync(join(snapshot.workspace, 'inputs', 'doc_1-alice.txt'), 'utf8'), 'AAA');
  } finally { await f.close(); }
});

test('Workspace scene accepts first sources after discussion and rejects replacing bound files', options, async () => {
  const scene = { ...multiScenes[0], id: 'paper-proofreading', adapter: 'workspace', mcp_rows: [] };
  const f = await fixture({ broker: true, scenes: [scene], capability_profile: 'paper-proofreading' });
  try {
    const { sessionId } = await f.ctx.sessionController.create({});
    await f.ctx.sessionController.prompt({ sessionId, requestId: 'first', mode: 'queue',
      content: [{ type: 'text', text: 'First turn' }] }, new AbortController().signal);
    const first = (await f.api()).value.tasks[0];
    await f.complete(first);
    await f.ctx.sessionController.prompt({ sessionId, requestId: 'second', mode: 'queue',
      content: [{ type: 'text', text: 'Second turn' }] }, new AbortController().signal);
    const second = (await f.api()).value.tasks.find(row => row.task_id !== first.task_id);
    assert.equal(second.session_id, sessionId);
    assert.equal(second.status, 'running');
    assert.equal(f.promptCalls.length, 2);
    await f.complete(second);
    const uploaded = await f.ctx.fileUploads.uploadStream({ sessionId, name: 'new.txt',
      data: (async function* () { yield Buffer.from('new evidence'); })() });
    const mounts=f.presetCalls.length;
    const accepted = await f.api({ action: 'preview', session_id: sessionId,
      request: { content: [{ type: 'file', receiptId: uploaded.receiptId }] } });
    assert.equal(accepted.status,200); assert.equal(accepted.value.source_pending,false);
    assert.equal(f.presetCalls.length,mounts,'first sources use the already mounted lazy workspace adapter');
    await f.submit(accepted.value);await f.complete(accepted.value);
    const denied = await f.api({ action: 'preview', session_id: sessionId,
      request: { content: [{ type: 'file', receiptId: uploaded.receiptId }] } });
    assert.equal(denied.status, 409);
    assert.equal(denied.value.error.code, 'new_session_required');
  } finally { await f.close(); }
});

test('Cold scene followup restores MCP schemas even when the selected model was persisted', options, async () => {
  const scene = { ...multiScenes[0], id: 'new-scene', adapter: 'workspace', mcp_rows: [] };
  const f = await fixture({ broker: true, dshHome: true, scenes: [scene], capability_profile: 'new-scene' });
  try {
    const { sessionId } = await f.ctx.sessionController.create({});
    const prompt = id => f.ctx.sessionController.prompt({ sessionId, requestId: id, mode: 'queue',
      content: [{ type: 'text', text: 'Restore this same scene and model' }] }, new AbortController().signal);
    await prompt('before-cold');
    const first = (await f.api()).value.tasks[0]; await f.complete(first);
    await f.restart(); assert.equal(f.agents.size, 0);
    await prompt('after-cold');
    const second = (await f.api()).value.tasks.find(row => row.task_id !== first.task_id);
    assert.equal(second.status, 'running'); assert.equal(second.session_id, sessionId);
    assert.ok(f.agents.has(sessionId)); assert.equal(f.promptCalls.length, 2);
    await f.complete(second);
  } finally { await f.close(); }
});

test('Changed uploaded bytes invalidate the frozen task before budget activation', options, async () => {
  const scene = { ...multiScenes[0], adapter: 'workspace', mcp_rows: [] };
  const f = await fixture({ scenes: [scene] });
  try {
    const draft = await f.preview('Freeze session input');
    const snapshot = JSON.parse(readFileSync(join(f.directory, 'tasks', draft.task_id, 'effective-config.json')));
    writeFileSync(join(snapshot.workspace, 'inputs', 'injected.txt'), 'Unconfirmed evidence');
    const denied = await f.submit(draft);
    assert.equal(denied.value.error.code, 'confirmation_changed');
    assert.equal(f.controlCalls.filter(call => call.path === '/tasks/activate').length, 0);
    assert.equal(f.promptCalls.length, 0);
  } finally { await f.close(); }
});


test('Production Execute requires a certified whole-schema snapshot and rejects descriptor/type drift', options, async () => {
  const manifest = fileURLToPath(new URL('../examples/motif-library/research-portfolio-v1/online-manifest.json', import.meta.url));
  const task = fileURLToPath(new URL('../examples/motif-library/research-portfolio-v1/task.json', import.meta.url));
  const library = JSON.parse(readFileSync(manifest));
  const rows = Object.entries(library.contracts).map(([name, contract]) => ({ name, description: contract.description,
    parameters: { type: 'object', properties: Object.fromEntries(contract.required_params.map(param => [param, { type: 'string' }])), required: contract.required_params } }))
    .sort((a, b) => a.name < b.name ? -1 : 1);
  const scene = { ...multiScenes[0], allowed_tools: rows.map(row => row.name), manifest, task,
    embedding_endpoint: 'http://127.0.0.1:1/v1/embeddings', embedding_model: 'fixture', certified_input_sha256: 'a'.repeat(64) };
  const f = await fixture({ scenes: [scene], fixture_schemas: rows });
  try {
    const missing = await f.api({ action: 'preview', request: { instruction: 'No certified full schema', mode: 'execute' } });
    assert.equal(missing.value.error.code, 'execute_unavailable');
    assert.match(missing.value.error.message, /no_certified_tool_schemas/);
    assert.equal(f.registrations.size, 0);
  } finally { await f.close(); }
  const changed = structuredClone(rows); changed[0].description = 'Changed after certification';
  const g = await fixture({ scenes: [{ ...scene, certified_tool_schemas: changed }], fixture_schemas: rows });
  try {
    const denied = await g.api({ action: 'preview', request: { instruction: 'Schema mismatch', mode: 'execute' } });
    assert.equal(denied.value.error.code, 'execute_unavailable'); assert.match(denied.value.error.message, /certified_tool_schema_mismatch/);
    assert.equal(g.registrations.size, 0); assert.equal(g.promptCalls.length, 0);
  } finally { await g.close(); }
});

test('Member zero-tool policy cannot inherit owner scene MCP capabilities', options, async () => {
  const f = await fixture({ broker: true, allowed_tools: [], fixtureSchemas: [], scenes: productScenes, capability_profile: 'new-scene' });
  try {
    const list = (await f.settings()).value.scenes;
    assert.equal(list.find(row => row.id === 'new-scene').available, true);
    assert.equal(list.find(row => row.id === 'ppt').unavailable_reason, 'scene_not_deployed_in_member_sandbox');
    assert.equal((await f.settings({ action: 'select', selection: { scene: 'ppt', mode: 'baseline' } })).value.error.code, 'scene_not_connected');
    const denied = await f.api({ action: 'preview', request: { content: [{type:'text',text:'PPT must not use ordinary chat as its backend'}], capability_profile:'ppt' } });
    assert.equal(denied.value.error.code, 'scene_not_connected');
    await f.settings({ action: 'select', selection: { scene: 'new-scene' } });
    const draft = await f.preview('Generic member task');
    assert.deepEqual(f.agents.get(draft.session_id).allow.allow, []);
    assert.equal(f.registrations.size, 1);
  } finally { await f.close(); }
});

test('Restricted member starts New Scene even when owner default is a privileged scene', options, async () => {
  const rows = productScenes.map(row => ({ ...row, preset: row.id === 'ppt' ? 'sss-task' : 'sss-' + row.id }));
  const f = await fixture({ broker: true, allowed_tools: [], fixtureSchemas: [], scenes: rows, capability_profile: 'ppt', budget_task_prefix: 'a1234567' });
  try {
    assert.equal((await f.settings()).value.selection.scene, 'new-scene');
    const task = await f.preview('Member generic chat');
    assert.equal(task.scene, 'new-scene'); assert.equal(task.user_id, 'member-a1234567');
    assert.ok(task.task_id.startsWith('a1234567')); assert.equal(f.presetCalls.length, 0);
  } finally { await f.close(); }
});

test('Restored terminal task retains its approved scene version and selected Off mode', options, async () => {
  const f = await fixture({ scenes: multiScenes });
  try {
    await f.settings({ action: 'select', selection: { mode: 'execute', rsi: false } });
    const task = await f.preview('Frozen version through restart'); await f.submit(task); await f.complete(task);
    const file = join(f.directory, 'policy.json'); const policy = JSON.parse(readFileSync(file));
    policy.scenes[0].config_sha256 = 'c'.repeat(64); writeFileSync(file, JSON.stringify(policy));
    await f.restart();
    const recovered = (await f.api(undefined, '?task_id=' + task.task_id)).value;
    assert.equal(recovered.scene_sha256, 'a'.repeat(64)); assert.equal(recovered.selected_mode, 'execute');
    assert.equal(recovered.mode, 'baseline'); assert.equal(recovered.confirmation_digest, task.confirmation_digest);
    assert.equal((await f.settings()).value.scenes[0].config_sha256, 'c'.repeat(64));
    assert.equal(f.promptCalls.length, 1);
  } finally { await f.close(); }
});

test('Settings first touch safely admits an untouched local blank session before the picker fetch', options, async () => {
  const f = await fixture({ broker:true });
  try {
    await f.originalController.create({ sessionId:'fresh-picker', agentPreset:'sss-task' });
    const menu = await f.settings(undefined, '?session_id=fresh-picker');
    assert.equal(menu.status,200); assert.equal(menu.value.selection.scene,'example');
    assert.equal(f.registrations.size,0); assert.equal(f.promptCalls.length,0);
    await f.originalController.create({ sessionId:'unknown-history', agentPreset:'sss-task' });
    f.agents.get('unknown-history').events.push({ type:'user/message', data:{ content:[] } });
    assert.equal((await f.settings(undefined,'?session_id=unknown-history')).status,404);
  } finally { await f.close(); }
});

test('Native workspace creation uses one location and scene-switch sessions stay in the owning group', options, async () => {
  const f=await fixture({broker:true,scenes:multiScenes});
  try {
    const group=await f.ctx.workspaceRegistry.create(f.directory,'课题组');
    const created=await f.ctx.sessionController.create({workspaceId:group.id,sessionId:'native-workspace'});
    assert.ok(group.sessionIds.includes(created.sessionId));
    const child=await f.settings({action:'new_session',inherit_session:created.sessionId,selection:{scene:'other'}});
    assert.equal(child.status,200);assert.ok(group.sessionIds.includes(child.value.session_id));
    await assert.rejects(f.ctx.sessionController.create({workspaceId:group.id,cwd:f.directory}),/不能同时/);
    await f.restart();assert.equal((await f.settings(undefined,'?session_id='+child.value.session_id)).status,200);
    assert.equal(f.registrations.size,0);
  } finally {await f.close();}
});

test('Managed workspace name flow creates grouped chats and preserves legacy groups in both budget modes', options, async () => {
  for (const broker of [false, true]) {
    const f = await fixture({ broker, scenes: multiScenes });
    const post = async (path, data) => {
      const request = new Request('http://localhost' + path, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(data) });
      request.authorized = true;
      const response = await f.routes.get(path).fetch(request);
      assert.equal(response.status, 200);
      return response.json();
    };
    try {
      const made = await post('/api/harless/workspaces', { name: '研究项目', request_id: randomUUID() });
      const adoption = await post('/api/workspace/create', { type: 'client-request', rpcId: 'native-adoption', method: 'workspace/create',
        payload: { args: { request: { path: made.workspace.path } } } });
      assert.equal(adoption.result.ok, true);
      const workspaceId = adoption.result.value.workspace.workspaceId;
      const first = await f.ctx.sessionController.create({ workspaceId });
      const second = await f.ctx.sessionController.create({ workspaceId });
      const group = f.ctx.workspaceRegistry.get(workspaceId);
      assert.deepEqual(group.sessionIds, [first.sessionId, second.sessionId]);
      assert.equal((await f.ctx.sessionController.inspect(first.sessionId)).meta.cwd, group.path);
      assert.equal(made.workspace.path, '/workspaces/' + workspaceId);
      assert.notEqual(group.path, made.workspace.path, 'host storage is not returned as a browser address');
      const switched = await f.settings({ action: 'new_session', inherit_session: second.sessionId, selection: { scene: 'other' } });
      assert.equal(switched.status, 200); assert.ok(group.sessionIds.includes(switched.value.session_id));
      const oldPath = join(f.directory, 'legacy-project'); mkdirSync(oldPath); writeFileSync(join(oldPath, 'notes.txt'), 'preserve');
      const legacy = await f.ctx.workspaceRegistry.create(oldPath, '旧工作区');
      const legacyChat = await f.ctx.sessionController.create({ workspaceId: legacy.id });
      assert.ok(legacy.sessionIds.includes(legacyChat.sessionId));
      assert.equal(readFileSync(join(oldPath, 'notes.txt'), 'utf8'), 'preserve');
      await assert.rejects(f.ctx.sessionController.create({ cwd: oldPath }), error => error.code === 'workspace_not_allowed');
      await assert.rejects(f.ctx.sessionController.create({ workspaceId: '' }), error => error.code === 'workspace_not_allowed');
      await f.restart();
      const reopened = await f.ctx.sessionController.create({ workspaceId });
      assert.ok(group.sessionIds.includes(reopened.sessionId));
      assert.equal(f.registrations.size, 0); assert.equal(f.promptCalls.length, 0);
    } finally { await f.close(); }
  }
});

test('Managed chat creation rejects another account workspace ID without registering a session', options, async () => {
  const alice = await fixture({ broker: true, user_id: 'alice' });
  const bob = await fixture({ broker: true, user_id: 'bob' });
  try {
    const foreign = await alice.ctx.workspaceRegistry.create(alice.directory, 'Alice project');
    const before = bob.agents.size;
    await assert.rejects(bob.ctx.sessionController.create({ workspaceId: foreign.id }), error => error.code === 'workspace_not_allowed' && error.status === 403);
    assert.equal(bob.agents.size, before); assert.deepEqual(foreign.sessionIds, []);
    const own = await bob.ctx.workspaceRegistry.create(bob.directory, 'Bob project');
    const accepted = await bob.ctx.sessionController.create({ workspaceId: own.id });
    assert.deepEqual(own.sessionIds, [accepted.sessionId]);
    assert.equal(alice.registrations.size + bob.registrations.size, 0);
  } finally { await bob.close(); await alice.close(); }
});

test('A scene switch on started history fails before mutation and restart repairs old planned-scene pollution', options, async () => {
  const f = await fixture({ broker:true, scenes:multiScenes });
  try {
    const {sessionId}=await f.ctx.sessionController.create({});
    const send = request_id => f.ctx.sessionController.prompt({ sessionId, requestId:request_id, mode:'queue', content:[{type:'text',text:'普通续聊'}] },new AbortController().signal);
    await send('first'); await f.complete((await f.api()).value.tasks[0]);
    const switched=await f.settings({action:'select',session_id:sessionId,selection:{scene:'other'}});
    assert.equal(switched.status,409); assert.equal(switched.value.error.code,'scene_requires_new_session');
    assert.equal((await f.settings(undefined,'?session_id='+sessionId)).value.selection.scene,'example');
    const path=join(f.directory,'harless-settings.json'), saved=JSON.parse(readFileSync(path));
    saved.sessions[sessionId].scene='other'; writeFileSync(path,JSON.stringify(saved));
    await f.restart(); assert.equal((await f.settings(undefined,'?session_id='+sessionId)).value.selection.scene,'example');
    await send('second'); const task=(await f.api()).value.tasks.find(row=>row.request_id==='second');
    assert.equal(task.scene,'example'); await f.complete(task);
  } finally { await f.close(); }
});

test('PPT shortcut selects the scene, strips only its control token, and preserves the job across followups and restart', options, async () => {
  const ppt={ ...multiScenes[0],id:'ppt',label:'PPT',adapter:'ppt',mcp_rows:[] };
  const f=await fixture({broker:true,scenes:[ppt],capability_profile:'ppt'});
  try {
    const {sessionId}=await f.ctx.sessionController.create({});
    const prompt=(text,requestId)=>f.ctx.sessionController.prompt({sessionId,requestId,mode:'queue',content:[{type:'text',text}]},new AbortController().signal);
    await prompt('/ppt','selection-only'); assert.equal(f.promptCalls.length,0); assert.equal(f.registrations.size,0);
    await prompt('/ppt 先讨论结构','first-ppt'); let task=(await f.api()).value.tasks[0];
    assert.equal(f.promptCalls[0].content[0].text,'先讨论结构'); await f.complete(task);
    const jobPath=join(f.directory,'sessions',sessionId,'work','job.json'), jobBefore=readFileSync(jobPath,'utf8'), presetCount=f.presetCalls.length;
    await prompt('接着讨论第二页','second-ppt'); task=(await f.api()).value.tasks.find(row=>row.request_id==='second-ppt');
    assert.equal(task.scene,'ppt'); assert.equal(f.presetCalls.length,presetCount); assert.equal(readFileSync(jobPath,'utf8'),jobBefore);
    await f.complete(task); await f.restart();
    await prompt('继续第三页','third-ppt'); task=(await f.api()).value.tasks.find(row=>row.request_id==='third-ppt');
    assert.equal(readFileSync(jobPath,'utf8'),jobBefore); await f.complete(task);
    const denied=await f.api({action:'preview',session_id:sessionId,request:{content:[{type:'text',text:'变更权限'}],scene_options:{allow_output:true}}});
    assert.equal(denied.value.error.code,'new_session_required');
    assert.equal(f.registrations.size,3);
  } finally { await f.close(); }
});
test('PPT menu options are scoped, model-free, persisted, and cannot modify a preview',options,async()=>{
  const rows=[{id:'ppt',label:'PPT',preset:'sss-task',allowed_tools:toolSchemas.map(t=>t.name),adapter:'ppt',mcp_rows:[]},
    {id:'new-scene',label:'New Scene',preset:'sss-general',allowed_tools:toolSchemas.map(t=>t.name)}];
  const f=await fixture({scenes:rows,capability_profile:'ppt'});
  try{
    const first=await f.ctx.sessionController.create({});
    const route=f.routes.get('/api/harless/settings');
    const call=async body=>{const r=await route.fetch(new Request('http://local/api/harless/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}));return {status:r.status,value:await r.json()};};
    const saved=await call({action:'set_scene_options',session_id:first.sessionId,options:{slides:8,template:'lab',allow_output:false}});
    assert.equal(saved.status,200);assert.equal(saved.value.model_calls,0);
    const draft=await f.api({action:'preview',session_id:first.sessionId,request:'Read-only inspection'});
    assert.equal(draft.value.scene_options.slides,8);
    const changed=await call({action:'set_scene_options',session_id:first.sessionId,options:{slides:12,allow_output:true}});
    assert.equal(changed.status,409); assert.equal(changed.value.error.code,'scene_requires_new_session');
    const existing=(await f.api(undefined,'?task_id='+draft.value.task_id)).value;
    assert.equal(existing.scene_options.slides,8);assert.equal(existing.scene_options.allow_output,false);
    assert.equal(existing.confirmation_digest,draft.value.confirmation_digest);
    assert.equal((await call({action:'set_scene_options',session_id:'foreign',options:{allow_output:true}})).status,404);
    assert.equal((await call({action:'set_scene_options',session_id:first.sessionId,options:{command:'arbitrary'}})).status,409);
    assert.equal(f.promptCalls.length,0);
    await f.api({action:'cancel',task_id:draft.value.task_id});
    await f.api(undefined,'?task_id='+draft.value.task_id);
    await f.restart();
    const restored=await f.settings(undefined,'?session_id='+first.sessionId);
    assert.equal(restored.value.scene_options.allow_output,false); assert.equal(restored.value.scene_options.slides,8);
  }finally{await f.close();}
});

test('Empty file scenes keep normal scene tools and model routing across turns and restart', options, async () => {
  for (const [id, adapter] of [['ppt','ppt'], ['paper-proofreading','workspace'], ['research-data-analysis','data-report'], ['literature','literature'], ['files','files']]) {
    const scene = {...multiScenes[0], id, label:id, adapter, mcp_rows:[]};
    const f = await fixture({ broker:true, scenes:[scene], capability_profile:id });
    try {
      const { sessionId } = await f.ctx.sessionController.create({});
      assert.equal((await f.ctx.sessionController.inspect(sessionId)).meta.title, '新会话');
      for (let round=0;round<3;round++) {
        if(round===2) await f.restart();
        const result=await f.api({action:'preview',session_id:sessionId,request:{instruction:'你好，请介绍你能帮我做什么',request_id:`empty-${round}`}});
        assert.equal(result.status,200,JSON.stringify(result.value));
        const task=result.value; assert.equal(task.source_pending,true); assert.deepEqual(task.scene_inputs,[]);
        assert.deepEqual(f.agents.get(sessionId).allow.allow,scene.allowed_tools);
        assert.match(f.agents.get(sessionId).instruction,/正常回应问候/);
        assert.equal((await f.submit(task)).status,200);
        await f.complete(task);
      }
      assert.equal(f.promptCalls.length,3);
    } finally {await f.close();}
  }
});

test('General workspace keeps its tools without requiring uploads', options, async()=>{
 const scene={...multiScenes[0],id:'new-scene',adapter:'workspace',mcp_rows:[]};
 const f=await fixture({broker:true,scenes:[scene],capability_profile:'new-scene'});
 try {
  const {sessionId}=await f.ctx.sessionController.create({});
  const result=await f.api({action:'preview',session_id:sessionId,request:'创建一份新的笔记'});
  assert.equal(result.status,200);assert.equal(result.value.source_pending,false);
  assert.deepEqual(f.agents.get(sessionId).allow.allow,scene.allowed_tools);
 }finally{await f.close();}
});


test('Completed parent routes ordinary → data → PPT → chat without moving history or mutating prior scopes',options,async()=>{
 const scenes=[{...multiScenes[0],id:'new-scene',adapter:'workspace',mcp_rows:[]},
  {...multiScenes[0],id:'research-data-analysis',preset:'sss-data',adapter:'workspace',mcp_rows:[]},
  {...multiScenes[0],id:'ppt',preset:'sss-ppt',adapter:'ppt',mcp_rows:[]}];
 const f=await fixture({broker:true,scenes,capability_profile:'new-scene',comparison_scenes:['research-data-analysis','ppt']});
 try{
  const {sessionId}=await f.ctx.sessionController.create({});
  const send=(text,id)=>f.ctx.sessionController.prompt({sessionId,requestId:id,mode:'queue',content:[{type:'text',text}]},new AbortController().signal);
  await send('Remember ordinary context','ordinary');const first=(await f.api()).value.tasks[0];
  f.agents.get(sessionId).session.append('assistant/message',{message:{content:[{type:'text',text:'ordinary remembered'}]}});await f.complete(first);
  const priorScopes=f.presetCalls.length;
  const compare=async(id,stream=false,parent=sessionId)=>{const request=new Request('http://local/api/harless/comparisons?session_id='+parent+'&id='+id+(stream?'&stream=1':''));request.authorized=true;return f.routes.get('/api/harless/comparisons').fetch(request);};
  const settle=async (id,parent=sessionId)=>{for(let attempt=0;attempt<200;attempt++){
    for(const task of (await f.api()).value.tasks)if(task.status==='running'){
      f.agents.get(task.session_id).session.append('assistant/message',{message:{content:[{type:'text',text:'answer-'+task.scene+'-'+task.session_id}]}});
      if(task.scene==='ppt'){const outputs=join(f.directory,'sessions',task.session_id,'work','outputs');mkdirSync(outputs,{recursive:true});writeFileSync(join(outputs,'report.pdf'),'pdf-'+task.session_id);}
      await f.complete(task);
    }
    const value=await (await compare(id,false,parent)).json();if(['completed','failed'].includes(value.status)){assert.equal(value.status,'completed',JSON.stringify(value));return value;}await new Promise(r=>setTimeout(r,10));
  }throw Error('comparison timeout');};
  const data=await send('/data Discuss data','data');
  const running=(await f.settings({action:'select',session_id:sessionId,selection:{scene:'ppt'}}));assert.equal(running.value.error.code,'session_busy');
  const dataView=await settle(data.comparison_id);assert.equal(dataView.session_id,sessionId);
  const parentGroup=f.ctx.workspaceRegistry.list().find(group=>group.sessionIds.includes(sessionId));
  assert.deepEqual(parentGroup.sessionIds,[sessionId],'comparison lanes must not become workspace chats');
  assert.equal(f.ctx.workspaceRegistry.list().length,1,'private lanes must not create their own visible groups');
  for(const lane of Object.values(dataView.lanes))await assert.rejects(f.ctx.sessionController.create({sessionId:lane.session_id,workspaceId:parentGroup.id}),error=>error.code==='comparison_child');
  const dataState=JSON.parse(readFileSync(join(f.directory,'comparisons.json'))).turns.at(-1);
  assert.match(dataState.prior_context.baseline,/ordinary remembered/);
  const ppt=await send('/ppt Use previous findings','ppt'),pptView=await settle(ppt.comparison_id);
  assert.equal(pptView.session_id,sessionId);assert.notEqual(dataView.lanes.baseline.session_id,pptView.lanes.baseline.session_id);
  assert.match(JSON.parse(readFileSync(join(f.directory,'comparisons.json'))).turns.at(-1).prior_context.baseline,/answer-research-data-analysis/);
  const chat=await send('/chat Explain the slides','chat'),chatView=await settle(chat.comparison_id);
  assert.equal(chatView.presentation,'single');assert.deepEqual(Object.keys(chatView.lanes),['baseline']);
  assert.equal((await f.ctx.sessionController.inspect(sessionId)).events.filter(e=>e.type==='user/message').length,4);
  const old=(await f.api(undefined,'?task_id='+first.task_id)).value;assert.equal(old.answer,'ordinary remembered');assert.equal(old.scene,'new-scene');
  assert.ok(f.presetCalls.length>priorScopes);assert.equal(f.presetCalls.filter(row=>row.session_id===sessionId).length,priorScopes);
  const response=await compare(chat.comparison_id,true);assert.match(response.headers.get('Content-Type'),/event-stream/);const reader=response.body.getReader();
  const chunk=new TextDecoder().decode((await reader.read()).value);assert.match(chunk,/event: snapshot/);assert.match(chunk,/snapshot_revision/);await reader.cancel();
  const parentEvents=(await f.ctx.sessionController.inspect(sessionId)).events;
  // The synthetic native fixture does not number its direct first prompt;
  // normalize that pre-fixture event exactly as the real Session log does.
  parentEvents.forEach((event,index)=>event.seq=index);
  const pptEvent=parentEvents.find(event=>event.data?.harless_comparison?.id===ppt.comparison_id);
  const branch=await f.ctx.sessionController.fork({sessionId,atSeq:pptEvent.seq});
  const branchInputs=JSON.parse(readFileSync(join(f.directory,'sessions',branch.sessionId,'work','branch-inputs.json')));
  for(const lane of ['baseline','motif']){
    assert.equal(branchInputs.lanes[lane].length,1);
    assert.equal(comparisonArtifacts(f.directory).read(branch.sessionId,lane,branchInputs.lanes[lane][0]).toString(),'pdf-'+pptView.lanes[lane].session_id);
    assert.match(JSON.stringify(branchInputs.context[lane]),new RegExp(pptView.lanes[lane].session_id));
    assert.doesNotMatch(JSON.stringify(branchInputs.context[lane]),new RegExp(pptView.lanes[lane==='baseline'?'motif':'baseline'].session_id));
  }
  const branchEvents=(await f.ctx.sessionController.inspect(branch.sessionId)).events;
  const dataAnchor=branchEvents.find(event=>event.type==='user/message'&&event.data.content?.some(part=>part.text?.includes('Discuss data'))).seq;
  const earlier=await f.ctx.sessionController.fork({sessionId:branch.sessionId,atSeq:dataAnchor});
  const earlierInputs=JSON.parse(readFileSync(join(f.directory,'sessions',earlier.sessionId,'work','branch-inputs.json')));
  for(const lane of ['baseline','motif']){
    assert.equal(earlierInputs.lanes[lane].length,0,'later PPT delivery cannot cross a nested branch cutoff');
    assert.match(JSON.stringify(earlierInputs.context[lane]),new RegExp(dataView.lanes[lane].session_id));
    assert.doesNotMatch(JSON.stringify(earlierInputs.context[lane]),new RegExp(pptView.lanes[lane].session_id));
  }
  const continued=await f.ctx.sessionController.prompt({sessionId:branch.sessionId,requestId:'branch-continue',mode:'queue',content:[{type:'text',text:'/ppt Continue from the report'}]},new AbortController().signal);
  const continuedView=await settle(continued.comparison_id,branch.sessionId);
  for(const lane of ['baseline','motif']){
    const work=join(f.directory,'sessions',continuedView.lanes[lane].session_id,'work');
    const job=JSON.parse(readFileSync(join(work,'job.json')));assert.equal(job.allow_output,true);assert.equal(job.inputs.length,1);
    assert.equal(readFileSync(job.inputs[0].path,'utf8'),'pdf-'+pptView.lanes[lane].session_id);
  }
  await f.restart();assert.equal((await f.settings(undefined,'?session_id='+sessionId)).value.selection.scene,'new-scene');
 }finally{await f.close();}
});

test('Native fork creates independently numbered fresh scopes in the same account workspace',options,async()=>{
 const f=await fixture({broker:true,scenes:multiScenes});
 try{
  const {sessionId}=await f.ctx.sessionController.create({});const source=f.agents.get(sessionId);
  source.session.append('turn/start',{turn:1});
  source.session.append('user/message',{id:'u',role:'user',source:{kind:'user'},content:[{type:'text',text:'original'}]},{surfaceOp:'append'});
  source.session.append('assistant/message',{turn:1,step:0,stream:[],message:{id:'a',role:'assistant',source:{kind:'model',provider:'deepseek-official',model:'deepseek-flash'},content:[{type:'text',text:'answer'}]}},{surfaceOp:'append'});
  source.session.append('turn/end',{turn:1,reason:{kind:'completed'}});
  await f.ctx.sessionController.rename({sessionId,title:'Research'});
  const [a,b]=await Promise.all([f.ctx.sessionController.fork({sessionId,atSeq:2}),f.ctx.sessionController.fork({sessionId,atSeq:2})]);
  const first=await f.ctx.sessionController.inspect(a.sessionId),second=await f.ctx.sessionController.inspect(b.sessionId);
  assert.equal(first.meta.title,'Research（1）');assert.equal(second.meta.title,'Research（2）');
  assert.notEqual(a.sessionId,b.sessionId);assert.equal(first.events[1].data.content[0].text,'original');
  assert.equal(first.meta.parentSession,sessionId);assert.equal(first.meta.cwd,(await f.ctx.sessionController.inspect(sessionId)).meta.cwd);
  await assert.rejects(f.ctx.sessionController.fork({sessionId:'foreign'}),error=>error.code==='session_not_owned');
  assert.equal(f.registrations.size,0);
 }finally{await f.close();}
});


test('Task API exposes real text chunks and tool activity before completion and retains safe progress on restart',options,async()=>{
 const f=await fixture({broker:true});try{
  const task=await f.preview({instruction:'stream fixture'});await f.submit(task);
  const stream=f.stream(f.modelRequest(task),async function*(){yield {type:'text-delta',index:0,text:'first'};yield {type:'text-delta',index:0,text:' second'};});
  const iterator=stream[Symbol.asyncIterator]();await iterator.next();
  let live=(await f.api(undefined,'?task_id='+task.task_id)).value;assert.equal(live.answer,'first');assert.equal(live.progress.status,'running');
  await iterator.next();live=(await f.api(undefined,'?task_id='+task.task_id)).value;assert.equal(live.answer,'first second');await iterator.next();
  f.emit('session/event',f.agents.get(task.session_id).session,{type:'tool/call',data:{name:'mcp__demo__read_note',callId:'safe',arguments:{path:'/private/server'}}});
  live=(await f.api(undefined,'?task_id='+task.task_id)).value;assert.equal(live.activity[0].label,'读取资料');assert.doesNotMatch(JSON.stringify(live.activity),/private/);
  await f.complete(task);await f.restart();live=(await f.api(undefined,'?task_id='+task.task_id)).value;
  assert.equal(live.progress.status,'completed');assert.equal(live.activity[0].status,'failed','a tool without a real result is never presented as success');
 }finally{await f.close();}
});
