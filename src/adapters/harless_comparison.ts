/** Account-local paired turns over the existing DSH task runner. No new Agent loop. */
import { randomUUID, createHash } from 'node:crypto';
import { existsSync, readFileSync, writeFileSync, renameSync, mkdirSync, appendFileSync } from 'node:fs';
import { join } from 'node:path';

const hash = (value: unknown) => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const terminal = new Set(['completed', 'failed', 'cancelled']);
const lanes = ['baseline', 'motif'] as const;
type LaneName = typeof lanes[number];
type Lane = { session_id: string; task_id?: string; status: string; answer?: string; failure?: string;
  mode?:string;library_sha256?:string;
  attempt: number; output_sha256?: string; stats?: any; fallback_reason?: string; artifacts?: any[] };
type Turn = { id: string; session_id: string; request_id: string; fingerprint: string; scene: string;
  options: any; model: any; input_sha256: string; created_at: string; status: string;
  lanes: Record<LaneName, Lane>; scores: Partial<Record<LaneName, number>>; score_revision: number; input: any;
  published?: boolean; cancellation_requested?: boolean; source_files?:Record<string,any> };
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
  cancel(taskId: string): Promise<void>;
  publish(parent: string, turn: any, request?: any): Promise<void>;
  ready?(): boolean;
};

