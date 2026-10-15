/** 明确 page/changes 的普通零模型入口；复用真实 MCP 交付，不解析自然语言。 */
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport, getDefaultEnvironment } from '@modelcontextprotocol/sdk/client/stdio.js';
import { createHash, randomUUID } from 'node:crypto';
import { appendFile, copyFile, mkdir, readFile, realpath, stat, writeFile } from 'node:fs/promises';
import { constants } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { AdapterRejected, canonical, digest, inside, object, preflightPlan, privateFile, validateEvidenceRebind, type Obj } from './delivery-adapter.js';
import { ExecutionPolicy } from './execution-policy.js';

const FIELDS = ['title','bullets','sources','notes','image','table','chart','layout','comparison','process','takeaway','archetype','evidence_notes'];
const REMOVABLE = new Set(['image','table','chart','layout','comparison','process','takeaway','archetype','evidence_notes']);
const TOOLS = ['list_inputs','list_templates','pin_source','read_source','read_page','extract_figure',
  'inspect_deck','deliver_deck','read_deck_plan','list_restorable_decks','render_deck','restyle_deck','revise_deck','validate_deck','build_delivery',
  'render_delivery','revise_delivery','pin_deck_pages','read_pinned_deck_pages','read_pending_plan','repair_pending_plan'];
export type DirectEditOptions = {job: string; deckId: string; updatesFile: string; output?: string; expectedSha256?: string; apply: boolean};
type Update = {page: number; changes: Obj};
type Difference = {page: number; field: string; before: unknown; after: unknown; removed: boolean};
const reject = (code: string, message: string): never => { throw new AdapterRejected(code,message); };
const hash = (x: unknown): x is string => typeof x === 'string' && /^[a-f0-9]{64}$/.test(x);
const shortString = (x: unknown): x is string => typeof x === 'string' && x.length > 0 && x.length <= 500 && !/[\x00-\x1f]/.test(x);
const fileHash = async (path: string): Promise<string> => createHash('sha256').update(await readFile(path)).digest('hex');

export function parseDirectEditArgs(args: string[]): DirectEditOptions {
  const values: Record<string,string> = {}; let apply = false;
  for (let i=0;i<args.length;i++) {
    const name=args[i];
    if (name==='--apply') {
      if (apply) reject('invalid_arguments','--apply 不能重复。');
      apply=true; continue;
    }
    if (!['--job','--deck-id','--updates','--out','--expect-sha256'].includes(name) || name in values
      || i+1>=args.length || args[i+1].startsWith('--')) reject('invalid_arguments','未知、重复或缺少值的参数。');
    values[name]=args[++i];
  }
  if (!shortString(values['--job']) || !shortString(values['--deck-id']) || !shortString(values['--updates']))
    reject('invalid_arguments','必须明确提供 --job、--deck-id 和 --updates；不支持 --pptx 或自然语言指令。');
  if (values['--out']!==undefined && !shortString(values['--out'])) reject('invalid_arguments','--out 路径无效。');
  if (values['--expect-sha256']!==undefined && !hash(values['--expect-sha256'])) reject('invalid_arguments','--expect-sha256 必须是预览显示的完整小写 SHA256。');
  if (apply && !hash(values['--expect-sha256'])) reject('expected_version_required','执行必须携带预览显示的 --expect-sha256。');
  return {job:values['--job'],deckId:values['--deck-id'],updatesFile:values['--updates'],output:values['--out'],
    expectedSha256:values['--expect-sha256'],apply};
}

