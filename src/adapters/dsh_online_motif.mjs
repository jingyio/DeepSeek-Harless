/** DSH adapter: replace one model decision with one certified read-only tool call. */

import { randomUUID, createHash } from 'node:crypto';
import { appendFileSync, mkdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { isAgentLoopRequest } from '@deepseek-ai/dsh-llm';
import { digest, observation, parseStructuredTask, proposeNext,
  syntheticToolStream, validateOnlineManifest } from './online_motif_frontier.mjs';

export const name = 'sss-online-motif';
export const inject = ['llm', 'agents'];

function outputField(output, path) {
  return path?.split('.').reduce((value, key) =>
    value && typeof value === 'object' ? value[key] : undefined, output);
}

function cosine(a, b) {
  if (!Array.isArray(a) || !Array.isArray(b) || !a.length ||
      a.length !== b.length || [...a, ...b].some((value) =>
        typeof value !== 'number' || !Number.isFinite(value))) {
    throw new TypeError('invalid local embedding vector');
  }
  const dot = a.reduce((sum, value, index) => sum + value * b[index], 0);
  const left = Math.sqrt(a.reduce((sum, value) => sum + value * value, 0));
  const right = Math.sqrt(b.reduce((sum, value) => sum + value * value, 0));
  if (!left || !right) throw new TypeError('zero local embedding vector');
  return dot / left / right;
}

export function loopbackSimilarity(endpoint, model, fetcher = fetch) {
  const url = new URL(endpoint);
  if (url.protocol !== 'http:' ||
      !['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname) ||
      !url.pathname.endsWith('/v1/embeddings') || !model) {
    throw new TypeError('Motif embeddings must use a local loopback endpoint');
  }
  return async (query, descriptions) => {
    const response = await fetcher(url, { method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ model, input: [query, ...descriptions] }),
      signal: AbortSignal.timeout(20000) });
    if (!response.ok) throw new Error('local embedding request failed');
    const body = await response.json();
    const rows = body?.data;
    if (!Array.isArray(rows) || rows.length !== descriptions.length + 1) {
      throw new TypeError('local embedding result count changed');
    }
    const ordered = [...rows].sort((a, b) => a.index - b.index);
    if (ordered.some((row, index) => row.index !== index)) {
      throw new TypeError('local embedding result order changed');
    }
    return ordered.slice(1).map((row) => cosine(ordered[0].embedding, row.embedding));
  };
}

/** Injectable for protocol tests; the production entry point is apply(). */
export function createOnlineInterceptor({ manifest, task, similarity, mode = 'shadow',
                                           minSimilarity = 0.8, minMargin = 0.1,
                                           audit = () => {} }) {
  validateOnlineManifest(manifest);
  const parsedTask = parseStructuredTask(task, manifest);
  if (!['shadow', 'execute'].includes(mode) ||
      typeof similarity !== 'function' || typeof audit !== 'function') {
    throw new TypeError('invalid online Motif policy');
  }
  const states = new Map();
  function state(sessionId) {
    let found = states.get(sessionId);
    if (!found) {
      found = { history: [], pending: new Map(), attempted: 0 };
      states.set(sessionId, found);
    }
    return found;
  }
  function observe(sessionId, exec, result) {
    if (sessionId !== parsedTask.session_id) return;
    const current = state(sessionId);
    const output = observation(result);
    const version = outputField(output, manifest.version_fields[exec.name]);
    const ok = result?.isError !== true && output !== null;
    current.history.push({ name: exec.name, ok,
      arguments: exec.arguments, output, sourceVersion: version,
      inputVersion: parsedTask.input_version });
    current.history.splice(0, Math.max(0, current.history.length - 12));
    const pending = current.pending.get(exec.callId);
    if (pending) {
      const verified = ok && exec.name === pending.tool &&
        exec.arguments && typeof exec.arguments === 'object' &&
        digest(exec.arguments) === digest(pending.arguments) &&
        version === parsedTask.source_versions[exec.name];
      audit({ kind: verified ? 'model_request_skipped_verified' : 'bypass_result_unverified',
        session_id: sessionId, call_id: exec.callId, motif_id: pending.motif_id,
        tool: exec.name });
      current.pending.delete(exec.callId);
    }
  }
  async function intercept(sessionId, options, next) {
    if (sessionId !== parsedTask.session_id) return next();
    const current = state(sessionId);
    const availableTools = new Map((options.tools ?? [])
      .filter((tool) => typeof tool?.name === 'string')
      .map((tool) => [tool.name, tool]));
    let proposal;
    try {
      proposal = await proposeNext({ manifest, task: parsedTask,
        history: current.history, availableTools, similarity,
        minSimilarity, minMargin });
    } catch (error) {
      audit({ kind: 'motif_deferred', session_id: sessionId,
        reason: error?.name ?? 'candidate_error' });
      return next();
    }
    if (!proposal || !manifest.version_fields[proposal.tool] ||
        !parsedTask.source_versions[proposal.tool] || current.pending.size) {
      return next();
    }
    if (mode === 'shadow') {
      audit({ kind: 'shadow_candidate', session_id: sessionId,
        motif_id: proposal.motif_id, tool: proposal.tool });
      return next();
    }
    const callId = `sss-motif-${randomUUID()}`;
    current.pending.set(callId, proposal);
    current.attempted++;
    audit({ kind: 'motif_bypass_attempt', session_id: sessionId,
      call_id: callId, motif_id: proposal.motif_id,
      certified_digest: proposal.certified_digest, tool: proposal.tool,
      similarity: proposal.similarity, score: proposal.score });
    return syntheticToolStream(callId, proposal);
  }
  return { observe, intercept, state };
}

