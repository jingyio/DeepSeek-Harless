/** 科研 PPT stdio MCP proxy：复用场景工具；TS负责固定有限dispatch，Python仅为现有工具后端。 */
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport, getDefaultEnvironment } from '@modelcontextprotocol/sdk/client/stdio.js';
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { CallToolRequestSchema, ListToolsRequestSchema, type Tool } from '@modelcontextprotocol/sdk/types.js';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { appendFile, readFile, realpath, stat, writeFile } from 'node:fs/promises';
import { AdapterRejected, DeliveryAdapter, dependencyFiles, digest, inside, object, preflightPlan, privateFile, type Obj } from './delivery-adapter.js';
import { PendingPlanStore } from './pending-plan.js';
import { PlanRecovery } from './plan-recovery.js';
import { ExecutionPolicy } from './execution-policy.js';

const BASE_TOOL_ORDER = ['list_inputs','list_templates','pin_source','read_source','read_page','extract_figure',
  'inspect_deck','deliver_deck','read_deck_plan','list_restorable_decks','render_deck','restyle_deck','revise_deck','validate_deck','build_delivery'];
let liveClient: Client | null = null;
const strings = {type:'string',minLength:1,maxLength:500};
const input = (properties: Record<string, object>, required: string[]): Tool['inputSchema'] => ({type:'object',properties,required,additionalProperties:false});
const annotated = (name: string, description: string, properties: Record<string, object>, required: string[], readOnly: boolean): Tool => ({name,description,
  inputSchema:input(properties,required),annotations:{readOnlyHint:readOnly,destructiveHint:false,openWorldHint:false}});
const ARCHETYPE_SCHEMA = {type:'string',enum:['evidence-focus','result-summary','method-map']};
const EVIDENCE_NOTES_SCHEMA = {type:'array',maxItems:3,items:{type:'object',required:['label','text','source_index'],additionalProperties:false,
  properties:{label:{type:'string',minLength:1,maxLength:24},text:{type:'string',minLength:1,maxLength:110},source_index:{type:'integer',minimum:1,maximum:20}}}};
const SLIDE_PROPERTIES = {
  title:{type:'string',minLength:1,maxLength:70},bullets:{type:'array',maxItems:5,items:{type:'string',minLength:1,maxLength:150}},
  sources:{type:'array',minItems:1,maxItems:20,items:{type:'object',required:['source_id','page'],additionalProperties:false,
    properties:{source_id:strings,page:{type:'integer',minimum:1,maximum:200}}}},
  notes:{type:'string',maxLength:6000},layout:{type:'string',enum:['title','content','image','table','chart','section','comparison','process']},
  image:{type:'object',required:['source_id','image_id'],additionalProperties:false,properties:{source_id:strings,image_id:strings}},
  table:{type:'array',minItems:2,maxItems:6,items:{type:'array',minItems:1,maxItems:4,items:{type:'string',minLength:1,maxLength:45}}},
  chart:{type:'object',required:['type','categories','series'],additionalProperties:false,properties:{
    type:{type:'string',enum:['bar','line']},categories:{type:'array',minItems:2,maxItems:10,items:{type:'string',minLength:1,maxLength:25}},
    series:{type:'array',minItems:1,maxItems:3,items:{type:'object',required:['name','values'],additionalProperties:false,properties:{
      name:{type:'string',minLength:1,maxLength:30},values:{type:'array',minItems:2,maxItems:10,items:{type:'number'}}}}},
    x_label:{type:'string',minLength:1,maxLength:40},y_label:{type:'string',minLength:1,maxLength:40},unit:{type:'string',minLength:1,maxLength:40}}},
  comparison:{type:'object',required:['left','right'],additionalProperties:false,properties:Object.fromEntries(['left','right'].map(side=>[side,
    {type:'object',required:['title','bullets'],additionalProperties:false,properties:{title:{type:'string',minLength:1,maxLength:35},
      bullets:{type:'array',maxItems:4,items:{type:'string',minLength:1,maxLength:100}}}}]))},
  process:{type:'object',required:['steps'],additionalProperties:false,properties:{steps:{type:'array',minItems:2,maxItems:5,
    items:{type:'object',required:['label','detail'],additionalProperties:false,properties:{
      label:{type:'string',minLength:1,maxLength:28},detail:{type:'string',minLength:1,maxLength:90}}}}}},
  takeaway:{type:'string',minLength:1,maxLength:90},
  archetype:ARCHETYPE_SCHEMA,evidence_notes:EVIDENCE_NOTES_SCHEMA,
};
const REMOVABLE_FIELDS = new Set(['image','table','chart','layout','comparison','process','takeaway','archetype','evidence_notes']);
const CHANGES_SCHEMA = {type:'object',minProperties:1,additionalProperties:false,
  properties:Object.fromEntries(Object.entries(SLIDE_PROPERTIES).map(([field,schema])=>[field,
    REMOVABLE_FIELDS.has(field)?{anyOf:[schema,{type:'null'}]}:schema]))};
