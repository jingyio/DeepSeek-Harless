/** Native Web admission policy. The official Controller/Agent own all execution. */
import { createHash } from 'node:crypto';
import { appendFileSync, readFileSync, writeFileSync, renameSync } from 'node:fs';
import { join, basename } from 'node:path';
import { DeepSeekAdapter, resolveAdapterOptions } from '@deepseek-ai/dsh-llm-deepseek';
import { isAgentLoopRequest } from '@deepseek-ai/dsh-llm';
import { createOnlineInterceptor, loopbackSimilarity } from './dsh_online_motif.mjs';
import { digest } from '../motif_core/online_skill_runtime.mjs';
import { scopeOf } from '@deepseek-ai/dsh-scope';

export const name = 'sss-web-policy';
export const inject = ['llm', 'agents', 'sessionController'];
type Policy = { output: string; prompt_sha256: string; allowed_tools: string[];
  endpoint: string; max_output_tokens: number; mode: 'baseline' | 'shadow' | 'execute';
  manifest?: string; task?: string; embedding_endpoint: string; fixture?: string };
// The official composer trims the outer whitespace before admission. Keep all
// internal bytes intact; this is a documented transport normalization, not fuzzy matching.
const sha = (value: string) => createHash('sha256').update(value.trim()).digest('hex');