function privateAudit(root, sessionId, row) {
  const dir = join(root, '.local', 'online-motif');
  mkdirSync(dir, { recursive: true, mode: 0o700 });
  const file = join(dir, `${createHash('sha256').update(sessionId).digest('hex')}.jsonl`);
  appendFileSync(file, JSON.stringify(row) + '\n', { mode: 0o600 });
}

export function apply(ctx) {
  const manifestPath = process.env.SSS_ONLINE_MOTIF_MANIFEST;
  const taskPath = process.env.SSS_ONLINE_MOTIF_TASK;
  if (!manifestPath || !taskPath) return;
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
  const task = JSON.parse(readFileSync(taskPath, 'utf8'));
  const similarity = loopbackSimilarity(
    process.env.SSS_MOTIF_EMBEDDING_ENDPOINT ?? '',
    process.env.SSS_MOTIF_EMBEDDING_MODEL ?? '');
  const mode = process.env.SSS_ONLINE_MOTIF_MODE ?? 'shadow';
  const promptHash = process.env.SSS_ONLINE_MOTIF_PROMPT_SHA256;
  if (mode === 'execute' && !/^[a-f0-9]{64}$/.test(promptHash ?? '')) {
    throw new TypeError('execute mode needs the frozen research prompt digest');
  }
  const interceptor = createOnlineInterceptor({ manifest, task, similarity, mode,
    minSimilarity: Number(process.env.SSS_MOTIF_MIN_SIMILARITY ?? 0.8),
    minMargin: Number(process.env.SSS_MOTIF_MIN_MARGIN ?? 0.1),
    audit: (row) => privateAudit(process.cwd(), row.session_id, row) });
  const live = new Set();
  ctx.on('agent/created', ({ agent }) => {
    if (agent.session.id !== task.session_id) return;
    live.add(agent.session.id);
    agent.ctx.on('tools/result', (exec, result) =>
      interceptor.observe(agent.session.id, exec, result));
  });
  ctx.on('agent/disposed', ({ agent }) => live.delete(agent.session.id));
  ctx.on('llm/stream', (options, next) => {
    if (!isAgentLoopRequest(options) || !live.has(options.sessionId)) return next();
    const human = options.messages?.filter((message) =>
      message?.role === 'user' && message?.source?.kind === 'user') ?? [];
    if (human.length !== 1) return next();
    const promptText = human[0].content?.length === 1 &&
      human[0].content[0]?.type === 'text' ? human[0].content[0].text : null;
    if (typeof promptText !== 'string' || (promptHash &&
        createHash('sha256').update(promptText).digest('hex') !== promptHash)) {
      return next();
    }
    return (async function* () {
      const stream = await interceptor.intercept(options.sessionId, options, next);
      yield* stream;
    })();
  });
}
