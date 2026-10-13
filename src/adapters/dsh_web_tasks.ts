/** Dynamic business tasks on the official Harness Web/Session lifecycle. */
import { createHash, randomUUID } from 'node:crypto';
import { appendFileSync, mkdirSync, readFileSync, writeFileSync, renameSync } from 'node:fs';
import { join } from 'node:path';
import { DeepSeekAdapter, resolveAdapterOptions } from '@deepseek-ai/dsh-llm-deepseek';
import { isAgentLoopRequest } from '@deepseek-ai/dsh-llm';
import { scopeOf } from '@deepseek-ai/dsh-scope';
import { createOnlineInterceptor, loopbackSimilarity } from './dsh_online_motif.mjs';
import { digest, offeredSchemaMatches } from '../motif_core/online_skill_runtime.mjs';
import { normalizeWebTaskRequest, WebTaskRequestError } from './web_task_request.ts';
import { sceneCatalog, initialSelection, changeSelection, parseHarlessCommand, SettingsError } from './harless_settings.ts';
import { sessionWorkspace, sessionPreset, bindSceneInputs, sceneOptions } from './harless_task_scope.ts';
import type { SceneOptions } from './harless_task_scope.ts';
import type { Scene, Selection } from './harless_settings.ts';
import type { NormalizedWebTask, PromptPart, ExecutionMode } from './web_task_request.ts';

