/** Account-local paired turns over the existing DSH task runner. No new Agent loop. */
import { randomUUID, createHash } from 'node:crypto';
import { existsSync, readFileSync, writeFileSync, renameSync, mkdirSync, appendFileSync } from 'node:fs';
import { join } from 'node:path';
import { hasReportPlaceholders, REPORT_ANSWER_BINDING } from './harless_report_answer.ts';

const hash = (value: unknown) => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const terminal = new Set(['completed', 'failed', 'cancelled']);
const lanes = ['baseline', 'motif'] as const;
type LaneName = typeof lanes[number];
type Lane = { session_id: string; task_id?: string; status: string; answer?: string; failure?: string;
  failure_stage?: 'preparation' | 'execution';
  answer_display?: string; answer_binding?: any; progress?: any; activity?: any[]; messages?: any[]; trace?: any[];
  started_at?: string; finished_at?: string; duration_ms?: number; feedback?: 'up'|'down'|null;
  mode?:string;library_sha256?:string;source_pending?:boolean;
  delivery_reconciled?: boolean;
  attempt: number; output_sha256?: string; stats?: any; fallback_reason?: string; artifacts?: any[] };
type Turn = { id: string; session_id: string; request_id: string; fingerprint: string; scene: string;
  options: any; model: any; input_sha256: string; created_at: string; status: string;
  reasoning_effort?: 'off' | 'high';
  lanes: Record<LaneName, Lane>; scores: Partial<Record<LaneName, number>>; score_revision: number; input: any;
  presentation?: 'paired' | 'single'; prior_artifacts?: Partial<Record<LaneName,any[]>>; prior_sources?: any[];
  published?: boolean; cancellation_requested?: boolean; source_files?:Record<string,any>; prior_context?: Partial<Record<LaneName,string>> };
const turnLanes = (t: Pick<Turn,'presentation'>): readonly LaneName[] => t.presentation === 'single' ? ['baseline'] : lanes;
const admissionMessages: Record<string, string> = {
  data_requires_csv_or_tsv: '此前任务未能读取附件，请重新发送；如果仍有问题，请反馈给管理员。',
  data_input_format_unsupported: '此前任务未能读取附件，请重新发送；如果仍有问题，请反馈给管理员。',
  data_text_requires_utf8: '需求说明文件不是有效的 UTF-8 文本。请将 TXT/MD 另存为 UTF-8 编码后重新上传。',
  ppt_requires_pdf_or_pptx: '此前任务未能读取附件，请重新发送；如果仍有问题，请反馈给管理员。',
  paper_input_format_unsupported: '此前任务未能读取附件，请重新发送；如果仍有问题，请反馈给管理员。',
  literature_requires_pdf: '此前任务未能读取附件，请重新发送；如果仍有问题，请反馈给管理员。',
  literature_requires_question: '请在输入框说明需要解决的文献问题，然后重新发送。',
  scene_input_limit: '附件超出上传限制。每次最多 8 份，每份不超过 20 MiB；请调整附件后重新发送。',
  duplicate_scene_filename: '附件文件名重复。请为文件使用不同名称后重新上传。',
  paper_requires_safe_flat_filenames: '论文附件名称不符合要求。请使用简短的文字、数字、点、下划线或连字符命名文件，避免路径和开头的点。',
  file_bytes_changed: '附件内容已发生变化。请重新上传当前版本，再发送任务。',
  file_receipt_not_owned: '附件上传记录已失效或不属于当前会话。请在本会话重新上传后发送。',
  scene_not_connected: '当前场景服务暂时不可用，请稍后重试。',
  scene_tools_unavailable: '当前场景服务暂时不可用，请稍后重试。',
  scene_output_unavailable: '当前场景的文件生成功能暂时不可用，请稍后重试。',
};
function admissionFailure(error: any): string | undefined {
  // Only exact, known codes have public wording. Never surface arbitrary
  // exception messages, paths, stack traces, or private backend diagnostics.
  for (const code of [error?.code, error?.message])
    if (typeof code === 'string' && Object.hasOwn(admissionMessages, code)) return admissionMessages[code];
}
export class ComparisonError extends Error {
  code: string; status: number;
  constructor(code: string, message: string, status = 409) { super(message); this.code = code; this.status = status; }
}
export type ComparisonHost = {
  owns(id: string): Promise<void>;
  createLane(parent: string, scene: string, lane: LaneName): Promise<string>;
  prepare(turn: any, lane: LaneName, requestId: string): Promise<{ task_id: string }>;
  submit(taskId: string): Promise<void>;
  inspect(taskId: string, context?: { turn: any; lane: LaneName; recoverMissing?: boolean }): Promise<any>;
  subscribe?(taskId: string, listener: (task: any) => void): () => void;
  cancel(taskId: string): Promise<void>;
  publish(parent: string, turn: any, request?: any): Promise<void>;
  parallel?(turn: any): boolean;
  ready?(turn: any, lane: LaneName): boolean;
};