/** 只合并用户明确值；容量/类型不合格时拒绝，不截短、推断、删事实或选页面。 */
export function previewExplicitUpdates(plan: unknown, updates: unknown, expectedSlides: number): {plan: Obj; updates: Update[]; differences: Difference[]; changedPages: number[]} {
  preflightPlan(plan,expectedSlides);
  if (!object(plan) || !Array.isArray(updates) || !updates.length || updates.length>expectedSlides)
    return reject('invalid_revision','updates 必须是明确 page/changes 的非空数组。');
  const merged = structuredClone(plan); const slides=merged.slides as Obj[];
  const pages = new Set<number>(); const differences: Difference[]=[];
  for (const item of updates) {
    if (!object(item) || Object.keys(item).length!==2 || !Object.hasOwn(item,'page') || !Object.hasOwn(item,'changes')
      || !Number.isSafeInteger(item.page) || Number(item.page)<1 || Number(item.page)>expectedSlides || pages.has(Number(item.page))
      || !object(item.changes) || !Object.keys(item.changes).length || Object.keys(item.changes).some(k=>!FIELDS.includes(k)))
      reject('invalid_revision','只接受唯一合法 page 和显式 changes；不能传递自动操作或未知字段。');
    const page=Number(item.page), changes=item.changes as Obj, original=structuredClone(slides[page-1]); pages.add(page);
    for (const [field,value] of Object.entries(changes)) {
      if (value===null && !REMOVABLE.has(field)) reject('invalid_revision','仅可选媒体/布局字段允许显式 null 移除。');
      const before=slides[page-1][field];
      if (value===null) delete slides[page-1][field]; else slides[page-1][field]=structuredClone(value);
      if (canonical(before)!==canonical(slides[page-1][field]) || (value===null && before!==undefined))
        differences.push({page,field,before:before??null,after:value,removed:value===null});
    }
    validateEvidenceRebind(original,slides[page-1],changes,page);
  }
  preflightPlan(merged,expectedSlides);
  if (!differences.length) reject('no_changes','指定值与当前页面一致，不创建无意义的新交付。');
  return {plan:merged,updates:structuredClone(updates) as Update[],differences,changedPages:[...pages].sort((a,b)=>a-b)};
}