export function apply(ctx: any) {
  const config: Policy = JSON.parse(readFileSync(process.env.SSS_WEB_POLICY!, 'utf8'));
  if (!/^http:\/\/127\.0\.0\.1:\d+\/v1$/.test(config.endpoint) ||
      !/^[a-f0-9]{64}$/.test(config.prompt_sha256) ||
      !Array.isArray(config.allowed_tools) || !config.allowed_tools.length ||
      !['baseline', 'shadow', 'execute'].includes(config.mode)) throw Error('Invalid Web policy');
  const allowed = new Set(config.allowed_tools);
  let sessionId: string | null = null, prompted = false, interceptor: any;
  const schemas = new Map<string, string>();
  let status = 'ready', failure: string | null = null;
  const privateJson = (filename: string, value: unknown) => {
    const file = join(config.output, filename);
    writeFileSync(file + '.tmp', JSON.stringify(value), { mode: 0o600 });
    renameSync(file + '.tmp', file);
  };
  const audit = (row: object) => appendFileSync(join(config.output, 'motif-audit.jsonl'),
    JSON.stringify(row) + '\n', { mode: 0o600 });
  const record = () => privateJson('task-state.json',
    { task_id: basename(config.output), session_id: sessionId, status, failure, mode: config.mode });
  const refuse = (reason: string): never => { audit({ kind: 'policy_denied', reason }); throw Error(reason); };
  const owner = (id: string) => { if (!sessionId || id !== sessionId) refuse('Other Web session is not authorized'); };
  record();
  // A fixed adapter connection cannot be redirected by the Models/settings UI.
  // Other provider routes are removed by the host overlay and denied at the waterfall.
  const options = resolveAdapterOptions({ baseURL: config.endpoint, thinking: 'disabled',
    reasoningEffort: 'off', maxTokens: config.max_output_tokens } as any);
  ctx.effect(() => ctx.llm.registerAdapter(['deepseek-official'], new DeepSeekAdapter({
    options: () => options, resolveApiKey: async () => 'sss-mock-only',
    resolveUserId: () => 'sss-web-free-fixture',
    prepareExtensions: async () => ({ fields: {}, accept: async () => {} }),
  })), 'sss-web-fixed-provider');
  const controller = ctx.sessionController;
  const originalCreate = controller.create.bind(controller);
  let creation = Promise.resolve();
  controller.create = (request: any) => {
    const result = creation.then(async () => {
      if (sessionId && request.sessionId !== sessionId) refuse('One task per Web launch; restart for another task');
      const first = sessionId === null;
      const result = await originalCreate(request);
      sessionId = result.sessionId;
      writeFileSync(join(config.output, 'tool-schemas.json'), schemas.get(result.sessionId)!, { mode: 0o600 });
      if (first) {
        const snapshot = await controller.inspect(sessionId);
        privateJson('session-header.json', snapshot.meta);
        // agent-preset/selected and other constructor records precede agent/created.
        // Retain the initial prefix once; later events use the native append feed.
        for (const event of snapshot.events) appendFileSync(join(config.output, 'events.jsonl'),
          JSON.stringify(event) + '\n', { mode: 0o600 });
      }
      record(); return result;
    });
    creation = result.catch(() => undefined); return result;
  };
  const originalPrompt = controller.prompt.bind(controller);
  controller.prompt = async (request: any, signal: AbortSignal) => {
    owner(request.sessionId);
    const parts = request.content;
    if (!Array.isArray(parts) || parts.length !== 1 || parts[0].type !== 'text' ||
        sha(parts[0].text) !== config.prompt_sha256) refuse('Prompt changed; restart and bind a new task');
    if (prompted) refuse('This launch already admitted its task');
    prompted = true; status = 'running'; record();
    try {
      privateJson('web-task-binding.json', { task_id: basename(config.output), session_id: sessionId,
        prompt_sha256: config.prompt_sha256, mode: config.mode, tool_schemas_digest: digest(JSON.parse(schemas.get(sessionId!)!)) });
      if (config.mode !== 'baseline') {
      const task = JSON.parse(readFileSync(config.task!, 'utf8'));
      task.session_id = sessionId;
      writeFileSync(join(config.output, 'bound-task.json'), JSON.stringify(task), { mode: 0o600 });
      const similarity = loopbackSimilarity(config.embedding_endpoint, 'fixture-vectors-not-a-semantic-model');
      interceptor = createOnlineInterceptor({ manifest: JSON.parse(readFileSync(config.manifest!, 'utf8')),
        task, similarity, mode: config.mode, minSimilarity: 0.8, minMargin: 0.1, audit });
      }
      return await originalPrompt(request, signal);
    }
    catch (error) { status = 'failed'; failure = String(error); record(); throw error; }
  };
  controller.fork = () => refuse('Fork is disabled for the single-task Web entry');
  const select = controller.selectModel.bind(controller);
  controller.selectModel = (request: any, signal: AbortSignal) => {
    owner(request.sessionId);
    if (request.provider !== 'deepseek-official' || request.model !== 'deepseek-flash' ||
        (request.reasoningEffort !== undefined && request.reasoningEffort !== 'off')) refuse('Model configuration is fixed for the mock task');
    return select({ ...request, reasoningEffort: 'off' }, signal);
  };
  const cancel = controller.cancel.bind(controller);
  controller.cancel = (request: any) => { owner(request.sessionId); const result = cancel(request);
    status = 'cancelled'; failure = 'user_cancelled'; record(); return result; };
  ctx.on('agent/created', ({ agent }: any) => {
    agent.ctx.tools.restrict({ allow: config.allowed_tools });
    agent.ctx.tools.guard((call: any) => allowed.has(call.name) ? undefined : 'Tool is outside this scenario');
    if (config.fixture === 'tool-failure') agent.ctx.tools.guard((call: any) =>
      call.name.endsWith('__read_pinned') ? 'injected mock tool failure' : undefined);
    // dsh-system-prompt orderTools() defaults to code-point order by tool name.
    // Record and enforce that exact order as well as the complete schema.
    const tools = agent.ctx.tools.schemas(scopeOf(agent.ctx)).sort((a: any, b: any) =>
      a.name < b.name ? -1 : a.name > b.name ? 1 : 0);
    schemas.set(agent.session.id, JSON.stringify(tools));
    agent.ctx.on('tools/result', (exec: any, result: any) => {
      if (agent.session.id === sessionId) interceptor?.observe(sessionId, exec, result);
    });
  });
  ctx.on('session/event', (session: any, event: any) => {
    if (session.id !== sessionId) return;
    appendFileSync(join(config.output, 'events.jsonl'), JSON.stringify(event) + '\n', { mode: 0o600 });
    if (event.type === 'assistant/message') {
      privateJson('answer.json', event);
      writeFileSync(join(config.output, 'answer.md'), event.data.message.content
        .filter((part: any) => part.type === 'text').map((part: any) => part.text).join('\n'), { mode: 0o600 });
    }
  }, { global: true });
  ctx.on('agent/error', ({ agent, error }: any) => {
    if (agent.session.id !== sessionId) return;
    status = /budget|request limit|429/i.test(String(error)) ? 'budget_exhausted' : 'failed';
    failure = String(error); record();
  }, { global: true });
  ctx.on('agent/status', ({ agent, status: next }: any) => {
    if (agent.session.id === sessionId && next === 'idle' && status === 'running') {
      status = 'completed'; record();
    }
  }, { global: true });
  ctx.on('llm/stream', (request: any, next: any) => {
    owner(request.sessionId);
    if (!prompted || request.provider !== 'deepseek-official' || request.model !== 'deepseek-flash' ||
        request.reasoningEffort !== 'off' || request.maxTokens !== config.max_output_tokens) refuse('Unapproved model request');
    if (!isAgentLoopRequest(request)) refuse('Auxiliary model calls are disabled');
    const humans = request.messages.filter((message: any) => message.role === 'user' && message.source?.kind === 'user');
    const texts = humans.map((message: any) => message.content?.length === 1 && message.content[0]?.type === 'text' ? message.content[0].text : null);
    if (texts.filter((text: any) => typeof text === 'string' && sha(text) === config.prompt_sha256).length !== 1 ||
        texts.some((text: any) => typeof text !== 'string' || (sha(text) !== config.prompt_sha256 &&
          !text.startsWith('<system-reminder>\n') && !text.startsWith('Current runtime context. This snapshot supersedes')))) refuse('User envelope changed');
    if (new Set(request.tools?.map((tool: any) => tool.name)).size !== allowed.size ||
        request.tools?.some((tool: any) => !allowed.has(tool.name))) refuse('Tool schema surface changed');
    if (digest(request.tools) !== digest(JSON.parse(schemas.get(request.sessionId)!))) {
      audit({ kind: 'schema_mismatch', expected: JSON.parse(schemas.get(request.sessionId)!), actual: request.tools });
      refuse('Tool schema version changed');
    }
    return (async function* () { yield* interceptor ? await interceptor.intercept(sessionId, request, next) : next(); })();
  }, { global: true });
}