export function createComparisonService(output: string, principal: string, host: ComparisonHost,
  { pollMs = 400 }: { pollMs?: number } = {}) {
  mkdirSync(output, { recursive: true, mode: 0o700 });
  const path = join(output, 'comparisons.json');
  const state: { version: number; revision?: number; snapshot_epoch?: number; principal: string; threads: Record<string, any>; turns: Turn[] } = existsSync(path)
    ? JSON.parse(readFileSync(path, 'utf8')) : { version: 1, principal, threads: {}, turns: [] };
  if (state.version !== 1 || state.principal !== principal || !Array.isArray(state.turns)) throw Error('comparison_store_scope_mismatch');
  if (!Number.isSafeInteger(state.snapshot_epoch ?? 0) || (state.snapshot_epoch ?? 0) < 0 || state.snapshot_epoch === Number.MAX_SAFE_INTEGER)
    throw Error('comparison_store_epoch_invalid');
  // A crashed process may have emitted revisions newer than its checkpoint.
  // Persist a new generation before exposing any view, so clients can accept
  // recovery even when that generation starts at a lower local revision.
  state.snapshot_epoch = (state.snapshot_epoch ?? 0) + 1;
  const pending: Turn[] = [], inFlight = new Set<string>();
  const subscribers = new Map<string, Set<(value: any) => void>>();
  const reconciledDeliveries = new Set<string>();
  let running = false, disposed = false, admission = Promise.resolve(), feedbackAdmission = Promise.resolve();
  let checkpoint: ReturnType<typeof setTimeout> | undefined;
  const writeState = () => { const tmp = path + '.' + randomUUID() + '.tmp'; writeFileSync(tmp, JSON.stringify(state), { mode: 0o600 }); renameSync(tmp, path); };
  const save = (defer = false) => {
    state.revision = (state.revision ?? 0) + 1;
    // Native deltas still publish immediately. Coalesce only the growing
    // on-disk snapshot; admissions, final results and feedback remain durable.
    if (defer) {
      checkpoint ??= setTimeout(() => {
        checkpoint = undefined;
        try { writeState(); } catch { /* Native task journals remain authoritative; the next durable transition retries and propagates failure. */ }
      }, 250);
      return;
    }
    if (checkpoint) { clearTimeout(checkpoint); checkpoint = undefined; }
    writeState();
  };
  // Reconnect never starts a paid task. A stopped turn needs an explicit retry.
  for (const t of state.turns) if (!terminal.has(t.status)) {
    for (const name of turnLanes(t)) if (!terminal.has(t.lanes[name].status)) Object.assign(t.lanes[name], { status: 'failed', failure: '服务重启中断了这一路，请重试。' });
    t.status = 'failed';
  }
  save();
  const locked = <T>(fn: () => Promise<T>): Promise<T> => {
    const job = admission.then(fn); admission = job.then(() => undefined, () => undefined); return job;
  };
  // Rating writes have their own short critical section. Creating a new
  // execution scope must not delay feedback on an already completed result.
  const feedbackLocked = <T>(fn: () => Promise<T>): Promise<T> => {
    const job = feedbackAdmission.then(fn); feedbackAdmission = job.then(() => undefined, () => undefined); return job;
  };
  const outputHash = (lane: Lane) => hash([lane.answer, lane.artifacts,
    ...(lane.answer_display === undefined ? [] : [{ answer_display: lane.answer_display, answer_binding: lane.answer_binding }])]);
  const view = (t: Turn) => ({ snapshot_epoch: state.snapshot_epoch, snapshot_revision: state.revision ?? 0, presentation: t.presentation ?? 'paired', id: t.id, session_id: t.session_id, scene: t.scene, status: t.status,
    input_sha256: t.input_sha256, created_at: t.created_at, score_revision: t.score_revision, scores: { ...t.scores },
    scoring_available: t.presentation !== 'single' && turnLanes(t).every(name => t.lanes[name].status === 'completed'),
    lanes: Object.fromEntries(turnLanes(t).map(name => {
      const lane = t.lanes[name], artifacts = (lane.artifacts ?? []).filter(row=>
        t.scene!=='research-data-analysis'||row.verification==='data-report-delivery-v1');
      const {delivery_reconciled, ...publicLane} = lane;
      const notStarted = lane.status === 'failed' && !lane.task_id && !lane.answer && !lane.answer_display && !artifacts.length &&
        !lane.activity?.length && ['upstream_requests', 'model_requests', 'tool_calls', 'llm_decisions', 'verified_skips']
          .every(field => !Number(lane.stats?.[field]));
      const delivery_status = artifacts.length ? 'available' : notStarted ? 'not_started' : terminal.has(lane.status) ? 'not_delivered' : 'pending';
      const failure = notStarted && lane.failure === '这一路未完成，请重试；另一侧结果已保留。'
        ? '任务未能启动，请检查附件后重试。' : lane.failure;
      return [name, { ...publicLane, ...(failure === undefined ? {} : {failure}), artifacts, delivery_status,
        delivery_message: delivery_status === 'available' ? '结果文件已保存，可下载到本地。'
          : delivery_status === 'pending' ? '结果文件会在生成并通过交付检查后显示。'
          : delivery_status === 'not_started' ? '本轮尚未开始执行，暂无结果文件。'
          : lane.source_pending ? '本轮没有生成结果文件。你可以继续提问或上传资料。'
          : t.scene === 'research-data-analysis' ? '本轮尚无通过交付校验的报告。模型回复结束不表示报告已成功生成。'
          : '本轮没有可下载的结果文件。' }];
    })) });
  async function get(session: string, id: string) {
    await host.owns(session);
    const t = state.turns.find(t => t.id === id && t.session_id === session);
    if (!t) throw new ComparisonError('comparison_not_found', '找不到这条对照结果。', 404);
    return t;
  }
  function summary(t: Turn) {
    const statuses = turnLanes(t).map(name => t.lanes[name].status);
    t.status = statuses.every(s => s === 'completed') ? 'completed' : statuses.every(s => terminal.has(s))
      ? statuses.includes('failed') ? 'failed' : 'cancelled' : 'running';
  }
  function applyTask(t: Turn, name: LaneName, task: any) {
    const lane = t.lanes[name];
    if (disposed) return;
    Object.assign(lane, { status: t.cancellation_requested ? 'cancelled' : task.status === 'budget_exhausted' ? 'failed' : task.status === 'awaiting_confirmation' ? 'queued' : task.status,
      answer: task.answer ?? lane.answer ?? '', stats: task.stats, fallback_reason: task.fallback_reason ?? null,
      answer_display: task.answer_display, answer_binding: task.answer_binding, progress: task.progress, activity: task.activity,
      messages:task.messages,trace:task.trace,started_at:task.started_at,finished_at:task.finished_at,duration_ms:task.duration_ms,
      mode:task.mode,library_sha256:task.library_sha256,source_pending:task.source_pending === true,
      artifacts: task.deliveries ?? lane.artifacts ?? [], failure: task.status === 'budget_exhausted'
        ? (task.deliveries?.length ? '已完成的文件通过交付校验，可下载；后续模型回复达到请求或预算上限，未完成的部分与支出均已保留。' : '这一路达到预算或请求上限，结果与已有支出已保留。')
        : task.status === 'failed' ? '这一路运行失败，请查看状态后重试；已校验的交付文件仍可下载。' : undefined });
    if (terminal.has(lane.status)) {
      lane.output_sha256 = outputHash(lane);
      if (Array.isArray(task.deliveries)) lane.delivery_reconciled = true;
    }
    summary(t); save(!terminal.has(lane.status));
  }
  async function refresh(t: Turn, name: LaneName) {
    const lane = t.lanes[name];
    if (!lane.task_id) return;
    const previous = hash(view(t));
    applyTask(t,name,await host.inspect(lane.task_id, { turn: t, lane: name }));
    if(disposed)return;
    if (hash(view(t)) !== previous) await publish(t);
  }
  async function run(t: Turn) {
    inFlight.add(t.id);
    try {
      const runLane = async (name: LaneName) => {
        const lane = t.lanes[name];
        let unsubscribe: (()=>void)|undefined;
        if (disposed || terminal.has(lane.status)) return;
        try {
          while (host.ready?.(t, name) === false && !disposed && !terminal.has(lane.status)) await new Promise(resolve => setTimeout(resolve, pollMs));
          if (disposed || terminal.has(lane.status)) return;
          if (!lane.task_id) await prepare(t, name);
          if (disposed || terminal.has(lane.status)) return;
          unsubscribe=host.subscribe?.(lane.task_id!,task=>{
            // Native chunk notifications carry the full current task view. A
            // terminal update is reconciled below with verified deliveries.
            if(disposed||terminal.has(task.status)||terminal.has(lane.status))return;
            applyTask(t,name,task);
            for(const subscriber of subscribers.get(t.id)??[])try{subscriber(view(t));}catch{}
          });
          await host.submit(lane.task_id);
          do {
            await refresh(t, name);
            if (terminal.has(lane.status) || disposed) break;
            await new Promise(resolve => setTimeout(resolve, pollMs));
          } while (!disposed);
        } catch (error: any) {
          // Private diagnostic metadata only; never include the request/files in
          // the public result or discard the other lane's successful output.
          appendFileSync(join(output, 'comparison-errors.jsonl'), JSON.stringify({
            id: t.id, lane: name, code: error?.code ?? error?.name ?? 'unknown',
            message: String(error?.message ?? error).slice(0, 1024) }) + '\n', { mode: 0o600 });
          const preparing = !lane.task_id;
          Object.assign(lane, { status: t.cancellation_requested || disposed ? 'cancelled' : 'failed', failure_stage: preparing ? 'preparation' : 'execution',
            failure: preparing ? admissionFailure(error) ?? '任务未能启动，请稍后重试；如果仍有问题，请反馈给管理员。'
              : '这一路未完成，请重试；已生成的结果会保留。' });
        } finally { unsubscribe?.(); }
        summary(t); save(); await publish(t);
      };
      if (host.parallel?.(t) === false) for (const name of turnLanes(t)) await runLane(name);
      else await Promise.all(turnLanes(t).map(runLane));
    } finally { inFlight.delete(t.id); if (!disposed) { summary(t); save(); } }
  }
  async function drain() {
    if (running || disposed) return;
    running = true;
    try { while (pending.length && !disposed) await run(pending.shift()!); }
    finally { running = false; }
  }
  const enqueue = (t: Turn) => { pending.push(t); void drain().catch(() => {}); };
  async function publish(t: Turn) {
    for (const subscriber of subscribers.get(t.id) ?? []) { try { subscriber(view(t)); } catch { /* A disconnected reader cannot interrupt execution. */ } }
    // Persisted results remain readable even when a transient UI event fails.
    try { await host.publish(t.session_id, view(t)); } catch { /* GET recovers the saved state. */ }
  }
  async function prepare(t: Turn, name: LaneName) {
    const lane = t.lanes[name];
    const req = 'compare-' + hash([t.id, name, lane.attempt]).slice(0, 48);
    const result = await host.prepare(t, name, req);
    lane.task_id = result.task_id;
    if (t.cancellation_requested || disposed) {
      lane.status = 'cancelled'; await host.cancel(result.task_id);
    } else Object.assign(lane, { status: 'queued', failure: undefined, failure_stage: undefined });
  }
  return {
    hasSession: (id: string) => Boolean(state.threads[id]),
    busy: (id: string) => state.turns.some(t => t.session_id === id && !terminal.has(t.status)),
    async subscribe(session: string, id: string, listener: (value: any) => void) {
      const t = await get(session, id); const listeners = subscribers.get(id) ?? new Set();
      listeners.add(listener); subscribers.set(id, listeners); listener(view(t));
      return () => { listeners.delete(listener); if (!listeners.size) subscribers.delete(id); };
    },
    snapshot: (session: string, id: string) => { const t = state.turns.find(t => t.session_id === session && t.id === id); return t ? view(t) : undefined; },
    // Only a previously admitted request in this account can resolve a retired
    // upload receipt. These server-minted references never appear in GET views.
    sourceFor: (session:string,requestId:string,receipt:string) =>
      state.turns.find(t=>t.session_id===session&&t.request_id===requestId)?.source_files?.[receipt],
    requestContext: (session:string,requestId:string) => {
      const turn=state.turns.find(t=>t.session_id===session&&t.request_id===requestId);
      return turn ? structuredClone({scene:turn.scene,options:turn.options,model:turn.model,
        reasoning_effort:turn.reasoning_effort??'off',presentation:turn.presentation??'paired'}) : undefined;
    },
    isLane: (id: string) => state.turns.some(t => turnLanes(t).some(name => t.lanes[name].session_id === id)) || Object.values(state.threads).some((thread: any) => Object.values(thread.lanes).includes(id)),
    parentFor: (id: string) => state.turns.find(t => turnLanes(t).some(name => t.lanes[name].session_id === id))?.session_id ?? Object.entries(state.threads).find(([, thread]: any) => Object.values(thread.lanes).includes(id))?.[0] ?? null,
    async admit(session: string, request: any, context: any) { return locked(async () => {
      await host.owns(session);
      if (disposed) throw new ComparisonError('comparison_stopping', '服务正在重启，请稍后再试。');
      const fingerprint = hash([request.content, context.scene, context.options, context.model, context.reasoning_effort ?? 'off']);
      const duplicate = state.turns.find(t => t.session_id === session && t.request_id === request.requestId);
      if (duplicate) {
        // Stored turns from before reasoning selection were all Off. Preserve
        // their idempotent admission without allowing a replay to switch to On.
        const legacyOff = duplicate.reasoning_effort === undefined && (context.reasoning_effort ?? 'off') === 'off'
          && duplicate.fingerprint === hash([request.content, context.scene, context.options, context.model]);
        if (duplicate.fingerprint !== fingerprint && !legacyOff) throw new ComparisonError('request_id_conflict', '同一发送请求不能更改内容。');
        if (duplicate.published === false) {
          await host.publish(session, view(duplicate), request);
          for (const name of turnLanes(duplicate)) duplicate.lanes[name].status = 'queued';
          summary(duplicate);
          duplicate.published = true; save(); enqueue(duplicate);
        }
        return { accepted: true, comparison_id: duplicate.id };
      }
      if (state.turns.some(t => t.session_id === session && !terminal.has(t.status))) throw new ComparisonError('comparison_busy', '这条对照仍在运行，请等待或取消。');
      let thread = state.threads[session];
      const history = state.turns.filter(t => t.session_id === session);
      const withFiles = request.content.some((part: any) => part.type === 'file');
      const presentation = context.presentation === 'single' ? 'single' : 'paired';
      const selectedLanes: readonly LaneName[] = presentation === 'single' ? ['baseline'] : lanes;
      const newSources = Boolean(thread && withFiles);
      const changed = Boolean(thread && hash([thread.scene, thread.options, thread.presentation ?? 'paired']) !== hash([context.scene, context.options, presentation]));
      // A conversation is stable; immutable tool/budget/evidence scopes belong
      // to its private execution children. Rotate those children on transitions.
      const rotate = !thread || newSources || changed;
      const priorContext = rotate ? Object.fromEntries(selectedLanes.map(name => [name, JSON.stringify([
        ...(context.prior_context_by_lane?.[name] ?? context.prior_context ?? []).slice(-12).map(({source_seq,...row}:any)=>row),
        ...history.slice(-6).map(t => ({
          scene: t.scene,
          user: t.input.filter((part: any) => part.type === 'text').map((part: any) => part.text).join('\n'),
          assistant: t.lanes[t.presentation === 'single' ? 'baseline' : name]?.answer_display ?? t.lanes[t.presentation === 'single' ? 'baseline' : name]?.answer ?? '',
        })),
      ])])) : undefined;
      // Only internal, same-parent, same-lane immutable deliveries are handed
      // forward. The Host rechecks hashes and target scene formats before copy.
      const priorArtifacts = rotate && !withFiles ? Object.fromEntries(selectedLanes.map(name => [name,
        history.slice(-6).flatMap(t => (t.lanes[t.presentation === 'single' ? 'baseline' : name]?.artifacts ?? [])
          .filter(row => t.scene !== 'research-data-analysis' || row.verification === 'data-report-delivery-v1')
          .map(row => ({ turn: t.id, lane: t.presentation === 'single' ? 'baseline' : name, row }))).slice(-32),
      ])) : undefined;
      const priorSources = rotate && !withFiles ? ([...history].reverse().find(t => Object.keys(t.source_files ?? {}).length)?.source_files ?? context.prior_sources) : undefined;
      if (rotate) {
        thread = { scene: context.scene, options: context.options, presentation, lanes: {} };
        for (const name of selectedLanes) thread.lanes[name] = await host.createLane(session, context.scene, name);
        state.threads[session] = thread; save();
      }
      const t: Turn = { id: 'comparison-' + randomUUID(), session_id: session, request_id: request.requestId,
        fingerprint, scene: context.scene, options: context.options, model: context.model, reasoning_effort: context.reasoning_effort ?? 'off', presentation,
        input_sha256: context.input_sha256, created_at: new Date().toISOString(), status: 'preparing',
        lanes: Object.fromEntries(selectedLanes.map(name => [name, { session_id: thread.lanes[name], status: 'preparing', attempt: 0 }])) as Record<LaneName,Lane>,
        scores: {}, score_revision: 0, input: request.content, published: false, source_files:context.source_files, prior_context: priorContext, prior_artifacts: priorArtifacts, prior_sources: Object.values(priorSources ?? {}) };
      state.turns.push(t); save();
      for (const name of turnLanes(t)) t.lanes[name].status = 'queued';
      summary(t); save();
      try { await host.publish(session, view(t), request); }
      catch (error) {
        for (const name of turnLanes(t)) Object.assign(t.lanes[name], { status: 'failed', failure: '请求未成功保存，请重新发送。' });
        summary(t); save(); throw error;
      }
      t.published = true; save();
      enqueue(t); return { accepted: true, comparison_id: t.id };
    }); },
    async view(session: string, id: string) {
      const t = await get(session, id);
      // Recover old hidden deliveries without submitting or charging a model
      // call. Ownership is checked above; original failure status stays visible.
      if (terminal.has(t.status)) for (const name of turnLanes(t)) {
        const lane = t.lanes[name], key = `${t.id}/${name}/${lane.attempt}`;
        const needsDeliveryAudit=t.scene==='research-data-analysis'&&lane.artifacts?.some(row=>row.verification!=='data-report-delivery-v1');
        // A running task can have an unresolved display before finished_at is
        // known. Re-audit that persisted result after a restart reaches a
        // terminal state; the per-attempt key below bounds this to one read.
        const needsAnswerBinding=t.scene==='research-data-analysis'&&hasReportPlaceholders(lane.answer??'')&&
          (lane.answer_binding?.version!==REPORT_ANSWER_BINDING||lane.answer_binding?.status==='unresolved');
        const needsTrace=!Array.isArray(lane.trace);
        const needsDeliveryRecovery=!lane.delivery_reconciled&&!lane.artifacts?.length;
        if (!terminal.has(lane.status) || !lane.task_id || (!needsDeliveryRecovery&&!needsDeliveryAudit&&!needsAnswerBinding&&!needsTrace) || reconciledDeliveries.has(key)) continue;
        try {
          const task = await host.inspect(lane.task_id, { turn: t, lane: name, recoverMissing: true });
          if (['completed', 'failed', 'budget_exhausted', 'cancelled'].includes(task.status)) {
            let changed = false;
            if (Array.isArray(task.deliveries)) { lane.delivery_reconciled=true; save(); }
            if(needsTrace&&Array.isArray(task.trace)){lane.trace=task.trace;lane.messages=task.messages;lane.started_at=task.started_at;lane.finished_at=task.finished_at;lane.duration_ms=task.duration_ms;save();}
            if ((!lane.artifacts?.length||needsDeliveryAudit) && Array.isArray(task.deliveries) && hash(task.deliveries)!==hash(lane.artifacts??[])) {
              lane.artifacts = task.deliveries; changed = true;
              if (lane.status !== 'completed'&&task.deliveries.length) lane.failure = (lane.failure ?? '这一路未完成。') + ' 已完成的文件通过交付校验，可下载。';
            }
            if (needsAnswerBinding && typeof task.answer_display==='string' && task.answer_binding?.version===REPORT_ANSWER_BINDING &&
                task.answer_binding.source_answer_sha256===createHash('sha256').update(lane.answer??'').digest('hex') &&
                hash([lane.answer_display,lane.answer_binding])!==hash([task.answer_display,task.answer_binding])) {
              lane.answer_display=task.answer_display;lane.answer_binding=task.answer_binding;changed=true;
            }
            if (changed) {
              lane.output_sha256 = outputHash(lane);
              // A recovered file or evidence-bound display changes the rated
              // output; stale ratings cannot apply to the new version.
              if (t.scores[name] !== undefined) { delete t.scores[name]; t.score_revision++; }
              lane.feedback=null;
              save(); await publish(t);
            }
          }
          reconciledDeliveries.add(key);
        } catch { /* Existing saved failure remains readable. */ }
      }
      return view(t);
    },
    async rate(session: string, id: string, name: string, score: number, revision: number, outputHash: string) { return feedbackLocked(async () => {
      const t = await get(session, id);
      if (!turnLanes(t).includes(name as LaneName) || !Number.isInteger(score) || score < 1 || score > 5) throw new ComparisonError('invalid_score', '请选择 1–5 分。', 400);
      if (!view(t).scoring_available) throw new ComparisonError('comparison_not_complete', '两侧都完成后才能评分。');
      if (revision !== t.score_revision || outputHash !== t.lanes[name as LaneName].output_sha256) throw new ComparisonError('score_version_changed', '结果或评分已更新，请刷新后评分。');
      t.scores[name as LaneName] = score; t.score_revision++; save();
      const event = { comparison_id: id, principal, lane: name, score, revision: t.score_revision,
        output_sha256: outputHash, input_sha256: t.input_sha256, at: new Date().toISOString() };
      writeFileSync(join(output, 'comparison-ratings.jsonl'), JSON.stringify(event) + '\n', { flag: 'a', mode: 0o600 });
      void publish(t);
      return view(t);
    }); },
    async feedback(session:string,id:string,name:string,vote:unknown,outputSha:string){return feedbackLocked(async()=>{
      const t=await get(session,id),lane=t.lanes[name as LaneName];
      if(!turnLanes(t).includes(name as LaneName)||!['up','down',null].includes(vote as any))throw new ComparisonError('invalid_feedback','反馈选项无效。',400);
      if(!terminal.has(lane.status)||!lane.output_sha256||outputSha!==lane.output_sha256)throw new ComparisonError('feedback_version_changed','回复尚未完成或已更新，请刷新后反馈。');
      lane.feedback=vote as 'up'|'down'|null;save();
      appendFileSync(join(output,'comparison-feedback.jsonl'),JSON.stringify({comparison_id:id,principal,lane:name,vote,output_sha256:outputSha,at:new Date().toISOString()})+'\n',{mode:0o600});
      void publish(t);return view(t);
    });},
    async trace(session:string,id:string,name:string,after=-1,limit=100){
      const t=await get(session,id);
      if(!turnLanes(t).includes(name as LaneName))throw new ComparisonError('invalid_lane','找不到这一路轨迹。',404);
      if(!Number.isSafeInteger(after)||after< -1||!Number.isSafeInteger(limit)||limit<1||limit>200)throw new ComparisonError('invalid_cursor','轨迹分页位置无效。',400);
      const lane=t.lanes[name as LaneName];
      if(lane.task_id){const task=await host.inspect(lane.task_id,{turn:t,lane:name as LaneName});if(Array.isArray(task.trace)){lane.trace=task.trace;lane.messages=task.messages;}}
      const rows=lane.trace??[],items=rows.slice(after+1,after+1+limit).map((row,index)=>({...row,cursor:after+1+index}));
      return {id,session_id:session,lane:name,items,next_cursor:items.length?items.at(-1)!.cursor:after,has_more:after+1+items.length<rows.length};
    },
    async retry(session: string, id: string, name: string) { return locked(async () => {
      const t = await get(session, id);
      if (!turnLanes(t).includes(name as LaneName) || !terminal.has(t.status) || inFlight.has(t.id)) throw new ComparisonError('comparison_busy', '请等当前对照结束后重试。');
      const lane = t.lanes[name as LaneName];
      if (lane.status === 'completed') throw new ComparisonError('lane_completed', '成功结果已保留，无需重复付费运行。');
      lane.attempt++; lane.task_id = undefined; lane.status = 'preparing'; lane.failure_stage = undefined;
      lane.delivery_reconciled=false;
      lane.feedback=null;lane.messages=[];lane.trace=[];
      t.cancellation_requested = false;
      summary(t); save(); enqueue(t); return view(t);
    }); },
    async cancel(session: string, id: string) { return locked(async () => {
      const t = await get(session, id);
      t.cancellation_requested = true;
      for (const name of turnLanes(t)) {
        const lane = t.lanes[name];
        if (terminal.has(lane.status)) continue;
        lane.status = 'cancelled';
        if (lane.task_id) await host.cancel(lane.task_id);
      }
      summary(t); save(); await publish(t); return view(t);
    }); },
    dispose() { disposed = true; subscribers.clear(); if(checkpoint){clearTimeout(checkpoint);checkpoint=undefined;writeState();} },
  };
}