const PLAN_SCHEMA = {type:'object',required:['title','slides'],additionalProperties:false,properties:{
  title:{type:'string',minLength:1,maxLength:100},template:{type:'string',enum:['academic','lab']},
  slides:{type:'array',minItems:1,maxItems:30,items:{type:'object',required:['title','sources'],additionalProperties:false,properties:SLIDE_PROPERTIES}}}};

/*
 * DeepSeek's function schema validator accepts the small JSON-schema subset
 * used by the original 19-tool surface, but rejects the deeply nested
 * chart/process/comparison/recovery schemas.  Keep the provider contract
 * bounded and discoverable while retaining the complete checks above in
 * preflightPlan/mergePendingPatch.  In other words, this is a transport
 * compatibility projection, not a weaker runtime validator.
 */
const PROVIDER_SLIDE_PROPERTIES = {
  title:SLIDE_PROPERTIES.title, bullets:SLIDE_PROPERTIES.bullets, sources:SLIDE_PROPERTIES.sources,
  notes:SLIDE_PROPERTIES.notes, layout:SLIDE_PROPERTIES.layout, image:SLIDE_PROPERTIES.image,
  table:SLIDE_PROPERTIES.table,
  chart:{type:'object'}, comparison:{type:'object'}, process:{type:'object'},
  takeaway:SLIDE_PROPERTIES.takeaway, archetype:SLIDE_PROPERTIES.archetype,
  evidence_notes:EVIDENCE_NOTES_SCHEMA,
};
const PROVIDER_PLAN_SCHEMA = {type:'object',required:['title','slides'],additionalProperties:false,properties:{
  title:{type:'string',minLength:1,maxLength:100},template:{type:'string',enum:['academic','lab']},
  slides:{type:'array',minItems:1,maxItems:30,items:{type:'object',required:['title','sources'],additionalProperties:false,
    properties:PROVIDER_SLIDE_PROPERTIES}}}};
const PROVIDER_CHANGES_SCHEMA = {type:'object',minProperties:1,additionalProperties:false,
  properties:Object.fromEntries(Object.entries(PROVIDER_SLIDE_PROPERTIES).map(([field,schema])=>[field,
    REMOVABLE_FIELDS.has(field)?{anyOf:[schema,{type:'null'}]}:schema]))};
const PROVIDER_REPAIR_SCHEMA = {
  draft_id:strings,version_sha256:strings,
  metadata:{type:'object'},
  updates:{type:'array',maxItems:30,items:{type:'object',required:['page','changes'],properties:{page:{type:'integer',minimum:1,maximum:30},changes:{type:'object'}}}},
  replacements:{type:'array',maxItems:30,items:{type:'object',required:['page','slide'],properties:{page:{type:'integer',minimum:1,maximum:30},slide:{type:'object'}}}},
  deletions:{type:'array',maxItems:30,items:{type:'integer',minimum:1,maximum:30}},
  insertions:{type:'array',maxItems:30,items:{type:'object',required:['before_page','slide'],properties:{before_page:{type:'integer',minimum:1,maximum:31},slide:{type:'object'}}}},
};
export const ADAPTER_TOOLS: Tool[] = [
  annotated('render_delivery','Ordinary bounded script: preflight then real render-inspect-validate-deliver; never invent or change content; not a learned Motif.',
    {plan:PROVIDER_PLAN_SCHEMA},['plan'],false),
  annotated('revise_delivery','Ordinary bounded script: revise explicit pages in a new copy, verify all non-target pages, real inspect-validate-deliver; not a learned Motif.',
    {deck_id:strings,updates:{type:'array',minItems:1,maxItems:30,items:{type:'object',required:['page','changes'],additionalProperties:false,
      properties:{page:{type:'integer',minimum:1,maximum:30},changes:PROVIDER_CHANGES_SCHEMA}}}},['deck_id','updates'],false),
  annotated('pin_deck_pages','Pin explicitly selected pages of a persisted deck. pages_csv contains exact page numbers such as 2,5; no automatic semantic selection.',
    {deck_id:strings,pages_csv:{type:'string',minLength:1,maxLength:89,pattern:'^[1-9][0-9]?(?:,[1-9][0-9]?){0,29}$'}},['deck_id','pages_csv'],true),
  annotated('read_pinned_deck_pages','Read only the explicitly pinned page plans of the current persisted PPT. Recheck source and deck versions; no content changes.',
    {source_id:strings},['source_id'],true),
  annotated('read_pending_plan','Read 1–5 explicit pages from a failed draft using its current version. Only host_delivery permits this; ordinary baseline_steps rejects it.',
    {draft_id:strings,version_sha256:strings,pages:{type:'array',minItems:1,maxItems:5,items:{type:'integer',minimum:1,maximum:30}}},
    ['draft_id','version_sha256','pages'],true),
  annotated('repair_pending_plan','Repair a stored failed draft by explicit local changes and run the original delivery checks. Do not resend the full plan; host_delivery only. Page numbers refer to the draft before modification.',
    {...PROVIDER_REPAIR_SCHEMA},
    ['draft_id','version_sha256'],false),
];

