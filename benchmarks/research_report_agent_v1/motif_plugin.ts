/** Benchmark-local TypeScript source (JavaScript-compatible subset).
 * Build: copy byte-for-byte to motif_plugin.mjs; no upstream/core changes.
 * Only independently certified receipt transfers may bypass one LLM request.
 */
import { createHash, randomUUID } from 'node:crypto';
import { appendFileSync, readFileSync, realpathSync } from 'node:fs';
import { isAbsolute, relative, sep } from 'node:path';
import { isAgentLoopRequest } from '@deepseek-ai/dsh-llm';
import { observation } from '../../src/motif_core/online_skill_runtime.mjs';

export const name = 'research-report-receipt-motif';
export const inject = ['llm', 'agents'];
const PREFIX = 'mcp__research_report__';
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const canonical = value => Array.isArray(value) ? value.map(canonical) :
  value && typeof value === 'object' ? Object.fromEntries(Object.keys(value).sort()
    .map(key => [key, canonical(value[key])])) : value;
export const digest = value => sha(JSON.stringify(canonical(value)));
const field = (value, path) => path.split('.').reduce((out, key) => out?.[key], value);
const full = tool => tool.startsWith(PREFIX) ? tool : PREFIX + tool;

export function validateLibrary(library) {
  const { library_digest, ...body } = library;
  if (library.schema_version !== 1 ||
      library.kind !== 'benchmark_workspace_receipt_motifs' ||
      digest(body) !== library_digest || digest(library.contracts) !== library.contracts_digest ||
      digest(library.tool_schemas) !== library.tool_schemas_digest) {
    throw new Error('invalid_library_or_contract_digest');
  }
  for (const motif of library.artifacts) {
    const { motif_id, certified_digest, ...content } = motif;
    if (digest(content) !== certified_digest || motif_id !== 'receipt-' + certified_digest.slice(0, 16)) {
      throw new Error('invalid_certified_motif_digest');
    }
    const training = new Set(motif.training_evidence.map(row => row.case_id));
    if (training.size < 2 || training.has(motif.certification_evidence.case_id) ||
        library.contracts[motif.to_tool]?.execution !== 'workspace_idempotent' ||
        JSON.stringify(library.contracts[motif.to_tool]?.required_params) !== JSON.stringify([motif.to_param])) {
      throw new Error('invalid_independent_certification_or_write_scope');
    }
  }
}

function inside(path, root) {
  const part = relative(root, path);
  return part !== '' && !isAbsolute(part) && part !== '..' && !part.startsWith('..' + sep);
}

export function checkReceipt(output, task) {
  const provenance = output?._provenance;
  if (!provenance || typeof provenance.record_path !== 'string' ||
      !Array.isArray(provenance.authorized_tools) ||
      provenance.data_sha256 !== task.csv_sha256 ||
      provenance.workspace_id !== task.workspace_id ||
      output.source_version !== task.study_version ||
      output.source_version !== provenance.study_sha256) throw new Error('receipt_provenance_mismatch');
  for (const item of task.source_files) {
    if (sha(readFileSync(item.path)) !== item.sha256) throw new Error('source_changed');
  }
  const root = realpathSync(task.workspace);
  const path = realpathSync(provenance.record_path);
  if (!inside(path, root)) throw new Error('receipt_outside_workspace');
  const bytes = readFileSync(path);
  if (sha(bytes) !== provenance.record_sha256) throw new Error('receipt_content_changed');
  const receipt = JSON.parse(bytes.toString('utf8'));
  if (receipt.workspace_id !== provenance.workspace_id || receipt.source_version !== output.source_version ||
      digest(receipt.authorized_tools) !== digest(provenance.authorized_tools)) {
    throw new Error('receipt_authority_mismatch');
  }
  return receipt;
}

function sameSchema(tool, contract, certifiedSchema) {
  const schema = tool?.parameters ?? tool?.inputSchema;
  return schema?.type === 'object' && Array.isArray(schema.required) &&
    !!certifiedSchema && digest(schema) === digest(certifiedSchema) &&
    JSON.stringify([...schema.required].sort()) === JSON.stringify([...contract.required_params].sort()) &&
    contract.required_params.every(key => schema.properties?.[key]?.type === 'string');
}

async function* synthetic(callId, tool, args) {
  const marker = 'Benchmark runtime executed a certified workspace-scoped receipt continuation; this is not model reasoning.';
  yield { type: 'block-start', index: 0, blockType: 'reasoning' };
  yield { type: 'reasoning-delta', index: 0, text: marker };
  yield { type: 'block-end', index: 0, block: { type: 'reasoning', text: marker } };
  yield { type: 'block-start', index: 1, blockType: 'tool-call' };
  const argumentsText = JSON.stringify(args);
  yield { type: 'tool-call-delta', index: 1, id: callId, name: tool, argumentsDelta: argumentsText };
  yield { type: 'block-end', index: 1, block: { type: 'tool-call', id: callId, name: tool, arguments: argumentsText } };
  yield { type: 'finish', reason: { kind: 'tool-calls' } };
}

