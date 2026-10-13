/** Private diagnostic projection of original Harness events, never training evidence. */
import { createHash, randomUUID } from 'node:crypto';
import { existsSync, lstatSync, readFileSync, realpathSync, writeFileSync, renameSync } from 'node:fs';
import { join, resolve, sep, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const sha = (data: string | Buffer) => createHash('sha256').update(data).digest('hex');
function args(value: any) {
  try { return typeof value === 'string' ? JSON.parse(value) : value ?? {}; } catch { return {}; }
}
function selection(value: any) {
  const result: any = {};
  for (const key of ['paper_id', 'page', 'start', 'length', 'source_id', 'claim_id', 'query',
    'document_version_sha256', 'extraction_id', 'verification_id', 'windows']) {
    if (value[key] !== undefined) result[key] = value[key];
  }
  if (value.plan !== undefined) {
    const plan = args(value.plan);
    result.plan = typeof value.plan === 'string' && value.plan.startsWith('source-') ? value.plan : plan;
  }
  return result;
}

export function projectEvents(events: any[], origin: any) {
  const records: any[] = [], results = new Map<string, any[]>();
  for (const event of events) if (event.type === 'tool/result') {
    for (const block of event.data?.message?.content ?? []) if (block.type === 'tool-result') {
      const id = block.toolCallId ?? event.data.message.source?.callId;
      if (!results.has(id)) results.set(id, []);
      results.get(id)!.push({ event, block });
    }
  }
  const ref = (e: any) => ({ ...origin, seq: e.seq, event_type: e.type, time: e.time,
    turn: e.data?.turn ?? null, step: e.data?.step ?? null });
  for (const event of events) {
    const data = event.data ?? {};
    if (event.type === 'assistant/message' && data.message?.source?.kind === 'model') {
      const text = (data.message.content ?? []).filter((b: any) => b.type === 'text').map((b: any) => b.text).join('\n');
      records.push({ kind: 'model_message', actor: 'model', origin: ref(event),
        stated_text: text.slice(0, 4000), stated_text_truncated: text.length > 4000,
        rationale_inferred: false, usage: data.usage ?? null,
        reason_scope: 'explicit visible text only; no reconstruction of unstated reasoning' });
    }
    if (event.type !== 'tool/call') continue;
    const matched = results.get(data.callId) ?? [];
    const pair = matched.length === 1 ? matched[0] : undefined;
    const text = pair?.block.content?.filter((b: any) => b.type === 'text').map((b: any) => b.text).join('\n') ?? '';
    const observed = args(text), input = args(data.arguments);
    const millis = (time: any) => typeof time === 'number' ? time : Date.parse(time);
    const elapsed = pair ? millis(pair.event.time) - millis(event.time) : NaN;
    records.push({ kind: 'tool_decision', actor: 'harness_tool_dispatch', origin: ref(event),
      call_id: data.callId, tool: data.name, selection: selection(input),
      arguments_sha256: sha(JSON.stringify(data.arguments)), result_origin: pair ? ref(pair.event) : null,
      outcome: !pair ? 'missing_or_ambiguous_result' : pair.block.isError ? 'error' : 'success',
      tool_status: observed.status ?? null, elapsed_ms: Number.isFinite(elapsed) && elapsed >= 0 ? elapsed : null,
      normalization: observed.normalization ?? null, cache_stats: observed.cache_stats ?? null,
      reused_windows: observed.reused_windows ?? null,
      error: pair?.block.isError ? text.slice(0, 1200) : null,
      rationale_inferred: false, rationale_origin: 'explicit window purpose/query or preceding model text; otherwise unknown',
      model_bypass_inferred: false });
  }
  return records;
}

function privateInput(path: string, base: string) {
  const absolute = resolve(path);
  if (!absolute.startsWith(resolve(base) + sep) || !existsSync(absolute)
      || lstatSync(absolute).isSymbolicLink() || !lstatSync(absolute).isFile()
      || !realpathSync(absolute).startsWith(realpathSync(base) + sep)) throw new Error('unavailable private native artifact');
  return absolute;
}

export function writeDecisionLog(directory: string, job: any) {
  const base = join(ROOT, '.local/runs'), records = [...(job.workflow_decisions ?? [])], runs: any[] = [], issues: any[] = [];
  const seen = new Set<string>();
  for (const stage of job.stages ?? []) for (const summary of stage.summaries ?? []) {
    if (!summary.output_dir || seen.has(summary.output_dir)) continue;
    seen.add(summary.output_dir);
    try {
      const path = privateInput(join(summary.output_dir, 'agent-events.jsonl'), base);
      const bytes = readFileSync(path), events = bytes.toString('utf8').split('\n').filter(Boolean).map(line => JSON.parse(line));
      const origin = { stage: stage.stage, run_directory: resolve(summary.output_dir),
        events_path: path, events_sha256: sha(bytes) };
      records.push(...projectEvents(events, origin));
      let ledger: any[] | null = null, ledgerSha: string | null = null;
      try {
        const bytes = readFileSync(privateInput(join(summary.output_dir, 'cost-ledger.jsonl'), base));
        ledger = bytes.toString('utf8').split('\n').filter(Boolean).map(line => JSON.parse(line)); ledgerSha = sha(bytes);
      } catch { issues.push({ stage: stage.stage, run: summary.output_dir, reason: 'native_cost_ledger_unavailable' }); }
      runs.push({ ...origin, metrics_summary: summary, ledger_sha256: ledgerSha, requests: ledger,
        fee_attribution: 'native request ledger and whole run only; no invented per-tool fee' });
    } catch { issues.push({ stage: stage.stage, run: summary.output_dir, reason: 'native_events_unavailable_or_invalid' }); }
  }
  const report = { schema_version: 1, kind: 'literature_decision_diagnostic', job_id: job.id,
    frame: job.frame, status: job.status, records, runs, issues, complete: issues.length === 0,
    model_requests: job.model_requests, accounted_usd: job.accounted_usd, cost_complete: job.cost_complete,
    synthetic_native_events: false, eligible_for_motif_training: false,
    scientific_quality_assessed: false, additional_model_requests: 0,
    limitations: 'Reasons not stated by the model remain unknown. Cache/normalization are scripts; '
      + 'native Motif skips must be checked against original plugin audit. This projection is not a training trace.' };
  const target = join(directory, 'decision-log.json'), temporary = target + '.tmp-' + randomUUID();
  writeFileSync(temporary, JSON.stringify(report, null, 2) + '\n', { mode: 0o600 }); renameSync(temporary, target);
  return { path: target, record_count: records.length, native_run_count: runs.length, complete: report.complete, issues };
}