/** 两组使用相同准确契约，实际运行仍独立核验，schema不代替守卫。 */
export function advertisedTools(base:Tool[],slides:number):Tool[] {
  const plan=structuredClone(PLAN_SCHEMA);plan.properties.slides.minItems=slides;plan.properties.slides.maxItems=slides;
  return [...base.map(tool=>tool.name==='render_deck'
    ? annotated('render_deck','Create a new cited editable PPTX. plan requires title and exactly the task slide count including cover. Failure may return a pending draft for explicit local repair in host_delivery.',{plan:{...PROVIDER_PLAN_SCHEMA,properties:{...PROVIDER_PLAN_SCHEMA.properties,slides:{...PROVIDER_PLAN_SCHEMA.properties.slides,minItems:slides,maxItems:slides}}}},['plan'],false)
    : tool.name==='revise_deck'
      ? annotated('revise_deck','Revise explicit pages of an existing same-task deck in a new copy; retain other pages and revalidate.',
        {deck_id:strings,updates:{type:'array',minItems:1,maxItems:30,items:{type:'object',required:['page','changes'],additionalProperties:false,
          properties:{page:{type:'integer',minimum:1,maximum:30},changes:PROVIDER_CHANGES_SCHEMA}}}},['deck_id','updates'],false)
      : tool),...ADAPTER_TOOLS];
}

function payload(value: unknown): Obj {
  if (!object(value)) throw new AdapterRejected('backend_protocol_rejected','后端MCP结果不是对象。');
  const structured=value.structuredContent;
  let result: unknown=structured;
  if (!object(result) && Array.isArray(value.content)) {
    const block=value.content.find(block=>object(block) && block.type==='text' && typeof block.text==='string');
    if (object(block)) { try { result=JSON.parse(String(block.text)); } catch { /* Fail closed below. */ } }
  }
  if (!object(result)) throw new AdapterRejected('backend_protocol_rejected','后端MCP没有完整可解析JSON；不从文本猜句柄。');
  if (value.isError===true) return {...result,isError:true};
  return result;
}
function result(value: Obj, isError=false) {
  return {content:[{type:'text' as const,text:JSON.stringify(value)}],structuredContent:value,...(isError?{isError:true}:{})};
}
function boundedArgs(args: unknown): Obj {
  if (!object(args) || JSON.stringify(args).length>2_000_000) throw new AdapterRejected('invalid_arguments','参数必须是有界JSON对象。');
  return args;
}
function exactArgs(args: Obj, fields: string[]): void {
  if (Object.keys(args).some(key=>!fields.includes(key)) || fields.some(key=>!Object.hasOwn(args,key)))
    throw new AdapterRejected('invalid_arguments','参数字段不完整或包含不支持字段。');
}
function stringArg(args: Obj, name: string): string {
  const value=args[name];
  if (typeof value!=='string' || !value.length || value.length>500 || /[\x00-\x1f]/.test(value))
    throw new AdapterRejected('invalid_arguments',`${name}必须是有界字符串，不会自动转换错误类型。`);
  return value;
}