export function directEditEnvironment(python: string, environment: NodeJS.ProcessEnv = process.env): Record<string,string> {
  if (!shortString(python)) reject('invalid_arguments','后端 Python 解释器路径无效。');
  const result: Record<string,string>={...getDefaultEnvironment(),SSS_PPT_DELIVERY_PYTHON:python,PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8'};
  for (const name of ['FONTCONFIG_FILE','FONTCONFIG_PATH']) if (environment[name]) result[name]=environment[name]!;
  return result;
}

/** 明确修订始终零模型；遵守冻结策略，不提供运行时 policy override。 */
export async function executeExplicitRevision(call: (name: string, args: Obj) => Promise<Obj>, policy: ExecutionPolicy,
  deckId: string, updates: Update[], expectedSlides: number, inputVersion: string): Promise<Obj> {
  const revisionArgs={deck_id:deckId,updates};
  if (policy.strategy==='legacy_model_selected') return call('revise_delivery',revisionArgs);
  const revised=await call('revise_deck',revisionArgs);
  if (policy.strategy==='host_delivery') {
    if (revised.delivered!==true || !object(revised.execution_policy)
      || revised.execution_policy.policy_sha256!==policy.snapshot().policy_sha256
      || revised.execution_policy.request_tool!=='revise_deck' || revised.execution_policy.host_script!=='revise_delivery')
      reject('delivery_contract_rejected','宿主交付未明确成功或不属于当前策略；不盲目重复验证/修改内容。');
    return revised;
  }
  const pages=updates.map(update=>update.page).sort((a,b)=>a-b);
  if (!shortString(revised.deck_id) || revised.deck_id===deckId || revised.parent_deck_id!==deckId || !hash(revised.file_sha256)
    || revised.input_version!==inputVersion || revised.slide_count!==expectedSlides || revised.each_slide_has_editable_text!==true
    || !object(revised.revision_audit) || revised.revision_audit.passed!==true
    || revised.revision_audit.non_target_slides_preserved!==true || revised.revision_audit.shared_styles_preserved!==true
    || revised.revision_audit.slide_count!==expectedSlides || canonical(revised.revision_audit.changed_pages)!==canonical(pages))
    reject('revision_contract_rejected','原子修订版本/可编辑性/非目标页保持未通过，不继续渲染交付。');
  const newDeck=String(revised.deck_id), inspected=await call('inspect_deck',{deck_id:newDeck});
  if (inspected.deck_id!==newDeck || inspected.file_sha256!==revised.file_sha256 || inspected.input_version!==inputVersion
    || inspected.slide_count!==expectedSlides || inspected.each_slide_has_editable_text!==true)
    reject('deck_contract_rejected','检查结果不属于当前修订版本。');
  const validated=await call('validate_deck',{deck_id:newDeck});
  if (validated.passed!==true || validated.deck_id!==newDeck || validated.file_sha256!==revised.file_sha256
    || validated.input_version!==inputVersion || !shortString(validated.validation_id))
    reject('validation_contract_rejected','真实渲染未通过或版本改变；不自动重试。');
  const delivered=await call('deliver_deck',{validation_id:validated.validation_id});
  if (delivered.deck_id!==newDeck || delivered.file_sha256!==revised.file_sha256 || delivered.input_version!==inputVersion
    || delivered.validation_id!==validated.validation_id || delivered.editable!==true || !Array.isArray(delivered.artifacts))
    reject('delivery_contract_rejected','原子交付回执缺少当前版本/可编辑性/真实预览。');
  return {...delivered,delivered:true,parent_deck_id:deckId,revision_audit:revised.revision_audit,
    origin:'explicit_revision_steps',mechanism:'ordinary_direct_edit_not_RSI'};
}

function payload(value: unknown): Obj {
  if (!object(value)) return reject('backend_protocol_rejected','实际 MCP 结果不是对象。');
  let output: unknown=value.structuredContent;
  if (!object(output) && Array.isArray(value.content)) {
    const block=value.content.find(x=>object(x) && x.type==='text' && typeof x.text==='string');
    if (object(block)) { try { output=JSON.parse(String(block.text)); } catch { /* Fail closed. */ } }
  }
  if (!object(output)) return reject('backend_protocol_rejected','实际 MCP 结果缺少结构化 JSON。');
  if (value.isError===true || output.ok===false) throw new AdapterRejected(typeof output.code==='string'?output.code:'backend_tool_failed',
    typeof output.message==='string'?output.message:'真实交付后端拒绝操作。',{backend_report:output});
  return output;
}

async function newPrivateDirectory(root: string, requested: string): Promise<string> {
  const target=resolve(requested), local=await realpath(resolve(root,'.local'));
  if (!inside(local,target) || target===local) reject('path_scope_rejected','输出必须是本仓库 .local 中的新子目录。');
  // 检查最近存在祖先的真实路径后逐级创建；不跟随越界符号链接。
  let parent=dirname(target); const missing:string[]=[];
  for (;;) {
    try { const actual=await realpath(parent); if (!inside(local,actual) || !(await stat(actual)).isDirectory()) reject('path_scope_rejected','输出祖先目录越界。'); break; }
    catch (error) { if (!object(error) || error.code!=='ENOENT') throw error; missing.push(parent); const next=dirname(parent); if (next===parent) throw error; parent=next; }
  }
  for (const path of missing.reverse()) { await mkdir(path,{mode:0o700}); if (!inside(local,await realpath(path))) reject('path_scope_rejected','输出父目录越界。'); }
  await mkdir(target,{mode:0o700});
  const actual=await realpath(target); if (!inside(local,actual)) reject('path_scope_rejected','输出目录越界。');
  return actual;
}

async function writeJson(path: string, value: Obj): Promise<void> {
  await writeFile(path,JSON.stringify(value,null,2)+'\n',{flag:'wx',mode:0o600});
}

export async function runDirectEdit(options: DirectEditOptions): Promise<Obj> {
  if (typeof options.apply!=='boolean' || !shortString(options.job) || !shortString(options.deckId) || !shortString(options.updatesFile)
    || (options.expectedSha256!==undefined && !hash(options.expectedSha256))) reject('invalid_arguments','运行入口需要明确参数和布尔 apply。');
  if (options.apply && !hash(options.expectedSha256)) reject('expected_version_required','执行必须携带预览显示的 --expect-sha256。');
  const area=resolve(dirname(fileURLToPath(import.meta.url)),'..'), root=await realpath(resolve(area,'../..'));
  const job=await privateFile(root,options.job), updatesFile=await privateFile(root,options.updatesFile);
  const raw=await readFile(updatesFile,'utf8'); if (Buffer.byteLength(raw,'utf8')>2_000_000) reject('invalid_revision','updates 文件超过2MB。');
  const updates:unknown=JSON.parse(raw.replace(/^\ufeff/,'')), jobData:unknown=JSON.parse(await readFile(job,'utf8'));
  if (!object(jobData) || !Number.isSafeInteger(jobData.slides) || Number(jobData.slides)<1 || Number(jobData.slides)>30
    || typeof jobData.allow_output!=='boolean') reject('invalid_job','任务需要固定页数和明确输出权限。');
  const checkedJob=jobData as Obj;
  const executionPolicy=new ExecutionPolicy(checkedJob.execution_policy);
  if (options.apply && !checkedJob.allow_output) reject('output_permission_denied','原任务没有 allow_output 授权；不会自行更改任务权限。');
  const adapterPath=await realpath(resolve(area,'dist/mcp-adapter.js'));
  if (!inside(area,adapterPath)) reject('path_scope_rejected','仅连接本场景安装的固定 MCP 适配器。');
  const output=await newPrivateDirectory(root,options.output??resolve(dirname(job),'direct-edits',randomUUID()));
  const started=Date.now(), attempts:Obj[]=[];
  const summary:Obj={schema_version:1,status:'started',operation:'explicit_slide_update',execution:'preview',mechanism:'ordinary_direct_edit_not_RSI',
    model_requests:0,input_tokens:0,output_tokens:0,provider_called:false,model_usage_basis:'this_code_path_has_no_provider_or_agent_loop',
    job,job_sha256:await fileHash(job),deck_id:options.deckId,updates_sha256:await fileHash(updatesFile),adapter_sha256:await fileHash(adapterPath),
    original_overwritten:false,output_directory:output,scientific_quality:'not_reviewed',independent_visual_quality:'not_reviewed'};
  summary.execution_policy=executionPolicy.snapshot();
  const client=new Client({name:'sss-ppt-explicit-direct-edit',version:'0.1.0'},{capabilities:{}});
  const transport=new StdioClientTransport({command:'node',args:[adapterPath,'--job',job],cwd:root,
    env:directEditEnvironment(process.env.SSS_PPT_DELIVERY_PYTHON??process.env.SSS_PYTHON??'python'),stderr:'pipe',maxBufferSize:20_000_000});
  transport.stderr?.on('data',chunk=>{ void appendFile(resolve(output,'mcp.stderr.log'),chunk,{mode:0o600}); });
  const call=async(name:string,args:Obj):Promise<Obj>=>{
    const t=Date.now(); const response=await client.callTool({name,arguments:args},undefined,{timeout:300_000});
    attempts.push({name,arguments:args,response,elapsed_ms:Date.now()-t});
    await appendFile(resolve(output,'actual-mcp-calls.jsonl'),JSON.stringify(attempts.at(-1))+'\n',{mode:0o600});
    return payload(response);
  };
  try {
    await client.connect(transport);
    const listing=await client.listTools();
    if (listing.nextCursor!==undefined || canonical(listing.tools.map(x=>x.name))!==canonical(TOOLS)) reject('backend_schema_rejected','实际 MCP 工具集合/顺序与可靠入口不一致。');
    summary.actual_tools_sha256=digest(listing.tools);
    const current=await call('read_deck_plan',{deck_id:options.deckId});
    if (current.deck_id!==options.deckId || !hash(current.file_sha256) || !hash(current.input_version)) reject('deck_contract_rejected','需要同 job 生成、保留完整计划且版本有效的稿；不支持任意外部 PPTX。');
    if (options.expectedSha256!==undefined && current.file_sha256!==options.expectedSha256) reject('artifact_version_changed','PPT SHA 与预览不一致，请重新预览。');
    const preview=previewExplicitUpdates(current.plan,updates,Number(checkedJob.slides));
    Object.assign(summary,{status:'previewed',original_sha256:current.file_sha256,input_version:current.input_version,
      changed_pages:preview.changedPages,differences:preview.differences,planned_plan_sha256:digest(preview.plan),
      expected_version_for_apply:current.file_sha256,budget:{model_usd:0,scope:'no_provider_invocation_not_an_API_billing_ledger'},
      impact:'新建修订副本与 PDF/PNG；仅显式目标页修改，原稿保留。'});
    await writeJson(resolve(output,'preview.json'),{...summary,updates:preview.updates});
    if (!options.apply) return summary;
    summary.execution='apply'; summary.status='applying';
    const revised=await executeExplicitRevision(call,executionPolicy,options.deckId,preview.updates,Number(checkedJob.slides),String(current.input_version));
    if (revised.delivered!==true || revised.parent_deck_id!==options.deckId || revised.deck_id===options.deckId
      || !hash(revised.file_sha256) || revised.input_version!==current.input_version || !object(revised.revision_audit) || revised.revision_audit.passed!==true
      || revised.revision_audit.non_target_slides_preserved!==true || revised.revision_audit.shared_styles_preserved!==true
      || canonical(revised.revision_audit.changed_pages)!==canonical(preview.changedPages) || !Array.isArray(revised.artifacts))
      reject('delivery_contract_rejected','实际修订/非目标页保持/渲染验收未明确通过，不导出。');
    // 原稿仍由实际后端核验，且目标页内容不得静默改变为其他值。
    const originalAgain=await call('read_deck_plan',{deck_id:options.deckId});
    if (originalAgain.file_sha256!==current.file_sha256 || canonical(originalAgain.plan)!==canonical(current.plan)) reject('original_changed','修订后原稿版本或计划改变。');
    const newPlan=await call('read_deck_plan',{deck_id:revised.deck_id});
    if (newPlan.file_sha256!==revised.file_sha256 || canonical(newPlan.plan)!==canonical(preview.plan)) reject('revision_contract_rejected','实际新稿计划与明确修订不一致。');
    const artifacts:Obj[]=[{kind:'pptx',path:revised.path,sha256:revised.file_sha256},...(revised.artifacts as unknown[]).filter(object)];
    if (artifacts.length!==Number(checkedJob.slides)+2 || artifacts.filter(x=>x.kind==='pdf').length!==1
      || canonical(artifacts.filter(x=>x.kind==='preview').map(x=>x.page).sort((a,b)=>Number(a)-Number(b)))!==canonical(Array.from({length:Number(checkedJob.slides)},(_,i)=>i+1)))
      reject('delivery_contract_rejected','交付需要一个 PPTX、一个 PDF 和每页 PNG。');
    const exported:Obj[]=[];
    for (const artifact of artifacts) {
      if (typeof artifact.path!=='string' || !hash(artifact.sha256)) reject('delivery_contract_rejected','产物缺少文件和 SHA。');
      const source=await privateFile(root,String(artifact.path));
      if (await fileHash(source)!==artifact.sha256) reject('artifact_version_changed','交付产物发生变化。');
      const name=artifact.kind==='pptx'?'revised.pptx':artifact.kind==='pdf'?'revised.pdf':`slide-${String(artifact.page).padStart(2,'0')}.png`;
      const target=resolve(output,name); await copyFile(source,target,constants.COPYFILE_EXCL);
      if (await fileHash(target)!==artifact.sha256) reject('export_failed','新副本复制后的 SHA 不一致。');
      exported.push({...artifact,path:target});
    }
    Object.assign(summary,{status:'delivered',delivery:revised,exported_artifacts:exported,new_deck_id:revised.deck_id,
      revision_audit:revised.revision_audit,original_preserved:true});
    return summary;
  } catch (error) {
    Object.assign(summary,{status:'failed',code:error instanceof AdapterRejected?error.code:'direct_edit_failed',
      error_type:error instanceof Error?error.name:typeof error,message:error instanceof AdapterRejected?error.message:'执行失败，详细信息保留在私有 MCP 日志。',
      ...(error instanceof AdapterRejected?error.details:{})});
    throw error;
  } finally {
    try { await client.close(); } finally {
      summary.elapsed_ms=Date.now()-started; summary.actual_tool_calls=attempts.length;
      await writeJson(resolve(output,'receipt.json'),summary);
    }
  }
}

if (process.argv[1] && resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  const args=process.argv.slice(2);
  if (args.length===1 && args[0]==='--help') {
    process.stdout.write('明确页修改（普通零模型路径）\n'+
      'python -m scenarios.research_ppt.direct_edit --job <job.json> --deck-id <id> --updates <updates.json> [--out <new-private-dir>]\n'+
      '默认预览；执行加 --apply --expect-sha256 <preview-original-sha256>。\n'+
      '仅支持同 job 生成且保留完整计划的稿；拒绝任意外部 PPTX、自然语言及自动改写。\n');
  } else Promise.resolve().then(()=>runDirectEdit(parseDirectEditArgs(args))).then(value=>process.stdout.write(JSON.stringify(value,null,2)+'\n')).catch(error=>{
    process.stderr.write(JSON.stringify({ok:false,code:error instanceof AdapterRejected?error.code:'direct_edit_failed',
      message:error instanceof AdapterRejected?error.message:'入口未完成；请检查私有运行记录。',model_requests:0,provider_called:false})+'\n'); process.exitCode=2;
  });
}
