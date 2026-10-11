/** 科研 PPT 有限 MCP 交付适配器。没有模型循环、任意代码执行或自动科学修订。 */
import { createHash } from 'node:crypto';
import { readFile, realpath, stat, appendFile } from 'node:fs/promises';
import { resolve, relative, isAbsolute, sep } from 'node:path';

export type Obj = Record<string, unknown>;
export type Backend = (name: string, args: Obj) => Promise<Obj>;
export class AdapterRejected extends Error {
  constructor(readonly code: string, message: string, readonly details: Obj = {}) {
    super(message); this.name = 'AdapterRejected';
  }
}
export const canonical = (value: unknown): string => {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value !== null && typeof value === 'object') return '{' + Object.entries(value).filter(([,item])=>item!==undefined)
    .sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)
    .map(([key, item]) => JSON.stringify(key) + ':' + canonical(item)).join(',') + '}';
  return JSON.stringify(value) ?? 'null';
};
export const digest = (value: unknown): string => createHash('sha256').update(canonical(value)).digest('hex');
export const object = (value: unknown): value is Obj => value !== null && typeof value === 'object' && !Array.isArray(value);
const text = (value: unknown, maximum = 500, empty = false): value is string => typeof value === 'string'
  && (empty || value.trim().length > 0) && value.length <= maximum && !/[\x00-\x08\x0b\x0c\x0e-\x1f]/.test(value);
const hash = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const keys = (value: Obj, required: string[], allowed = required): void => {
  if (required.some(key => !Object.hasOwn(value, key)) || Object.keys(value).some(key => !allowed.includes(key)))
    throw new AdapterRejected('invalid_arguments', '参数字段不完整或包含不支持字段。');
};
function fail(code: string, message: string, details: Obj = {}): never { throw new AdapterRejected(code, message, details); }
async function fileHash(path: string): Promise<string> { return createHash('sha256').update(await readFile(path)).digest('hex'); }
export function inside(root: string, path: string): boolean {
  const rel = relative(root, path); return rel !== '..' && !rel.startsWith('..' + sep) && !isAbsolute(rel);
}
export async function privateFile(root: string, path: string): Promise<string> {
  const full = await realpath(resolve(path));
  if (!inside(resolve(root, '.local'), full) || !(await stat(full)).isFile())
    fail('path_scope_rejected', '只允许本仓库私有任务与交付文件。');
  return full;
}

type Job = Obj & { slides: number; allow_output: boolean; inputs: Obj[] };
type Pinned = { deck_id: string; file_sha256: string; pages: number[]; result_sha256: string; version_sha256: string };
const SLIDE_KEYS = ['title','bullets','sources','notes','image','table','chart','layout','comparison','process','takeaway'];
const LAYOUTS = ['title','content','image','table','chart','section','comparison','process'];