async function main(): Promise<void> {
  const args=process.argv.slice(2); const flag=(name:string):string|undefined=>{ const i=args.indexOf(name); return i>=0?args[i+1]:undefined; };
  const area=resolve(dirname(fileURLToPath(import.meta.url)),'..');
  const root=await realpath(flag('--root')??resolve(area,'../..'));
  const webPrivateRoot=args.includes('--web-session') ? process.env.HARLESS_PRIVATE_ROOT : undefined;
  const job=await privateFile(root,flag('--job')??process.env.SSS_PPT_JOB??'',webPrivateRoot);
  const expectedRoot=await realpath(resolve(area,'../..'));
  if (root!==expectedRoot) throw new AdapterRejected('path_scope_rejected','root必须匹配已安装场景所在仓库。');
  const fixedBackend=await realpath(resolve(area,'delivery_server.py'));
  if (!inside(resolve(root,'scenarios/research_ppt'),fixedBackend) || !(await stat(fixedBackend)).isFile())
    throw new AdapterRejected('path_scope_rejected','固定后端必须是场景目录内的文件，拒绝越界符号链接。');
  const backendPath=await realpath(flag('--backend')??fixedBackend);
  if (backendPath!==fixedBackend) throw new AdapterRejected('path_scope_rejected','仅启动固定场景delivery_server.py后端。');
  const jobData:unknown=JSON.parse(await readFile(job,'utf8'));
  if (!object(jobData)) throw new AdapterRejected('invalid_job','任务必须是JSON对象。');
  const executionPolicy=new ExecutionPolicy(jobData.execution_policy);
  const client=new Client({name:'sss-ppt-delivery-backend-client',version:'0.1.0'},{capabilities:{}});
  liveClient=client;
  const renderEnvironment: Record<string,string> = {};
  for (const name of ['FONTCONFIG_FILE','FONTCONFIG_PATH']) {
    if (process.env[name]) renderEnvironment[name] = process.env[name]!;
  }
  const backendArgs = [backendPath, ...(webPrivateRoot ? ['--web-session','--private-root',dirname(job)] : [])];
  const transport=new StdioClientTransport({command:process.env.SSS_PPT_DELIVERY_PYTHON??process.env.SSS_PYTHON??'python',args:backendArgs,cwd:root,
    env:{...getDefaultEnvironment(),...renderEnvironment,PYTHONPATH:root,PYTHONUTF8:'1',SSS_PPT_JOB:job},stderr:'pipe',maxBufferSize:20_000_000});
  transport.stderr?.on('data',chunk=>{ void appendFile(resolve(dirname(job),'delivery-backend.stderr.log'),chunk,{mode:0o600}); });
  await client.connect(transport);
  const listing=await client.listTools();
  if (listing.nextCursor!==undefined) throw new AdapterRejected('backend_schema_rejected','后端工具分页不满足冻结工具集合。');
  const expected=[...BASE_TOOL_ORDER];
  const byName=new Map(listing.tools.map(tool=>[tool.name,tool]));
  if (byName.size!==expected.length || expected.some(name=>!byName.has(name)))
    throw new AdapterRejected('backend_schema_rejected','实际后端工具集合与冻结配置不一致。');
  const offered=advertisedTools(expected.map(name=>byName.get(name)!),Number(jobData.slides));
  const schemaDigest=digest(offered);
  const adapterDirectory=dirname(fileURLToPath(import.meta.url));
  const adapter=await DeliveryAdapter.create(root,job,async(name,args)=>payload(await client.callTool({name,arguments:args},undefined,{timeout:240_000})),
    await dependencyFiles(root,backendPath,adapterDirectory),args.includes('--web-session'),webPrivateRoot);
  const pendingPlans=executionPolicy.strategy==='host_delivery' && jobData.allow_output===true
    ? await PendingPlanStore.create({root,jobPath:job,privateRoot:adapter.privateRoot,expectedSlides:Number(jobData.slides),
      evidence:adapter.versionEvidence(schemaDigest),guard:()=>adapter.guard(),audit:(kind,data)=>adapter.audit(kind,data)}) : undefined;
  const recovery=new PlanRecovery(pendingPlans,executionPolicy,adapter);
  const runtime={schema_version:1,backend_tool_order:expected,advertised_tool_order:offered.map(tool=>tool.name),actual_tools:offered,
    schema_sha256:schemaDigest,input_version:adapter.inputVersion,job:job,execution_policy:executionPolicy.snapshot(),
    scope:'actual_mcp_proxy_schema_not_provider_payload'};
  if (flag('--export-schema')) {
    const target=resolve(flag('--export-schema')!);
    const parent=await realpath(dirname(target));
    const { inside }=await import('./delivery-adapter.js');
    if (!inside(resolve(root,'.local'),parent)) throw new AdapterRejected('path_scope_rejected','schema快照必须在私有目录。');
    await writeFile(target,JSON.stringify(runtime,null,2)+'\n',{flag:'wx',mode:0o600});
    await client.close(); process.stdout.write(JSON.stringify({schema_path:target,schema_sha256:schemaDigest})+'\n'); return;
  }
  await adapter.audit('actual_schema',runtime);
  await adapter.audit('execution_policy_loaded',executionPolicy.snapshot());
  const server=new Server({name:'SSS research PPT finite TS delivery adapter',version:'0.1.0'},{capabilities:{tools:{}}});
  let queue:Promise<unknown>=Promise.resolve();
  server.setRequestHandler(ListToolsRequestSchema,async()=>({tools:offered}));
  server.setRequestHandler(CallToolRequestSchema,async request=>{
    const pending=queue.then(async()=>{
      let args: Obj={};
      try {
        await adapter.guard(); args=boundedArgs(request.params.arguments??{});
        const name=request.params.name;
        if (name==='read_pending_plan') {
          exactArgs(args,['draft_id','version_sha256','pages']);return result(await recovery.read(args));
        }
        if (name==='repair_pending_plan') {
          const value=await recovery.repair(args);
          await adapter.guard();await adapter.audit('adapter_tool',{name,arguments:args,result:value});
          return result(value,value.ok===false||value.delivered===false);
        }
        if (name==='render_deck') {
          const recovered=await recovery.render(args);
          if (recovered!==undefined) {
            await adapter.guard();await adapter.audit('adapter_tool',{name,arguments:args,result:recovered});
            return result(recovered,recovered.delivered!==true);
          }
          exactArgs(args,['plan']);preflightPlan(args.plan,Number(jobData.slides));
        }
        const controlled=await executionPolicy.dispatch(adapter,name,args);
        if (controlled!==undefined) {
          await adapter.guard(); await adapter.audit('adapter_tool',{name,arguments:args,result:controlled});
          return result(controlled);
        }
        if (byName.has(name)) return result(await adapter.call(name,args));
        let value:Obj;
        switch(name) {
          case 'render_delivery': exactArgs(args,['plan']); value=await adapter.renderDelivery(args.plan); break;
          case 'revise_delivery': exactArgs(args,['deck_id','updates']); value=await adapter.reviseDelivery(stringArg(args,'deck_id'),args.updates); break;
          case 'pin_deck_pages': exactArgs(args,['deck_id','pages_csv']); value=await adapter.pinDeckPages(stringArg(args,'deck_id'),stringArg(args,'pages_csv')); break;
          case 'read_pinned_deck_pages': exactArgs(args,['source_id']); value=await adapter.readPinnedDeckPages(stringArg(args,'source_id')); break;
          default: throw new AdapterRejected('tool_not_allowed','工具不在冻结集合中。');
        }
        await adapter.guard(); await adapter.audit('adapter_tool',{name,arguments:args,result:value}); return result(value);
      } catch(error) {
        const known=error instanceof AdapterRejected;
        const report={ok:false,code:known?error.code:'adapter_execution_failed',message:known?error.message:'操作未完成；详细错误只留私有日志。',
          ...(known?error.details:{}),retry:'由模型审阅反馈后选择修正或回退；适配器不自动重试。'};
        await adapter.audit('adapter_failure',{name:request.params.name,arguments:args,report,error_type:error instanceof Error?error.name:typeof error});
        return result(report,true);
      }
    });
    queue=pending.then(()=>undefined,()=>undefined); return pending;
  });
  const stdio=new StdioServerTransport(process.stdin,process.stdout,{maxBufferSize:20_000_000});
  const close=()=>{ void server.close().finally(()=>client.close()).finally(()=>process.exit(0)); };
  process.once('SIGTERM',close);process.once('SIGINT',close);process.stdin.once('end',close);
  await server.connect(stdio);
}

if (process.argv[1] && resolve(process.argv[1])===fileURLToPath(import.meta.url)) main().catch(async error=>{process.stderr.write(JSON.stringify({ok:false,code:error instanceof AdapterRejected?error.code:'adapter_start_failed',
  error_type:error instanceof Error?error.name:typeof error})+'\n');
  try { await liveClient?.close(); } finally { process.exit(1); }
});
