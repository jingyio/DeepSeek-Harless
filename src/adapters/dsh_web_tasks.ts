/** Dynamic business tasks on the official Harness Web/Session lifecycle. */
import { createHash, randomUUID } from 'node:crypto';
import { appendFileSync, mkdirSync, readFileSync, writeFileSync, renameSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { DeepSeekAdapter, resolveAdapterOptions } from '@deepseek-ai/dsh-llm-deepseek';
import { isAgentLoopRequest } from '@deepseek-ai/dsh-llm';
import { scopeOf } from '@deepseek-ai/dsh-scope';
import { createOnlineInterceptor, loopbackSimilarity } from './dsh_online_motif.mjs';
import { digest } from '../motif_core/online_skill_runtime.mjs';
import { normalizeWebTaskRequest, WebTaskRequestError } from './web_task_request.ts';
import type { NormalizedWebTask, PromptPart, ExecutionMode } from './web_task_request.ts';

export const name = 'sss-web-tasks';
export const inject = ['llm', 'agents', 'sessionController', 'connection', 'webServer', 'fileUploads'];
type Policy = {
  output: string; allowed_tools: string[]; endpoint: string; max_output_tokens: number;
  mode: ExecutionMode; budget_usd: number; capability_profile: string;
  provider_mode: 'mock' | 'real'; control_endpoint: string; control_token: string;
  manifest?: string; task?: string; certified_input_sha256?: string;
  embedding_endpoint?: string; embedding_model?: string; fixture?: string;
  resources?: Record<string, { version: string; text: string }>;
};
type Task = {
  request: NormalizedWebTask; delivery: PromptPart[]; confirmation_digest: string;
  status: string; created_at: string; started_at?: string; finished_at?: string;
  failure: string | null; fallback_reason: string | null; answer: string;
  output: string; stats: Record<string, any>; interceptor?: any;
  humans: Map<string, string>; sources: { resource_id: string; version: string; sha256: string }[];
  closing?: Promise<void>; entrypoint: 'workbench' | 'native_chat';
};
class TaskError extends Error {
  code: string; status: number;
  constructor(code: string, message: string, status = 400) { super(message); this.code = code; this.status = status; }
}
const sha = (value: string | Uint8Array) => createHash('sha256').update(value).digest('hex');
const fileSha = (path: string | undefined) => { try { return path ? sha(readFileSync(path)) : null; } catch { return null; } };
const utc = () => new Date().toISOString();
const terminal = new Set(['completed', 'failed', 'cancelled', 'budget_exhausted']);
const loopback = (endpoint: string) => /^http:\/\/127\.0\.0\.1:\d+(?:\/v1)?$/.test(endpoint);
const json = (path: string, value: unknown) => {
  writeFileSync(path + '.tmp', JSON.stringify(value, null, 2), { mode: 0o600 });
  renameSync(path + '.tmp', path);
};

export function apply(ctx: any) {
  const config: Policy = JSON.parse(readFileSync(process.env.SSS_WEB_POLICY!, 'utf8'));
  if (!loopback(config.endpoint) || !loopback(config.control_endpoint) ||
      !config.control_token || !config.allowed_tools?.length ||
      !['baseline', 'shadow', 'execute'].includes(config.mode) ||
      !['mock', 'real'].includes(config.provider_mode)) throw Error('Invalid dynamic Web policy');
  const tasks = new Map<string, Task>(), sessions = new Map<string, string>();
  const schemas = new Map<string, any[]>(), requests = new Map<string, string>();
  const ownedSessions = new Set<string>(), allowed = new Set(config.allowed_tools);
  let active: string | null = null;
  // Serial admission prevents two preview/submit retries from creating duplicate work.
  let admission: Promise<unknown> = Promise.resolve();
  const serialize = <T>(operation: () => Promise<T>): Promise<T> => {
    const result = admission.then(operation); admission = result.catch(() => undefined); return result;
  };
  async function control(path: string, payload?: unknown) {
    const response = await fetch(config.control_endpoint + path, {
      method: payload === undefined ? 'GET' : 'POST',
      headers: { 'X-SSS-Control-Token': config.control_token, 'Content-Type': 'application/json' },
      ...(payload === undefined ? {} : { body: JSON.stringify(payload) }), signal: AbortSignal.timeout(10000),
    });
    const value: any = await response.json();
    if (!response.ok) throw new TaskError('budget_control_failed', value.error || 'Budget service refused request', 409);
    return value;
  }
  function get(id: unknown): Task {
    if (typeof id !== 'string' || !tasks.has(id)) throw new TaskError('task_not_found', 'Unknown task', 404);
    return tasks.get(id)!;
  }
  const forSession = (id: string): Task | undefined => tasks.get(sessions.get(id) ?? '');
  function view(task: Task, detail = false) {
    const request = task.request;
    return { task_id: request.task_id, session_id: request.session_id, request_id: request.request_id,
      capability_profile: request.capability_profile, mode: request.mode, budget_usd: request.budget_usd,
      entrypoint: task.entrypoint, status: task.status, failure: task.failure, fallback_reason: task.fallback_reason,
      created_at: task.created_at, started_at: task.started_at, finished_at: task.finished_at,
      input_summary: request.summary, prompt_sha256: request.prompt_sha256,
      request_sha256: request.request_sha256, confirmation_digest: task.confirmation_digest,
      provider_mode: config.provider_mode, paid_calls_enabled: config.provider_mode === 'real',
      effects: 'Only server-configured MCP capabilities; file changes require MCP-side confirmation.',
      stats: task.stats, sources: task.sources,
      ...(detail ? { answer: task.answer, input_preview: task.delivery.filter(part => part.type === 'text').map(part => (part as any).text).join('\n').slice(0, 4096), artifacts: ['task.json', 'effective-config.json', 'events.jsonl',
        'ledger.jsonl', 'motif-audit.jsonl', ...(task.answer ? ['answer.md'] : [])] } : {}) };
  }
  function record(task: Task) { json(join(task.output, 'task-state.json'), view(task)); }
  function audit(task: Task, row: any) {
    appendFileSync(join(task.output, 'motif-audit.jsonl'), JSON.stringify({ ...row, task_id: task.request.task_id }) + '\n', { mode: 0o600 });
    if (row.kind === 'motif_bypass_attempt') task.stats.motif_attempts = Number(task.stats.motif_attempts) + 1;
    if (row.kind === 'shadow_candidate') task.stats.shadow_candidates = Number(task.stats.shadow_candidates) + 1;
    if (row.kind === 'model_request_skipped_verified') task.stats.verified_skips = Number(task.stats.verified_skips) + 1;
    record(task);
  }
  async function refresh(task: Task) {
    await task.closing;
    const counters = await control('/tasks/stats?session_id=' + encodeURIComponent(task.request.session_id));
    Object.assign(task.stats, counters.stats ?? counters);
    task.stats.model_requests = Number(task.stats.upstream_requests ?? 0);
    task.stats.actual_paid_usd = config.provider_mode === 'mock' ? 0 : null;
    if (task.started_at) task.stats.elapsed_seconds =
      (Date.parse(task.finished_at ?? utc()) - Date.parse(task.started_at)) / 1000;
    record(task); return view(task, true);
  }
  function requireIdle() {
    if (active) throw new TaskError('task_busy', 'Another task is running; wait or cancel it', 409);
  }
  function finish(task: Task, status: string, failure: string | null = null) {
    if (terminal.has(task.status)) return;
    task.status = status; task.failure = failure; task.finished_at = utc();
    record(task);
    // Every terminal task closes its proxy admission; in-flight calls still settle.
    // Release the launch slot only after budget ownership is retired.
    task.closing = control('/tasks/cancel', { session_id: task.request.session_id }).then(() => {
      if (active === task.request.task_id) active = null;
    }).catch((error) => { task.failure = 'budget_close_failed: ' + String(error); record(task); });
  }
  const controller = ctx.sessionController;
  const original = { create: controller.create.bind(controller), prompt: controller.prompt.bind(controller),
    cancel: controller.cancel.bind(controller), selectModel: controller.selectModel.bind(controller) };
  controller.create = async (request: any) => {
    if (request.agentPreset && request.agentPreset !== 'sss-task') throw new TaskError('profile_not_allowed', 'Use the server-configured DeepSeek Harless preset');
    if (request.sessionId && !ownedSessions.has(request.sessionId)) throw new TaskError('session_not_owned', 'Session is outside this Web run');
    const created = await original.create({ ...request, agentPreset: 'sss-task' });
    ownedSessions.add(created.sessionId); return created;
  };
  controller.fork = () => { throw new TaskError('fork_not_supported', 'Create a new task to preserve its input, budget and trace binding'); };
  // Native queue editing would change the approved content after its digest was
  // shown. Edits use a new task/preview rather than silently mutating this binding.
  controller.updateQueue = () => { throw new TaskError('queue_edit_not_supported', 'Preview a new task before changing queued input', 409); };
  controller.selectModel = (request: any, signal: AbortSignal) => {
    if (!ownedSessions.has(request.sessionId) || request.provider !== 'deepseek-official' ||
        request.model !== 'deepseek-flash' || (request.reasoningEffort !== undefined && request.reasoningEffort !== 'off')) {
      throw new TaskError('model_not_allowed', 'Provider/model are fixed by the server configuration');
    }
    return original.selectModel({ ...request, reasoningEffort: 'off' }, signal);
  };
  async function preview(input: unknown, existingSession?: string, entrypoint: Task['entrypoint'] = 'workbench'): Promise<Task> {
    const taskId = randomUUID().replaceAll('-', ''), tentativeSession = existingSession ?? 'pending';
    const request = normalizeWebTaskRequest(input, { task_id: taskId, session_id: tentativeSession,
      default_mode: config.mode, default_budget_usd: config.budget_usd, max_budget_usd: config.budget_usd,
      default_profile: config.capability_profile, allowed_profiles: [config.capability_profile],
      max_content_bytes: 768 * 1024, max_parts: 32 });
    const previous = requests.get(request.request_id);
    if (previous) {
      const task = get(previous);
      if (request.request_sha256 !== task.request.request_sha256) throw new TaskError('request_id_conflict', 'request_id already binds different input', 409);
      return task;
    }
    const sources: Task['sources'] = [];
    const delivery = request.content.map(part => ({ ...part }));
    for (const reference of request.resources) {
      const resource = config.resources?.[reference.resource_id];
      if (!resource) throw new TaskError('resource_not_registered', `Resource is not registered: ${reference.resource_id}`, 404);
      if (reference.version !== undefined && reference.version !== resource.version) throw new TaskError('resource_version_changed', `Resource version differs: ${reference.resource_id}`, 409);
      sources.push({ resource_id: reference.resource_id, version: resource.version, sha256: sha(resource.text) });
      delivery.push({ type: 'text', text: `\n\n[来源 ${reference.resource_id}；版本 ${resource.version}]\n${resource.text}` });
    }
    if (Buffer.byteLength(JSON.stringify(delivery)) > 768 * 1024) throw new TaskError('request_too_large', 'Resolved input exceeds byte limit', 413);
    request.session_id = existingSession ?? (await controller.create({})).sessionId;
    if (sessions.has(request.session_id)) throw new TaskError('session_already_bound', 'This session already has a task; create a new task', 409);
    const output = join(config.output, 'tasks', taskId); mkdirSync(output, { recursive: true, mode: 0o700 });
    const task: Task = { request, delivery, confirmation_digest: '', status: 'awaiting_confirmation',
      entrypoint, created_at: utc(), failure: null, fallback_reason: null, answer: '', output, humans: new Map(), sources,
      stats: { tool_calls: 0, tool_errors: 0, llm_decisions: 0, motif_attempts: 0, shadow_candidates: 0, verified_skips: 0,
        upstream_requests: 0, model_requests: 0, actual_paid_usd: config.provider_mode === 'mock' ? 0 : null } };
    for (const filename of ['events.jsonl', 'motif-audit.jsonl']) writeFileSync(join(output, filename), '', { mode: 0o600 });
    await control('/tasks/register', { task_id: taskId, session_id: request.session_id, budget_usd: request.budget_usd });
    tasks.set(taskId, task); sessions.set(request.session_id, taskId); requests.set(request.request_id, taskId);
    const snapshot = await controller.inspect(request.session_id);
    json(join(output, 'session-header.json'), snapshot.meta);
    for (const event of snapshot.events) appendFileSync(join(output, 'events.jsonl'), JSON.stringify(event) + '\n', { mode: 0o600 });
    updateDraft(task); return task;
  }
  function updateDraft(task: Task) {
    task.confirmation_digest = digest({ task_id: task.request.task_id, request: task.request.request_sha256,
      delivery: task.delivery, sources: task.sources, schemas: schemas.get(task.request.session_id),
      provider_mode: config.provider_mode, max_output_tokens: config.max_output_tokens });
    json(join(task.output, 'task.json'), task.request);
    json(join(task.output, 'effective-config.json'), { ...view(task), tools: schemas.get(task.request.session_id),
      tool_schemas_sha256: digest(schemas.get(task.request.session_id)), reasoning_effort: 'off', compression: false,
      run_config: '../../effective-config.json', manifest_sha256: fileSha(config.manifest) });
    record(task);
  }
  function configureMotif(task: Task) {
    if (task.request.mode === 'baseline') return;
    const parts = task.request.content;
    if (!config.manifest || !config.task) task.fallback_reason = 'no_certified_library';
    else if (!config.embedding_endpoint) task.fallback_reason = 'no_embedding_service';
    else if (parts.length !== 1 || parts[0].type !== 'text' || task.sources.length ||
        sha(parts[0].text.trim()) !== config.certified_input_sha256) task.fallback_reason = 'input_not_certified_for_library';
    else try {
      const binding = JSON.parse(readFileSync(config.task, 'utf8'));
      binding.session_id = task.request.session_id; binding.task_id = task.request.task_id;
      json(join(task.output, 'bound-motif-task.json'), binding);
      task.interceptor = createOnlineInterceptor({ manifest: JSON.parse(readFileSync(config.manifest, 'utf8')),
        task: binding, mode: task.request.mode, minSimilarity: 0.8, minMargin: 0.1,
        similarity: loopbackSimilarity(config.embedding_endpoint, config.embedding_model ?? 'fixture-vectors-not-a-semantic-model'),
        audit: (row: unknown) => audit(task, row) });
    } catch (error) {
      task.interceptor = undefined; task.fallback_reason = 'no_valid_certified_library';
      audit(task, { kind: 'motif_library_invalid', error_type: (error as Error).name });
    }
    if (task.fallback_reason) audit(task, { kind: 'motif_fallback', reason: task.fallback_reason });
  }
  async function submit(task: Task, confirmation: unknown, signal: AbortSignal) {
    if (confirmation !== task.confirmation_digest) throw new TaskError('confirmation_changed', 'Input/configuration changed; preview and confirm again', 409);
    if (task.status !== 'awaiting_confirmation') return view(task, true); // exact retry never reruns the Agent
    requireIdle(); active = task.request.task_id; task.status = 'running'; task.started_at = utc(); record(task);
    try {
      configureMotif(task);
      await control('/tasks/activate', { session_id: task.request.session_id });
      await original.prompt({ requestId: task.request.request_id, sessionId: task.request.session_id,
        mode: 'queue', content: task.delivery }, signal);
      return view(task, true);
    } catch (error) { finish(task, 'failed', String(error)); throw error; }
  }
  controller.prompt = (request: any, signal: AbortSignal) => serialize(async () => {
    if (!ownedSessions.has(request.sessionId)) throw new TaskError('session_not_owned', 'Session is outside this Web run');
    if (request.mode !== 'queue') throw new TaskError('delivery_not_supported', 'Use a new queued task; steer is not task admission');
    const task = await preview({ content: request.content, request_id: request.requestId }, request.sessionId, 'native_chat');
    // The official Web bridge displays the bound preview; paid admission stays closed
    // until its explicit confirmation uses the same task API as the workbench.
    if (config.provider_mode === 'mock') await submit(task, task.confirmation_digest, signal);
    return { accepted: true };
  });
  controller.cancel = async (request: any) => {
    if (!ownedSessions.has(request.sessionId)) throw new TaskError('session_not_owned', 'Session is outside this Web run');
    const task = forSession(request.sessionId);
    const result = await original.cancel(request); if (task) finish(task, 'cancelled', 'user_cancelled'); return result;
  };
  const options = resolveAdapterOptions({ baseURL: config.endpoint, thinking: 'disabled', reasoningEffort: 'off', maxTokens: config.max_output_tokens } as any);
  ctx.effect(() => ctx.llm.registerAdapter(['deepseek-official'], new DeepSeekAdapter({ options: () => options,
    resolveApiKey: async () => config.provider_mode === 'mock' ? 'sss-mock-only' : process.env.DEEPSEEK_API_KEY!,
    resolveUserId: () => 'sss-web-operator', prepareExtensions: async () => ({ fields: {}, accept: async () => {} }),
  })), 'sss-web-task-provider');
  ctx.on('agent/created', ({ agent }: any) => {
    agent.ctx.tools.restrict({ allow: config.allowed_tools });
    agent.ctx.tools.guard((call: any) => allowed.has(call.name) ? undefined : 'Tool is outside the configured capability profile');
    if (config.fixture === 'tool-failure') agent.ctx.tools.guard((call: any) => call.name.endsWith('__read_pinned') ? 'injected mock tool failure' : undefined);
    schemas.set(agent.session.id, agent.ctx.tools.schemas(scopeOf(agent.ctx)).sort((a: any, b: any) => a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
    agent.ctx.on('tools/result', (execution: any, result: any) => forSession(agent.session.id)?.interceptor?.observe(agent.session.id, execution, result));
  });
  ctx.on('session/event', (session: any, event: any) => {
    const task = forSession(session.id); if (!task) return;
    appendFileSync(join(task.output, 'events.jsonl'), JSON.stringify(event) + '\n', { mode: 0o600 });
    // Controller has already validated and transformed receipt/image input here.
    if (event.type === 'user/message' && event.data.source?.kind === 'user' && task.status === 'running') {
      task.humans.set(event.data.id, digest(event.data.content));
    }
    if (event.type === 'tool/call') task.stats.tool_calls = Number(task.stats.tool_calls) + 1;
    if (event.type === 'tool/result' && event.data.message?.content?.some((part: any) => part.isError === true)) task.stats.tool_errors = Number(task.stats.tool_errors) + 1;
    if (event.type === 'assistant/message') {
      task.answer = event.data.message.content.filter((part: any) => part.type === 'text').map((part: any) => part.text).join('\n');
      json(join(task.output, 'answer.json'), event);
      writeFileSync(join(task.output, 'answer.md'), task.answer, { mode: 0o600 });
    }
    record(task);
  }, { global: true });
  ctx.on('agent/error', ({ agent, error }: any) => {
    const task = forSession(agent.session.id); if (task) finish(task, /budget|request limit|429/i.test(String(error)) ? 'budget_exhausted' : 'failed', String(error));
  }, { global: true });
  ctx.on('agent/status', ({ agent, status }: any) => {
    const task = forSession(agent.session.id); if (task?.status === 'running' && status === 'idle') finish(task, 'completed');
  }, { global: true });
  ctx.on('llm/stream', (request: any, next: any) => {
    const task = forSession(request.sessionId);
    if (!task || task.status !== 'running' || active !== task.request.task_id ||
        request.provider !== 'deepseek-official' || request.model !== 'deepseek-flash' ||
        request.reasoningEffort !== 'off' || request.maxTokens !== config.max_output_tokens || !isAgentLoopRequest(request)) throw Error('Unapproved task model request');
    const humans = request.messages.filter((message: any) => message.role === 'user' && message.source?.kind === 'user');
    if (request.messages.some((message: any) => message.source?.kind === 'goal')) throw Error('Goal continuation is outside this task admission');
    if (!humans.length || humans.some((message: any) => task.humans.get(message.id) !== digest(message.content))) throw Error('Task user envelope changed');
    if (digest(request.tools) !== digest(schemas.get(request.sessionId))) throw Error('Tool schema version changed');
    json(join(task.output, 'model-request-config.json'), { provider: request.provider, model: request.model,
      reasoning_effort: request.reasoningEffort, max_output_tokens: request.maxTokens,
      tools_order: request.tools.map((tool: any) => tool.name), tools_sha256: digest(request.tools),
      human_message_sha256: humans.map((message: any) => digest(message.content)), mode: task.request.mode });
    task.stats.llm_decisions = Number(task.stats.llm_decisions) + 1; record(task);
    return (async function* () { yield* task.interceptor ? await task.interceptor.intercept(request.sessionId, request, next) : next(); })();
  }, { global: true });
  const taskRoute = { methods: ['GET', 'POST'] as const, requestBody: 'buffered' as const,
    fetch: async (request: Request) => {
      try {
        if (request.method === 'GET') {
          const id = new URL(request.url).searchParams.get('task_id');
          if (id) return Response.json(await refresh(get(id)), { headers: { 'Cache-Control': 'no-store' } });
          const rows = await Promise.all([...tasks.values()].map(refresh));
          const aggregate: Record<string, number> = { tasks: rows.length };
          for (const row of rows) { aggregate[row.status] = (aggregate[row.status] ?? 0) + 1;
            for (const field of ['upstream_requests', 'verified_skips', 'tool_calls', 'prompt_tokens', 'completion_tokens']) aggregate[field] = (aggregate[field] ?? 0) + Number(row.stats[field] ?? 0); }
          return Response.json({ tasks: rows, aggregate, capability_profile: config.capability_profile,
            provider_mode: config.provider_mode, default_mode: config.mode, budget_usd: config.budget_usd });
        }
        const body: any = await request.json();
        const result = await serialize(async () => {
          if (body.action === 'preview') return view(await preview(body.request), true);
          const task = get(body.task_id);
          if (body.action === 'submit') return submit(task, body.confirmation_digest, request.signal);
          if (body.action === 'cancel') { await controller.cancel({ sessionId: task.request.session_id }); return view(task, true); }
          if (body.action === 'upload') {
            if (task.status !== 'awaiting_confirmation') throw new TaskError('task_not_draft', 'Only draft tasks accept attachments', 409);
            if (typeof body.name !== 'string' || !body.name.length || body.name.length > 255 || /[\x00-\x1f]/.test(body.name) ||
                typeof body.data !== 'string' || body.data.length > 350000 || Buffer.from(body.data, 'base64').toString('base64') !== body.data) throw new TaskError('invalid_upload', 'Invalid file name or canonical base64');
            const data = Buffer.from(body.data, 'base64');
            if (!data.length || data.length > 256 * 1024) throw new TaskError('upload_too_large', 'File limit is 256 KiB', 413);
            const uploaded = await ctx.fileUploads.uploadStream({ sessionId: task.request.session_id,
              name: body.name, data: (async function* () { yield data; })(), signal: request.signal });
            const changed = normalizeWebTaskRequest({ content: [...task.request.content, { type: 'file', receiptId: uploaded.receiptId }],
              inputs: task.request.resources, mode: task.request.mode, budget_usd: task.request.budget_usd,
              request_id: task.request.request_id, capability_profile: task.request.capability_profile }, {
              task_id: task.request.task_id, session_id: task.request.session_id, default_mode: config.mode,
              default_budget_usd: config.budget_usd, max_budget_usd: config.budget_usd,
              default_profile: config.capability_profile, allowed_profiles: [config.capability_profile], max_parts: 32, max_content_bytes: 768 * 1024 });
            task.request = changed; task.delivery.push({ type: 'file', receiptId: uploaded.receiptId });
            updateDraft(task); return view(task, true);
          }
          throw new TaskError('unknown_action', 'Supported actions: preview, submit, cancel, upload');
        });
        return Response.json(result, { headers: { 'Cache-Control': 'no-store' } });
      } catch (error) {
        const known = error instanceof TaskError || error instanceof WebTaskRequestError;
        return Response.json({ error: { code: known ? error.code : 'task_request_failed', message: String((error as Error).message ?? error) } },
          { status: error instanceof TaskError ? error.status : 400 });
      }
    } };
  for (const path of ['/api/harless/tasks', '/api/sss/tasks']) {
    ctx.effect(() => ctx.connection.fetch.register({ ...taskRoute, path }), 'harless-tasks-api-' + path);
  }
  const panel = readFileSync(fileURLToPath(new URL('./web_task_panel.html', import.meta.url)), 'utf8');
  const panelHandler = (request: any, response: any) => {
    const rejected = ctx.connection.requestRejection(request);
    response.writeHead(rejected ?? 200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
    response.end(rejected ? '请先打开本次 Harness 认证地址。' : panel);
  };
  for (const path of ['/tasks', '/sss']) {
    ctx.effect(() => ctx.webServer.register({ kind: 'exact', path, handler: panelHandler }), 'harless-tasks-panel-' + path);
  }
  const nativeBridge = config.provider_mode === 'real' ? '<script>' + readFileSync(fileURLToPath(new URL('./web_native_bridge.js', import.meta.url)), 'utf8') + '</script>' : '';
  ctx.effect(() => ctx.webServer.tapIndex((html: string) => html.replace('</body>',
    '<a href="/tasks" style="position:fixed;right:18px;bottom:18px;z-index:9999;padding:10px 15px;border-radius:8px;background:#245cba;color:white;text-decoration:none">DeepSeek Harless 任务工作台</a>' + nativeBridge + '</body>')), 'sss-web-tasks-link');
}
