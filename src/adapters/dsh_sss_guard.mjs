/** Restrict a dedicated DSH Agent to the SSS runtime's audited tools.
 *
 * This is a host plugin, not a model-visible Skill. It uses DSH's documented
 * agent-scoped ToolRuntime restriction and monotonic pre-dispatch guard. The
 * global plugin must only be mounted in the dedicated SSS profile.
 */

import { createHash } from 'node:crypto';
import { mkdirSync, renameSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { isDeepStrictEqual } from 'node:util';

export const name = 'sss-motif-gate';
export const inject = ['tools', 'agents'];

export const SSS_TOOLS = Object.freeze([
  'mcp__sss_runtime__collect_sources',
  'mcp__sss_runtime__read_page',
  'mcp__sss_runtime__refresh_sources',
  'mcp__sss_runtime__open_point',
  'mcp__sss_runtime__resolve_point',
]);

function resultObject(result) {
  const value = result?.value;
  if (value?.structuredContent && typeof value.structuredContent === 'object') {
    return value.structuredContent;
  }
  const block = value?.content?.find((item) => item?.type === 'text');
  if (typeof block?.text === 'string') {
    try {
      const parsed = JSON.parse(block.text);
      return parsed && typeof parsed === 'object' ? parsed : null;
    } catch { /* An unstructured MCP response cannot issue a run handle. */ }
  }
  return null;
}

/** Record only SSS-issued run handles, not coincidental argument equality. */
export function createProvenanceTracker(persist) {
  const issued = new Map();
  const frontiers = new Map();
  const sidecar = {};
  return (exec, result) => {
    if (!SSS_TOOLS.includes(exec?.name) || result?.isError) return;
    const args = exec.arguments;
    const parent = args && typeof args === 'object' ? issued.get(args.run_id) : null;
    if (parent && typeof exec.callId === 'string') {
      sidecar[exec.callId] = { run_id: parent };
      const frontier = frontiers.get(args.frontier_id);
      if (exec.name === 'mcp__sss_runtime__resolve_point' && frontier &&
          frontier.run_id === args.run_id) {
        for (const [param, field] of Object.entries({
          frontier_id: 'frontier_id',
          point_id: 'point_id',
          question: 'question',
          source_allowlist: 'allowed_sources',
          handoff_signature: 'handoff_signature',
        })) {
          if (Object.hasOwn(args, param) &&
              isDeepStrictEqual(args[param], frontier.output[field])) {
            sidecar[exec.callId][param] = {
              from_call_id: frontier.from_call_id,
              from_field: field,
            };
          }
        }
      }
      persist(sidecar);
    }
    if (exec.name === 'mcp__sss_runtime__open_point') {
      const output = resultObject(result);
      if (typeof output?.frontier_id === 'string' &&
          output.run_id === args?.run_id && typeof exec.callId === 'string') {
        frontiers.set(output.frontier_id, {
          run_id: output.run_id, from_call_id: exec.callId, output,
        });
      }
    }
    if (exec.name === 'mcp__sss_runtime__collect_sources' ||
        exec.name === 'mcp__sss_runtime__refresh_sources') {
      const output = resultObject(result);
      if (typeof output?.run_id === 'string' && typeof exec.callId === 'string') {
        issued.set(output.run_id, {
          from_call_id: exec.callId,
          from_field: 'run_id',
        });
      }
    }
  };
}

function provenanceWriter(sessionId) {
  const directory = join(process.cwd(), '.local', 'sss-runtime', 'provenance');
  const basename = createHash('sha256').update(String(sessionId)).digest('hex');
  const target = join(directory, `${basename}.json`);
  return (sidecar) => {
    mkdirSync(directory, { recursive: true, mode: 0o700 });
    const temporary = `${target}.tmp`;
    writeFileSync(temporary, JSON.stringify(sidecar, null, 2), { mode: 0o600 });
    renameSync(temporary, target);
  };
}

export function apply(ctx) {
  ctx.on('agent/created', ({ agent }) => {
    agent.ctx.tools.restrict({ allow: SSS_TOOLS });
    agent.ctx.tools.guard((call) =>
      SSS_TOOLS.includes(call.name)
        ? undefined
        : 'This SSS session executes tools through the Motif runtime only.');
    agent.ctx.on('tools/result', createProvenanceTracker(
      provenanceWriter(agent.session.id)));
  });
}
