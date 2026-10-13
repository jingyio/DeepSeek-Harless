/** Scene workflow and local UI. All model turns remain in the original Harness. */
import { createHash, randomUUID, timingSafeEqual } from 'node:crypto';
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { existsSync, mkdirSync, readFileSync, writeFileSync, renameSync, readdirSync, realpathSync, lstatSync } from 'node:fs';
import { dirname, join, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { writeDecisionLog } from './decision-log.ts';

export const HERE = dirname(fileURLToPath(import.meta.url));
export const ROOT = resolve(HERE, '../..');
export const JOBS = join(ROOT, '.local/literature-notes/agent-jobs');
const DEFAULT_QUESTION = '这三篇论文的方法、实验证据和限制，对构建高效科研 Agent 有什么启示？';
type Result = { code: number; stdout: string; stderr: string };
type Executor = (args: string[], input?: unknown) => Promise<Result>;
type Options = { papers_dir?: string; question?: string; budget_usd?: number; call_model?: boolean;
                 reading_entry_policy?: string; claim_entry_policy?: string; incremental_entry_policy?: string;
                 claim_terminal_policy?: string;
                 model_review?: boolean; parent_job?: string; manifest?: string; force_refresh?: boolean; repair_rounds?: number; repair_only?: boolean;
                 repair_scope?: 'unresolved_claims_only' | 'all_claim_audit' | 'support_audit'; synthesis_only?: boolean };

export function digest(value: unknown): string {
  function canonical(v: any): string {
    if (Array.isArray(v)) return '[' + v.map(canonical).join(',') + ']';
    if (v && typeof v === 'object') return '{' + Object.keys(v).sort().map(k => JSON.stringify(k) + ':' + canonical(v[k])).join(',') + '}';
    return JSON.stringify(v);
  }
  return createHash('sha256').update(canonical(value)).digest('hex');
}
function save(path: string, value: unknown) {
  mkdirSync(dirname(path), { recursive: true, mode: 0o700 });
  const temp = path + '.tmp-' + randomUUID();
  writeFileSync(temp, JSON.stringify(value, null, 2) + '\n', { mode: 0o600 });
  renameSync(temp, path);
}
function privateFile(path: string): string {
  const absolute = resolve(path);
  if (lstatSync(absolute).isSymbolicLink() || !lstatSync(absolute).isFile()
      || !realpathSync(absolute).startsWith(realpathSync(join(ROOT, '.local')) + sep)) throw new Error('无效的私有工件路径');
  return absolute;
}
function read(path: string) { return JSON.parse(readFileSync(privateFile(path), 'utf8')); }
function jobDir(id: string): string {
  if (!/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/.test(id)) throw new Error('无效任务ID');
  return join(JOBS, id);
}
export function loadJob(id: string) { return read(join(jobDir(id), 'job.json')); }
export function lines(stdout: string): any[] {
  return stdout.split('\n').flatMap(line => { try { const v = JSON.parse(line); return v && typeof v === 'object' && !Array.isArray(v) ? [v] : []; } catch { return []; } });
}
export const execute: Executor = (args, input) => new Promise((accept, reject) => {
  const child = spawn(process.execPath, [join(ROOT, 'scripts/project.mjs'), 'python', ...args],
    { cwd: ROOT, env: process.env, stdio: ['pipe', 'pipe', 'pipe'] });
  let stdout = '', stderr = '';
  child.stdout.setEncoding('utf8'); child.stderr.setEncoding('utf8');
  child.stdout.on('data', d => { stdout += d; }); child.stderr.on('data', d => { stderr += d; });
  child.on('error', reject); child.on('close', code => accept({ code: code ?? 2, stdout, stderr }));
  child.stdin.end(input === undefined ? '' : JSON.stringify(input));
});
async function support(operation: string, values: any, exec: Executor) {
  const result = await exec([join(HERE, 'agent-support.py')], { operation, ...values });
  if (result.code) throw new Error('来源检查或交付校验未通过：' + result.stderr.trim().split('\n').at(-1));
  const data = lines(result.stdout).at(-1);
  if (!data) throw new Error('缺少场景校验结果');
  return data;
}
export function costOf(result: Result): { summaries: any[]; cost: number; complete: boolean } {
  let summaries = lines(result.stdout).filter(v => typeof v.output_dir === 'string');
  if (!summaries.length) summaries = lines(result.stdout).filter(v =>
    v.scope === 'deterministic reuse of previously source-checked artifacts'
    && v.model_requests === 0 && v.budget_accounted_usd === 0
    && v.receipt?.reviewed_field_count === 0 && v.receipt?.retained_field_count > 0);
  const complete = summaries.length > 0 && summaries.every(s => typeof s.budget_accounted_usd === 'number'
    && Number.isFinite(s.budget_accounted_usd) && s.budget_accounted_usd >= 0);
  return { summaries, complete, cost: summaries.reduce((a, s) => a +
    (typeof s.budget_accounted_usd === 'number' && Number.isFinite(s.budget_accounted_usd)
      && s.budget_accounted_usd >= 0 ? s.budget_accounted_usd : 0), 0) };
}
function logResult(directory: string, stage: string, result: Result) {
  for (const key of ['stdout', 'stderr'] as const) writeFileSync(join(directory, stage + '-' + key + '.txt'), result[key], { mode: 0o600 });
}
function indexMetadata(result: any) {
  return { automatic_dependency_graph_sha256: result.automatic_dependency_graph_sha256,
    automatic_dependency_policy: result.automatic_dependency_policy, index_model_requests: result.index_model_requests };
}
function safeOptions(options: Options) {
  const question = options.question ?? DEFAULT_QUESTION;
  const budget = options.budget_usd ?? 100;
  if (typeof question !== 'string' || !question.trim() || question.length > 4000 || !Number.isFinite(budget) || budget <= 0 || budget > 100) throw new Error('研究问题或预算无效');
  for (const k of ['call_model', 'model_review', 'force_refresh', 'repair_only', 'synthesis_only'] as const) if (options[k] !== undefined && typeof options[k] !== 'boolean') throw new Error('运行选项必须为布尔值');
  const rounds = options.repair_rounds ?? (options.repair_only ? 1 : 2);
  if (!Number.isInteger(rounds) || rounds < 0 || rounds > 2 || (options.repair_only && !options.parent_job)) throw new Error('修复轮次须为0–2，续修需要原任务');
  if (options.repair_only && (rounds === 0 || options.model_review === false)) throw new Error('续修需要1–2轮自动语义复核');
  if (options.synthesis_only && !options.repair_only) throw new Error('只综合需要已有稿');
  if (options.repair_scope !== undefined && !['unresolved_claims_only', 'all_claim_audit', 'support_audit'].includes(options.repair_scope)) throw new Error('无效修复范围');
  if (options.manifest && (options.reading_entry_policy || options.claim_entry_policy || options.incremental_entry_policy)) throw new Error('入口策略与旧Motif不能混用');
  if (options.claim_terminal_policy && (options.manifest || options.reading_entry_policy || options.claim_entry_policy || options.incremental_entry_policy)) throw new Error('末尾策略与旧策略组合尚未认证');
  return { repair_rounds: rounds, repair_only: options.repair_only === true,
    repair_scope: options.repair_scope ?? (options.repair_only ? 'unresolved_claims_only' : 'support_audit'),
    synthesis_only: options.synthesis_only === true,
    papers_dir: resolve(options.papers_dir ?? join(ROOT, 'testpdf')), question: question.trim(),
    budget_usd: budget, call_model: options.call_model === true, model_review: options.model_review !== false,
    parent_job: options.parent_job, force_refresh: options.force_refresh === true,
    reading_entry_policy: options.reading_entry_policy ? privateFile(options.reading_entry_policy) : undefined,
    claim_entry_policy: options.claim_entry_policy ? privateFile(options.claim_entry_policy) : undefined,
    incremental_entry_policy: options.incremental_entry_policy ? privateFile(options.incremental_entry_policy) : undefined,
    claim_terminal_policy: options.claim_terminal_policy ? privateFile(options.claim_terminal_policy) : undefined,
    manifest: options.manifest ? privateFile(options.manifest) : undefined };
}

export async function runWorkflow(raw: Options, exec: Executor = execute, onJob?: (job: any) => void) {
  const options = safeOptions(raw);
  const parent = options.parent_job ? loadJob(options.parent_job) : null;
  const frame = await support('capture', { directory: options.papers_dir, question: options.question }, exec);
  const id = randomUUID(), directory = jobDir(id);
  mkdirSync(directory, { recursive: true, mode: 0o700 });
  const job: any = { schema_version: 1, id, created_at: new Date().toISOString(), status: 'preparing',
    options, frame, parent_job: parent?.id ?? null, stages: [], accounted_usd: 0, cost_complete: true,
    model_requests: 0, verified_skips: 0, quality: 'processing', delivery_policy: 'automatic_v1',
    entry_verified_batches: 0,
    terminal_verified_batches: 0,
    human_review_required: false, user_pdf_writes: false, workflow_decisions: [] };
  function decide(action: string, reason: string, facts: any = {}) {
    job.workflow_decisions.push({ kind: 'workflow_decision', actor: 'scene_program',
      time: new Date().toISOString(), action, reason, facts, learned_motif: false });
  }
  function persist() { job.updated_at = new Date().toISOString(); save(join(directory, 'job.json'), job); onJob?.(job); }
  persist();
  let embedding: ReturnType<typeof createServer> | undefined;
  let embeddingURL = '', embeddingRequests = 0;
  try {
    // Same-input reuse is a simple result cache; it never certifies the draft.
    decide('check_result_cache', options.force_refresh ? 'explicit_refresh' : 'revalidate_matching_source_and_configuration',
      { enabled: options.call_model && !options.force_refresh && !options.repair_only });
    const candidates = parent ? [parent] : readdirSync(JOBS).filter(n => n !== id).flatMap(n => {
      try { return [loadJob(n)]; } catch { return []; }
    }).sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
    if (options.call_model && !options.force_refresh && !options.repair_only) for (const old of candidates) {
      if (!['delivered', 'delivered_with_gaps', 'needs_review', 'approved', 'cached'].includes(old.status) || digest(old.frame) !== digest(frame)
          || old.options.model_review !== options.model_review || (old.options.repair_rounds ?? 0) !== options.repair_rounds) continue;
      try {
        await support('validate', { evidence: join(jobDir(old.id), 'evidence.json'), snapshot: join(jobDir(old.id), 'source-snapshot.json'),
          ...(old.quality === 'human_source_checked' ? { dependencies: join(jobDir(old.id), 'dependencies.json') } : {}) }, exec);
        for (const name of ['evidence.json', 'source-snapshot.json', 'review-cards.json', 'research-notes.md',
          'model-review.json', 'source-checked-evidence.json', 'source-check.json', 'dependencies.json']) {
          if (existsSync(join(jobDir(old.id), name))) writeFileSync(join(directory, name), readFileSync(privateFile(join(jobDir(old.id), name))), { mode: 0o600 });
        }
        Object.assign(job, { status: 'cached', quality: old.quality, cached_from: old.id, evidence_sha256: old.evidence_sha256,
          gap_count: old.gap_count, numeric_gap_count: old.numeric_gap_count, claim_count: old.claim_count,
          cache_kind: 'exact_source_revalidated_result; not learned RSI', source_run: old.source_run });
        Object.assign(job, indexMetadata(await support('index_automatic', { job: directory }, exec)));
        decide('reuse_result', 'matching_task_and_configuration_passed_current_source_replay', { cached_from: old.id });
        persist(); return job;
      } catch (error) { job.cache_rejected = true;
        decide('reject_result_cache', 'current_source_or_artifact_validation_failed', { cached_from: old.id, error: String(error) });
        persist(); }
    }
    if (options.manifest) {
      embedding = createServer((_req, res) => { embeddingRequests++; res.writeHead(503); res.end('Closed structural execution only; no semantic embeddings.'); });
      await new Promise<void>(accept => embedding!.listen(0, '127.0.0.1', accept));
      embeddingURL = 'http://127.0.0.1:' + (embedding.address() as any).port + '/v1/embeddings';
      job.manifest_sha256 = digest(read(options.manifest)); persist();
    }
    const motifArgs = options.manifest ? ['--mode', 'execute', '--manifest', options.manifest,
      '--embedding-endpoint', embeddingURL, '--embedding-model', 'disabled-closed-source-only'] : [];
    function account(stage: string, result: Result) {
      const usage = costOf(result);
      job.stages.push({ stage, exit_code: result.code, ...usage });
      job.cost_complete &&= usage.complete;
      job.accounted_usd += usage.cost;
      job.model_requests += usage.summaries.reduce((a, s) => a + (s.upstream_requests ?? 0), 0);
      job.verified_skips += usage.summaries.reduce((a, s) => a + (s.model_requests_skipped_verified ?? 0), 0);
      job.entry_verified_batches += usage.summaries.reduce((a, s) => a + (s.entry_model_requests_bypassed_verified ?? 0), 0);
      job.terminal_verified_batches += usage.summaries.reduce((a, s) => a + (s.terminal_model_requests_bypassed_verified ?? 0), 0);
      persist();
      if (!usage.complete) throw new Error('本阶段缺少费用记录，已停止后续模型调用');
      if (job.accounted_usd > options.budget_usd + 1e-10) throw new Error('费用记录超过总预算，已停止');
      return usage.summaries.at(-1);
    }
    const automaticIncremental = !!parent && existsSync(join(jobDir(parent.id), 'automatic-dependencies.json'));
    const incremental = automaticIncremental || (parent?.quality === 'human_source_checked' && existsSync(join(jobDir(parent.id), 'dependencies.json')));
    decide('choose_reading_route', options.repair_only ? 'repair_prior_result' : incremental ? 'parent_has_dependency_graph' : 'full_reading',
      { parent_job: parent?.id ?? null, automatic_incremental: automaticIncremental, force_refresh: options.force_refresh });
    if (parent && !incremental) job.update_strategy = 'source_revalidated_cache_or_full_automatic_run';
    let args = incremental ? [join(HERE, 'run-incremental.py'), '--dependencies', join(jobDir(parent.id),
      automaticIncremental ? 'automatic-dependencies.json' : 'dependencies.json')]
      : [join(HERE, 'run-pdf.py'), '--rate-retries', '0'];
    args.push('--papers-dir', options.papers_dir, '--question', options.question, '--budget-usd', String(options.budget_usd), ...motifArgs);
    if (options.reading_entry_policy) {
      if (incremental || options.repair_only) throw new Error('阅读入口策略只用于普通首次阅读，尚未认证增量路径');
      args.push('--entry-policy', options.reading_entry_policy);
    }
    if (options.incremental_entry_policy) {
      if (!incremental || options.repair_only) throw new Error('增量入口策略只用于有依赖图的增量阅读');
      args.push('--entry-policy', options.incremental_entry_policy);
    }
    if (options.manifest && !incremental) args.push('--auto-motif-task');
    if (options.call_model) args.push('--call-model');
    job.status = options.call_model ? (options.repair_only ? 'preparing' : incremental ? 'updating' : 'reading') : 'preview'; persist();
    let evidencePath: string, snapshotPath: string, reviewInput: string;
    if (options.repair_only) {
      if (!['delivered', 'delivered_with_gaps', 'needs_review', 'cached', 'approved', 'superseded'].includes(parent.status)) throw new Error('原任务没有完整结果');
      for (const key of ['task_sha256', 'parser_sha256', 'contract_sha256']) {
        if (!parent.frame[key] || parent.frame[key] !== frame[key]) throw new Error('来源或处理契约变化，需要重新运行');
      }
      evidencePath = join(jobDir(parent.id), 'evidence.json');
      snapshotPath = join(jobDir(parent.id), 'source-snapshot.json');
      reviewInput = '';
      Object.assign(job, await support('package', { job: directory, evidence_path: evidencePath, snapshot_path: snapshotPath,
        ...(existsSync(join(jobDir(parent.id), 'model-review.json')) ? { review_path: join(jobDir(parent.id), 'model-review.json') } : {}) }, exec));
      job.source_run = parent.source_run;
      job.resume_scope = 'new semantic repair of frozen prior result; original costs remain in parent';
      persist();
      if (!options.call_model) {
        const plan = await support(options.synthesis_only ? 'synthesis_plan' : 'repair_plan', { job: directory,
          ...(!options.synthesis_only ? { round_number: 1, scope: options.repair_scope, parent_job: jobDir(parent.id) } : {}) }, exec);
        job.repair_preview = { target_count: plan.claim_ids.length, scope: plan.scope };
        if (!plan.claim_ids.length && !options.synthesis_only) { job.status = 'preview'; job.repair_stop_reason = 'no_unresolved_claims'; persist(); return job; }
        const preview = await exec([join(HERE, 'repair-pdf.py'), '--run', plan.input_directory,
          '--budget-usd', String(options.budget_usd)]);
        logResult(directory, 'repair-preview', preview);
        job.status = preview.code ? 'error' : 'preview';
        if (preview.code) job.error = '修复配置预览失败，尚未调用模型';
        job.repair_preview = { target_count: plan.claim_ids.length, scope: plan.scope };
        persist(); return job;
      }
    } else {
      const first = await exec(args); logResult(directory, 'reading', first);
      if (!options.call_model) { job.status = first.code ? 'error' : 'preview'; persist(); return job; }
      const initial = account('reading', first);
      if (first.code) throw new Error('阅读或更新未完成；已保留失败费用和日志');
      job.source_run = initial.output_dir;
      reviewInput = initial.output_dir;
      if (incremental) {
        const out = lines(first.stdout).filter(v => v.incremental_directory).at(-1);
        if (!initial.output_dir && out) {
          const stored = read(join(out.incremental_directory, 'outcome.json'));
          if (digest(stored) !== digest(initial)) throw new Error('离线复用记录不一致');
          out.receipt = stored.receipt;
          job.source_run = out.incremental_directory;
        }
        if (!out?.receipt) throw new Error('缺少经核验的增量交付收据');
        evidencePath = join(out.incremental_directory, 'incremental-evidence.json');
        snapshotPath = join(out.incremental_directory, 'input-snapshot.json');
        job.incremental = { retained: out.receipt.retained_field_count, regenerated: out.receipt.reviewed_field_count };
        job.update_strategy = automaticIncremental ? 'automatic_source_bound_changed_fields; scientifically_unverified' : 'legacy_source_checked_incremental';
        // Review the validated merged artifact. Keep its actual native event source, not a fabricated preview call.
        reviewInput = join(directory, 'review-input'); mkdirSync(reviewInput, { mode: 0o700 });
        for (const [name, path] of [['evidence.json', evidencePath], ['pdf-input-snapshot.json', snapshotPath]]) {
          writeFileSync(join(reviewInput, name), readFileSync(privateFile(path)), { mode: 0o600 });
        }
        // Empty offline history is explicit; never synthesize a native tool event.
        writeFileSync(join(reviewInput, 'agent-events.jsonl'), initial.output_dir
          ? readFileSync(privateFile(join(initial.output_dir, 'agent-events.jsonl'))) : '', { mode: 0o600 });
        save(join(reviewInput, 'input-provenance.json'), { kind: initial.output_dir
          ? 'validated_incremental_receipt' : 'offline_source_checked_publication',
          native_run: initial.output_dir ?? null, receipt: out.receipt });
      } else {
        const delivery = lines(first.stdout).find(v => v.pdf_delivery)?.pdf_delivery;
        if (!delivery || delivery.status === 'missing_preview') throw new Error('缺少工具确认的阅读交付');
        evidencePath = join(initial.output_dir, 'evidence.json'); snapshotPath = join(initial.output_dir, 'pdf-input-snapshot.json');
      }
      Object.assign(job, await support('package', { job: directory, evidence_path: evidencePath, snapshot_path: snapshotPath }, exec));
      persist();
    }
    if (options.model_review && !options.repair_only && !options.repair_rounds) {
      const remaining = options.budget_usd - job.accounted_usd;
      if (remaining < 0.002) throw new Error('剩余预算不足，已保留待审阅草稿');
      job.status = 'reviewing'; persist();
      const reviewed = await exec([join(HERE, 'review-pdf.py'), '--run', reviewInput, '--budget-usd', String(remaining), '--call-model']);
      logResult(directory, 'review', reviewed); account('review', reviewed);
      const reviewResult = lines(reviewed.stdout).find(v => v.claim_review);
      if (reviewed.code || !reviewResult) throw new Error('自动审阅未完成，原始草稿已保留');
      const reviewDir = reviewResult.claim_review;
      Object.assign(job, await support('package', { job: directory, evidence_path: join(reviewDir, 'revised-evidence.json'),
        snapshot_path: snapshotPath, review_path: join(reviewDir, 'claim-review.json') }, exec));
      job.model_review_directory = reviewDir;
    }
    if (options.model_review && options.repair_rounds && !options.synthesis_only) {
      job.repair_rounds = [];
      for (let round = 1; round <= options.repair_rounds; round++) {
        const plan = await support('repair_plan', { job: directory, round_number: round,
          scope: round > 1 ? 'unresolved_claims_only' : options.repair_scope, ...(options.repair_only ? { parent_job: jobDir(parent.id) } : {}),
          ...(incremental && !options.repair_only && Array.isArray(job.incremental_claim_ids)
            ? { target_claim_ids: job.incremental_claim_ids } : {}) }, exec);
        if (!plan.claim_ids.length) { job.repair_stop_reason = 'no_unresolved_claims';
          decide('skip_repair', 'no_target_claims', { round, scope: plan.scope }); break; }
        const remaining = options.budget_usd - job.accounted_usd;
        if (remaining < 0.002) { job.repair_stop_reason = 'remaining_budget_insufficient';
          decide('stop_repair', 'remaining_budget_insufficient', { round, remaining_usd: remaining }); break; }
        decide('repair_claims', 'automatic_support_review_or_explicit_gap_targets',
          { round, scope: plan.scope, target_claim_ids: plan.claim_ids, input_sha256: plan.input_sha256 });
        job.status = 'repairing'; job.active_repair_round = round; persist();
        const entryArgs = options.claim_entry_policy && round === 1 && plan.scope === 'claim_support_audit'
          ? ['--entry-policy', options.claim_entry_policy] : [];
        const terminalArgs = options.claim_terminal_policy && round === 1 && plan.scope === 'claim_support_audit'
          ? ['--terminal-policy', options.claim_terminal_policy] : [];
        const result = await exec([join(HERE, 'repair-pdf.py'), '--run', plan.input_directory,
          '--budget-usd', String(remaining), '--call-model', ...entryArgs, ...terminalArgs]);
        logResult(directory, 'repair-' + round, result); account('repair-' + round, result);
        const repaired = lines(result.stdout).find(v => v.claim_repair);
        if (result.code || !repaired?.receipt) {
          job.repair_rounds.push({ round, input_sha256: plan.input_sha256, scope: plan.scope,
            target_count: plan.claim_ids.length, status: 'failed', expense_retained: true });
          job.repair_stop_reason = 'stage_failed';
          job.repair_warning = '补证据阶段未完成，交付上一份来源校验通过的稿件；本次失败费用已计入。';
          decide('retain_prior_draft', 'repair_stage_failed', { round, exit_code: result.code, expense_retained: true });
          break;
        }
        const repairDir = repaired.claim_repair;
        Object.assign(job, await support('package', { job: directory,
          evidence_path: join(repairDir, 'revised-evidence.json'), snapshot_path: snapshotPath,
          review_path: join(repairDir, 'claim-review.json') }, exec));
        job.model_review_directory = repairDir;
        job.repair_rounds.push({ round, input_sha256: plan.input_sha256, scope: plan.scope,
          target_count: plan.claim_ids.length, ...repaired.receipt, receipt_origin: repaired.receipt_origin ?? 'native_tool_submission', output_directory: repairDir });
        job.repair_stop_reason = repaired.receipt.unresolved_claim_ids.length ? 'round_limit_reached' : 'no_unresolved_claims';
        persist();
        if (!repaired.receipt.unresolved_claim_ids.length) break;
      }
    }
    if (options.synthesis_only || (options.model_review && job.incremental_synthesis_requires_review)
        || job.repair_rounds?.some((r: any) => r.scope !== 'all_claim_audit' && r.changed_claim_count > 0)) {
      const remaining = options.budget_usd - job.accounted_usd;
      if (remaining < 0.002) throw new Error('剩余预算不足以重新综合，已保留字段结果');
      const plan = await support('synthesis_plan', { job: directory }, exec);
      decide('synthesize', 'current_fields_require_new_question_level_synthesis', { input_sha256: plan.input_sha256 });
      job.status = 'reviewing'; persist();
      const result = await exec([join(HERE, 'repair-pdf.py'), '--run', plan.input_directory,
        '--budget-usd', String(remaining), '--call-model']);
      logResult(directory, 'synthesis', result); account('synthesis', result);
      const completed = lines(result.stdout).find(v => v.claim_repair);
      if (result.code || !completed?.receipt) throw new Error('全局综合未完成，已保留字段结果及费用');
      Object.assign(job, await support('package', { job: directory,
        evidence_path: join(completed.claim_repair, 'revised-evidence.json'), snapshot_path: snapshotPath,
        review_path: join(completed.claim_repair, 'claim-review.json') }, exec));
      job.synthesis_result = { output_directory: completed.claim_repair, receipt_origin: completed.receipt_origin ?? 'native_tool_submission',
        retained_field_count: job.claim_count, input_sha256: plan.input_sha256 };
    }
    if (digest(await support('capture', { directory: options.papers_dir, question: options.question }, exec)) !== digest(frame)) throw new Error('执行中来源或配置变化，交付已失效');
    Object.assign(job, indexMetadata(await support('index_automatic', { job: directory }, exec)));
    job.quality = job.research_quality;
    job.status = job.gap_count || job.numeric_gap_count || job.repair_warning ? 'delivered_with_gaps' : 'delivered';
    decide('deliver', 'current_source_and_configuration_revalidated',
      { status: job.status, gap_count: job.gap_count, numeric_gap_count: job.numeric_gap_count, scientific_truth_certified: false });
    persist(); return job;
  } catch (error) {
    decide('stop_with_error', 'workflow_or_accounting_check_failed', { error: String(error), expense_retained: true });
    job.status = 'error'; job.error = String(error); persist(); return job;
  } finally {
    if (embedding) await new Promise<void>(accept => embedding!.close(() => accept()));
    job.embedding_requests = embeddingRequests;
    try { job.decision_log = writeDecisionLog(directory, job); }
    catch (error) { job.decision_log = { complete: false, error: String(error) }; }
    persist();
  }
}

export async function approveJob(id: string, evidence_sha256: string, claim_ids: string[], synthesis_reviewed: boolean, exec: Executor = execute) {
  const job = loadJob(id);
  if (!['delivered', 'delivered_with_gaps', 'needs_review', 'cached'].includes(job.status)) throw new Error('任务尚未交付可审阅稿');
  const current = await support('capture', { directory: job.options.papers_dir, question: job.options.question }, exec);
  if (digest(current) !== digest(job.frame)) throw new Error('来源或配置变化，先更新任务');
  const approval = await support('approve', { job: jobDir(id), expected_sha: evidence_sha256, claim_ids, synthesis_reviewed }, exec);
  Object.assign(job, { status: 'approved', quality: 'human_source_checked', approval, updated_at: new Date().toISOString() });
  save(join(jobDir(id), 'job.json'), job); return job;
}

/** Validate a final typed model proposal without spending another model request. */
export async function recoverJob(id: string, exec: Executor = execute) {
  const old = loadJob(id), original = jobDir(id);
  const failed = old.stages?.filter((s: any) => /^repair-[12]$/.test(s.stage) || s.stage === 'synthesis').at(-1);
  const synthesis = failed?.stage === 'synthesis';
  const native = failed?.summaries?.at(-1)?.output_dir;
  if (!old.cost_complete || !native || (!synthesis && (!old.active_repair_round || old.repair_stop_reason !== 'stage_failed'))) {
    throw new Error('没有完整账本与原始修复提案可回收');
  }
  const frame = await support('capture', { directory: old.options.papers_dir, question: old.options.question }, exec);
  for (const key of ['task_sha256', 'parser_sha256', 'contract_sha256']) {
    if (!old.frame[key] || old.frame[key] !== frame[key]) throw new Error('来源或处理契约变化，拒绝回收旧提案');
  }
  const recovered = await exec([join(HERE, 'recover-repair.py'), '--run', join(original,
    synthesis ? 'synthesis-input' : 'repair-input-' + old.active_repair_round), '--model-run', native,
    ...(synthesis ? ['--native-receipt'] : [])]);
  const result = lines(recovered.stdout).find(v => v.claim_repair && v.receipt_origin ===
    (synthesis ? 'native_tool_submission_recaptured' : 'validated_model_final_json_recovery'));
  if (recovered.code || !result || result.model_call_enabled !== false || result.model_requests !== 0 || result.budget_accounted_usd !== 0) {
    throw new Error('没有通过来源重放的完整结构化提案；保留旧结果');
  }
  const freshId = randomUUID(), directory = jobDir(freshId);
  mkdirSync(directory, { recursive: true, mode: 0o700 });
  const job: any = { schema_version: 1, id: freshId, created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(), options: old.options, frame, parent_job: id,
    inherited_expense_usd: old.accounted_usd, inherited_model_requests: old.model_requests,
    stages: [{ stage: 'offline_typed_proposal_validation', complete: true, cost: 0 }],
    model_requests: 0, accounted_usd: 0, cost_complete: true, verified_skips: 0,
    resume_origin: synthesis ? 'actual native tool receipt recaptured; zero new model requests' : 'native model final JSON, validated by Runtime; not a native model tool submission',
    human_review_required: false, repair_stop_reason: 'offline_proposal_recovered',
    repair_rounds: [{ round: old.active_repair_round, ...result.receipt, receipt_origin: result.receipt_origin }],
    model_review_directory: result.claim_repair };
  Object.assign(job, await support('package', { job: directory,
    evidence_path: join(result.claim_repair, 'revised-evidence.json'),
    snapshot_path: join(original, 'source-snapshot.json'), review_path: join(result.claim_repair, 'claim-review.json') }, exec));
  if (digest(frame) !== digest(await support('capture', { directory: old.options.papers_dir, question: old.options.question }, exec))) {
    throw new Error('回收时来源或配置变化');
  }
  job.quality = job.research_quality;
  job.status = job.gap_count || job.numeric_gap_count ? 'delivered_with_gaps' : 'delivered';
  save(join(directory, 'job.json'), job); return job;
}

/** Re-publish a legacy result under the delivery policy, preserving its historical run. */
export async function redeliverJob(id: string, exec: Executor = execute) {
  const old = loadJob(id), original = jobDir(id);
  if (!['needs_review', 'delivered', 'delivered_with_gaps', 'cached', 'approved'].includes(old.status)) throw new Error('旧任务没有完整交付');
  const frame = await support('capture', { directory: old.options.papers_dir, question: old.options.question }, exec);
  for (const key of ['task_sha256', 'parser_sha256', 'contract_sha256']) {
    if (!old.frame[key] || old.frame[key] !== frame[key]) throw new Error('来源、问题或处理契约变化，需要重新运行');
  }
  await support('validate', { evidence: join(original, 'evidence.json'), snapshot: join(original, 'source-snapshot.json') }, exec);
  const freshId = randomUUID(), directory = jobDir(freshId);
  mkdirSync(directory, { recursive: true, mode: 0o700 });
  const job: any = { schema_version: 1, id: freshId, created_at: new Date().toISOString(),
    options: old.options, frame, parent_job: id, cached_from: id, source_run: old.source_run,
    cache_kind: 'policy_redelivery_after_source_replay; not learned RSI',
    stages: [], model_requests: 0, accounted_usd: 0, cost_complete: true, verified_skips: 0,
    embedding_requests: 0, user_pdf_writes: false, original_quality: old.quality,
    redelivery_scope: 'Delivery policy only; no new semantic review or human certification.' };
  try {
    // Package from current evidence only; an old model audit may predate subsequent edits.
    Object.assign(job, await support('package', { job: directory, evidence_path: join(original, 'evidence.json'),
      snapshot_path: join(original, 'source-snapshot.json') }, exec));
    if (digest(await support('capture', { directory: old.options.papers_dir, question: old.options.question }, exec)) !== digest(frame)) throw new Error('执行中来源或配置变化');
    job.quality = job.research_quality;
    job.status = job.gap_count || job.numeric_gap_count || job.repair_warning ? 'delivered_with_gaps' : 'delivered';
  } catch (error) { job.status = 'error'; job.error = String(error); }
  job.updated_at = new Date().toISOString(); save(join(directory, 'job.json'), job); return job;
}

export async function reviseJob(id: string, data: any, exec: Executor = execute) {
  const job = loadJob(id);
  if (!['delivered', 'delivered_with_gaps', 'needs_review', 'cached', 'approved'].includes(job.status)) throw new Error('任务尚未交付可修订稿');
  const result = await support('revise', { job: jobDir(id), expected_sha: data.evidence_sha256,
    statements: data.statements, synthesis: data.synthesis }, exec);
  Object.assign(job, result, { status: result.gap_count || result.numeric_gap_count ? 'delivered_with_gaps' : 'delivered',
    quality: result.research_quality, updated_at: new Date().toISOString() });
  delete job.approval;
  save(join(jobDir(id), 'job.json'), job); return job;
}

export async function serve(port = 8765) {
  const token = randomUUID(); let busy = false;
  const server = createServer(async (req, res) => {
    const host = `127.0.0.1:${(server.address() as any)?.port}`;
    function send(code: number, value: unknown) { res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' }); res.end(JSON.stringify(value)); }
    try {
      if (req.headers.host !== host) return send(403, { error: '只接受本机地址' });
      const path = new URL(req.url!, 'http://' + host).pathname;
      if (req.method === 'GET' && path === '/') {
        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store',
          'Content-Security-Policy': "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; object-src 'none'; frame-ancestors 'none'" });
        return res.end(readFileSync(join(HERE, 'agent-ui.html'), 'utf8').replace('__SESSION_TOKEN__', token));
      }
      if (req.method === 'GET' && path === '/api/jobs') {
        mkdirSync(JOBS, { recursive: true, mode: 0o700 });
        return send(200, readdirSync(JOBS).flatMap(id => { try { return [loadJob(id)]; } catch { return []; } }).sort((a, b) => b.created_at.localeCompare(a.created_at)));
      }
      const match = path.match(/^\/api\/jobs\/([a-f0-9-]+)(?:\/(cards|notes|approve|revise))?$/);
      if (match && req.method === 'GET') {
        const job = loadJob(match[1]);
        if (match[2] === 'cards') return send(200, read(join(jobDir(job.id), 'review-cards.json')));
        if (match[2] === 'notes') {
          res.writeHead(200, { 'Content-Type': 'text/markdown; charset=utf-8', 'Content-Disposition': 'attachment; filename="research-notes.md"' });
          return res.end(readFileSync(privateFile(join(jobDir(job.id), 'research-notes.md'))));
        }
        if (!match[2]) return send(200, job);
      }
      if (req.method !== 'POST') return send(404, { error: '未找到' });
      const supplied = req.headers['x-agent-session'];
      if (req.headers.origin !== 'http://' + host || typeof supplied !== 'string'
          || supplied.length !== token.length || !timingSafeEqual(Buffer.from(supplied), Buffer.from(token))) return send(403, { error: '需要本机页面的操作许可' });
      if (busy) return send(409, { error: '已有任务执行中，请等待完成' });
      let body = ''; for await (const chunk of req) { body += chunk; if (body.length > 24000) throw new Error('请求过大'); }
      const data = JSON.parse(body);
      if (data.reading_entry_policy || data.claim_entry_policy || data.incremental_entry_policy || data.claim_terminal_policy) throw new Error('策略只允许本机CLI配置');
      // Another request may have started while this body was streaming.
      if (busy) return send(409, { error: '已有任务执行中，请等待完成' });
      if (match?.[2] === 'approve' || match?.[2] === 'revise') {
        busy = true;
        try { return send(200, match[2] === 'approve'
          ? await approveJob(match[1], data.evidence_sha256, data.claim_ids, data.synthesis_reviewed)
          : await reviseJob(match[1], data)); } finally { busy = false; }
      }
      if (path !== '/api/run') return send(404, { error: '未找到' });
      busy = true;
      let sent = false;
      runWorkflow(data, execute, job => { if (!sent) { send(202, { job_id: job.id }); sent = true; } })
        .catch(error => { if (!sent) send(400, { error: String(error) }); }).finally(() => { busy = false; });
    } catch (error) { send(400, { error: String(error) }); }
  });
  await new Promise<void>((accept, reject) => { server.once('error', reject); server.listen(port, '127.0.0.1', accept); });
  console.log(JSON.stringify({ url: `http://127.0.0.1:${(server.address() as any).port}`, scope: 'local PDF agent; user PDFs unchanged; model calls require explicit enablement' }));
  return server;
}