/** 仅检查可执行计划形状与容量；不补页、不删页、不改科学内容。后端仍执行独立全部守卫。 */
export function preflightPlan(plan: unknown, expectedSlides: number): Obj {
  if (!object(plan)) return fail('invalid_plan', 'plan 必须是一个对象。');
  keys(plan, ['title','slides'], ['title','slides','template']);
  if (!text(plan.title, 100) || !Array.isArray(plan.slides)) return fail('invalid_plan', 'plan 需要 title 和 slides 数组；不能再嵌套 plan。');
  if (plan.slides.length !== expectedSlides) return fail('slide_count_mismatch', '提交页数必须精确等于任务页数，封面计算在内。',
    { expected_slides: expectedSlides, submitted_slides: plan.slides.length, no_automatic_content_change: true });
  if (plan.template !== undefined && !['lab','academic'].includes(String(plan.template))) return fail('invalid_plan', '模板只能是 academic 或 lab。');
  for (const [index, slide] of plan.slides.entries()) {
    const page = index + 1;
    if (!object(slide)) return fail('invalid_plan', '页面必须是对象。', { page });
    keys(slide, ['title','sources'], SLIDE_KEYS);
    if (!text(slide.title, 70) || !Array.isArray(slide.sources) || !slide.sources.length || slide.sources.length > 20)
      return fail('invalid_plan', '每页需要短标题和1–20个实际来源。', { page });
    for (const cite of slide.sources) {
      if (!object(cite)) return fail('invalid_plan', 'sources 每项需要 source_id 和 page。', { page });
      keys(cite, ['source_id','page']);
      if (!text(cite.source_id) || !Number.isSafeInteger(cite.page) || Number(cite.page) < 1)
        return fail('invalid_plan', '来源句柄和页号不合法。', { page });
    }
    const bullets = slide.bullets ?? [];
    if (!Array.isArray(bullets) || bullets.length > 5 || bullets.some(x => !text(x, 150)))
      return fail('invalid_plan', '每页 bullets 最多5条，每条最多150字符。', { page });
    const media = ['image','table','chart','comparison','process'].filter(key => slide[key] !== undefined);
    if (media.length > 1 || bullets.join('').length > (['image','table','chart'].some(key => slide[key] !== undefined) ? 220 : 500))
      return fail('invalid_plan', '页面媒体类型冲突或正文超过公开渲染器容量。', { page });
    if (slide.notes !== undefined && !text(slide.notes, 6000, true)) return fail('invalid_plan', 'notes 超出容量或含非法字符。', { page });
    if (slide.takeaway !== undefined && !text(slide.takeaway, 90)) return fail('invalid_plan', 'takeaway 必须为短结论。', { page });
    if (slide.layout !== undefined && !LAYOUTS.includes(String(slide.layout))) return fail('invalid_plan', '未知 layout。', { page });
    if (slide.image !== undefined) {
      if (!object(slide.image)) return fail('invalid_image', '图片必须引用真实素材句柄。', { page });
      keys(slide.image, ['source_id','image_id']);
      if (!text(slide.image.source_id) || !text(slide.image.image_id)) return fail('invalid_image', '图片素材句柄不合法。', { page });
    }
    if (slide.table !== undefined && (!Array.isArray(slide.table) || slide.table.length < 2 || slide.table.length > 6
      || slide.table.some(row => !Array.isArray(row) || row.length < 1 || row.length > 4 || row.some(cell => !text(cell,45)))
      || new Set(slide.table.map(row => (row as unknown[]).length)).size !== 1))
      return fail('invalid_plan', '表格需要2–6行、1–4列及短单元格。', { page });
    if (slide.chart !== undefined) {
      const c=slide.chart;
      if (!object(c)) return fail('invalid_plan','chart必须为已核对来源的显式数据对象。',{page});
      keys(c,['type','categories','series'],['type','categories','series','x_label','y_label','unit']);
      if (!['bar','line'].includes(String(c.type)) || !Array.isArray(c.categories) || c.categories.length<2 || c.categories.length>10
        || c.categories.some(x=>!text(x,25)) || new Set(c.categories).size!==c.categories.length
        || !Array.isArray(c.series) || c.series.length<1 || c.series.length>3
        || [c.x_label,c.y_label,c.unit].some(x=>x!==undefined&&!text(x,40)))
        return fail('invalid_plan','chart需要2–10个不同分类、1–3组有限数值及短标注。',{page});
      const categories=c.categories;
      for (const series of c.series) {
        if (!object(series)) return fail('invalid_plan','chart数据序列必须是对象。',{page});
        keys(series,['name','values']);
        if (!text(series.name,30) || !Array.isArray(series.values) || series.values.length!==categories.length
          || series.values.some(x=>typeof x!=='number'||!Number.isFinite(x)))
          return fail('invalid_plan','chart序列必须与分类等长，且只有有限数值。',{page});
      }
    }
    if (slide.process !== undefined) {
      const p = slide.process;
      if (!object(p) || Object.keys(p).some(key => key !== 'steps') || !Array.isArray(p.steps) || p.steps.length < 2 || p.steps.length > 5
        || p.steps.some(step => !object(step) || Object.keys(step).some(k => !['label','detail'].includes(k)) || !text(step.label,28) || !text(step.detail,90))
        || slide.layout !== 'process' || bullets.length > 0) return fail('invalid_plan', 'process 必须2–5个短步骤，layout=process且bullets为空。', { page });
    }
    if (slide.comparison !== undefined) {
      const c = slide.comparison;
      if (!object(c) || Object.keys(c).some(k => !['left','right'].includes(k)) || [c.left,c.right].some(col => !object(col)
        || Object.keys(col).some(k => !['title','bullets'].includes(k)) || !text(col.title,35) || !Array.isArray(col.bullets)
        || col.bullets.length > 4 || col.bullets.some(x => !text(x,100)) || col.bullets.join('').length > 240)
        || bullets.length > 0) return fail('invalid_plan', 'comparison 需要两个短内容列，页面bullets为空。', { page });
    }
    const inferred = slide.layout ?? (media[0] ?? 'content');
    if ((['image','table','chart','comparison','process'].includes(String(inferred)) && slide[String(inferred)] === undefined)
      || (['title','section','content'].includes(String(inferred)) && media.length > 0))
      return fail('invalid_plan', 'layout 与实际页面内容类型不一致。', { page });
  }
  return { valid: true, slide_count: expectedSlides, plan_sha256: digest(plan),
    scope: 'shape_and_capacity_only', scientific_quality: 'not_reviewed', no_automatic_content_change: true };
}

