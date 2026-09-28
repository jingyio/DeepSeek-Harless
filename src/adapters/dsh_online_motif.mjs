/** DSH adapter: replace one model decision with certified read-only calls. */

import { randomUUID, createHash } from 'node:crypto';
import { appendFileSync, mkdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { isAgentLoopRequest } from '@deepseek-ai/dsh-llm';
import { digest, observation, parseStructuredTask, proposeReadyBatch,
  syntheticToolStreamBatch, validateOnlineManifest } from '../motif_core/online_skill_runtime.mjs';

export const name = 'sss-online-motif';
export const inject = ['llm', 'agents'];

function outputField(output, path) {
  return path?.split('.').reduce((value, key) =>
    value && typeof value === 'object' ? value[key] : undefined, output);
}

function versionWithinTask(task, tool, value) {
  const allowed = task.source_versions[tool];
  return typeof value === 'string' &&
    (Array.isArray(allowed) ? allowed.includes(value) : allowed === value);
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
      found = { history: [], pending: new Map(), batches: new Map(),
        usedPrefixes: new Set(), attempted: 0, halted: false };
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
    const barrier = !ok || manifest.contracts[exec.name]?.read_only !== true ||
      (!!manifest.version_fields[exec.name] &&
       !versionWithinTask(parsedTask, exec.name, version));
    current.history.push({ name: exec.name, callId: exec.callId, ok,
      barrier, arguments: exec.arguments, output, sourceVersion: version,
      inputVersion: parsedTask.input_version });
    current.history.splice(0, Math.max(0, current.history.length - 12));
    const pending = current.pending.get(exec.callId);
    if (pending) {
      const verified = ok && exec.name === pending.tool &&
        exec.arguments && typeof exec.arguments === 'object' &&
        digest(exec.arguments) === digest(pending.arguments) &&
        version === pending.expected_version;
      const batch = current.batches.get(pending.batch_id);
      batch.remaining.delete(exec.callId);
      batch.failed ||= !verified;
      audit({ kind: verified ? 'motif_tool_result_verified' : 'motif_tool_result_unverified',
        session_id: sessionId, batch_id: pending.batch_id,
        call_id: exec.callId, motif_id: pending.motif_id, tool: exec.name });
      current.pending.delete(exec.callId);
      if (!batch.remaining.size) {
        audit({ kind: batch.failed ? 'bypass_result_unverified' : 'model_request_skipped_verified',
          session_id: sessionId, batch_id: pending.batch_id,
          tool_count: batch.tool_count });
        if (batch.failed) current.halted = true;
        current.batches.delete(pending.batch_id);
      }
    }
  }
  async function intercept(sessionId, options, next) {
    if (sessionId !== parsedTask.session_id) return next();
    const current = state(sessionId);
    if (current.halted || current.pending.size) return next();
    const availableTools = new Map((options.tools ?? [])
      .filter((tool) => typeof tool?.name === 'string')
      .map((tool) => [tool.name, tool]));
    let proposals;
    try {
      proposals = await proposeReadyBatch({ manifest, task: parsedTask,
        history: current.history, availableTools, similarity,
        minSimilarity, minMargin, usedPrefixes: current.usedPrefixes });
    } catch (error) {
      audit({ kind: 'motif_deferred', session_id: sessionId,
        reason: error?.name ?? 'candidate_error' });
      return next();
    }
    if (!proposals.length) {
      audit({ kind: 'motif_frontier_empty', session_id: sessionId,
        observed_tool_count: current.history.length,
        recent_tools: current.history.slice(-4).map((row) => row.name),
        recent_barriers: current.history.slice(-4).map((row) => row.barrier) });
      return next();
    }
    if (mode === 'shadow') {
      audit({ kind: 'shadow_candidate', session_id: sessionId,
        motifs: proposals.map((row) => row.motif_id),
        tools: proposals.map((row) => row.tool) });
      return next();
    }
    const batchId = `sss-batch-${randomUUID()}`;
    const calls = proposals.map((proposal) => ({
      callId: `sss-motif-${randomUUID()}`, proposal }));
    current.batches.set(batchId, { remaining: new Set(calls.map((row) => row.callId)),
      failed: false, tool_count: calls.length });
    for (const { callId, proposal } of calls) {
      current.pending.set(callId, { ...proposal, batch_id: batchId });
      current.usedPrefixes.add(proposal.prefix_key);
    }
    current.attempted++;
    audit({ kind: 'motif_bypass_attempt', session_id: sessionId,
      batch_id: batchId, call_ids: calls.map((row) => row.callId),
      motifs: proposals.map((row) => row.motif_id),
      certified_digests: proposals.map((row) => row.certified_digest),
      tools: proposals.map((row) => row.tool),
      selection_bases: proposals.map((row) => row.selection_basis),
      code_node_ids: proposals.flatMap((row) => row.code_node_ids),
      code_program_digests: proposals.flatMap((row) => row.code_program_digests),
      similarities: proposals.map((row) => row.similarity) });
    return syntheticToolStreamBatch(calls);
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
  const audit = (kind, reason) => privateAudit(process.cwd(), task.session_id,
    { kind, session_id: task.session_id, reason });
  audit('motif_plugin_loaded', 'manifest_validated');
  const live = new Set();
  let trustedUserEnvelope = null;
  ctx.on('agent/created', ({ agent }) => {
    if (agent.session.id !== task.session_id) return;
    audit('motif_agent_attached', 'session_matched');
    live.add(agent.session.id);
    agent.ctx.on('tools/result', (exec, result) =>
      interceptor.observe(agent.session.id, exec, result));
  });
  ctx.on('agent/disposed', ({ agent }) => live.delete(agent.session.id));
  ctx.on('llm/stream', (options, next) => {
    audit('motif_stream_seen', options.sessionId === task.session_id
      ? 'session_matched' : 'other_session');
    if (options.sessionId !== task.session_id) return next();
    if (!isAgentLoopRequest(options)) {
      audit('motif_gate_deferred', 'not_agent_loop_request');
      return next();
    }
    if (!live.has(options.sessionId)) {
      audit('motif_gate_deferred', 'agent_not_live');
      return next();
    }
    const human = options.messages?.filter((message) =>
      message?.role === 'user' && message?.source?.kind === 'user') ?? [];
    const texts = human.map((message) => message.content?.length === 1 &&
      message.content[0]?.type === 'text' ? message.content[0].text : null);
    const matching = texts.filter((value) => typeof value === 'string' &&
      createHash('sha256').update(value).digest('hex') === promptHash);
    const reminder = texts.filter((value) => typeof value === 'string' &&
      value.startsWith('<system-reminder>\n'));
    const runtime = texts.filter((value) => typeof value === 'string' &&
      value.startsWith('Current runtime context. This snapshot supersedes'));
    if (matching.length !== 1 || reminder.length > 1 || runtime.length > 1 ||
        matching.length + reminder.length + runtime.length !== human.length) {
      audit('motif_gate_deferred', 'prompt_or_scaffold_mismatch');
      return next();
    }
    const envelope = digest(human.map((message) =>
      ({ id: message.id, content: message.content })));
    if (trustedUserEnvelope !== null && envelope !== trustedUserEnvelope) {
      audit('motif_gate_deferred', 'user_envelope_changed');
      return next();
    }
    trustedUserEnvelope = envelope;
    return (async function* () {
      const stream = await interceptor.intercept(options.sessionId, options, next);
      yield* stream;
    })();
  }, { global: true });
}
