/** 失败计划的有限局部修复；普通确定性工程机制，不生成工具、不替代科研判断。 */
import { createHash, randomUUID } from 'node:crypto';
import { lstat, mkdir, readFile, readdir, realpath, rename, rmdir, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { AdapterRejected, canonical, digest, inside, object, preflightPlan, privateFile,
  SLIDE_KEYS, SLIDE_REMOVABLE_FIELDS, validateEvidenceRebind, type Obj } from './delivery-adapter.js';

export type PendingEvidence = {
  job_sha256: string; input_version: string; schema_sha256: string;
  implementation_sha256: string; permission_sha256: string;
};
export type PendingFailure = { code: string; message: string; details?: Obj };
export type PendingPatch = {
  metadata?: { title?: string; template?: 'academic' | 'lab' };
  updates?: { page: number; changes: Obj }[];
  replacements?: { page: number; slide: Obj }[];
  /** 页号均指修改前的版本；插入 before_page=原页数+1 表示末尾。 */
  insertions?: { before_page: number; slide: Obj }[];
  deletions?: number[];
};
export type PendingOptions = {
  root: string; jobPath: string; expectedSlides: number; evidence: PendingEvidence;
  guard: () => Promise<void>; audit?: (kind: string, data: Obj) => Promise<void>;
  maxAttempts?: number; maxPatches?: number;
};
type Attempt = { attempt_id: string; plan_sha256: string; started_utc: string;
  finished_utc?: string; outcome?: 'failed' | 'delivered' };
type RecordState = {
  schema_version: 1; draft_id: string; revision: number; evidence: PendingEvidence;
  expected_slides: number; max_attempts: number; max_patches: number;
  plan: Obj; plan_sha256: string; patch_count: number; attempts: Attempt[];
  status: 'pending' | 'in_flight' | 'delivered'; last_failure: Obj; created_utc: string;
};
const ID = /^pending-[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const HASH = /^[a-f0-9]{64}$/;
const MAX_PLAN_BYTES = 2_000_000;
const MAX_RECORD_BYTES = MAX_PLAN_BYTES + 32_000;
const MAX_DRAFTS = 3;
const removable = new Set<string>(SLIDE_REMOVABLE_FIELDS);
const SAFE_FIELDS = new Set<string>([...SLIDE_KEYS, 'slides', 'template', 'plan', 'source_id', 'image_id', 'page',
  'label', 'text', 'source_index', 'type', 'categories', 'series', 'x_label', 'y_label', 'unit', 'name', 'values',
  'steps', 'detail', 'left', 'right', 'changes', 'updates']);
const SAFE_ROLE = /^(?:title|body|body_[1-5]|left|right|left_heading|right_heading|left_[1-4]|right_[1-4]|footer|page|takeaway|image|table|chart|process|process_[1-5]_(?:heading|detail|number)|process_connector_[1-4]|evidence_note_[1-3](?:_heading)?)$/;
function reject(code: string, message: string, details: Obj = {}): never {
  throw new AdapterRejected(code, message, details);
}
const exact = (value: Obj, required: string[], allowed = required): void => {
  if (required.some(k => !Object.hasOwn(value, k)) || Object.keys(value).some(k => !allowed.includes(k)))
    reject('invalid_pending_patch', '只接受公开局部修复字段，不执行自动删改或任意代码。');
};
function boundedJSON(value: unknown, maximum = MAX_PLAN_BYTES): unknown {
  let raw: string;
  try { raw = JSON.stringify(value); } catch { return reject('invalid_pending_plan', '计划必须是可序列化 JSON。'); }
  if (typeof raw !== 'string' || Buffer.byteLength(raw, 'utf8') > maximum)
    return reject('pending_plan_size_exceeded', '计划超过私有存储容量。');
  const parsed: unknown = JSON.parse(raw);
  let nodes = 0;
  const visit = (item: unknown, depth: number): void => {
    if (++nodes > 50_000 || depth > 24) reject('pending_plan_size_exceeded', '计划结构过深或元素过多。');
    if (Array.isArray(item)) item.forEach(x => visit(x, depth + 1));
    else if (object(item)) for (const [key, child] of Object.entries(item)) {
      if (['__proto__', 'prototype', 'constructor'].includes(key)) reject('invalid_pending_plan', '计划包含危险对象键。');
      visit(child, depth + 1);
    }
  };
  visit(parsed, 0); return parsed;
}
/** 保留可修复的有限失败输入；不能借此绕过最终 preflight/后端独立认证。 */
function recoverablePlan(value: unknown): Obj {
  const plan = boundedJSON(value);
  if (!object(plan) || Object.keys(plan).some(k => !['title', 'slides', 'template'].includes(k))
    || (Object.hasOwn(plan, 'title') && (typeof plan.title !== 'string' || !plan.title.trim() || plan.title.length > 100))
    || !Array.isArray(plan.slides) || !plan.slides.length || plan.slides.length > 30
    || plan.slides.some(slide => !object(slide)))
    return reject('invalid_pending_plan', '仅保存 slides 完整、最多30页且已有 title 合法有界的可局部修复计划。');
  return plan;
}
function compactFailure(failure: PendingFailure): Obj {
  const pages = new Set<number>();
  const location: Obj = {};
  let visited = 0;
  const visit = (value: unknown, depth: number): void => {
    if (++visited > 100 || depth > 5) return;
    if (Array.isArray(value)) { value.slice(0, 30).forEach(x => visit(x, depth + 1)); return; }
    if (!object(value)) return;
    if (Number.isSafeInteger(value.page) && Number(value.page) >= 1 && Number(value.page) <= 30) pages.add(Number(value.page));
    if (typeof value.field === 'string' && SAFE_FIELDS.has(value.field)) location.field = value.field;
    for (const field of ['fields', 'missing_fields', 'allowed_fields']) if (Array.isArray(value[field]))
      location[field] = (value[field] as unknown[]).filter((item): item is string => typeof item === 'string' && SAFE_FIELDS.has(item)).slice(0, 32);
    if (typeof value.role === 'string' && SAFE_ROLE.test(value.role)) location.role = value.role;
    for (const field of ['expected_slides', 'submitted_slides']) if (Number.isSafeInteger(value[field]) && Number(value[field]) >= 0 && Number(value[field]) <= 30)
      location[field] = value[field];
    for (const key of ['details', 'errors', 'issues', 'failures', 'violations', 'backend_report']) if (value[key]) visit(value[key], depth + 1);
  };
  visit(failure.details, 0);
  return { code: String(failure.code ?? 'pending_execution_failed').slice(0, 100),
    message: String(failure.message ?? '执行未通过，请只修复明确问题。').slice(0, 500),
    failing_pages: [...pages].sort((a, b) => a - b), ...location, automatic_content_change: false };
}
function preflight(plan: Obj, expectedSlides: number): Obj {
  try { return preflightPlan(plan, expectedSlides); }
  catch (error) {
    if (!(error instanceof AdapterRejected)) throw error;
    return { valid: false, ...compactFailure(error), ...(Number.isSafeInteger(error.details.page) ? { page: error.details.page } : {}),
      ...(error.code === 'slide_count_mismatch' ? { expected_slides: expectedSlides,
        submitted_slides: Array.isArray(plan.slides) ? plan.slides.length : null } : {}) };
  }
}
function pageNumber(value: unknown, maximum: number): number {
  if (!Number.isSafeInteger(value) || Number(value) < 1 || Number(value) > maximum)
    return reject('invalid_pending_patch', '页号必须是当前失败计划中的显式整数。');
  return Number(value);
}

/** 所有修改针对旧版本页号；未指定字段和页面逐项保持，不自动减少科学内容。 */
export function mergePendingPatch(plan: Obj, patch: unknown, expectedSlides: number): { plan: Obj; changed_pages: number[]; deleted_pages: number[]; inserted_before_pages: number[]; changed_metadata: string[] } {
  const original = recoverablePlan(plan), value = boundedJSON(patch);
  if (!object(value)) return reject('invalid_pending_patch', 'patch 必须为对象。');
  exact(value, [], ['metadata', 'updates', 'replacements', 'insertions', 'deletions']);
  const fields = ['updates', 'replacements', 'insertions', 'deletions'];
  if (!Object.keys(value).length || fields.some(k => value[k] !== undefined && (!Array.isArray(value[k]) || (value[k] as unknown[]).length > 30))
    || (!fields.some(k => Array.isArray(value[k]) && (value[k] as unknown[]).length > 0) && !Object.hasOwn(value, 'metadata')))
    return reject('invalid_pending_patch', '需要至少一个有界显式局部修改。');
  const merged = structuredClone(original), slides = merged.slides as Obj[], touched = new Set<number>();
  const changedMetadata: string[] = [];
  if (Object.hasOwn(value, 'metadata')) {
    if (!object(value.metadata) || !Object.keys(value.metadata).length) reject('invalid_pending_patch', 'metadata 必须包含明确 title 或 template。');
    exact(value.metadata, [], ['title', 'template']);
    if (value.metadata.title !== undefined && (typeof value.metadata.title !== 'string' || !value.metadata.title.trim() || value.metadata.title.length > 100)
      || value.metadata.template !== undefined && !['academic', 'lab'].includes(String(value.metadata.template)))
      reject('invalid_pending_patch', 'metadata 只接受合法短标题与 academic/lab 模板，不自动补默认值。');
    for (const [field, child] of Object.entries(value.metadata)) {
      if (canonical(merged[field]) !== canonical(child)) changedMetadata.push(field);
      merged[field] = structuredClone(child);
    }
  }
  for (const item of (value.updates ?? []) as unknown[]) {
    if (!object(item)) reject('invalid_pending_patch', 'updates 每项为 page/changes 对象。');
    exact(item, ['page', 'changes']);
    const page = pageNumber(item.page, slides.length), changes = item.changes;
    if (touched.has(page) || !object(changes) || !Object.keys(changes).length || Object.keys(changes).some(k => !SLIDE_KEYS.includes(k)))
      reject('invalid_pending_patch', '页号不能重复，changes 只接受公开页面字段。');
    touched.add(page); const before = structuredClone(slides[page - 1]);
    for (const [field, child] of Object.entries(changes)) {
      if (child === null && !removable.has(field)) reject('invalid_pending_patch', '只有可选媒体/布局字段允许显式 null。');
      if (child === null) delete slides[page - 1][field]; else slides[page - 1][field] = structuredClone(child);
    }
    validateEvidenceRebind(before, slides[page - 1], changes, page);
  }
  for (const item of (value.replacements ?? []) as unknown[]) {
    if (!object(item)) reject('invalid_pending_patch', 'replacements 每项为 page/slide 对象。');
    exact(item, ['page', 'slide']); const page = pageNumber(item.page, slides.length);
    if (touched.has(page) || !object(item.slide) || Object.keys(item.slide).some(k => !SLIDE_KEYS.includes(k)))
      reject('invalid_pending_patch', '替换页不能重复且只含公开页面字段。');
    const before = slides[page - 1], after = structuredClone(item.slide);
    // 整页替换须显式声明旧证据说明的移除或重绑，不能通过省略偷偷漂移来源索引。
    const sourceChanged = canonical(before.sources) !== canonical(after.sources);
    if (sourceChanged && Array.isArray(before.evidence_notes) && before.evidence_notes.length && !Object.hasOwn(after, 'evidence_notes'))
      reject('invalid_revision', '替换来源时必须显式 evidence_notes=[] 或给出新的绑定。', { page });
    validateEvidenceRebind(before, after, after, page);
    touched.add(page); slides[page - 1] = after;
  }
  const deleted = ((value.deletions ?? []) as unknown[]).map(item => pageNumber(item, slides.length));
  if (new Set(deleted).size !== deleted.length || deleted.some(page => touched.has(page)))
    reject('invalid_pending_patch', '删除页号不能重复，也不能同时修改同一页。');
  const additions = new Map<number, Obj>();
  for (const item of (value.insertions ?? []) as unknown[]) {
    if (!object(item)) reject('invalid_pending_patch', 'insertions 每项为 before_page/slide 对象。');
    exact(item, ['before_page', 'slide']); const page = pageNumber(item.before_page, slides.length + 1);
    if (additions.has(page) || !object(item.slide) || Object.keys(item.slide).some(k => !SLIDE_KEYS.includes(k)))
      reject('invalid_pending_patch', '插入位置不能重复，新增页只含公开页面字段。');
    additions.set(page, structuredClone(item.slide));
  }
  const result: Obj[] = [];
  for (let page = 1; page <= slides.length + 1; page++) {
    const addition = additions.get(page); if (addition) result.push(addition);
    if (page <= slides.length && !deleted.includes(page)) result.push(slides[page - 1]);
  }
  if (result.length !== expectedSlides) reject('slide_count_mismatch', '局部修复后的页数必须精确等于任务页数；不会自动补删科研内容。',
    { expected_slides: expectedSlides, submitted_slides: result.length, no_automatic_content_change: true });
  merged.slides = result;
  recoverablePlan(merged);
  if (digest(merged) === digest(original)) reject('no_changes', '局部修改与当前计划一致，拒绝无变化重试。');
  return { plan: merged, changed_pages: [...touched].sort((a, b) => a - b),
    deleted_pages: deleted.sort((a, b) => a - b), inserted_before_pages: [...additions.keys()].sort((a, b) => a - b), changed_metadata: changedMetadata };
}

export class PendingPlanStore {
  private constructor(private options: PendingOptions, readonly directory: string, private jobPath: string,
    private maxAttempts: number, private maxPatches: number) {}

  static async create(options: PendingOptions): Promise<PendingPlanStore> {
    if (!Number.isSafeInteger(options.expectedSlides) || options.expectedSlides < 1 || options.expectedSlides > 30
      || Object.keys(options.evidence).sort().join(',') !== 'implementation_sha256,input_version,job_sha256,permission_sha256,schema_sha256'
      || Object.values(options.evidence).some(value => typeof value !== 'string' || !HASH.test(value)))
      return reject('invalid_pending_scope', '失败计划需要完整冻结任务、来源、权限、schema 和实现摘要。');
    const maxAttempts = options.maxAttempts ?? 6, maxPatches = options.maxPatches ?? 8;
    if (!Number.isSafeInteger(maxAttempts) || maxAttempts < 1 || maxAttempts > 6
      || !Number.isSafeInteger(maxPatches) || maxPatches < 1 || maxPatches > 8)
      return reject('invalid_pending_scope', '修复预算只能在每任务6次提交/8次修改上限内收紧。');
    const root = await realpath(options.root), jobPath = await privateFile(root, options.jobPath);
    const jobDirectory = dirname(jobPath), directory = resolve(jobDirectory, 'pending-plans');
    const store = new PendingPlanStore({ ...options, root, evidence: structuredClone(options.evidence) }, directory, jobPath, maxAttempts, maxPatches);
    await store.guard(); await store.safeDirectory(jobDirectory);
    try { await mkdir(directory, { mode: 0o700 }); } catch (error) { if ((error as NodeJS.ErrnoException).code !== 'EEXIST') throw error; }
    await store.safeDirectory(directory); return store;
  }
  private async guard(): Promise<void> {
    await this.options.guard();
    const path = await privateFile(this.options.root, this.jobPath), raw = await readFile(path);
    if (createHash('sha256').update(raw).digest('hex') !== this.options.evidence.job_sha256)
      reject('job_version_changed', '任务、预算或权限版本改变，拒绝旧失败计划。');
    const job: unknown = JSON.parse(raw.toString('utf8'));
    if (!object(job) || job.allow_output !== true || job.slides !== this.options.expectedSlides)
      reject('output_permission_denied', '失败计划修复仍需要原任务明确输出授权与固定页数。');
  }
  private async safeDirectory(path: string): Promise<void> {
    const info = await lstat(path), actual = await realpath(path);
    if (info.isSymbolicLink() || !info.isDirectory() || actual !== resolve(path) || !inside(resolve(this.options.root, '.local'), actual))
      reject('path_scope_rejected', '失败计划目录不能为符号链接或越出私有任务范围。');
  }
  private async safeRead(path: string): Promise<unknown> {
    await this.safeDirectory(dirname(path));
    const info = await lstat(path);
    if (info.isSymbolicLink() || !info.isFile() || info.size > MAX_RECORD_BYTES || !inside(this.directory, await realpath(path)))
      reject('pending_storage_rejected', '失败计划记录不是有界私有普通文件。');
    return JSON.parse(await readFile(path, 'utf8'));
  }
  private async atomicJSON(path: string, value: unknown): Promise<void> {
    await this.safeDirectory(dirname(path));
    try { if ((await lstat(path)).isSymbolicLink()) reject('pending_storage_rejected', '拒绝写入符号链接记录。'); }
    catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error; }
    const temporary = resolve(dirname(path), '.write-' + randomUUID() + '.json');
    await writeFile(temporary, JSON.stringify(value) + '\n', { flag: 'wx', mode: 0o600 });
    await this.safeDirectory(dirname(path)); await rename(temporary, path);
  }
  private async locked<T>(work: () => Promise<T>): Promise<T> {
    await this.guard(); await this.safeDirectory(this.directory);
    const lock = resolve(this.directory, '.write-lock');
    try { await mkdir(lock, { mode: 0o700 }); }
    catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'EEXIST') reject('pending_plan_busy', '另一个进程正在修改失败计划；不删除或抢占其锁。');
      throw error;
    }
    try { await this.safeDirectory(lock); const value = await work(); await this.guard(); return value; }
    finally { await this.safeDirectory(lock); await rmdir(lock); }
  }
  private async state(id: string): Promise<RecordState> {
    if (!ID.test(id)) return reject('invalid_pending_handle', '需要当前任务返回的真实失败计划句柄。');
    const area = resolve(this.directory, id);
    const head = await this.safeRead(resolve(area, 'head.json'));
    if (!object(head) || Object.keys(head).sort().join(',') !== 'revision,version_sha256'
      || !Number.isSafeInteger(head.revision) || Number(head.revision) < 1 || Number(head.revision) > 30
      || typeof head.version_sha256 !== 'string' || !HASH.test(head.version_sha256))
      return reject('pending_storage_rejected', '失败计划头记录无效。');
    const record = await this.safeRead(resolve(area, `revision-${head.revision}.json`));
    if (!object(record) || record.schema_version !== 1 || record.draft_id !== id || record.revision !== head.revision
      || digest(record) !== head.version_sha256 || !object(record.evidence)
      || canonical(record.evidence) !== canonical(this.options.evidence) || record.expected_slides !== this.options.expectedSlides
      || record.max_attempts !== this.maxAttempts || record.max_patches !== this.maxPatches)
      return reject('pending_scope_changed', '失败计划完整性或任务/来源/schema/实现/权限版本不一致，拒绝复用。');
    if (!Array.isArray(record.attempts) || record.attempts.length > this.maxAttempts || !Number.isSafeInteger(record.patch_count)
      || Number(record.patch_count) < 0 || Number(record.patch_count) > this.maxPatches
      || !['pending', 'in_flight', 'delivered'].includes(String(record.status)) || !object(record.last_failure)
      || !object(record.plan) || digest(record.plan) !== record.plan_sha256)
      return reject('pending_storage_rejected', '失败计划状态或预算记录不一致。');
    recoverablePlan(record.plan);
    return record as unknown as RecordState;
  }
  private async all(): Promise<RecordState[]> {
    await this.safeDirectory(this.directory);
    const ids = (await readdir(this.directory)).filter(name => ID.test(name));
    if (ids.length > MAX_DRAFTS) reject('pending_storage_rejected', '失败计划数量超出任务容量。');
    return Promise.all(ids.map(id => this.state(id)));
  }
  private receipt(record: RecordState): Obj {
    return { draft_id: record.draft_id, version_sha256: digest(record), plan_sha256: record.plan_sha256,
      slide_count: (record.plan.slides as unknown[]).length, expected_slides: record.expected_slides, status: record.status,
      attempts: record.attempts.length, max_attempts: this.maxAttempts, patch_count: record.patch_count, max_patches: this.maxPatches,
      failure: structuredClone(record.last_failure), preflight: preflight(record.plan, record.expected_slides),
      recovery: 'read_pending_plan or repair_pending_plan with this draft_id/version_sha256; do not resend the full plan',
      automatic_content_change: false, scientific_quality: 'not_reviewed', mechanism: 'ordinary_versioned_local_repair' };
  }
  private async persist(record: RecordState): Promise<void> {
    const area = resolve(this.directory, record.draft_id); await this.safeDirectory(area);
    await this.guard();
    await writeFile(resolve(area, `revision-${record.revision}.json`), JSON.stringify(record) + '\n', { flag: 'wx', mode: 0o600 });
    await this.atomicJSON(resolve(area, 'head.json'), { revision: record.revision, version_sha256: digest(record) });
    await this.options.audit?.('pending_plan_state', { ...this.receipt(record), evidence: record.evidence });
  }
  private current(record: RecordState, version: string): void {
    if (typeof version !== 'string' || !HASH.test(version) || version !== digest(record))
      reject('pending_version_changed', '失败计划已被其他修复或提交改变，拒绝旧版本。', { pending_plan: this.receipt(record) });
    if (record.status === 'delivered') reject('pending_already_delivered', '失败计划已经完成，不重复渲染或交付。');
    if (record.status === 'in_flight') reject('pending_attempt_in_flight', '已有执行结果尚未确认；禁止重试或覆盖不确定状态。');
  }

  async activePending(): Promise<Obj | undefined> {
    await this.guard(); const active = (await this.all()).filter(row => row.status !== 'delivered');
    if (active.length > 1) reject('pending_storage_rejected', '同任务出现多个活动失败计划，停止执行。');
    await this.guard(); return active.length ? this.receipt(active[0]) : undefined;
  }
  async capture(plan: unknown, failure: PendingFailure): Promise<Obj> {
    const captured = recoverablePlan(plan);
    return this.locked(async () => {
      const states = await this.all(), active = states.find(row => row.status !== 'delivered');
      if (active) reject('pending_plan_exists', '当前已有失败计划，请局部修复；不接受重发整稿绕过修复上限。', { pending_plan: this.receipt(active) });
      if (states.length >= MAX_DRAFTS || states.reduce((sum, row) => sum + row.attempts.length, 0) >= this.maxAttempts)
        reject('pending_attempt_limit', '当前任务失败提交上限已用完，请审阅失败证据；不会自动重启任务。');
      const id = 'pending-' + randomUUID(), now = new Date().toISOString();
      const record: RecordState = { schema_version: 1, draft_id: id, revision: 1,
        evidence: structuredClone(this.options.evidence), expected_slides: this.options.expectedSlides,
        max_attempts: this.maxAttempts, max_patches: this.maxPatches, plan: captured, plan_sha256: digest(captured), patch_count: 0,
        attempts: [{ attempt_id: randomUUID(), plan_sha256: digest(captured), started_utc: now, finished_utc: now, outcome: 'failed' }],
        status: 'pending', last_failure: compactFailure(failure), created_utc: now };
      const area = resolve(this.directory, id); await mkdir(area, { mode: 0o700 }); await this.persist(record);
      return this.receipt(record);
    });
  }
  async read(draftId: string, version: string, pages: number[]): Promise<Obj> {
    await this.guard(); const record = await this.state(draftId); this.current(record, version);
    if (!Array.isArray(pages) || !pages.length || pages.length > 5 || new Set(pages).size !== pages.length)
      reject('invalid_pending_pages', '只读取明确的1–5个不同页面，避免重发整稿。');
    const selected = pages.map(page => pageNumber(page, (record.plan.slides as unknown[]).length));
    await this.guard(); return { ...this.receipt(record), title: record.plan.title, template: record.plan.template ?? null,
      slides: selected.map(page => ({ page, slide: structuredClone((record.plan.slides as Obj[])[page - 1]) })), scope: 'explicit_pending_pages_only' };
  }
  async patch(draftId: string, version: string, patch: PendingPatch | unknown): Promise<Obj> {
    return this.locked(async () => {
      const record = await this.state(draftId); this.current(record, version);
      if (record.patch_count >= this.maxPatches) reject('pending_patch_limit', '当前任务局部修复次数已用完，保留失败证据。');
      const merged = mergePendingPatch(record.plan, patch, record.expected_slides);
      record.plan = merged.plan; record.plan_sha256 = digest(record.plan); record.patch_count++; record.revision++;
      // 可保存仍有明确错误的局部修复；完整 preflight 和实际后端守卫必须在提交前全部通过。
      record.last_failure = preflight(record.plan, record.expected_slides);
      await this.persist(record); return { ...this.receipt(record), changed_pages: merged.changed_pages,
        deleted_pages: merged.deleted_pages, inserted_before_pages: merged.inserted_before_pages, changed_metadata: merged.changed_metadata };
    });
  }
  /** 仅宿主取完整计划；这个返回值不得原样发给模型。 */
  async prepareAttempt(draftId: string, version: string): Promise<{ plan: Obj; receipt: Obj; attempt_id: string }> {
    return this.locked(async () => {
      const record = await this.state(draftId); this.current(record, version);
      const states = await this.all();
      if (states.reduce((sum, row) => sum + row.attempts.length, 0) >= this.maxAttempts)
        reject('pending_attempt_limit', '同任务全部失败提交预算已用完；不会新建候选或重启绕过上限。', { pending_plan: this.receipt(record) });
      if (record.attempts.some(attempt => attempt.plan_sha256 === record.plan_sha256))
        reject('pending_unchanged_retry', '该完整计划已提交过；必须明确局部修复后才能再执行。', { pending_plan: this.receipt(record) });
      preflightPlan(record.plan, record.expected_slides);
      const attemptId = randomUUID(); record.attempts.push({ attempt_id: attemptId, plan_sha256: record.plan_sha256, started_utc: new Date().toISOString() });
      record.status = 'in_flight'; record.revision++; await this.persist(record);
      return { plan: structuredClone(record.plan), receipt: this.receipt(record), attempt_id: attemptId };
    });
  }
  async recordOutcome(draftId: string, version: string, attemptId: string, outcome: { delivered: true } | { delivered: false; failure: PendingFailure }): Promise<Obj> {
    return this.locked(async () => {
      const record = await this.state(draftId), last = record.attempts.at(-1);
      if (version !== digest(record) || record.status !== 'in_flight' || last?.attempt_id !== attemptId || last.finished_utc)
        reject('pending_attempt_changed', '执行版本或 attempt_id 不匹配；拒绝替换其他进程的结果。');
      last.finished_utc = new Date().toISOString(); last.outcome = outcome.delivered ? 'delivered' : 'failed';
      record.status = outcome.delivered ? 'delivered' : 'pending';
      record.last_failure = outcome.delivered ? {} : compactFailure(outcome.failure);
      record.revision++; await this.persist(record); return this.receipt(record);
    });
  }
}