export class DeliveryAdapter {
  private pinned = new Map<string, Pinned>();
  private dependencies = new Map<string, string>();
  private jobHash = '';
  private constructor(readonly root: string, readonly jobPath: string, readonly job: Job, private backend: Backend,
    readonly auditPath: string, readonly inputVersion: string) {}

  static async create(rootPath: string, jobPath: string, backend: Backend, dependencyFiles: string[]): Promise<DeliveryAdapter> {
    const root = await realpath(rootPath); const path = await privateFile(root, jobPath);
    const raw = await readFile(path, 'utf8'); const value: unknown = JSON.parse(raw);
    if (!object(value) || !Number.isSafeInteger(value.slides) || Number(value.slides) < 1 || Number(value.slides) > 30
      || typeof value.allow_output !== 'boolean' || !Array.isArray(value.inputs) || !value.inputs.length || value.inputs.length > 8
      || value.inputs.some(x => !object(x) || typeof x.path !== 'string' || !hash(x.version_sha256)))
      return fail('invalid_job', '固定任务缺少页数、权限或批准来源版本。');
    const job = value as Job;
    // 与 PPTService.input_version 的 Python json.dumps 默认空格精确一致。
    const inputVersion = createHash('sha256').update(JSON.stringify(job.inputs.map(row => row.version_sha256)).replace(/,/g, ', ')).digest('hex');
    const self = new DeliveryAdapter(root, path, job, backend, resolve(path, '../delivery-adapter-audit.jsonl'), inputVersion);
    self.jobHash = await fileHash(path);
    for (const file of dependencyFiles) {
      const resolved = await realpath(file);
      if (!inside(root, resolved) || !(await stat(resolved)).isFile()) fail('dependency_scope_rejected', '后端实现必须在本仓库内。');
      self.dependencies.set(resolved, await fileHash(resolved));
    }
    await self.guard();
    await self.audit('adapter_started', { job_sha256: self.jobHash, input_version: inputVersion,
      dependency_hashes: Object.fromEntries(self.dependencies), scope: 'ordinary_scripts_and_read_only_pins_not_an_agent_loop' });
    return self;
  }
  async audit(kind: string, data: Obj): Promise<void> {
    await appendFile(this.auditPath, JSON.stringify({kind, utc: new Date().toISOString(), ...data}) + '\n', { encoding:'utf8', mode:0o600 });
  }
  async guard(): Promise<void> {
    if (await fileHash(this.jobPath) !== this.jobHash) fail('job_version_changed', '任务、预算或权限版本变化，停止使用旧进程。');
    for (const row of this.job.inputs) {
      const path = await privateFile(this.root, String(row.path));
      if (await fileHash(path) !== row.version_sha256) fail('source_version_changed', '来源版本已变化，请重新准备任务。');
    }
    for (const [path, expected] of this.dependencies) if (await fileHash(path) !== expected)
      fail('implementation_version_changed', '适配器或工具实现变化，停止旧版本执行。');
  }
  private outputAllowed(): void { if (!this.job.allow_output) fail('output_permission_denied', '任务仍为预览模式，不能生成文件。'); }
  async call(name: string, args: Obj): Promise<Obj> {
    await this.guard(); const start = Date.now();
    const result = await this.backend(name, args);
    await this.guard();
    await this.audit('backend_tool', { name, arguments: args, result, elapsed_ms: Date.now() - start });
    if (result.ok === false || result.isError === true || result.error)
      fail('backend_tool_failed', '实际后端拒绝了操作；保留具体报告，交回模型处理。', { backend_tool: name, backend_report: result });
    return result;
  }
  private async checkedDeck(result: Obj, deckId?: string): Promise<void> {
    if (!text(result.deck_id) || (deckId !== undefined && result.deck_id !== deckId) || !hash(result.file_sha256)
      || result.input_version !== this.inputVersion || result.slide_count !== this.job.slides || result.each_slide_has_editable_text !== true)
      fail('deck_contract_rejected', '实际PPT版本、页数或可编辑性不满足固定任务。');
  }
  private async checkedDelivery(result: Obj): Promise<void> {
    if (!text(result.deck_id) || !text(result.validation_id) || !hash(result.file_sha256) || result.input_version !== this.inputVersion
      || result.editable !== true || !Array.isArray(result.artifacts) || result.artifacts.length < this.job.slides + 1)
      fail('delivery_contract_rejected', '交付缺少完整版本和真实预览证据。');
    const target = await privateFile(this.root, String(result.path));
    if (await fileHash(target) !== result.file_sha256) fail('artifact_version_changed', 'PPT已变化，交付失效。');
    let pdf = 0; const pages = new Set<number>();
    for (const artifact of result.artifacts) {
      if (!object(artifact) || typeof artifact.path !== 'string' || !hash(artifact.sha256)) fail('delivery_contract_rejected', '预览产物缺少SHA证据。');
      const path = await privateFile(this.root, artifact.path);
      if (await fileHash(path) !== artifact.sha256) fail('preview_artifact_version_changed', '实际PDF或PNG变化，交付失效。');
      if (artifact.kind === 'pdf') pdf += 1;
      else if (artifact.kind === 'preview' && Number.isSafeInteger(artifact.page) && Number(artifact.page) >= 1 && Number(artifact.page) <= this.job.slides) {
        if (pages.has(Number(artifact.page))) fail('delivery_contract_rejected', '预览页号重复。');
        pages.add(Number(artifact.page));
      } else fail('delivery_contract_rejected', '预览类型或页号不合法。');
    }
    if (pdf !== 1 || pages.size !== this.job.slides) fail('delivery_contract_rejected', '真实PDF/逐页PNG不完整。');
  }
  async finish(deckId: string, origin: string): Promise<Obj> {
    this.outputAllowed();
    const inspected = await this.call('inspect_deck', {deck_id: deckId}); await this.checkedDeck(inspected, deckId);
    const validated = await this.call('validate_deck', {deck_id: deckId});
    if (validated.passed !== true) return {delivered:false, origin, ...validated, automatic_retry:false};
    if (validated.deck_id !== deckId || validated.file_sha256 !== inspected.file_sha256 || validated.input_version !== this.inputVersion
      || !text(validated.validation_id)) fail('validation_contract_rejected', '验证结果不属于当前PPT版本。');
    const delivered = await this.call('deliver_deck', {validation_id:validated.validation_id});
    await this.checkedDelivery(delivered);
    if (delivered.deck_id !== deckId || delivered.file_sha256 !== inspected.file_sha256) fail('delivery_contract_rejected', '交付期间PPT版本变化。');
    return {delivered:true, ...delivered, origin, mechanism:'ordinary_bounded_script', scientific_quality:'not_reviewed'};
  }
  async renderDelivery(plan: unknown): Promise<Obj> {
    this.outputAllowed(); preflightPlan(plan, this.job.slides);
    const rendered = await this.call('render_deck', {plan}); await this.checkedDeck(rendered);
    return this.finish(String(rendered.deck_id), 'render_delivery');
  }
  async reviseDelivery(deckId: string, updates: unknown): Promise<Obj> {
    this.outputAllowed();
    if (!text(deckId) || !Array.isArray(updates) || !updates.length || updates.length > this.job.slides)
      fail('invalid_revision', '修订需要已有deck_id及明确page/changes列表。');
    const pages = new Set<number>();
    for (const update of updates) {
      if (!object(update)) fail('invalid_revision', '修订项必须为对象。');
      keys(update,['page','changes']);
      if (!Number.isSafeInteger(update.page) || Number(update.page)<1 || Number(update.page)>this.job.slides || pages.has(Number(update.page))
        || !object(update.changes) || !Object.keys(update.changes).length || Object.keys(update.changes).some(key=>!SLIDE_KEYS.includes(key)))
        fail('invalid_revision', '修订页号必须唯一合法，changes仅允许页面字段。');
      pages.add(Number(update.page));
    }
    const result = await this.call('revise_deck', {deck_id:deckId, updates}); await this.checkedDeck(result);
    if (result.parent_deck_id !== deckId || !object(result.revision_audit) || result.revision_audit.passed !== true
      || result.revision_audit.non_target_slides_preserved !== true || result.revision_audit.shared_styles_preserved !== true
      || result.revision_audit.slide_count !== this.job.slides
      || canonical(result.revision_audit.changed_pages) !== canonical([...pages].sort((a,b)=>a-b)))
      fail('revision_contract_rejected', '非目标页保持检查未明确通过，拒绝交付。', {revision_audit: result.revision_audit});
    const delivered = await this.finish(String(result.deck_id), 'revise_delivery');
    return {...delivered,parent_deck_id:deckId,revision_audit:result.revision_audit};
  }
  async pinDeckPages(deckId: string, pagesCsv: string): Promise<Obj> {
    if (!text(deckId) || typeof pagesCsv!=='string' || !/^[1-9][0-9]?(?:,[1-9][0-9]?){0,29}$/.test(pagesCsv))
      fail('invalid_arguments','pages_csv为显式页号字符串，例如1,3；不自动选择页面。');
    const pages=pagesCsv.split(',').map(Number);
    if (pages.some(page=>page>this.job.slides) || new Set(pages).size!==pages.length)
      fail('invalid_arguments','页号必须唯一且在任务范围内。');
    const full=await this.call('read_deck_plan',{deck_id:deckId});
    if (full.deck_id!==deckId || full.input_version!==this.inputVersion || !hash(full.file_sha256) || !object(full.plan)
      || !Array.isArray(full.plan.slides) || full.plan.slides.length!==this.job.slides) fail('deck_contract_rejected','恢复计划缺少完整版本证据。');
    const plan=full.plan; const slides=plan.slides as unknown[];
    const projection={title:plan.title,template:plan.template??this.job.template,
      slides:pages.map(page=>({page,slide:slides[page-1]}))};
    const pin:Pinned={deck_id:deckId,file_sha256:String(full.file_sha256),pages,
      result_sha256:digest(projection),version_sha256:this.inputVersion};
    const sourceId='source-'+digest(pin).slice(0,32); this.pinned.set(sourceId,pin);
    return {source_id:sourceId,deck_id:deckId,version_sha256:this.inputVersion,file_sha256:pin.file_sha256,
      pages_csv:pagesCsv,scope:'explicit_pages_from_current_persisted_plan',scientific_quality:'not_reviewed'};
  }
  async readPinnedDeckPages(sourceId: string): Promise<Obj> {
    await this.guard(); const pin=this.pinned.get(sourceId);
    if (!pin) fail('invalid_source','先pin_deck_pages固定需要查看的明确页面。');
    const full=await this.call('read_deck_plan',{deck_id:pin.deck_id});
    if (full.file_sha256!==pin.file_sha256 || full.input_version!==this.inputVersion || !object(full.plan)
      || !Array.isArray(full.plan.slides) || full.plan.slides.length!==this.job.slides) fail('artifact_version_changed','固定PPT计划变化，拒绝旧页面句柄。');
    const plan=full.plan; const slides=plan.slides as unknown[];
    const projection={title:plan.title,template:plan.template??this.job.template,slides:pin.pages.map(page=>({page,slide:slides[page-1]}))};
    if (digest(projection)!==pin.result_sha256) fail('artifact_version_changed','固定页面内容已变化。');
    return {source_id:sourceId,deck_id:pin.deck_id,version_sha256:this.inputVersion,file_sha256:pin.file_sha256,
      total_slides:this.job.slides,...projection,scope:'explicit_pages_only_no_semantic_selection',scientific_quality:'not_reviewed'};
  }
}

/** 明确实际运行依赖；不将无关实验控制器纳入在线版本。 */
export async function dependencyFiles(root: string, backendServer: string, adapterDirectory: string): Promise<string[]> {
  const scene=resolve(root,'scenarios/research_ppt');
  const runtimeFiles=['service.py','server.py','delivery_server.py','recovery.py','documents.py','revision.py',
    'validation.py','restyle.py','generated_tools.py','figure_catalog.py','layout_learning.py',
    'contracts.json','version-fields.json','delivery-contracts.json','delivery-version-fields.json','package-lock.json',
    'dist/render.js','dist/layout-policy.js','dist/layout-policy-cli.js',
    'ts/render.ts','ts/layout-policy.ts','ts/layout-policy-cli.ts','ts/guard.ts','ts/guard-cli.ts',
    'dist/guard.js','dist/guard-cli.js','ts/delivery-adapter.ts','ts/mcp-adapter.ts'];
  return [...new Set([backendServer,...runtimeFiles.map(name=>resolve(scene,name)),
    resolve(adapterDirectory,'delivery-adapter.js'),resolve(adapterDirectory,'mcp-adapter.js')])];
}