export const name = 'sss-web-tasks';
export const inject = ['llm', 'agents', 'sessionController', 'connection', 'webServer', 'fileUploads', 'commands', 'agentPresets', 'attachments'];
type Policy = {
  output: string; user_id?: string; allowed_tools: string[]; endpoint: string; max_output_tokens: number;
  mode: ExecutionMode; budget_usd: number; capability_profile: string;
  provider_mode: 'mock' | 'real'; control_endpoint: string; control_token: string;
  manifest?: string; task?: string; certified_input_sha256?: string;
  embedding_endpoint?: string; embedding_model?: string; fixture?: string;
  scenes?: Scene[]; scene_registry_sha256?: string;
  resources?: Record<string, { version: string; text: string }>;
  models?: ModelOption[];
};
type ModelOption = { provider: string; model: string; label: string; available: boolean };
type Task = {
  request: NormalizedWebTask; delivery: PromptPart[]; confirmation_digest: string;
  status: string; created_at: string; started_at?: string; finished_at?: string;
  failure: string | null; fallback_reason: string | null; answer: string;
  output: string; stats: Record<string, any>; interceptor?: any;
  humans: Map<string, string>; sources: { resource_id: string; version: string; sha256: string }[];
  scene: Scene; selection: Selection; tools: any[]; manifest_sha256: string | null; binding_sha256: string | null;
  closing?: Promise<void>; entrypoint: 'workbench' | 'native_chat';
  model_option: ModelOption; workspace: string; scene_options: SceneOptions; scene_inputs: any[];
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
  const modelOptions = config.models ?? [{ provider: 'deepseek-official', model: 'deepseek-flash', label: 'DeepSeek Flash', available: true }];
  const defaultModel = modelOptions.find(option => option.available);
  if (!defaultModel || modelOptions.some(option => !/^[a-z][a-z0-9-]*$/.test(option.provider) || !/^[A-Za-z0-9._-]+$/.test(option.model) ||
        typeof option.label !== 'string' || !option.label || typeof option.available !== 'boolean') ||
      new Set(modelOptions.map(option => option.model)).size !== modelOptions.length) throw Error('Invalid server model catalog');
  const modelSelections = new Map<string, ModelOption>();
  const findModel = (id: unknown): ModelOption => {
    const option = modelOptions.find(row => row.model === id && row.available);
    if (!option) throw new TaskError('model_not_allowed', 'Model is not enabled by the server configuration');
    return option;
  };
  const schemas = new Map<string, any[]>(), requests = new Map<string, string>();
  const ownedSessions = new Set<string>();
  const scenes = sceneCatalog(config.scenes ?? [{ ...config, id: config.capability_profile, label: config.capability_profile, preset: 'sss-task' }]);
  if (!scenes.some(scene => scene.id === config.capability_profile)) throw Error('Default scene is not registered');
  let defaults = initialSelection(config.capability_profile, config.mode);
  const selections = new Map<string, Selection>(), agents = new Map<string, any>();
  const workspaces = new Map<string, string>();
  const principal = config.user_id ?? 'local-operator';
  const guards = new Map<string, (() => void)[]>();
  const sceneFor = (id: string) => {
    const scene = scenes.find(scene => scene.id === id);
    if (!scene) throw new SettingsError('scene_not_found', '场景未登记');
    return scene;
  };
  function executeUnavailable(scene: Scene): string | null {
    if (scene.unavailable_reason) return scene.unavailable_reason;
    if (!scene.manifest || !scene.task) return 'no_certified_library';
    if (!scene.embedding_endpoint) return 'no_embedding_service';
    if (!/^[a-f0-9]{64}$/.test(scene.certified_input_sha256 ?? '')) return 'no_certified_input';
    try {
      loopbackSimilarity(scene.embedding_endpoint, scene.embedding_model ?? 'fixture-vectors-not-a-semantic-model');
      const manifest = JSON.parse(readFileSync(scene.manifest, 'utf8'));
      if (Object.keys(manifest.contracts ?? {}).some(tool => !scene.allowed_tools.includes(tool))) return 'library_tools_outside_scene';
      createOnlineInterceptor({ manifest, task: JSON.parse(readFileSync(scene.task, 'utf8')), mode: 'execute',
        similarity: async () => [], audit: () => {} });
    } catch { return 'no_valid_certified_library'; }
    return null;
  }
  function bindScene(agent: any, scene: Scene) {
    for (const dispose of guards.get(agent.session.id) ?? []) dispose();
    const allowed = new Set(scene.allowed_tools);
    const disposers = [agent.ctx.tools.restrict({ allow: scene.allowed_tools }),
      agent.ctx.tools.guard((call: any) => allowed.has(call.name) ? undefined : 'Tool is outside the configured capability profile')];
    if (scene.instructions) disposers.push(agent.ctx.systemPrompt.section({ name: 'harless-scene', order: 10210, text: scene.instructions }));
    if (config.fixture === 'tool-failure') disposers.push(agent.ctx.tools.guard((call: any) => call.name.endsWith('__read_pinned') ? 'injected mock tool failure' : undefined));
    guards.set(agent.session.id, disposers.filter(dispose => typeof dispose === 'function'));
    schemas.set(agent.session.id, agent.ctx.tools.schemas(scopeOf(agent.ctx)).sort((a: any, b: any) => a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
  }
  function settingsView(sessionId?: string) {
    if (sessionId && !ownedSessions.has(sessionId)) throw new TaskError('session_not_owned', 'Session is outside this Web run', 404);
    const selected = sessionId ? selections.get(sessionId)! : defaults;
    const task = sessionId ? forSession(sessionId) : undefined;
    return { selection: selected, applies_to: task ? 'next_task' : 'next_prompt',
      preview_scene: selected.scene, // compatibility alias; now an actual registered selection
      preview_scenes: scenes.map(scene => ({ id: scene.id, label: scene.label, available: !scene.unavailable_reason, unavailable_reason: scene.unavailable_reason })),
      current_task: task ? { task_id: task.request.task_id, scene: task.scene.id, mode: task.request.mode, rsi: task.selection.rsi, status: task.status } : null,
      scenes: scenes.map(scene => ({ id: scene.id, label: scene.label, config_sha256: scene.config_sha256,
        available: !scene.unavailable_reason, unavailable_reason: scene.unavailable_reason,
        execute_available: !executeUnavailable(scene), execute_unavailable_reason: executeUnavailable(scene) })),
      session_id: sessionId ?? null, model_calls: 0 };
  }
  async function setSelection(sessionId: string | undefined, patch: unknown) {
    settingsView(sessionId); // ownership before mutation
    const current = sessionId ? selections.get(sessionId)! : defaults;
    const next = changeSelection(current, patch, scenes, executeUnavailable);
    if (sessionId) {
      const agent = agents.get(sessionId);
      if (!forSession(sessionId) && next.scene !== current.scene) {
        const scene = sceneFor(next.scene);
        if (!scene.unavailable_reason) {
          await selectPreset!(agent, sessionPreset(config.output, workspaces.get(sessionId)!, scene));
          bindScene(agent, scene);
        }
      }
      selections.set(sessionId, next);

    } else defaults = next;
    json(join(config.output, 'harless-settings.json'), { defaults, sessions: Object.fromEntries(selections) });
    return settingsView(sessionId);
  }
  const selectPreset = ctx.agentPresets?.select.bind(ctx.agentPresets);
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
      capability_profile: request.capability_profile, scene: task.scene.id, scene_sha256: task.scene.config_sha256,
      user_id: principal, selected_mode: task.selection.mode, rsi: task.selection.rsi, mode: request.mode, budget_usd: request.budget_usd,
      entrypoint: task.entrypoint, status: task.status, failure: task.failure, fallback_reason: task.fallback_reason,
      created_at: task.created_at, started_at: task.started_at, finished_at: task.finished_at,
      input_summary: request.summary, prompt_sha256: request.prompt_sha256,
      request_sha256: request.request_sha256, confirmation_digest: task.confirmation_digest,
      provider_mode: config.provider_mode, provider: task.model_option.provider, model: task.model_option.model,
      paid_calls_enabled: config.provider_mode === 'real',
      scene_options: task.scene_options, scene_inputs: task.scene_inputs,
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
    if (request.agentPreset && !scenes.some(scene => scene.preset === request.agentPreset)) throw new TaskError('profile_not_allowed', 'Use the server-configured DeepSeek Harless preset');
    if (request.sessionId && !ownedSessions.has(request.sessionId)) throw new TaskError('session_not_owned', 'Session is outside this Web run');
    const chosen = request.agentPreset ? scenes.find(scene => scene.preset === request.agentPreset)! : sceneFor(defaults.scene);
    if (chosen.unavailable_reason) throw new TaskError('scene_not_connected', chosen.unavailable_reason, 409);
    if (request.cwd !== undefined || request.workspaceId !== undefined)
      throw new TaskError('workspace_not_allowed', 'The server allocates a private Session workspace');
    if (request.sessionId && ownedSessions.has(request.sessionId)) return original.create(request);
    const sessionId = 'sss-' + randomUUID().replaceAll('-', '');
    const workspace = sessionWorkspace(config.output, sessionId);
    workspaces.set(sessionId, workspace);
    const created = await original.create({ ...request, sessionId, cwd: workspace,
      agentPreset: sessionPreset(config.output, workspace, chosen) });
    ownedSessions.add(created.sessionId);
    if (!selections.has(created.sessionId)) {
      selections.set(created.sessionId, { ...defaults, scene: chosen.id });
      bindScene(agents.get(created.sessionId), chosen);
      await original.selectModel({ sessionId: created.sessionId, provider: defaultModel.provider,
        model: defaultModel.model,
        ...(defaultModel.provider === 'harless-glm' ? {} : { reasoningEffort: 'off' }) });
      modelSelections.set(created.sessionId, defaultModel);
    }
    return created;
  };
  controller.fork = () => { throw new TaskError('fork_not_supported', 'Create a new task to preserve its input, budget and trace binding'); };
  // Native queue editing would change the approved content after its digest was
  // shown. Edits use a new task/preview rather than silently mutating this binding.
  controller.updateQueue = () => { throw new TaskError('queue_edit_not_supported', 'Preview a new task before changing queued input', 409); };
  controller.selectModel = async (request: any, signal: AbortSignal) => {
    const option = findModel(request.model);
    if (!ownedSessions.has(request.sessionId) || forSession(request.sessionId) || request.provider !== option.provider ||
        (request.reasoningEffort !== undefined && request.reasoningEffort !== 'off'))
      throw new TaskError('model_not_allowed', 'Model selection is outside the approved task configuration');
    const requested = { ...request };
    if (option.provider === 'harless-glm') delete requested.reasoningEffort;
    else requested.reasoningEffort = 'off';
    const result = await original.selectModel(requested, signal);
    modelSelections.set(request.sessionId, option);
    return result;
  };
  if (ctx.agentPresets) ctx.agentPresets.select = (agent: any, preset: string) => serialize(async () => {
    const scene = scenes.find(scene => scene.preset === preset);
    if (!scene) throw new SettingsError('scene_not_found', '只能选择服务器登记的场景');
    if (forSession(agent.session.id)) throw new TaskError('session_already_bound', '当前会话已绑定任务，请新建会话后选择 Harless 设置', 409);
    await setSelection(agent.session.id, { scene: scene.id }); return preset;
  });
  async function preview(input: unknown, existingSession?: string, entrypoint: Task['entrypoint'] = 'workbench'): Promise<Task> {
    const taskId = randomUUID().replaceAll('-', ''), tentativeSession = existingSession ?? 'pending';
    const supplied = input && typeof input === 'object' && !Array.isArray(input) ? input as Record<string, unknown> : {};
    const chosenModel = supplied.model === undefined ? (existingSession ? modelSelections.get(existingSession) ?? defaultModel : defaultModel) : findModel(supplied.model);
    const taskInput = input && typeof input === 'object' && !Array.isArray(input)
      ? { ...supplied } : input;
    if (taskInput && typeof taskInput === 'object' && !Array.isArray(taskInput)) { delete taskInput.model; delete taskInput.scene_options; }
    const selected = existingSession ? selections.get(existingSession)! : defaults;
    if (existingSession && !selected) throw new TaskError('session_not_owned', 'Session is outside this Web run');
    const request = normalizeWebTaskRequest(taskInput, { task_id: taskId, session_id: tentativeSession,
      default_mode: selected.mode, default_budget_usd: config.budget_usd, max_budget_usd: config.budget_usd,
      default_profile: selected.scene, allowed_profiles: scenes.map(scene => scene.id),
      max_content_bytes: 768 * 1024, max_parts: 32 });
    const requestedMode = request.mode;
    if (!selected.rsi) {
      request.mode = 'baseline';
      request.request_sha256 = digest({ request: request.request_sha256, rsi: false });
    }
    if (chosenModel.provider === 'harless-glm' && request.content.some(part => part.type !== 'text'))
      throw new TaskError('unsupported_input', 'The GLM connection currently supports text only; remove images and files before retrying');
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
    const scene = sceneFor(request.capability_profile);
    if (scene.unavailable_reason) throw new TaskError('scene_not_connected', scene.unavailable_reason, 409);
    const options = sceneOptions(supplied.scene_options, scene);
    const selection = changeSelection(selected, { scene: scene.id, mode: requestedMode }, scenes, executeUnavailable);
    request.request_sha256 = digest({ request: request.request_sha256, selection, scene_options: options, user_id: principal });
    const previous = requests.get(request.request_id);
    if (previous) {
      const task = get(previous);
      if (request.request_sha256 !== task.request.request_sha256 || chosenModel.model !== task.model_option.model) throw new TaskError('request_id_conflict', 'request_id already binds different input or model', 409);
      return task;
    }
    request.session_id = existingSession ?? (await controller.create({ agentPreset: scene.preset })).sessionId;
    if (existingSession && scene.id !== selected.scene) throw new TaskError('scene_changed', '预览前请先选择与当前会话一致的 Harless 场景', 409);
    if (sessions.has(request.session_id)) throw new TaskError('session_already_bound', 'This session already has a task; create a new task', 409);
    if (modelSelections.get(request.session_id)?.model !== chosenModel.model) await controller.selectModel({
      sessionId: request.session_id, provider: chosenModel.provider, model: chosenModel.model, reasoningEffort: 'off'
    }, new AbortController().signal);
    const workspace = workspaces.get(request.session_id)!;
    const sceneInputs = scene.adapter ? await bindSceneInputs(ctx, agents.get(request.session_id), workspace, scene,
      request.content, options, delivery.filter(part => part.type === 'text').map(part => (part as any).text).join('\n'), taskId) : [];
    if (scene.adapter) {
      await selectPreset!(agents.get(request.session_id), sessionPreset(config.output, workspace, scene));
      bindScene(agents.get(request.session_id), scene);
    }
    const tools = structuredClone(schemas.get(request.session_id) ?? []);
    if (tools.length !== scene.allowed_tools.length || tools.some((tool: any) => !scene.allowed_tools.includes(tool.name)))
      throw new TaskError('scene_tools_unavailable', 'Configured MCP tool surface did not load', 409);
    if (request.mode === 'execute') {
      const manifest = JSON.parse(readFileSync(scene.manifest!, 'utf8'));
      const offered = new Map(tools.map((tool: any) => [tool.name, tool]));
      if (Object.entries(manifest.contracts).some(([name, contract]) => !offeredSchemaMatches(offered, name, contract)))
        throw new TaskError('execute_unavailable', 'library_tool_schema_mismatch', 409);
      try {
        const binding = JSON.parse(readFileSync(scene.task!, 'utf8'));
        await loopbackSimilarity(scene.embedding_endpoint!, scene.embedding_model!)(binding.intent, ['Runtime admission probe']);
      } catch { throw new TaskError('execute_unavailable', 'embedding_service_unavailable', 409); }
    }
    selections.set(request.session_id, selection);
    const output = join(config.output, 'tasks', taskId); mkdirSync(output, { recursive: true, mode: 0o700 });
    const task: Task = { request, delivery, confirmation_digest: '', status: 'awaiting_confirmation',
      scene, selection: Object.freeze({ ...selection }), tools, workspace, scene_options: options, scene_inputs: sceneInputs,
      manifest_sha256: fileSha(scene.manifest), binding_sha256: fileSha(scene.task),
      entrypoint, created_at: utc(), failure: null, fallback_reason: null, answer: '', output, humans: new Map(), sources,
      model_option: chosenModel,
      stats: { tool_calls: 0, tool_errors: 0, llm_decisions: 0, motif_attempts: 0, shadow_candidates: 0, verified_skips: 0,
        upstream_requests: 0, model_requests: 0, actual_paid_usd: config.provider_mode === 'mock' ? 0 : null } };
    for (const filename of ['events.jsonl', 'motif-audit.jsonl']) writeFileSync(join(output, filename), '', { mode: 0o600 });
    await control('/tasks/register', { task_id: taskId, session_id: request.session_id,
      budget_usd: request.budget_usd, model: chosenModel.model });
    tasks.set(taskId, task); sessions.set(request.session_id, taskId); requests.set(request.request_id, taskId);
    const snapshot = await controller.inspect(request.session_id);
    json(join(output, 'session-header.json'), snapshot.meta);
    for (const event of snapshot.events) appendFileSync(join(output, 'events.jsonl'), JSON.stringify(event) + '\n', { mode: 0o600 });
    updateDraft(task); return task;
  }
  function updateDraft(task: Task) {
    task.confirmation_digest = digest({ task_id: task.request.task_id, request: task.request.request_sha256,
      delivery: task.delivery, sources: task.sources, schemas: task.tools, scene: task.scene.id,
      scene_sha256: task.scene.config_sha256, instructions: task.scene.instructions, selection: task.selection,
      manifest_sha256: task.manifest_sha256, binding_sha256: task.binding_sha256,
      scene_options: task.scene_options, scene_inputs: task.scene_inputs, user_id: principal,
      provider_mode: config.provider_mode, max_output_tokens: config.max_output_tokens });
    task.confirmation_digest = digest({ confirmation: task.confirmation_digest,
      provider: task.model_option.provider, model: task.model_option.model });
    json(join(task.output, 'task.json'), task.request);
    json(join(task.output, 'effective-config.json'), { ...view(task), selection: task.selection, tools: task.tools,
      scenario: task.scene.scenario, scenario_version: task.scene.scenario_version,
      instructions: task.scene.instructions, instructions_sha256: task.scene.instructions_sha256,
      allowed_tools: task.scene.allowed_tools, workspace: task.workspace,
      tool_schemas_sha256: digest(task.tools), reasoning_effort: 'off', compression: false,
      run_config: '../../effective-config.json', manifest_sha256: task.manifest_sha256, binding_sha256: task.binding_sha256, scene_registry_sha256: config.scene_registry_sha256 });
    record(task);
  }
  function configureMotif(task: Task) {
    if (task.request.mode === 'baseline') return;
    const parts = task.request.content, scene = task.scene;
    const availableTools = new Map(task.tools.map(tool => [tool.name, tool]));
    const pinned = (path: string, expected: string | null) => { const bytes = readFileSync(path); if (sha(bytes) !== expected) throw Error('Motif binding version changed'); return JSON.parse(bytes.toString('utf8')); };
    if (!scene.manifest || !scene.task) task.fallback_reason = 'no_certified_library';
    else if (!scene.embedding_endpoint) task.fallback_reason = 'no_embedding_service';
    else if (parts.length !== 1 || parts[0].type !== 'text' || task.sources.length ||
        sha(parts[0].text.trim()) !== scene.certified_input_sha256) task.fallback_reason = 'input_not_certified_for_library';
    else try {
      const manifest = pinned(scene.manifest, task.manifest_sha256);
      if (Object.entries(manifest.contracts).some(([name, contract]) => !offeredSchemaMatches(availableTools, name, contract))) throw Error('library_tool_schema_mismatch');
      const binding = pinned(scene.task, task.binding_sha256);
      binding.session_id = task.request.session_id; binding.task_id = task.request.task_id;
      json(join(task.output, 'bound-motif-task.json'), binding);
      task.interceptor = createOnlineInterceptor({ manifest,
        task: binding, mode: task.request.mode, minSimilarity: 0.8, minMargin: 0.1,
        similarity: loopbackSimilarity(scene.embedding_endpoint, scene.embedding_model ?? 'fixture-vectors-not-a-semantic-model'),
        audit: (row: unknown) => audit(task, row) });
    } catch (error) {
      task.interceptor = undefined; task.fallback_reason = (error as Error).message === 'library_tool_schema_mismatch' ? 'library_tool_schema_mismatch' : 'no_valid_certified_library';
      audit(task, { kind: 'motif_library_invalid', error_type: (error as Error).name });
    }
    if (task.fallback_reason) audit(task, { kind: 'motif_fallback', reason: task.fallback_reason });
  }
  async function submit(task: Task, confirmation: unknown, signal: AbortSignal) {
    if (confirmation !== task.confirmation_digest) throw new TaskError('confirmation_changed', 'Input/configuration changed; preview and confirm again', 409);
    if (task.status !== 'awaiting_confirmation') return view(task, true); // exact retry never reruns the Agent
    if (digest(schemas.get(task.request.session_id)) !== digest(task.tools) ||
        fileSha(task.scene.manifest) !== task.manifest_sha256 || fileSha(task.scene.task) !== task.binding_sha256) {
      throw new TaskError('confirmation_changed', 'Tools or library changed; preview a new task', 409);
    }
    if (task.request.mode === 'execute') {
      const reason = executeUnavailable(task.scene);
      if (reason) throw new TaskError('execute_unavailable', reason, 409);
    }
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
    await submit(task, task.confirmation_digest, signal);
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
    agents.set(agent.session.id, agent);
    agent.ctx.on('tools/result', (execution: any, result: any) => forSession(agent.session.id)?.interceptor?.observe(agent.session.id, execution, result));
  }, { global: true });
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
        request.provider !== task.model_option.provider || request.model !== task.model_option.model ||
        request.reasoningEffort !== (task.model_option.provider === 'harless-glm' ? undefined : 'off') ||
        request.maxTokens !== config.max_output_tokens || !isAgentLoopRequest(request)) throw Error('Unapproved task model request');
    const humans = request.messages.filter((message: any) => message.role === 'user' && message.source?.kind === 'user');
    if (request.messages.some((message: any) => message.source?.kind === 'goal')) throw Error('Goal continuation is outside this task admission');
    if (!humans.length || humans.some((message: any) => task.humans.get(message.id) !== digest(message.content))) throw Error('Task user envelope changed');
    if (digest(request.tools) !== digest(task.tools)) throw Error('Tool schema version changed');
    json(join(task.output, 'model-request-config.json'), { provider: request.provider, model: request.model,
      reasoning_effort: request.reasoningEffort ?? 'off', reasoning_effort_sent: request.reasoningEffort !== undefined,
      max_output_tokens: request.maxTokens,
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
            provider_mode: config.provider_mode, model_options: modelOptions,
            default_mode: defaults.mode, budget_usd: config.budget_usd, settings: settingsView() });
        }
        const body: any = await request.json();
        const result = await serialize(async () => {
          if (body.action === 'preview') {
            if (body.session_id && !ownedSessions.has(body.session_id)) throw new TaskError('session_not_owned', 'Session is outside this Web run');
            return view(await preview(body.request, body.session_id), true);
          }
          const task = get(body.task_id);
          if (body.action === 'submit') return submit(task, body.confirmation_digest, request.signal);
          if (body.action === 'cancel') { await controller.cancel({ sessionId: task.request.session_id }); return view(task, true); }
          if (body.action === 'upload') {
            if (task.status !== 'awaiting_confirmation') throw new TaskError('task_not_draft', 'Only draft tasks accept attachments', 409);
            if (task.model_option.provider === 'harless-glm') throw new TaskError('unsupported_input', 'The GLM connection currently supports text only', 400);
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
              default_profile: task.scene.id, allowed_profiles: [task.scene.id], max_parts: 32, max_content_bytes: 768 * 1024 });
            task.request = changed; task.delivery.push({ type: 'file', receiptId: uploaded.receiptId });
            if (task.scene.adapter) {
              task.scene_inputs = await bindSceneInputs(ctx, agents.get(task.request.session_id), task.workspace, task.scene,
                task.request.content, task.scene_options, task.delivery.filter(part => part.type === 'text').map(part => (part as any).text).join('\n'), task.request.task_id);
              await selectPreset!(agents.get(task.request.session_id), sessionPreset(config.output, task.workspace, task.scene));
              bindScene(agents.get(task.request.session_id), task.scene);
              if (digest(schemas.get(task.request.session_id)) !== digest(task.tools)) throw new TaskError('confirmation_changed', 'Tool schema changed', 409);
            }
            updateDraft(task); return view(task, true);
          }
          throw new TaskError('unknown_action', 'Supported actions: preview, submit, cancel, upload');
        });
        return Response.json(result, { headers: { 'Cache-Control': 'no-store' } });
      } catch (error) {
        appendFileSync(join(config.output, 'admission-errors.jsonl'), JSON.stringify({ time: utc(), error: String(error) }) + '\n', { mode: 0o600 });
        const known = error instanceof TaskError || error instanceof WebTaskRequestError || error instanceof SettingsError;
        return Response.json({ error: { code: known ? error.code : 'task_request_failed', message: known ? String((error as Error).message) : 'Task configuration or input admission failed; inspect the private server log' } },
          { status: error instanceof TaskError ? error.status : 400 });
      }
    } };
  for (const path of ['/api/harless/tasks', '/api/sss/tasks']) {
    ctx.effect(() => ctx.connection.fetch.register({ ...taskRoute, path }), 'harless-tasks-api-' + path);
  }
  const settingsRoute = { methods: ['GET', 'POST'] as const, requestBody: 'buffered' as const,
    fetch: async (request: Request) => {
      try {
        const url = new URL(request.url), sessionId = url.searchParams.get('session_id') ?? undefined;
        if (request.method === 'GET') {
          return Response.json({ ...settingsView(sessionId), sessions: [...ownedSessions].map(session_id => ({ session_id, ...settingsView(session_id) })) }, { headers: { 'Cache-Control': 'no-store' } });
        }
        const body: any = await request.json();
        const result = await serialize(async () => {
          if (body.action === 'select') return setSelection(body.session_id, body.selection);
          if (body.action === 'select_preview_scene') return setSelection(body.session_id, { scene: body.scene_id });
          if (body.action === 'clear_preview_scene') return setSelection(body.session_id, { scene: config.capability_profile });
          if (body.action === 'new_session') {
            const chosen = body.inherit_session ? settingsView(body.inherit_session).selection : defaults;
            const created = await controller.create({ agentPreset: sceneFor(chosen.scene).preset });
            selections.set(created.sessionId, { ...chosen });

            return { session_id: created.sessionId, ...settingsView(created.sessionId) };
          }
          throw new SettingsError('unknown_action', 'Supported actions: select, select_preview_scene, clear_preview_scene, new_session');
        });
        return Response.json(result, { headers: { 'Cache-Control': 'no-store' } });
      } catch (error) {
        return Response.json({ error: { code: (error as any).code ?? 'settings_failed', message: String((error as Error).message) } },
          { status: error instanceof TaskError ? error.status : 400 });
      }
    } };
  ctx.effect(() => ctx.connection.fetch.register({ ...settingsRoute, path: '/api/harless/settings' }), 'harless-settings-api');
  if (ctx.commands) ctx.effect(() => ctx.commands.register({ name: 'harless', description: 'Choose a scene, mode, and RSI setting',
    input: { hint: 'scene | mode | rsi | list | status' },
    handler: ({ agent, rawInput }: any) => serialize(async () => {
      try {
        const id = agent.session.id, command = parseHarlessCommand(rawInput);
        settingsView(id);
        if (command.kind === 'panel') {
          return { kind: 'success', text: 'Choose a scene, mode, or RSI setting from the /harless picker.' };
        }
        if (command.kind === 'list') return { kind: 'success', text: scenes.map(scene =>
          `${scene.label} · ${scene.unavailable_reason ?? 'connected'}`).join('\n') };
        const value = command.kind === 'change' ? await setSelection(id, command.patch) : settingsView(id);
        const current = value.current_task;
        const planned = sceneFor(value.selection.scene);
        return { kind: 'success', text: `${planned.label}${planned.unavailable_reason ? ' (' + planned.unavailable_reason + ')' : ''} · Mode ${value.selection.mode === 'baseline' ? 'Origin' : value.selection.mode} · RSI ${value.selection.rsi ? 'On' : 'Off'}${current ? ` · Current task: ${current.scene} / ${current.mode} / ${current.status}` : ''}` };
      } catch (error) { return { kind: 'error', text: String((error as Error).message) }; }
    }) }), 'harless-command');
  for (const path of ['/tasks', '/sss', '/harless']) {
    ctx.effect(() => ctx.webServer.register({ kind: 'exact', path, handler: (_request: any, response: any) => {
      response.writeHead(302, { Location: '/', 'Cache-Control': 'no-store' });
      response.end();
    } }), 'harless-legacy-page-redirect-' + path);
  }
}