export function createInterceptor({ library, task, mode = 'shadow', audit = () => {} }) {
  validateLibrary(library);
  if (!['shadow', 'execute'].includes(mode)) throw new Error('invalid_mode');
  let latest = null;
  let pending = null;
  let halted = false;
  const used = new Set();
  const successful = new Set();
  function observe(exec, result) {
    const output = observation(result, exec.name);
    const ok = !!output && output.ok !== false && output.passed !== false && output.quality_passed !== false &&
      !result?.isError && !result?.value?.isError;
    let args;
    try { args = typeof exec.arguments === 'string' ? JSON.parse(exec.arguments) : exec.arguments; }
    catch { latest = null; halted = true; return; }
    latest = ok ? { name: exec.name, callId: exec.callId, arguments: args, output } : null;
    if (ok) successful.add(digest({ name: exec.name, arguments: args }));
    if (pending && pending.callId === exec.callId) {
      let verified = ok && exec.name === pending.tool && digest(args) === digest(pending.arguments);
      try { if (verified) checkReceipt(output, task); } catch { verified = false; }
      audit({ kind: verified ? 'model_request_skipped_verified' : 'motif_result_unverified',
        call_id: exec.callId, tool: exec.name, motif_id: pending.motif_id, tool_count: 1 });
      halted ||= !verified;
      pending = null;
    } else if (!ok) {
      audit({ kind: 'motif_fallback', reason: 'tool_failure_barrier', tool: exec.name });
    }
  }
  async function intercept(options, next) {
    if (halted || pending || !latest) return next();
    const candidates = [];
    try {
      const receipt = checkReceipt(latest.output, task);
      const authorized = new Set(latest.output._provenance.authorized_tools.map(full));
      for (const motif of library.artifacts) {
        if (motif.from_tool !== latest.name || !authorized.has(motif.to_tool)) continue;
        const value = field(latest.output, motif.from_field);
        // IDs must belong to the verified receipt, never arbitrary free text.
        if (typeof value !== 'string' || value.length < 16 || receipt.id !== value) continue;
        const tool = (options.tools ?? []).find(row => row.name === motif.to_tool);
        if (!sameSchema(tool, library.contracts[motif.to_tool], library.tool_schemas[motif.to_tool])) continue;
        const args = { [motif.to_param]: value };
        const key = digest({ name: motif.to_tool, arguments: args });
        if (used.has(key) || successful.has(key)) continue;
        candidates.push({ motif, args, key });
      }
    } catch (error) {
      audit({ kind: 'motif_fallback', reason: error.message, after_call_id: latest.callId });
      return next();
    }
    if (candidates.length !== 1) {
      audit({ kind: 'motif_fallback', reason: candidates.length ? 'ambiguous_continuation' : 'semantic_or_unlearned_frontier',
        after_call_id: latest.callId });
      return next();
    }
    const { motif, args, key } = candidates[0];
    if (mode === 'shadow') {
      audit({ kind: 'shadow_candidate', motif_id: motif.motif_id, tool: motif.to_tool, arguments: args });
      return next();
    }
    const callId = 'rra-motif-' + randomUUID();
    pending = { callId, tool: motif.to_tool, arguments: args, motif_id: motif.motif_id };
    used.add(key);
    audit({ kind: 'motif_bypass_attempt', motif_id: motif.motif_id, certified_digest: motif.certified_digest,
      call_id: callId, after_call_id: latest.callId, tool: motif.to_tool, arguments: args,
      selection: 'unique_witnessed_receipt_binding_and_explicit_llm_plan_permission',
      record_sha256: latest.output._provenance.record_sha256 });
    return synthetic(callId, motif.to_tool, args);
  }
  return { observe, intercept };
}

export function apply(ctx) {
  const config = JSON.parse(readFileSync(process.env.RRA_MOTIF_TASK, 'utf8'));
  const library = JSON.parse(readFileSync(process.env.RRA_MOTIF_LIBRARY, 'utf8'));
  const audit = row => appendFileSync(config.audit_path,
    JSON.stringify({ utc: new Date().toISOString(), session_id: config.session_id, ...row }) + '\n', { mode: 0o600 });
  const interceptor = createInterceptor({ library, task: config,
    mode: process.env.RRA_MOTIF_MODE ?? 'shadow', audit });
  let live = false;
  let envelope = null;
  audit({ kind: 'plugin_loaded', library_digest: library.library_digest });
  ctx.on('agent/created', ({ agent }) => {
    if (agent.session.id !== config.session_id) return;
    live = true;
    agent.ctx.on('tools/result', (exec, result) => interceptor.observe(exec, result));
  });
  ctx.on('agent/disposed', ({ agent }) => { if (agent.session.id === config.session_id) live = false; });
  ctx.on('llm/stream', (options, next) => {
    if (!live || options.sessionId !== config.session_id || !isAgentLoopRequest(options)) return next();
    const human = (options.messages ?? []).filter(row => row.role === 'user' && row.source?.kind === 'user');
    const original = human.filter(row => row.content?.length === 1 && row.content[0]?.type === 'text' &&
      sha(row.content[0].text) === config.prompt_sha256);
    const known = human.every(row => row.content?.length === 1 && row.content[0]?.type === 'text' &&
      (sha(row.content[0].text) === config.prompt_sha256 ||
       row.content[0].text.startsWith('<system-reminder>\n') ||
       row.content[0].text.startsWith('Current runtime context. This snapshot supersedes')));
    const hash = digest(human.map(row => ({ id: row.id, content: row.content })));
    if (original.length !== 1 || !known || (envelope !== null && envelope !== hash)) {
      audit({ kind: 'motif_fallback', reason: 'user_request_changed' });
      return next();
    }
    envelope = hash;
    return (async function* () { yield* await interceptor.intercept(options, next); })();
  }, { global: true });
}