export function createComparisonService(output: string, principal: string, host: ComparisonHost,
  { pollMs = 400 }: { pollMs?: number } = {}) {
  mkdirSync(output, { recursive: true, mode: 0o700 });
  const path = join(output, 'comparisons.json');
  const state: { version: number; principal: string; threads: Record<string, any>; turns: Turn[] } = existsSync(path)
    ? JSON.parse(readFileSync(path, 'utf8')) : { version: 1, principal, threads: {}, turns: [] };
  if (state.version !== 1 || state.principal !== principal || !Array.isArray(state.turns)) throw Error('comparison_store_scope_mismatch');
  const pending: Turn[] = [], inFlight = new Set<string>();
  const reconciledDeliveries = new Set<string>();
  let running = false, disposed = false, admission = Promise.resolve();
  const save = () => { const tmp = path + '.' + randomUUID() + '.tmp'; writeFileSync(tmp, JSON.stringify(state), { mode: 0o600 }); renameSync(tmp, path); };
  // Reconnect never starts a paid task. A stopped turn needs an explicit retry.
  for (const t of state.turns) if (!terminal.has(t.status)) {
    for (const name of lanes) if (!terminal.has(t.lanes[name].status)) Object.assign(t.lanes[name], { status: 'failed', failure: '服务重启中断了这一路，请重试。' });
    t.status = 'failed';
  }
  save();
  const locked = <T>(fn: () => Promise<T>): Promise<T> => {
    const job = admission.then(fn); admission = job.then(() => undefined, () => undefined); return job;
  };
  const view = (t: Turn) => ({ id: t.id, session_id: t.session_id, scene: t.scene, status: t.status,
    input_sha256: t.input_sha256, created_at: t.created_at, score_revision: t.score_revision, scores: { ...t.scores },
    scoring_available: lanes.every(name => t.lanes[name].status === 'completed'),
    lanes: Object.fromEntries(lanes.map(name => {
      const lane = t.lanes[name], artifacts = (lane.artifacts ?? []).filter(row=>
        t.scene!=='research-data-analysis'||row.verification==='data-report-delivery-v1');
      const delivery_status = artifacts.length ? 'available' : terminal.has(lane.status) ? 'not_delivered' : 'pending';
      return [name, { ...lane, artifacts, delivery_status,
        delivery_message: delivery_status === 'available' ? '结果文件已保存，可下载到本地。'
          : delivery_status === 'pending' ? '结果文件会在生成并通过交付检查后显示。'
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
    const statuses = lanes.map(name => t.lanes[name].status);
    t.status = statuses.every(s => s === 'completed') ? 'completed' : statuses.every(s => terminal.has(s))
      ? statuses.includes('failed') ? 'failed' : 'cancelled' : 'running';
  }
  async function refresh(t: Turn, name: LaneName) {
    const lane = t.lanes[name];
    if (!lane.task_id) return;
    const previous = hash(view(t));
    const task = await host.inspect(lane.task_id, { turn: t, lane: name });
    if (disposed) return;
    Object.assign(lane, { status: t.cancellation_requested ? 'cancelled' : task.status === 'budget_exhausted' ? 'failed' : task.status === 'awaiting_confirmation' ? 'queued' : task.status,
      answer: task.answer ?? lane.answer ?? '', stats: task.stats, fallback_reason: task.fallback_reason ?? null,
      mode:task.mode,library_sha256:task.library_sha256,
      artifacts: task.deliveries ?? [], failure: task.status === 'budget_exhausted'
        ? (task.deliveries?.length ? '已完成的文件通过交付校验，可下载；后续模型回复达到请求或预算上限，未完成的部分与支出均已保留。' : '这一路达到预算或请求上限，结果与已有支出已保留。')
        : task.status === 'failed' ? '这一路运行失败，请查看状态后重试；已校验的交付文件仍可下载。' : undefined });
    if (terminal.has(lane.status)) lane.output_sha256 = hash([lane.answer, lane.artifacts]);
    summary(t); save();
    if (hash(view(t)) !== previous) await publish(t);
  }
  async function run(t: Turn) {
    inFlight.add(t.id);
    try {
      for (const name of lanes) {
        const lane = t.lanes[name];
        if (disposed || terminal.has(lane.status)) continue;
        try {
          while (host.ready?.() === false && !disposed && !terminal.has(lane.status)) await new Promise(resolve => setTimeout(resolve, pollMs));
          if (disposed || terminal.has(lane.status)) continue;
          if (!lane.task_id) await prepare(t, name);
          if (disposed || terminal.has(lane.status)) continue;
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
          Object.assign(lane, { status: 'failed', failure: '这一路未完成，请重试；另一侧结果已保留。' });
        }
        summary(t); save(); await publish(t);
      }
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
    } else Object.assign(lane, { status: 'queued', failure: undefined });
  }
  return {
    hasSession: (id: string) => Boolean(state.threads[id]),
    // Only a previously admitted request in this account can resolve a retired
    // upload receipt. These server-minted references never appear in GET views.
    sourceFor: (session:string,requestId:string,receipt:string) =>
      state.turns.find(t=>t.session_id===session&&t.request_id===requestId)?.source_files?.[receipt],
    isLane: (id: string) => Object.values(state.threads).some((thread: any) => Object.values(thread.lanes).includes(id)),
    parentFor: (id: string) => Object.entries(state.threads).find(([, thread]: any) => Object.values(thread.lanes).includes(id))?.[0] ?? null,
    async admit(session: string, request: any, context: any) { return locked(async () => {
      await host.owns(session);
      if (disposed) throw new ComparisonError('comparison_stopping', '服务正在重启，请稍后再试。');
      const fingerprint = hash([request.content, context.scene, context.options, context.model]);
      const duplicate = state.turns.find(t => t.session_id === session && t.request_id === request.requestId);
      if (duplicate) {
        if (duplicate.fingerprint !== fingerprint) throw new ComparisonError('request_id_conflict', '同一发送请求不能更改内容。');
        if (duplicate.published === false) {
          await host.publish(session, view(duplicate), request);
          for (const name of lanes) duplicate.lanes[name].status = 'queued';
          summary(duplicate);
          duplicate.published = true; save(); enqueue(duplicate);
        }
        return { accepted: true, comparison_id: duplicate.id };
      }
      if (state.turns.some(t => t.session_id === session && !terminal.has(t.status))) throw new ComparisonError('comparison_busy', '这条对照仍在运行，请等待或取消。');
      let thread = state.threads[session];
      if (thread && request.content.some((part: any) => part.type === 'file')) throw new ComparisonError('new_session_required', '新增资料需要新会话，原对照与评分已保留。');
      if (thread && hash([thread.scene, thread.options]) !== hash([context.scene, context.options])) throw new ComparisonError('new_session_required', '更换场景或文件权限需要新会话，原对照已保留。');
      if (!thread) {
        thread = { scene: context.scene, options: context.options, lanes: {} };
        for (const name of lanes) thread.lanes[name] = await host.createLane(session, context.scene, name);
        state.threads[session] = thread; save();
      }
      const t: Turn = { id: 'comparison-' + randomUUID(), session_id: session, request_id: request.requestId,
        fingerprint, scene: context.scene, options: context.options, model: context.model,
        input_sha256: context.input_sha256, created_at: new Date().toISOString(), status: 'preparing',
        lanes: { baseline: { session_id: thread.lanes.baseline, status: 'preparing', attempt: 0 },
          motif: { session_id: thread.lanes.motif, status: 'preparing', attempt: 0 } },
        scores: {}, score_revision: 0, input: request.content, published: false, source_files:context.source_files };
      state.turns.push(t); save();
      for (const name of lanes) t.lanes[name].status = 'queued';
      summary(t); save();
      try { await host.publish(session, view(t), request); }
      catch (error) {
        for (const name of lanes) Object.assign(t.lanes[name], { status: 'failed', failure: '请求未成功保存，请重新发送。' });
        summary(t); save(); throw error;
      }
      t.published = true; save();
      enqueue(t); return { accepted: true, comparison_id: t.id };
    }); },
    async view(session: string, id: string) {
      const t = await get(session, id);
      // Recover old hidden deliveries without submitting or charging a model
      // call. Ownership is checked above; original failure status stays visible.
      if (terminal.has(t.status)) for (const name of lanes) {
        const lane = t.lanes[name], key = `${t.id}/${name}/${lane.attempt}`;
        const needsDeliveryAudit=t.scene==='research-data-analysis'&&lane.artifacts?.some(row=>row.verification!=='data-report-delivery-v1');
        if (!terminal.has(lane.status) || !lane.task_id || (lane.artifacts?.length&&!needsDeliveryAudit) || reconciledDeliveries.has(key)) continue;
        try {
          const task = await host.inspect(lane.task_id, { turn: t, lane: name, recoverMissing: true });
          if (Array.isArray(task.deliveries) && hash(task.deliveries)!==hash(lane.artifacts??[]) &&
              ['completed', 'failed', 'budget_exhausted', 'cancelled'].includes(task.status)) {
            lane.artifacts = task.deliveries;
            if (lane.status !== 'completed'&&task.deliveries.length) lane.failure = (lane.failure ?? '这一路未完成。') + ' 已完成的文件通过交付校验，可下载。';
            lane.output_sha256 = hash([lane.answer, lane.artifacts]);
            // A recovered file changes the rated output; stale ratings cannot
            // silently apply to the newly available version.
            if (t.scores[name] !== undefined) { delete t.scores[name]; t.score_revision++; }
            save(); await publish(t);
          }
          reconciledDeliveries.add(key);
        } catch { /* Existing saved failure remains readable. */ }
      }
      return view(t);
    },
    async rate(session: string, id: string, name: string, score: number, revision: number, outputHash: string) { return locked(async () => {
      const t = await get(session, id);
      if (!lanes.includes(name as LaneName) || !Number.isInteger(score) || score < 1 || score > 5) throw new ComparisonError('invalid_score', '请选择 1–5 分。', 400);
      if (!view(t).scoring_available) throw new ComparisonError('comparison_not_complete', '两侧都完成后才能评分。');
      if (revision !== t.score_revision || outputHash !== t.lanes[name as LaneName].output_sha256) throw new ComparisonError('score_version_changed', '结果或评分已更新，请刷新后评分。');
      t.scores[name as LaneName] = score; t.score_revision++; save();
      const event = { comparison_id: id, principal, lane: name, score, revision: t.score_revision,
        output_sha256: outputHash, input_sha256: t.input_sha256, at: new Date().toISOString() };
      writeFileSync(join(output, 'comparison-ratings.jsonl'), JSON.stringify(event) + '\n', { flag: 'a', mode: 0o600 });
      await publish(t);
      return view(t);
    }); },
    async retry(session: string, id: string, name: string) { return locked(async () => {
      const t = await get(session, id);
      if (!lanes.includes(name as LaneName) || !terminal.has(t.status) || inFlight.has(t.id)) throw new ComparisonError('comparison_busy', '请等当前对照结束后重试。');
      const lane = t.lanes[name as LaneName];
      if (lane.status === 'completed') throw new ComparisonError('lane_completed', '成功结果已保留，无需重复付费运行。');
      lane.attempt++; lane.task_id = undefined; lane.status = 'preparing';
      t.cancellation_requested = false;
      summary(t); save(); enqueue(t); return view(t);
    }); },
    async cancel(session: string, id: string) { return locked(async () => {
      const t = await get(session, id);
      t.cancellation_requested = true;
      for (const name of lanes) {
        const lane = t.lanes[name];
        if (terminal.has(lane.status)) continue;
        lane.status = 'cancelled';
        if (lane.task_id) await host.cancel(lane.task_id);
      }
      summary(t); save(); await publish(t); return view(t);
    }); },
    dispose() { disposed = true; },
  };
}