async function main() {
  const [command = 'serve', ...argv] = process.argv.slice(2);
  function value(flag: string) { const i = argv.indexOf(flag); return i >= 0 ? argv[i + 1] : undefined; }
  if (command === 'serve') { await serve(Number(value('--port') ?? 8765)); return; }
  if (command === 'status') { console.log(JSON.stringify(loadJob(value('--job')!), null, 2)); return; }
  if (command === 'decisions') {
    const id = value('--job')!, job = loadJob(id);
    console.log(JSON.stringify(writeDecisionLog(jobDir(id), job), null, 2)); return;
  }
  if (command === 'index') {
    const id = value('--job')!, job = loadJob(id);
    const result = await support('index_automatic', { job: jobDir(id) }, execute);
    Object.assign(job, indexMetadata(result)); save(join(jobDir(id), 'job.json'), job);
    console.log(JSON.stringify(result, null, 2)); return;
  }
  if (command === 'recover') {
    const result = await recoverJob(value('--job')!); console.log(JSON.stringify(result, null, 2)); return;
  }
  if (command === 'deliver') {
    const result = await redeliverJob(value('--job')!);
    console.log(JSON.stringify(result, null, 2)); if (result.status === 'error') process.exitCode = 2; return;
  }
  if (!['run', 'update', 'repair'].includes(command)) throw new Error('使用 serve、run、update、repair、index、recover、deliver、decisions 或 status');
  const parent = ['update', 'repair'].includes(command) ? loadJob(value('--job')!) : null;
  const result = await runWorkflow({ papers_dir: value('--papers-dir') ?? parent?.options.papers_dir,
    question: value('--question') ?? parent?.options.question, budget_usd: Number(value('--budget-usd') ?? 100),
    call_model: argv.includes('--call-model'), model_review: !argv.includes('--no-model-review'),
    repair_only: command === 'repair', repair_rounds: Number(value('--repair-rounds') ?? (command === 'repair' ? 1 : 2)),
    repair_scope: argv.includes('--audit-support') ? 'support_audit' : argv.includes('--audit-all') ? 'all_claim_audit' : undefined, synthesis_only: argv.includes('--synthesis-only'),
    parent_job: parent?.id, manifest: value('--manifest'), force_refresh: argv.includes('--refresh'),
    reading_entry_policy: value('--reading-entry-policy'), claim_entry_policy: value('--claim-entry-policy'),
    incremental_entry_policy: value('--incremental-entry-policy'), claim_terminal_policy: value('--claim-terminal-policy') });
  console.log(JSON.stringify(result, null, 2));
  if (result.status === 'error') process.exitCode = 2;
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main().catch(error => { console.error(String(error)); process.exitCode = 2; });
