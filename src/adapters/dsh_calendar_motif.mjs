/** Opt-in DSH bridge for one certified, read-only Calendar continuation. */

import { createHash } from 'node:crypto';
import { appendFileSync, mkdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { isAgentLoopRequest } from '@deepseek-ai/dsh-llm';
import { createCalendarContinuation } from '../motif_core/calendar_continuation.mjs';
import { digest } from '../motif_core/online_skill_runtime.mjs';

export const name = 'sss-calendar-motif';
export const inject = ['llm', 'agents'];

export function apply(ctx) {
  const artifactPath = process.env.SSS_CALENDAR_MOTIF_ARTIFACT;
  const sessionId = process.env.SSS_CALENDAR_MOTIF_SESSION;
  const promptHash = process.env.SSS_CALENDAR_MOTIF_PROMPT_SHA256;
  const mode = process.env.SSS_CALENDAR_MOTIF_MODE ?? 'shadow';
  const auditRoot = process.env.SSS_CALENDAR_MOTIF_AUDIT_ROOT;
  if (!artifactPath || !sessionId || !auditRoot) return;
  if (!/^[a-f0-9]{64}$/.test(promptHash ?? '') ||
      !['shadow', 'execute'].includes(mode)) {
    throw new TypeError('Calendar Motif needs a frozen prompt and mode');
  }
  const auditFile = join(auditRoot, 'motif-events.jsonl');
  mkdirSync(auditRoot, { recursive: true, mode: 0o700 });
  const audit = (row) => appendFileSync(auditFile,
    JSON.stringify({ time: new Date().toISOString(), ...row }) + '\n', { mode: 0o600 });
  const artifact = JSON.parse(readFileSync(artifactPath, 'utf8'));
  const continuation = createCalendarContinuation({ artifact, sessionId, audit });
  audit({ kind: 'calendar_motif_plugin_loaded', motif_id: artifact.motif_id, mode });
  const live = new Set();
  let userEnvelope = null;
  ctx.on('agent/created', ({ agent }) => {
    if (agent.session.id !== sessionId) return;
    live.add(sessionId);
    audit({ kind: 'calendar_motif_agent_attached' });
    agent.ctx.on('tools/result', (exec, result) => continuation.observe(exec, result));
  });
  ctx.on('agent/disposed', ({ agent }) => live.delete(agent.session.id));
  ctx.on('llm/stream', (options, next) => {
    if (options.sessionId !== sessionId) return next();
    if (!live.has(sessionId) || !isAgentLoopRequest(options)) return next();
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
      audit({ kind: 'calendar_prompt_changed' });
      return next();
    }
    const envelope = digest(human.map((message) =>
      ({ id: message.id, content: message.content })));
    if (userEnvelope !== null && envelope !== userEnvelope) {
      audit({ kind: 'calendar_user_envelope_changed' });
      return next();
    }
    userEnvelope = envelope;
    if (mode === 'shadow') {
      audit({ kind: 'calendar_shadow_check', anchor: !!continuation.state.anchor });
      return next();
    }
    return continuation.intercept(options, next);
  }, { global: true });
}
