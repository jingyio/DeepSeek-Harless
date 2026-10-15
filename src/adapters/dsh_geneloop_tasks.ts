/** Dynamic business tasks on the official Harness Web/Session lifecycle. */
import {managementBridge,attachManagementRuntime,confirmManagementEffect,managementAcceptance} from './harless_management.ts';
import {createAcceptanceGuard} from './dsh_acceptance_guard.ts';
import {OperationJob} from './operation_job.ts';
import { createHash, randomUUID } from 'node:crypto';
import { appendFileSync, lstatSync, mkdirSync, readFileSync, readdirSync, writeFileSync, renameSync } from 'node:fs';
import { basename, extname, isAbsolute, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { resolveAdapterOptions } from '@deepseek-ai/dsh-llm-deepseek';
import { WebDeepSeekAdapter, webReasoningEffort } from './harless_reasoning.ts';
import type { WebReasoningEffort } from './harless_reasoning.ts';
import { isAgentLoopRequest, createUserMessage, createAssistantMessage } from '@deepseek-ai/dsh-llm';
import { scopeOf } from '@deepseek-ai/dsh-scope';
import { ApiSessionNotFound } from '@deepseek-ai/dsh-api-session-controller';
import { createOnlineInterceptor, loopbackSimilarity } from './dsh_online_motif.mjs';
import { digest, offeredSchemaMatches } from '../motif_core/online_skill_runtime.mjs';
import { normalizeWebTaskRequest, WebTaskRequestError } from './web_task_request.ts';
import { sceneCatalog, initialSelection, changeSelection, parseHarlessCommand, sceneShortcut, parseSceneShortcut, SettingsError } from './harless_settings.ts';
import { sessionWorkspace, sessionPreset, bindSceneInputs, sceneOptions, scopeDigest, sceneAttachmentContext } from './harless_task_scope.ts';
import type { SceneOptions } from './harless_task_scope.ts';
import type { Scene, Selection } from './harless_settings.ts';
import type { NormalizedWebTask, PromptPart, ExecutionMode } from './web_task_request.ts';
import {bindUploadedPptTask,bindUploadedSourceTask,structuralOnlySimilarity} from './harless_rsi_binding.ts';
import {createComparisonService} from './harless_comparison.ts';
import {comparisonArtifacts,captureComparisonDeliveries} from './harless_comparison_artifacts.ts';
import {dataInterceptor,paperShadowInterceptor,validateExistingData} from './harless_legacy_motif.ts';
import {bindReportAnswer} from './harless_report_answer.ts';
import {createTaskProgress} from './harless_task_progress.ts';
import {bindProductPrompt} from './harless_product_prompt.ts';
import {protectPublicSessionOutput, publicTaskView} from './harless_public_output.ts';
import {createSessionBranchService,sessionBranchTitle} from './harless_session_branch.ts';
import {registerManagedWorkspaceRoutes} from './harless_managed_workspaces.ts';
import {registerPrivateLanes} from './harless_private_lanes.ts';
import {createSessionTrash, protectDeletedSessions, protectDeletedSessionFiles, protectDeletedSessionQuery, registerSessionTrashRoute, SessionTrashError} from './harless_session_trash.ts';

export const name = 'sss-web-tasks';
export const inject = ['llm', 'agents', 'sessionController', 'sessionProjections', 'connection', 'webServer', 'fileUploads', 'commands', 'agentPresets', 'attachments', 'workspaceRegistry', 'workspaceController'];
type Policy = {
  output: string; user_id?: string; allowed_tools: string[]; endpoint: string; max_output_tokens: number | null;
  mode: ExecutionMode; budget_usd: number; request_limit?: number | null; run_budget_usd?: number | null; run_request_limit?: number | null; capability_profile: string;
  provider_mode: 'mock' | 'real'; control_endpoint: string; control_token: string;
  budget_broker_endpoint?: string;
  budget_task_prefix?: string;
  comparison_scenes?: string[];
  ownership_legacy_outputs?: string[];
  manifest?: string; task?: string; certified_input_sha256?: string;
  embedding_endpoint?: string; embedding_model?: string; fixture?: string;
  scenes?: Scene[]; scene_registry_sha256?: string;
  resources?: Record<string, { version: string; text: string }>;
  models?: ModelOption[];
};
type ModelOption = { provider: string; model: string; label: string; available: boolean };
type Task = {
  request: NormalizedWebTask; delivery: PromptPart[]; confirmation_digest: string;
  status: string; created_at: string; started_at?: string; finished_at?: string;
  failure: string | null; fallback_reason: string | null; answer: string;
  output: string; stats: Record<string, any>; interceptor?: any; management?: any;
  humans: Map<string, string>; current_humans: Set<string>;
  sources: { resource_id: string; version: string; sha256: string }[];
  scene: Scene; selection: Selection; tools: any[]; manifest_sha256: string | null; binding_sha256: string | null;
  closing?: Promise<void>; entrypoint: 'workbench' | 'native_chat';
  model_option: ModelOption; reasoning_effort?: WebReasoningEffort; workspace: string; scene_options: SceneOptions; scene_inputs: any[]; source_pending?: boolean; scope_sha256: string | null;
  budget_session_id: string;
  source_task_id?: string;
  bound_binding_sha256?: string | null;
};
class TaskError extends Error {
  code: string; status: number;
  constructor(code: string, message: string, status = 400) { super(message); this.code = code; this.status = status; }
}
const sha = (value: string | Uint8Array) => createHash('sha256').update(value).digest('hex');
const fileSha = (path: string | undefined) => { try { return path ? sha(readFileSync(path)) : null; } catch { return null; } };
const utc = () => new Date().toISOString();
const terminal = new Set(['completed', 'failed', 'cancelled', 'budget_exhausted']);
const loopback = (endpoint: string) => /^http:\/\/127\.0\.0\.1:\d+(?:\/v1)?$/.test(endpoint);
const json = (path: string, value: unknown) => {
  writeFileSync(path + '.tmp', JSON.stringify(value, null, 2), { mode: 0o600 });
  renameSync(path + '.tmp', path);
};

const browserJson = (value: any, init?: ResponseInit) => Response.json(publicTaskView(value), init);

export async function apply(ctx: any) {
  const config: Policy = JSON.parse(readFileSync(process.env.SSS_WEB_POLICY!, 'utf8'));
  if (!loopback(config.endpoint) || !loopback(config.control_endpoint) ||
      (config.budget_broker_endpoint !== undefined && !loopback(config.budget_broker_endpoint)) ||
      (config.budget_task_prefix !== undefined && !/^[a-f0-9]{8}$/.test(config.budget_task_prefix)) ||
      !config.control_token || !Array.isArray(config.allowed_tools) ||
      !['baseline', 'shadow', 'execute'].includes(config.mode) ||
      !['mock', 'real'].includes(config.provider_mode)) throw Error('Invalid dynamic Web policy');
  mkdirSync(join(config.output, 'tasks'), { recursive: true, mode: 0o700 });
  const tasks = new Map<string, Task>(), sessions = new Map<string, string>();
  const progress = new Map<string, ReturnType<typeof createTaskProgress>>();
  const brokerMode = config.budget_broker_endpoint !== undefined;
  if (config.comparison_scenes && (!brokerMode || !Array.isArray(config.comparison_scenes) || config.comparison_scenes.some(id => !['ppt', 'paper-proofreading', 'research-data-analysis', 'literature'].includes(id)))) throw Error('Invalid comparison policy');
  let comparisons: ReturnType<typeof createComparisonService> | undefined;
  let trash: ReturnType<typeof createSessionTrash>;
  const modelOptions = config.models ?? [{ provider: 'deepseek-official', model: 'deepseek-flash', label: 'DeepSeek Flash', available: true }];
  const defaultModel = modelOptions.find(option => option.available);
  if (!defaultModel || modelOptions.some(option => !/^[a-z][a-z0-9-]*$/.test(option.provider) || !/^[A-Za-z0-9._-]+$/.test(option.model) ||
        typeof option.label !== 'string' || !option.label || typeof option.available !== 'boolean') ||
      new Set(modelOptions.map(option => option.model)).size !== modelOptions.length) throw Error('Invalid server model catalog');
  const modelSelections = new Map<string, ModelOption>();
  const reasoningSelections = new Map<string, WebReasoningEffort>();
  const reasoningFor = (id: string, option = modelSelections.get(id) ?? defaultModel) =>
    webReasoningEffort(option.provider, option.provider === 'harless-glm' ? 'off' : reasoningSelections.get(id) ?? 'off');
  const modelSelection = (id: string, option = modelSelections.get(id) ?? defaultModel) => ({
    sessionId: id, provider: option.provider, model: option.model,
    ...(reasoningFor(id, option) === undefined ? {} : { reasoningEffort: reasoningFor(id, option) }),
  });
  const findModel = (id: unknown): ModelOption => {
    const option = modelOptions.find(row => row.model === id && row.available);
    if (!option) throw new TaskError('model_not_allowed', 'Model is not enabled by the server configuration');
    return option;
  };
  const schemas = new Map<string, any[]>(), requests = new Map<string, string>();
  const ownedSessions = new Set<string>();
  const legacyChatSessions = new Set<string>();
  const memberRestricted = brokerMode && config.allowed_tools.length === 0;
  const registeredScenes = config.scenes?.map(row => {
    if (!memberRestricted) return row;
    const { adapter, mcp_rows, environment_references, manifest, task, tool_schemas, certified_tool_schemas, certified_tool_schemas_sha256, ...safe } = row;
    const instructions = '当前会话仅开放 GeneLoop 普通对话；没有文件或场景工具。不要声称已读取文件或完成生成。';
    return { ...safe, allowed_tools: [], preset: 'sss-disabled-' + row.id,
      config_sha256: digest({ scene: row.id, parent: row.config_sha256 ?? null, role: 'member_chat_only', allowed_tools: [] }),
      ...(row.id === 'new-scene' ? { preset: 'sss-task', unavailable_reason: undefined, instructions, instructions_sha256: sha(instructions) }
      : { unavailable_reason: row.unavailable_reason ?? 'scene_not_deployed_in_member_sandbox' }) };
  });
  const scenes = sceneCatalog(registeredScenes ?? [{ ...config, id: config.capability_profile, label: config.capability_profile, preset: 'sss-task' }]);
  if (!scenes.some(scene => scene.id === config.capability_profile)) throw Error('Default scene is not registered');
  const defaultSceneId = memberRestricted && scenes.some(scene => scene.id === 'new-scene') ? 'new-scene' : config.capability_profile;
  let defaults = initialSelection(defaultSceneId, config.mode);
  const selections = new Map<string, Selection>(), agents = new Map<string, any>();
  const optionSelections = new Map<string,Record<string,SceneOptions>>();
  const workspaces = new Map<string, string>();
  const principal = brokerMode && config.budget_task_prefix ? 'member-' + config.budget_task_prefix : config.user_id ?? 'local-operator';
  registerManagedWorkspaceRoutes(ctx, {output: config.output, principal});
  const saveSettings = () => json(join(config.output, 'harless-settings.json'),
    { defaults, sessions: Object.fromEntries(selections),scene_options:Object.fromEntries(optionSelections) });
  const guards = new Map<string, (() => void)[]>();
  const sceneFor = (id: string) => {
    const scene = scenes.find(scene => scene.id === id);
    if (!scene) throw new SettingsError('scene_not_found', '场景未登记');
    return scene;
  };
  function executeUnavailable(scene: Scene): string | null {
    if (scene.unavailable_reason) return scene.unavailable_reason;
    if (scene.rsi_unavailable_reason) return scene.rsi_unavailable_reason;
    if (scene.runtime_kind==='management_graph_v3') return scene.management_config?null:'management_service_not_configured';
    if(scene.runtime_kind==='paper_shadow_v1')return 'existing_paper_library_shadow_only';
    if(scene.runtime_kind==='data_receipts_v3'){
      try{
        if(fileSha(scene.runtime_library)!==scene.runtime_library_sha256)return 'existing_data_library_changed';
        validateExistingData(JSON.parse(readFileSync(scene.runtime_library!,'utf8')));return null;
      }catch{return 'existing_data_library_invalid';}
    }
    if (!scene.manifest || !scene.task) return 'no_certified_library';
    if (!scene.diagnostic && !scene.certified_tool_schemas) return 'no_certified_tool_schemas';
    const structural=scene.matching_policy==='structural_only';
    if (!structural && !scene.embedding_endpoint) return 'no_embedding_service';
    if (!structural && !/^[a-f0-9]{64}$/.test(scene.certified_input_sha256 ?? '')) return 'no_certified_input';
    try {
      if(structural){
        if(!(['ppt','paper-proofreading','research-data-analysis','literature'].includes(scene.id)) ||
           scene.binding_policy!==(scene.id==='ppt'?'ppt_uploaded_sources_v1':'uploaded_source_handles_v1') ||
           scene.certification_scope!=='independent_trace_structure' || !scene.certification_path ||
           fileSha(scene.certification_path)!==scene.certification_sha256 || !scene.certified_code_locks ||
           Object.entries(scene.certified_code_locks).some(([path,expected])=>fileSha(path)!==expected))return 'runtime_bundle_certification_invalid';
      }else loopbackSimilarity(scene.embedding_endpoint!, scene.embedding_model ?? 'fixture-vectors-not-a-semantic-model');
      const manifest = JSON.parse(readFileSync(scene.manifest, 'utf8'));
      if (Object.keys(manifest.contracts ?? {}).some(tool => !scene.allowed_tools.includes(tool))) return 'library_tools_outside_scene';
      createOnlineInterceptor({ manifest, task: JSON.parse(readFileSync(scene.task, 'utf8')), mode: 'execute',
        similarity: async () => [], audit: () => {} });
    } catch { return 'no_valid_certified_library'; }
    return null;
  }
  function sessionScene(id: string, scene: Scene): Scene {
    if (!legacyChatSessions.has(id)) return scene;
    // A started Harness session has an immutable preset. Imported history must
    // not acquire a new MCP composition or reuse an obsolete tool surface.
    const { adapter, mcp_rows, environment_references, manifest, task, tool_schemas,
      certified_tool_schemas, certified_tool_schemas_sha256, ...safe } = scene;
    const instructions = '此会话为升级前保留的历史对话，只支持继续文字问答。当前没有文件或场景工具，不要声称已读取文件或完成生成；需要工作区工具时请用户新建会话。';
    return { ...safe, allowed_tools: [], instructions, instructions_sha256: sha(instructions),
      config_sha256: digest({ scene: scene.id, parent: scene.config_sha256 ?? null, legacy_chat_only: true }) };
  }
  const sourcePendingFor = (scene: Scene, inputs: any[]) => {
    if (!scene.adapter || scene.id === 'new-scene'||scene.runtime_kind==='management_graph_v3') return false;
    const formats = scene.adapter === 'data-report' ? ['.csv','.tsv']
      : scene.adapter === 'ppt' ? ['.pdf','.pptx'] : scene.adapter === 'literature' ? ['.pdf'] : undefined;
    return formats ? !inputs.some(row => formats.includes(extname(row.file ?? '').toLowerCase())) : !inputs.length;
  };
  const instructionsFor = (scene: Scene, sourcePending = false) => scene.adapter && scene.id !== 'new-scene'
    ? `${scene.instructions ?? ''}${scene.runtime_kind==='management_graph_v3'?'\n文件管理确认规则：高风险计划准备好后直接调用 execute_plan 请求原生确认；高风险恢复直接调用 restore_plan 请求确认。工具执行前会弹出一次性批准或拒绝，不要仅用聊天文字询问并提前结束。拒绝后保持文件不变并提交含真实缺口的报告。预期的移动源路径消失、内部副本标记和未读取的外部占位文件不属于交付缺口。':''}\n\n交互原则：以上工具流程仅在用户确实需要相应处理时适用。文字、附件及二者组合都走当前场景的正常执行流程，由你根据请求决定直接回答、询问资料或调用工具。正常回应问候、讨论目标、解释方法；不要为闲聊强制运行报告流程或要求上传。具体操作缺少必要来源时自然说明需要什么，不编造数据或交付，不暴露内部配置或服务器路径。${sourcePending ? '当前任务尚无可用于处理的数据来源；这不限制正常问答或可用工具，也不代表用户必须上传。' : ''}`
    : scene.instructions;
  function bindScene(agent: any, configuredScene: Scene, sourcePending = false) {
    const scene = sessionScene(agent.session.id, configuredScene);
    for (const dispose of guards.get(agent.session.id) ?? []) dispose();
    const allowedTools = scene.allowed_tools;
    const allowed = new Set(allowedTools);
    const instructions = instructionsFor(scene, sourcePending);
    const disposers = [...bindProductPrompt(agent), agent.ctx.tools.restrict({ allow: allowedTools }),
      agent.ctx.tools.guard((call: any) => allowed.has(call.name) ? undefined : 'Tool is outside the configured capability profile')];
    if (instructions) {
      // Report value tokens such as {{estimate}} are literal instructions, not
      // Harness prompt variables. Substitution values are not interpolated again.
      disposers.push(agent.ctx.systemPrompt.variable('harless_scene_literal',()=>instructions));
      disposers.push(agent.ctx.systemPrompt.section({ name: 'harless-scene', order: 10210, text: '{{harless_scene_literal}}' }));
    }
    if (config.fixture === 'tool-failure') disposers.push(agent.ctx.tools.guard((call: any) => call.name.endsWith('__read_pinned') ? 'injected mock tool failure' : undefined));
    guards.set(agent.session.id, disposers.filter(dispose => typeof dispose === 'function'));
    schemas.set(agent.session.id, agent.ctx.tools.schemas(scopeOf(agent.ctx)).sort((a: any, b: any) => a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
  }
  function settingsView(sessionId?: string) {
    if (sessionId) trash?.assertVisible(sessionId);
    if (sessionId && !ownedSessions.has(sessionId)) throw new TaskError('session_not_owned', 'Session is outside this Web run', 404);
    const selected = sessionId ? selections.get(sessionId) ?? defaults : defaults;
    const task = sessionId ? forSession(sessionId) : undefined;
    return { selection: selected, applies_to: task ? 'next_task' : 'next_prompt',
      conversation_only: sessionId ? legacyChatSessions.has(sessionId) : false,
      scene_locked: sessionId ? boundSessions.has(sessionId) || legacyChatSessions.has(sessionId) || Boolean(comparisons?.hasSession(sessionId)) : false,
      paired_comparison: Boolean(config.comparison_scenes?.includes(selected.scene)),
      motif_library: sceneFor(selected.scene).runtime_kind ? {kind:sceneFor(selected.scene).runtime_kind,
        mode:sceneFor(selected.scene).runtime_mode,sha256:sceneFor(selected.scene).runtime_library_sha256,loaded:!sceneFor(selected.scene).rsi_unavailable_reason}:null,
      comparison_child: sessionId ? Boolean(comparisons?.isLane(sessionId)) : false,
      comparison_parent_session_id: sessionId ? comparisons?.parentFor(sessionId) ?? null : null,
      preview_scene: selected.scene, // compatibility alias; now an actual registered selection
      preview_scenes: scenes.map(scene => ({ id: scene.id, label: scene.label, available: !scene.unavailable_reason, unavailable_reason: scene.unavailable_reason })),
      current_task: task ? { task_id: task.request.task_id, scene: task.scene.id, mode: task.request.mode, rsi: task.selection.rsi, status: task.status,confirmation_digest:task.confirmation_digest,verified_skips:task.stats.verified_skips,artifacts:(task.management?.artifacts??[]).map(({path,...r}:any)=>r) } : null,
      ...(task?.management?{continuous_learning:task.management.status}:{}),
      scenes: scenes.map(scene => ({ id: scene.id, label: scene.label, shortcut: sceneShortcut(scene), config_sha256: scene.config_sha256,
        available: !scene.unavailable_reason, unavailable_reason: scene.unavailable_reason,
        execute_available: !executeUnavailable(scene), execute_unavailable_reason: executeUnavailable(scene) })),
      scene_options:sessionId ? optionSelections.get(sessionId)?.[selected.scene] ?? {} : {},
      scene_option_fields:sceneFor(selected.scene).runtime_kind==='management_graph_v3' ? [
        {key:'allow_output',label:'操作权限',default:true,values:[{value:true,label:'自动整理工作区副本',detail:'复制、移动、重命名和创建目录自动执行；覆盖、永久删除及外部路径单独确认'},{value:false,label:'只读检查'}]},
      ] : sceneFor(selected.scene).adapter==='files' ? [
        {key:'allow_output',label:'整理权限',default:false,values:[
          {value:false,label:'只读盘点与检索'},
          {value:true,label:'允许整理任务副本',detail:'仅限已上传副本，最多 6 步；需预览、授权并留收据'},
        ]},
      ] : sceneFor(selected.scene).adapter==='ppt' ? [
        {key:'slides',label:'页数',default:6,values:[1,6,8,10,12].map(value=>({value,label:`${value} 页`}))},
        {key:'template',label:'模板',default:'academic',values:[{value:'academic',label:'学术模板'},{value:'lab',label:'组会模板'}]},
        {key:'allow_output',label:'输出权限',default:false,values:[{value:false,label:'只读检查'},{value:true,label:'允许生成 PPT 新副本',detail:sceneFor(selected.scene).output_unavailable_reason ?? '仅生成本任务的新文件'}]},
      ] : [],
      session_id: sessionId ?? null, model_calls: 0 };
  }
  const certifiedSchemaMatches = (scene: Scene, tools: any[]) =>
    [scene.certified_tool_schemas, ...(scene.certified_tool_schema_variants ?? [])].some(row => row && digest(row) === digest(tools));
  async function setSelection(sessionId: string | undefined, patch: unknown) {
    if (sessionId) await ensureOwned(sessionId);
    settingsView(sessionId); // ownership before mutation
    const current = sessionId ? selections.get(sessionId) ?? defaults : defaults;
    const next = changeSelection(current, patch, scenes, executeUnavailable);
    if (next.scene !== current.scene && sceneFor(next.scene).unavailable_reason)
      throw new TaskError('scene_not_connected', '该场景暂不可用：' + sceneFor(next.scene).unavailable_reason, 409);
    if (sessionId) {
      if (next.scene !== current.scene) {
        const previous = forSession(sessionId);
        if ((previous && !terminal.has(previous.status)) || comparisons?.busy(sessionId))
          throw new TaskError('session_busy', '请等待当前回复完成或取消后再切换场景。', 409);
        if (comparisons?.isLane(sessionId)) throw new TaskError('comparison_child', '请在原对话中选择场景。', 409);
        // The visible conversation routes to immutable private task agents.
        // Never mount a different tool composition over its earlier tool log.
        const routed = Boolean(brokerMode && config.comparison_scenes?.length &&
          (config.comparison_scenes.includes(next.scene) || comparisons?.hasSession(sessionId) || legacyChatSessions.has(sessionId) || (await controller.inspect(sessionId)).meta.isSeeded));
        if (!routed) {
          const snapshot = await controller.inspect(sessionId);
          if (boundSessions.has(sessionId) || legacyChatSessions.has(sessionId) || snapshot.events.some((event: any) =>
              ['user/message', 'assistant/message', 'tool/call', 'tool/result'].includes(event.type)))
            throw new TaskError('scene_requires_new_session', '该任务的工具范围已固定，请在支持场景切换的对话中继续。', 409);
          if (!agents.has(sessionId)) await original.selectModel(modelSelection(sessionId), new AbortController().signal);
          const scene = sceneFor(next.scene);
          await selectPreset!(agents.get(sessionId), sessionPreset(config.output, workspaceFor(sessionId), scene));
          bindScene(agents.get(sessionId), scene);
        }
      }
      selections.set(sessionId, next);

    } else defaults = next;
    saveSettings();
    return settingsView(sessionId);
  }
  const workspaceFor = (id: string) => {
    const path = workspaces.get(id) ?? sessionWorkspace(config.output, id);
    workspaces.set(id, path); return path;
  };
  const readBranchInputs = (id: string) => {
    try {
      const state = JSON.parse(readFileSync(join(workspaceFor(id), 'branch-inputs.json'), 'utf8'));
      if (state.version !== 1 || state.principal !== principal || state.session_id !== id) throw Error('branch_input_scope_mismatch');
      return state;
    } catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') return undefined; throw error; }
  };
  const selectPreset = ctx.agentPresets?.select.bind(ctx.agentPresets);
  // DSH history persists across deployments, so its admission record must
  // follow the same per-user DSH home instead of a disposable Web run output.
  const home = process.env.DSH_HOME ?? null;
  if (config.ownership_legacy_outputs !== undefined &&
      (!Array.isArray(config.ownership_legacy_outputs) ||
        config.ownership_legacy_outputs.some(path => typeof path !== 'string' || !isAbsolute(path))))
    throw Error('Invalid legacy Web ownership outputs');
  const runScope = digest({ output: config.output, home });
  const ownershipScope = home ? digest({ home, principal }) : runScope;
  const ownershipPath = home ? join(home, 'harless-web-ownership-' + ownershipScope + '.json')
    : join(config.output, 'session-ownership-' + ownershipScope + '.json');
  const boundSessions = new Set<string>();
  const readOwnership = (path: string, scope: string, legacy = false): boolean => {
    let saved: any;
    try { saved = JSON.parse(readFileSync(path, 'utf8')); }
    catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') return false; throw error; }
    if (saved.scope !== scope || !Array.isArray(saved.sessions) || !Array.isArray(saved.bound) ||
        [...saved.sessions, ...saved.bound].some(id => typeof id !== 'string' || !id.length) ||
        saved.bound.some(id => !saved.sessions.includes(id)) ||
        (saved.chat_only_sessions !== undefined && (!Array.isArray(saved.chat_only_sessions) ||
          saved.chat_only_sessions.some(id => !saved.sessions.includes(id))))) throw Error('Invalid Web session ownership record');
    for (const id of saved.sessions) ownedSessions.add(id);
    for (const id of legacy ? saved.sessions : saved.chat_only_sessions ?? []) legacyChatSessions.add(id);
    for (const id of saved.bound) {
      if (!ownedSessions.has(id)) throw Error('Unowned task session in ownership record');
      boundSessions.add(id);
    }
    return true;
  };
  readOwnership(ownershipPath, ownershipScope);
  let importedLegacy = false;
  if (home) for (const output of new Set([config.output, ...(config.ownership_legacy_outputs ?? [])])) {
    const scope = digest({ output, home });
    importedLegacy = readOwnership(join(output, 'session-ownership-' + scope + '.json'), scope, output !== config.output) || importedLegacy;
  }
  const saveOwnership = () => json(ownershipPath, { scope: ownershipScope,
    sessions: [...ownedSessions], bound: [...boundSessions], chat_only_sessions: [...legacyChatSessions] });
  if (importedLegacy) saveOwnership();
  const modelPath = join(config.output, 'session-models-' + runScope + '.json');
  try {
    const saved = JSON.parse(readFileSync(modelPath, 'utf8'));
    if (saved.scope !== runScope || !saved.models || typeof saved.models !== 'object') throw Error('Invalid Web model selection record');
    for (const [id, model] of Object.entries(saved.models)) {
      const option = modelOptions.find(row => row.model === model && row.available);
      if (ownedSessions.has(id) && option) modelSelections.set(id, option);
    }
    if (saved.reasoning_efforts !== undefined && (!saved.reasoning_efforts || typeof saved.reasoning_efforts !== 'object' || Array.isArray(saved.reasoning_efforts)))
      throw Error('Invalid Web reasoning selection record');
    for (const [id, effort] of Object.entries(saved.reasoning_efforts ?? {})) {
      if (ownedSessions.has(id)) reasoningSelections.set(id, webReasoningEffort('deepseek-official', effort)!);
    }
  } catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error; }
  const saveModels = () => json(modelPath, { scope: runScope,
    models: Object.fromEntries([...modelSelections].map(([id, option]) => [id, option.model])),
    reasoning_efforts: Object.fromEntries(reasoningSelections) });
  try {
    const saved = JSON.parse(readFileSync(join(config.output, 'harless-settings.json'), 'utf8'));
    const restoreSelection = (selection:any,id?:string) => {
      if(!scenes.some(scene=>scene.id===selection?.scene)){
        if(id)legacyChatSessions.add(id);
        return {...defaults};
      }
      try{return changeSelection(defaults, selection, scenes, executeUnavailable);}
      catch(error:any){if(error.code!=='execute_unavailable')throw error;
        return changeSelection(defaults,{...selection,mode:'baseline',rsi:false},scenes,executeUnavailable);}
    };
    if (saved.defaults) defaults = restoreSelection(saved.defaults);
    for (const [id, selection] of Object.entries(saved.sessions ?? {})) {
      if (ownedSessions.has(id)) selections.set(id, restoreSelection(selection,id));
    }
    for(const [id, values] of Object.entries(saved.scene_options ?? {}))if(ownedSessions.has(id)){
      const scoped:Record<string,SceneOptions>={};
      for(const [sceneId,value] of Object.entries(values as Record<string,unknown>))if(scenes.some(scene=>scene.id===sceneId))scoped[sceneId]=sceneOptions(value,sceneFor(sceneId));
      optionSelections.set(id,scoped);
    }
  } catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error; }
  const taskIndexPath = join(config.output, 'task-index-' + runScope + '.json');
  let indexedTasks: string[] = [];
  try {
    const saved = JSON.parse(readFileSync(taskIndexPath, 'utf8'));
    if (saved.scope !== runScope || !Array.isArray(saved.tasks) ||
        saved.tasks.some((id: unknown) => typeof id !== 'string' || !/^[a-f0-9]{32}$/.test(id)) ||
        new Set(saved.tasks).size !== saved.tasks.length) throw Error('Invalid Web task index');
    indexedTasks = saved.tasks;
  } catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error; }
  const saveTaskIndex = () => json(taskIndexPath, { scope: runScope, tasks: indexedTasks });
  // Earlier frontend versions wrote durable task files before they had a
  // scoped index. Recover only terminal tasks for sessions already proven to
  // belong to this DSH_HOME; the source run also contains other frontends.
  const indexedCount = indexedTasks.length;
  const indexed = new Set(indexedTasks);
  for (const id of readdirSync(join(config.output, 'tasks'))) {
    if (!/^[a-f0-9]{32}$/.test(id) || indexed.has(id)) continue;
    const output = join(config.output, 'tasks', id);
    if (!lstatSync(output).isDirectory()) continue;
    try {
      const state = JSON.parse(readFileSync(join(output, 'task-state.json'), 'utf8'));
      const request = JSON.parse(readFileSync(join(output, 'task.json'), 'utf8'));
      const header = JSON.parse(readFileSync(join(output, 'session-header.json'), 'utf8'));
      if (!terminal.has(state.status) || state.task_id !== id || request.task_id !== id ||
          state.session_id !== request.session_id || header.id !== request.session_id ||
           !(scenes.some(scene => scene.preset === header.agentPreset) || (String(header.agentPreset).startsWith('sss-bound-') && scenes.some(scene => scene.id === state.scene))) || !ownedSessions.has(request.session_id)) continue;
      indexedTasks.push(id); indexed.add(id);
    } catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error; }
  }
  indexedTasks.sort((a, b) => {
    const aState = JSON.parse(readFileSync(join(config.output, 'tasks', a, 'task-state.json'), 'utf8'));
    const bState = JSON.parse(readFileSync(join(config.output, 'tasks', b, 'task-state.json'), 'utf8'));
    return String(aState.created_at).localeCompare(String(bState.created_at));
  });
  if (indexedTasks.length !== indexedCount) saveTaskIndex();
  let creation: Promise<unknown> = Promise.resolve();
  let active: string | null = null;
  // Serial admission prevents two preview/submit retries from creating duplicate work.
  let admission: Promise<unknown> = Promise.resolve();
  const serialize = <T>(operation: () => Promise<T>): Promise<T> => {
    const result = admission.then(operation); admission = result.catch(() => undefined); return result;
  };
  async function control(path: string, payload?: unknown, allowMissing = false) {
    const response = await fetch(config.control_endpoint + path, {
      method: payload === undefined ? 'GET' : 'POST',
      headers: { 'X-SSS-Control-Token': config.control_token, 'Content-Type': 'application/json' },
      ...(payload === undefined ? {} : { body: JSON.stringify(payload) }), signal: AbortSignal.timeout(10000),
    });
    const value: any = await response.json();
    if (allowMissing && response.status === 404) return null;
    if (!response.ok) throw new TaskError('budget_control_failed', value.error || 'Budget service refused request', 409);
    return value;
  }
  async function broker(path: string, payload: unknown) {
    if (!config.budget_broker_endpoint) return;
    const response = await fetch(config.budget_broker_endpoint + path, {
      method: 'POST', headers: { 'X-SSS-Control-Token': config.control_token, 'Content-Type': 'application/json' },
      body: JSON.stringify(payload), signal: AbortSignal.timeout(10000),
    });
    if (!response.ok) throw new TaskError('budget_broker_failed', 'Turn budget routing refused the request', 409);
  }
  function get(id: unknown): Task {
    if (typeof id !== 'string' || !tasks.has(id)) throw new TaskError('task_not_found', 'Unknown task', 404);
    trash?.assertVisible(tasks.get(id)!.request.session_id);
    return tasks.get(id)!;
  }
  const forSession = (id: string): Task | undefined => tasks.get(sessions.get(id) ?? '');
  function view(task: Task, detail = false) {
    const request = task.request;
    return { task_id: request.task_id, session_id: request.session_id, request_id: request.request_id,
      capability_profile: request.capability_profile, scene: task.scene.id, scene_sha256: task.scene.config_sha256,
      user_id: principal, selected_mode: task.selection.mode, rsi: task.selection.rsi, mode: request.mode, budget_usd: request.budget_usd,
      entrypoint: task.entrypoint, source_task_id: task.source_task_id, status: task.status, failure: task.failure, fallback_reason: task.fallback_reason,
      created_at: task.created_at, started_at: task.started_at, finished_at: task.finished_at,
      input_summary: request.summary, prompt_sha256: request.prompt_sha256,
      request_sha256: request.request_sha256, confirmation_digest: task.confirmation_digest,
      provider_mode: config.provider_mode, provider: task.model_option.provider, model: task.model_option.model,
      reasoning_effort: task.reasoning_effort ?? null,
      motif_library:task.scene.runtime_kind??null,library_sha256:task.scene.runtime_library_sha256??null,
      paid_calls_enabled: config.provider_mode === 'real',
      ...(task.management?{continuous_learning:task.management.status,management_artifacts:(task.management.artifacts??[]).map(({path,...r}:any)=>r),management_operations:task.management.operations??0}:{}),
      scene_options: task.scene_options, scene_inputs: task.scene_inputs, source_pending: task.source_pending ?? false,
      effects: 'Only server-configured MCP capabilities; file changes require MCP-side confirmation.',
      stats: task.stats, sources: task.sources,
      ...(progress.has(task.request.task_id) ? {progress: progress.get(task.request.task_id)!.snapshot().progress, activity: progress.get(task.request.task_id)!.snapshot().activity} : {}),
      ...(detail ? { answer: task.answer, input_preview: task.delivery.filter(part => part.type === 'text').map(part => (part as any).text).join('\n').slice(0, 4096), artifacts: ['task.json', 'effective-config.json', 'events.jsonl',
        'ledger.jsonl', 'motif-audit.jsonl', ...(task.answer ? ['answer.md'] : [])] } : {}) };
  }
  function record(task: Task) {
    json(join(task.output,'task-state.json'),view(task));
    if(task.management)json(join(task.output,'management-runtime.json'),{config:task.management.config,binding:task.management.binding,rsi:task.management.rsi,used:task.management.used??false,status:task.management.status,artifacts:task.management.artifacts});
  }
  for (const taskId of indexedTasks) {
    const output = join(config.output, 'tasks', taskId);
    const request: NormalizedWebTask = JSON.parse(readFileSync(join(output, 'task.json'), 'utf8'));
    const state: any = JSON.parse(readFileSync(join(output, 'task-state.json'), 'utf8'));
    let route: any;
    try { route = JSON.parse(readFileSync(join(output, 'budget-route.json'), 'utf8')); }
    catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
      route = { session_id: request.session_id, budget_session_id: request.session_id };
    }
    if (request.task_id !== taskId || request.session_id !== route.session_id ||
        !ownedSessions.has(request.session_id) || typeof route.budget_session_id !== 'string' ||
        state.task_id !== taskId || state.session_id !== request.session_id) throw Error('Web task index identity mismatch');
    const effective = JSON.parse(readFileSync(join(output, 'effective-config.json'), 'utf8'));
    const configuredScene = scenes.find(scene=>scene.id===(state.scene??request.capability_profile))??sceneFor(defaults.scene);
    if(!scenes.some(scene=>scene.id===(state.scene??request.capability_profile))||
      (effective.allowed_tools&&digest(effective.allowed_tools)!==digest(configuredScene.allowed_tools)))legacyChatSessions.add(request.session_id);
    const restoredScene = sessionScene(request.session_id, configuredScene);
    const task: Task = { request, delivery: request.content, confirmation_digest: state.confirmation_digest,
      status: state.status, created_at: state.created_at, started_at: state.started_at,
      finished_at: state.finished_at, failure: state.failure, fallback_reason: state.fallback_reason,
      answer: '', output, stats: state.stats, humans: new Map(), current_humans: new Set(),
      sources: state.sources, entrypoint: state.entrypoint, budget_session_id: route.budget_session_id,
      source_task_id: state.source_task_id ?? request.task_id,
      scene: { ...restoredScene, config_sha256: effective.scene_sha256 ?? restoredScene.config_sha256,
        instructions: effective.instructions ?? restoredScene.instructions, instructions_sha256: effective.instructions_sha256,
        allowed_tools: effective.allowed_tools ?? restoredScene.allowed_tools },
      selection: { scene: state.scene ?? request.capability_profile, mode: state.selected_mode ?? request.mode, rsi: state.rsi ?? false },
      workspace: workspaceFor(request.session_id), scene_options: state.scene_options ?? {}, scene_inputs: state.scene_inputs ?? [], scope_sha256: effective.scope_sha256 ?? null,
      tools: effective.tools ?? [], source_pending: state.source_pending === true,
      manifest_sha256: effective.manifest_sha256 ?? null,
      binding_sha256: effective.binding_sha256 ?? null,
      bound_binding_sha256: effective.bound_binding_sha256 ?? null,
      model_option: modelOptions.find(option => option.model === state.model && option.provider === state.provider) ?? defaultModel,
      reasoning_effort: webReasoningEffort(state.provider ?? defaultModel.provider, state.reasoning_effort ?? effective.reasoning_effort ?? 'off') };
    try { task.answer = readFileSync(join(output, 'answer.md'), 'utf8'); }
    catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error; }
    tasks.set(taskId, task); progress.set(taskId, createTaskProgress({answer:task.answer,progress:state.progress,activity:state.activity})); sessions.set(request.session_id, taskId); requests.set(request.request_id, taskId);
    if (!selections.has(request.session_id)) selections.set(request.session_id, { ...task.selection });
    if (!modelSelections.has(request.session_id)) modelSelections.set(request.session_id, task.model_option);
    if (!reasoningSelections.has(request.session_id) && task.reasoning_effort !== undefined) reasoningSelections.set(request.session_id, task.reasoning_effort);
    if(task.scene.runtime_kind==='management_graph_v3'){
      task.management=JSON.parse(readFileSync(join(output,'management-runtime.json'),'utf8'));
      for(const e of [...JSON.parse(readFileSync(join(output,'native-prefix.json'),'utf8')),...readFileSync(join(output,'events.jsonl'),'utf8').split('\n').filter(Boolean).map(l=>JSON.parse(l))])
        if(e.type==='user/message'&&e.data.source?.kind==='user')task.humans.set(e.data.id,digest(e.data.content));
      await control('/tasks/register',{task_id:taskId,session_id:task.budget_session_id,budget_usd:request.budget_usd,model:task.model_option.model,job_file:task.management.binding.job_file,ledger_file:join(output,'ledger.jsonl')});
      if(!terminal.has(task.status)&&task.status!=='awaiting_confirmation'){
        task.status='interrupted';task.failure='frontend_restarted_original_task_preserved';record(task);continue;
      }
      if(task.status==='awaiting_confirmation'){
        task.management.live=attachManagementRuntime(task,task.management.rsi,row=>audit(task,row));task.management.acceptance=managementAcceptance(task);
      }
    }
    if (terminal.has(task.status)) {progress.get(taskId)?.finish(task.status);if(task.management)await control('/tasks/cancel',{session_id:task.budget_session_id});}
    if (!terminal.has(task.status)&&!task.management) {
      task.status = 'failed'; task.failure = 'frontend_restarted_before_completion'; task.finished_at = utc();
      progress.get(taskId)?.finish('failed'); record(task);
      task.closing = (async () => {
        await broker('/unbind', { session_id: request.session_id, budget_session_id: task.budget_session_id });
        await control('/tasks/cancel', { session_id: task.budget_session_id });
      })().catch(error => { task.failure = 'budget_close_failed: ' + String(error); record(task); });
    }
  }
  // Older clients stored a planned scene on a locked conversation. Recover its
  // actual binding so an unrelated next message cannot accidentally change it.
  for (const id of ownedSessions) {
    const actualScene = forSession(id)?.scene.id ?? (legacyChatSessions.has(id) ? defaults.scene : undefined);
    const selected = selections.get(id);
    if (!(brokerMode && config.comparison_scenes?.length) && actualScene && selected?.scene !== actualScene) selections.set(id, { ...(selected ?? defaults), scene: actualScene });
  }
  if (ownedSessions.size) saveSettings();
  function audit(task: Task, row: any) {
    appendFileSync(join(task.output, 'motif-audit.jsonl'), JSON.stringify({ ...row, task_id: task.request.task_id }) + '\n', { mode: 0o600 });
    if (row.kind === 'motif_bypass_attempt') task.stats.motif_attempts = Number(task.stats.motif_attempts) + 1;
    if (row.kind === 'shadow_candidate') task.stats.shadow_candidates = Number(task.stats.shadow_candidates) + 1;
    if (row.kind === 'model_request_skipped_verified') task.stats.verified_skips = Number(task.stats.verified_skips) + 1;
    record(task);
  }
  async function refresh(task: Task) {
    await task.closing;
    let counters;
    try { counters = await control('/tasks/stats?session_id=' + encodeURIComponent(task.budget_session_id), undefined, terminal.has(task.status)); }
    catch (error) {
      // A replaced budget process may no longer retain an old task route. Its
      // persisted final usage is still evidence, never a new zero-cost budget.
      // Active tasks and authorization/response errors remain fail-closed.
      if (!terminal.has(task.status) || !(error instanceof TypeError || (error as Error).name === 'TimeoutError')) throw error;
    }
    if (counters) Object.assign(task.stats, counters.stats ?? counters);
    task.stats.model_requests = Number(task.stats.upstream_requests ?? 0);
    task.stats.actual_paid_usd = config.provider_mode === 'mock' ? 0 : null;
    if (task.started_at) task.stats.elapsed_seconds =
      (Date.parse(task.finished_at ?? utc()) - Date.parse(task.started_at)) / 1000;
    record(task); return view(task, true);
  }
  function requireIdle() {
    if (active) throw new TaskError('task_busy', 'Another task is running; wait or cancel it', 409);
  }
  function finish(task: Task, status: string, failure: string | null = null) {
    if (terminal.has(task.status)||task.status==='interrupted'&&status!=='cancelled') return;
    if(task.management&&status==='failed'&&/503|502|MCP|recovery|closed|timeout|interrupted/i.test(failure??'')&&['running','paused'].includes(new OperationJob(fileURLToPath(new URL('../../',import.meta.url)),task.management.binding.job_file).load().status))status='interrupted';
    task.status = status; task.failure = failure; task.finished_at = utc();
    progress.get(task.request.task_id)?.finish(status);
    record(task);
    // Every terminal task closes its proxy admission; in-flight calls still settle.
    // Release the launch slot only after budget ownership is retired.
    task.closing = (async () => {
      await broker('/unbind', { session_id: task.request.session_id, budget_session_id: task.budget_session_id });
      await control(status==='interrupted'?'/tasks/suspend':'/tasks/cancel', { session_id: task.budget_session_id });
      if(task.management&&status!=='interrupted'){
        task.management.live.observer.taskFinalized();const counters=await control('/tasks/stats?session_id='+encodeURIComponent(task.budget_session_id));Object.assign(task.stats,counters.stats??counters);
        const d=join(task.output,'native-sessions');mkdirSync(d,{recursive:true,mode:0o700});const files=readdirSync(d).map(name=>({file:join(d,name),session_id:name.replace(/\.jsonl$/,''),sha256:fileSha(join(d,name))}));
        task.management.artifacts=await managementBridge(task.management.config,{action:'collect',directory:task.management.binding.directory,native_workspace:task.workspace});task.management.operations=task.management.artifacts.find((r:any)=>r.name==='management-report.json')?.operation_count??0;
        const metrics={...task.stats,budget_accounted_usd:task.stats.estimated_cost_usd,status:status==='completed'?'done':status,session_id:task.request.session_id,acceptance_passed:task.management.acceptance.state().accepted,acceptance_repairs:task.management.acceptance.state().repairs,
          native_session_files:files,agent_steps:task.stats.llm_decisions,elapsed_seconds:(Date.parse(task.finished_at!)-Date.parse(task.started_at!))/1000};
        task.management.sealed=await managementBridge(task.management.config,{action:'seal',directory:task.management.binding.directory,metrics});
        task.management.status=await managementBridge(task.management.config,{action:'status'});record(task);
      }
      if (active === task.request.task_id) active = null;
    })().catch((error) => { task.failure = 'budget_close_failed: ' + String(error); record(task); }).finally(()=>{if(active===task.request.task_id)active=null;});
  }
  const controller = ctx.sessionController;
  const privateLanes = registerPrivateLanes(ctx, config.output, principal, id => comparisons?.isLane(id) ?? false);
  const privateCreations = new WeakSet<object>();
  const inspectForTrash = controller.inspect.bind(controller);
  trash = createSessionTrash(ownershipPath.replace(/\.json$/, '-trash.json'), principal, {
    owns: ensureOwned,
    isPrivate: privateLanes.isPrivate,
    privateChildren: id => [...new Set([...privateLanes.childrenFor(id), ...[...ownedSessions]
      .filter(child => comparisons?.parentFor(child) === id)])],
    busy: ids => ids.some(id => comparisons?.busy(id) || agents.get(id)?.status === 'running' ||
      agents.get(id)?.inbox?.nextTurn?.length || agents.get(id)?.inbox?.nextStep?.length ||
      [...tasks.values()].some(task => task.request.session_id === id && task.status !== 'awaiting_confirmation' && !terminal.has(task.status))),
    async describe(id) {
      const snapshot = await inspectForTrash(id);
      const workspace = ctx.workspaceRegistry?.list().find((row: any) => row.sessionIds.includes(id));
      return { title: sessionBranchTitle(snapshot.meta, snapshot.events), ...(workspace ? { workspace_id: workspace.id } : {}) };
    },
  });
  const original = { create: controller.create.bind(controller), prompt: controller.prompt.bind(controller),
    cancel: controller.cancel.bind(controller), selectModel: controller.selectModel.bind(controller) };
  const titledSessions = new Set<string>();
  async function repairBlankTitle(id: string, snapshot?: any) {
    if (titledSessions.has(id) || !controller.rename) return;
    snapshot ??= await controller.inspect(id);
    if (!snapshot.meta.title && !snapshot.events.some((event: any) =>
        ['user/message', 'assistant/message', 'tool/call', 'tool/result'].includes(event.type)))
      await controller.rename({ sessionId: id, title: '新会话' });
    titledSessions.add(id);
  }
  async function ensureOwned(id: string) {
    trash.assertVisible(id);
    if (ownedSessions.has(id)) {
      await repairBlankTitle(id);
      if (!selections.has(id)) {
        const snapshot = await controller.inspect(id);
        const scene = forSession(id)?.scene ?? scenes.find(row => row.preset === snapshot.meta.agentPreset) ??
          (legacyChatSessions.has(id) ? sceneFor(defaults.scene) : undefined);
        if (!scene) throw new TaskError('session_not_owned', 'Session scene binding cannot be recovered', 409);
        selections.set(id, { ...defaults, scene: scene.id }); saveSettings();
      }
      return;
    }
    let snapshot: any;
    try { snapshot = await controller.inspect(id); }
    catch (error) {
      if (!(error instanceof ApiSessionNotFound)) throw error;
      throw new TaskError('session_not_owned', 'Session is outside this Web run; create a new session', 404);
    }
    // Upgrade only an ordinary, untouched blank session from this instance's
    // configured preset. Official Web reuses these after a process restart.
    // A session with history or a budget registration cannot be re-admitted.
    if (!scenes.some(scene => scene.preset === snapshot.meta.agentPreset) || snapshot.meta.isSeeded || snapshot.meta.origin ||
        snapshot.inheritedEventCount || snapshot.events.some((event: any) =>
          ['user/message', 'assistant/message', 'tool/call', 'tool/result'].includes(event.type))) {
      throw new TaskError('session_not_owned', 'Session is outside this Web run; create a new session', 404);
    }
    const registration = await control('/tasks/stats?session_id=' + encodeURIComponent(id), undefined, true);
    if (registration !== null && !brokerMode) throw new TaskError('session_already_bound', 'This session already has a task；请在工作区菜单中归档此空会话，然后新建会话。', 409);
    ownedSessions.add(id); saveOwnership();
    await repairBlankTitle(id, snapshot);
    if (!selections.has(id)) selections.set(id, { ...defaults,
      scene: scenes.find(scene => scene.preset === snapshot.meta.agentPreset)!.id });
    saveSettings();
  }
  controller.create = (request: any) => {
    const result = creation.then(async () => {
      if (request.sessionId) trash.assertVisible(request.sessionId);
      const privateCreation = privateCreations.has(request);
      if (request.sessionId && privateLanes.isPrivate(request.sessionId) && !privateCreation)
        throw new TaskError('comparison_child', '请在原对话中继续。', 409);
      if (request.agentPreset && !scenes.some(scene => scene.preset === request.agentPreset)) throw new TaskError('profile_not_allowed', 'Use the server-configured GeneLoop preset');
      if (request.sessionId && !ownedSessions.has(request.sessionId)) {
        // Official Web supplies a fresh client-generated ID. Allow only a proven
        // absent ID; adopting an existing foreign session still fails closed.
        let absent = false;
        try { await controller.inspect(request.sessionId); }
        catch (error) { if (!(error instanceof ApiSessionNotFound)) throw error; absent = true; }
        if (!absent) throw new TaskError('session_not_owned', 'Session is outside this Web run; create a new session');
      }
      const chosen = request.agentPreset ? scenes.find(scene => scene.preset === request.agentPreset)! : sceneFor(defaults.scene);
      if (chosen.unavailable_reason) throw new TaskError('scene_not_connected', chosen.unavailable_reason, 409);
      if (request.cwd !== undefined && request.workspaceId !== undefined)
        throw new TaskError('invalid_workspace', '请选择工作区或目录，不能同时指定两者');
      if (request.cwd !== undefined)
        throw new TaskError('workspace_not_allowed', 'The server allocates a private Session workspace');
      // Both managed workspaces and pre-existing groups are account-local in
      // the native registry. Accept their identities in either budget mode,
      // while refusing client-supplied host paths or another account's IDs.
      if (request.workspaceId !== undefined && (typeof request.workspaceId !== 'string' ||
          !ctx.workspaceRegistry?.get(request.workspaceId)))
        throw new TaskError('workspace_not_allowed', '此工作区不属于当前账号，请重新选择工作区。', 403);
      const id = request.sessionId ?? (brokerMode ? 'session-' + randomUUID() : 'sss-' + randomUUID().replaceAll('-', ''));
      const workspace = workspaceFor(id);
      const priorPreset = ownedSessions.has(id) ? (await controller.inspect(id)).meta.agentPreset : undefined;
      let location = request.workspaceId !== undefined ? { workspaceId: request.workspaceId } : { cwd: workspace };
      if (!privateCreation && request.workspaceId === undefined && ctx.workspaceRegistry) {
        const group = await ctx.workspaceRegistry.create(priorPreset ? (await controller.inspect(id)).meta.cwd : workspace, chosen.label);
        location = { workspaceId: group.id };
      }
      // Workspace IDs and cwd are mutually exclusive in the native API. A
      // group is account-local; MCP input/work paths remain session-local.
      const { cwd: _cwd, workspaceId: _workspaceId, ...identity } = request;
      const created = await original.create({ ...identity, sessionId: id, ...location,
        agentPreset: priorPreset ?? sessionPreset(config.output, workspace, chosen) });
      // Native title fallback is the storage directory basename (a UUID).
      // Give new chats a durable user-facing name without renaming old chats.
      if (!priorPreset && controller.rename) await controller.rename({ sessionId: created.sessionId, title: '新会话' });
      ownedSessions.add(created.sessionId); saveOwnership();
      if (!selections.has(created.sessionId)) {
        selections.set(created.sessionId, { ...defaults, scene: chosen.id });
        saveSettings();
        bindScene(agents.get(created.sessionId), chosen);
        const option = modelSelections.get(created.sessionId) ?? defaultModel;
        await original.selectModel(modelSelection(created.sessionId, option));
        modelSelections.set(created.sessionId, option);
        saveModels();
      }
      return created;
    });
    creation = result.catch(() => undefined); return result;
  };
  let branchSeqMap = new Map<number, number>();
  const branches = createSessionBranchService(config.output, principal, {
    ensureOwned: async id => { await ensureOwned(id); if (comparisons?.isLane(id)) throw new TaskError('comparison_child', '请在原对话中创建分支。', 409); },
    inspect: id => controller.inspect(id),
    listTitles: async () => { const titles: string[] = []; for (const id of ownedSessions) { try { const snapshot=await controller.inspect(id); titles.push(sessionBranchTitle(snapshot.meta,snapshot.events)); } catch {} } return titles; },
    projectEvents: (source, events) => {
      const projected: any[] = [];
      for (const event of events) {
        // Preserve native history as a detached seed. Comparison outputs live
        // in account storage, so materialize their current text without IDs
        // that could mutate original ratings or attach original runtime tools.
        projected.push(event);
        const reference = event.type === 'user/message' && event.data.harless_comparison;
        if (!reference) continue;
        const saved = comparisons?.snapshot(source, reference.id);
        if (!saved || !['completed','failed','cancelled'].includes(saved.status)) throw new TaskError('branch_turn_incomplete', '请等待所选回复完成后创建分支。', 409);
        const text = Object.entries(saved.lanes).map(([name, value]: [string, any]) =>
          (saved.presentation === 'single' ? '' : (name === 'baseline' ? 'Baseline\n' : 'Motif\n')) + (value.answer_display ?? value.answer ?? '')).join('\n\n');
        const option = modelSelections.get(source) ?? defaultModel;
        projected.push({ type:'assistant/message', time:event.time, surfaceOp:'append',
          data:{ turn:reference.turn ?? 1, step:0, stream:[], harless_branch_context:true, message:createAssistantMessage({content:[{type:'text',text}], source:{provider:option.provider,model:option.model}}) } });
      }
      // Filter old non-surface provenance dependencies only on synthesized
      // result rows; original event indices retain their relative ordering.
      const seqMap = new Map(events.map((event, index) => [event.seq, projected.indexOf(event)]));
      branchSeqMap = seqMap;
      return projected.map((event, index) => { const row = structuredClone(event); row.seq = index;
        if (Array.isArray(row.sourceEventSeqs)) row.sourceEventSeqs = row.sourceEventSeqs.map((seq: number) => seqMap.get(seq));
        if (row.surfaceOp && typeof row.surfaceOp === 'object') {
          const startSeq = seqMap.get(row.surfaceOp.startSeq)!;
          let endSeq = seqMap.get(row.surfaceOp.endSeq)!;
          while (endSeq + 1 < projected.length && !events.includes(projected[endSeq + 1])) endSeq++;
          row.surfaceOp = {...row.surfaceOp,startSeq,endSeq};
          row.sourceEventSeqs = [...new Set([...(row.sourceEventSeqs ?? []), ...projected.flatMap((candidate, position) =>
            position >= startSeq && position <= endSeq && !events.includes(candidate) && candidate.surfaceOp ? [position] : [])])].sort((a: number,b: number)=>a-b);
        }
        return row;
      });
    },
    async createSeeded({ sessionId, sourceSessionId, title, seed, inheritedEventCount, sourceAtSeq }) {
      if (!ctx.agents?.create || !ctx.agentPresets?.mount) throw new TaskError('branch_unavailable', '当前服务暂不能创建分支，请稍后重试。', 409);
      const workspace = workspaceFor(sessionId), scene = sceneFor(scenes.some(row => row.id === 'new-scene') ? 'new-scene' : defaults.scene);
      const selected = selections.get(sourceSessionId) ?? defaults;
      const option = modelSelections.get(sourceSessionId) ?? defaultModel;
      const group = ctx.workspaceRegistry?.list().find((row: any) => row.sessionIds.includes(sourceSessionId));
      const preset = sessionPreset(config.output, workspace, scene);
      // A fork starts its own tool scope. Prior event evidence is readable
      // history; the next routed send will allocate fresh task input copies.
      ownedSessions.add(sessionId); selections.set(sessionId, { ...selected }); modelSelections.set(sessionId, option);
      if (reasoningSelections.has(sourceSessionId)) reasoningSelections.set(sessionId, reasoningSelections.get(sourceSessionId)!);
      const sourceEvents = (await controller.inspect(sourceSessionId)).events.filter((event: any) => event.seq <= sourceAtSeq);
      const store = comparisonArtifacts(config.output), inherited = readBranchInputs(sourceSessionId);
      const snapshot: any = {version:1,principal,session_id:sessionId,inherited_event_count:inheritedEventCount,lanes:{},context:{}};
      const inheritedCut = inherited?.inherited_event_count ?? 0;
      const inCut = (row: any) => Number.isSafeInteger(row.source_seq) && row.source_seq <= sourceAtSeq;
      const mappedSeq = (seq: number) => branchSeqMap.get(seq) ?? (() => { throw new TaskError('branch_history_unavailable','分支历史位置暂不可用。',409); })();
      if (inherited && !Number.isSafeInteger(inherited.inherited_event_count))
        throw new TaskError('branch_history_unavailable','旧分支资料缺少历史位置，请从原对话创建分支。',409);
      for (const lane of ['baseline','motif']) {
        const destination = join(workspace,'inherited',lane), directory = join(destination,'outputs');
        mkdirSync(directory,{recursive:true,mode:0o700});
        const names = new Map<string,string>(), sourceSeqs = new Map<string,number>(), seen = new Set<string>(); let total = 0;
        const copy = (name: string, bytes: Uint8Array, sourceSeq: number) => {
          const version = sha(bytes);if(seen.has(version)||names.size>=32||bytes.length>20*1024*1024||total+bytes.length>80*1024*1024)return;
          const safe = basename(name).replace(/[^\p{L}\p{N}._-]/gu,'_').slice(-110);
          const filename = `${names.size+1}-${safe}${extname(safe).toLowerCase()==='.json'?'.txt':''}`;
          writeFileSync(join(directory,filename),bytes,{mode:0o600,flag:'wx'}); names.set('outputs/'+filename,safe);sourceSeqs.set('outputs/'+filename,mappedSeq(sourceSeq));seen.add(version);total+=bytes.length;
        };
        const history: any[] = (inherited?.context?.[lane] ?? []).filter(inCut).map((row:any)=>({...row,source_seq:mappedSeq(row.source_seq)}));
        for (const event of sourceEvents) {
          if (event.seq < inheritedCut) continue;
          const ref = event.type==='user/message' && event.data.harless_comparison;
          if (ref) {
            const saved = comparisons?.snapshot(sourceSessionId,ref.id);
            const sourceLane = saved?.presentation==='single'?'baseline':lane;
            const result = saved?.lanes[sourceLane];
            if (!saved || !result) throw new TaskError('branch_history_unavailable','分支历史结果暂不可用。',409);
            history.push({source_seq:mappedSeq(event.seq),user:event.data.content.filter((part:any)=>part.type==='text').map((part:any)=>part.text).join('\n'),assistant:result.answer_display??result.answer??''});
          } else if (!event.data?.harless_branch_context && ['user/message','assistant/message'].includes(event.type)) {
            history.push({source_seq:mappedSeq(event.seq),[event.type==='user/message'?'user':'assistant']:(event.data.content??event.data.message?.content??[]).filter((part:any)=>part.type==='text').map((part:any)=>part.text).join('\n')});
          }
        }
        // Newest verified report precedes chart files and original sources.
        const comparisonsAtCut = sourceEvents.filter((event:any)=>event.type==='user/message'&&event.data.harless_comparison).reverse();
        for (const event of comparisonsAtCut) {
          const saved = comparisons!.snapshot(sourceSessionId,event.data.harless_comparison.id)!;
          const sourceLane = saved.presentation==='single'?'baseline':lane;
          const files = [...(saved.lanes[sourceLane]?.artifacts??[])].sort((a:any,b:any)=>Number(/(?:research_)?report\.pdf$/i.test(b.name))-Number(/(?:research_)?report\.pdf$/i.test(a.name)));
          for (const row of files) copy(row.name,store.read(saved.id,sourceLane,row),event.seq);
        }
        for (const row of (inherited?.lanes?.[lane]??[]).filter(inCut)) copy(row.name,store.read(sourceSessionId,lane,row),row.source_seq);
        for (const event of [...sourceEvents].reverse()) if(event.type==='user/message') for(const part of event.data.content??[]) {
          if(part.type!=='file'||!part.attachment||part.attachment.bytes>20*1024*1024)continue;
          const ref=part.attachment,chunks:Buffer[]=[];let bytes=0;
          for await(const chunk of ctx.attachments.readFileStream(ref)){bytes+=chunk.length;if(bytes>20*1024*1024)throw new TaskError('scene_input_limit','分支资料过大。');chunks.push(Buffer.from(chunk));}
          const data=Buffer.concat(chunks);if(bytes!==ref.bytes||(typeof ref.sha256==='string'&&sha(data)!==ref.sha256))throw new TaskError('file_bytes_changed','分支资料版本已改变。');
          copy(ref.name,data,event.seq);
        }
        snapshot.lanes[lane]=store.snapshot(sessionId,lane,0,destination).map((row:any)=>({...row,name:names.get(row.name)??row.name,source_seq:sourceSeqs.get(row.name)}));
        snapshot.context[lane]=history;
      }
      json(join(workspace,'branch-inputs.json'),snapshot);
      try {
        await ctx.agents.create({ sessionId, seed, inheritedEventCount,
          meta:{ cwd:group?.path ?? workspace, parentSession:sourceSessionId, isSeeded:true, agentPreset:preset },
          agentOptions:{ provider:option.provider, model:option.model, ...(reasoningFor(sessionId, option) === undefined ? {} : {reasoningEffort: reasoningFor(sessionId, option)}) },
          setup:async (agentCtx: any) => { await ctx.agentPresets.mount(agentCtx,preset); },
        });
      } catch (error) { ownedSessions.delete(sessionId); selections.delete(sessionId); modelSelections.delete(sessionId); reasoningSelections.delete(sessionId); throw error; }
      if (group) await group.attachSession(sessionId);
      await controller.rename({sessionId,title});
      if (optionSelections.has(sourceSessionId)) optionSelections.set(sessionId,structuredClone(optionSelections.get(sourceSessionId)!));
      saveOwnership();saveSettings();saveModels();
      await original.selectModel(modelSelection(sessionId, option),new AbortController().signal);
    },
  });
  controller.fork = (request: any) => serialize(() => branches.fork(request));
  // Native queue editing would change the approved content after its digest was
  // shown. Edits use a new task/preview rather than silently mutating this binding.
  controller.updateQueue = () => { throw new TaskError('queue_edit_not_supported', 'Preview a new task before changing queued input', 409); };
  controller.selectModel = async (request: any, signal: AbortSignal) => {
    const option = findModel(request.model);
    const previousTask = forSession(request.sessionId);
    if (!ownedSessions.has(request.sessionId) || comparisons?.busy(request.sessionId) || (previousTask && (!brokerMode || !terminal.has(previousTask.status))) || request.provider !== option.provider)
      throw new TaskError('model_not_allowed', 'Model selection is outside the approved task configuration');
    let effort: WebReasoningEffort | undefined;
    try { effort = webReasoningEffort(option.provider, request.reasoningEffort ?? reasoningFor(request.sessionId, option)); }
    catch { throw new TaskError('model_not_allowed', '该模型不支持所选推理模式。'); }
    const requested = { ...request };
    if (effort === undefined) delete requested.reasoningEffort;
    else requested.reasoningEffort = effort;
    const result = await original.selectModel(requested, signal);
    modelSelections.set(request.sessionId, option);
    if (effort !== undefined) reasoningSelections.set(request.sessionId, effort);
    saveModels();
    return result;
  };
  if (ctx.agentPresets) ctx.agentPresets.select = (agent: any, preset: string) => serialize(async () => {
    const scene = scenes.find(scene => scene.preset === preset);
    if (!scene) throw new SettingsError('scene_not_found', '只能选择服务器登记的场景');
    if (forSession(agent.session.id)) throw new TaskError('session_already_bound', '当前会话已绑定任务，请新建会话后选择 GeneLoop 设置', 409);
    await setSelection(agent.session.id, { scene: scene.id }); return preset;
  });
  async function preview(input: unknown, existingSession?: string, entrypoint: Task['entrypoint'] = 'workbench'): Promise<Task> {
    const nonce = randomUUID().replaceAll('-', '');
    const taskId = config.budget_task_prefix ? config.budget_task_prefix + nonce.slice(8) : nonce;
    const tentativeSession = existingSession ?? 'pending';
    const supplied = input && typeof input === 'object' && !Array.isArray(input) ? input as Record<string, unknown> : {};
    const chosenModel = supplied.model === undefined ? (existingSession ? modelSelections.get(existingSession) ?? defaultModel : defaultModel) : findModel(supplied.model);
    let chosenReasoning: WebReasoningEffort | undefined;
    try { chosenReasoning = webReasoningEffort(chosenModel.provider,
      supplied.reasoning_effort ?? (existingSession ? reasoningFor(existingSession, chosenModel) : 'off')); }
    catch { throw new TaskError('model_not_allowed', '该模型不支持所选推理模式。'); }
    const taskInput = input && typeof input === 'object' && !Array.isArray(input)
      ? { ...supplied } : input;
    if (taskInput && typeof taskInput === 'object' && !Array.isArray(taskInput)) { delete taskInput.model; delete taskInput.scene_options; delete taskInput.reasoning_effort; }
    const selected = existingSession ? selections.get(existingSession)! : defaults;
    if (existingSession && !selected) throw new TaskError('session_not_owned', 'Session is outside this Web run');
    const request = normalizeWebTaskRequest(taskInput, { task_id: taskId, session_id: tentativeSession,
      default_mode: selected.mode, default_budget_usd: config.budget_usd, max_budget_usd: config.budget_usd,
      default_profile: selected.scene, allowed_profiles: scenes.map(scene => scene.id),
      max_content_bytes: 768 * 1024, max_parts: 32 });
    const requestedMode = request.mode;
    if (!selected.rsi) {
      request.mode = 'baseline';
      request.request_sha256 = digest({ request: request.request_sha256, rsi: false });
    }
    if (chosenModel.provider === 'harless-glm' && request.content.some(part => part.type !== 'text'))
      throw new TaskError('unsupported_input', 'The GLM connection currently supports text only; remove images and files before retrying');
    const sources: Task['sources'] = [];
    const delivery = request.content.map(part => ({ ...part }));
    for (const reference of request.resources) {
      const resource = config.resources?.[reference.resource_id];
      if (!resource) throw new TaskError('resource_not_registered', `Resource is not registered: ${reference.resource_id}`, 404);
      if (reference.version !== undefined && reference.version !== resource.version) throw new TaskError('resource_version_changed', `Resource version differs: ${reference.resource_id}`, 409);
      sources.push({ resource_id: reference.resource_id, version: resource.version, sha256: sha(resource.text) });
      delivery.push({ type: 'text', text: `\n\n[来源 ${reference.resource_id}；版本 ${resource.version}]\n${resource.text}` });
    }
    if (Buffer.byteLength(JSON.stringify(delivery)) > 768 * 1024) throw new TaskError('request_too_large', 'Resolved input exceeds byte limit', 413);
    const scene = sessionScene(existingSession ?? '', sceneFor(request.capability_profile));
    if (existingSession && legacyChatSessions.has(existingSession) && request.content.some(part => part.type !== 'text'))
      throw new TaskError('new_session_required', '历史会话可以继续文字对话；使用文件或场景工具请新建会话。', 409);
    if (scene.unavailable_reason) throw new TaskError('scene_not_connected', scene.unavailable_reason, 409);
    const previousTask = existingSession ? forSession(existingSession) : undefined;
    const options = sceneOptions(supplied.scene_options ?? (existingSession ? optionSelections.get(existingSession)?.[scene.id] : undefined) ?? (scene.runtime_kind==='management_graph_v3'?{allow_output:true}:scene.adapter === 'ppt' && previousTask?.scene.id === scene.id ? previousTask.scene_options : undefined), scene);
    if(options.allow_output && scene.output_unavailable_reason)throw new TaskError('scene_output_unavailable',scene.output_unavailable_reason,409);
    const selection = changeSelection(selected, { scene: scene.id, mode: requestedMode }, scenes, executeUnavailable);
    request.request_sha256 = digest({ request: request.request_sha256, selection, scene_options: options, user_id: principal,
      ...(chosenReasoning === 'high' ? {reasoning_effort: chosenReasoning} : {}) });
    const previous = requests.get(request.request_id);
    if (previous) {
      const task = get(previous);
      if (request.request_sha256 !== task.request.request_sha256 || chosenModel.model !== task.model_option.model) throw new TaskError('request_id_conflict', 'request_id already binds different input or model', 409);
      return task;
    }
    request.session_id = existingSession ?? (await controller.create({ agentPreset: scene.preset })).sessionId;
    if (existingSession && scene.id !== selected.scene) throw new TaskError('scene_changed', '预览前请先选择与当前会话一致的 GeneLoop 场景', 409);
    if (previousTask && !terminal.has(previousTask.status)) throw new TaskError('session_busy', '请等待本轮完成或取消，再发送下一条消息。', 409);
    await previousTask?.closing;
    if (scene.runtime_kind!=='management_graph_v3' && !brokerMode && (sessions.has(request.session_id) || boundSessions.has(request.session_id))) throw new TaskError('session_already_bound', 'This session already has a task；请点击“新会话”后发送新的任务。', 409);
    // Saved model selections survive process restarts; live Agents and their
    // MCP schemas do not. Restore the native Agent before checking its tools.
    if (!agents.has(request.session_id) || modelSelections.get(request.session_id)?.model !== chosenModel.model ||
        reasoningFor(request.session_id, chosenModel) !== chosenReasoning) await controller.selectModel({
      sessionId: request.session_id, provider: chosenModel.provider, model: chosenModel.model,
      ...(chosenReasoning === undefined ? {} : { reasoningEffort: chosenReasoning })
    }, new AbortController().signal);
    const newFileInput = request.content.some(part => part.type === 'file');
    if (scene.runtime_kind!=='management_graph_v3' && previousTask && (previousTask.scene.id !== scene.id || (scene.adapter && newFileInput && !previousTask.source_pending) ||
        digest(previousTask.scene_options) !== digest(options)))
      throw new TaskError('new_session_required', 'Create a new Session to bind a scene or new file task', 409);
    const workspace = workspaceFor(request.session_id);
    const firstSources = previousTask?.source_pending && newFileInput;
    const reuseWorkspace = scene.runtime_kind!=='management_graph_v3' && previousTask && scene.adapter && !firstSources;
    const sceneInputs = reuseWorkspace ? previousTask.scene_inputs : scene.adapter ? await bindSceneInputs(ctx, agents.get(request.session_id), workspace, scene,
      request.content, options, delivery.filter(part => part.type === 'text').map(part => (part as any).text).join('\n'), taskId) : [];
    const management=scene.runtime_kind==='management_graph_v3'?{config:scene.management_config,binding:await managementBridge(scene.management_config,{action:'prepare',
      output:join(config.output,'tasks',taskId),native_workspace:workspace,owner:principal,workspace_id:ctx.workspaceRegistry?.list().find((row:any)=>row.sessionIds.includes(request.session_id))?.id??request.session_id,
      task_id:taskId,objective:delivery.filter(p=>p.type==='text').map((p:any)=>p.text).join('\n'),source_files:sceneInputs.map(row=>({...row,path:join(workspace,'inputs',row.file)})),budget_usd:request.budget_usd,output_cap:Math.min(config.max_output_tokens??4000,4000),request_limit:Math.min(config.request_limit??96,96),allow_output:options.allow_output!==false,rsi:selection.rsi,external_roots:scene.management_config.external_roots})}:undefined;
    if (scene.adapter && !reuseWorkspace && !firstSources && !(management && (schemas.get(request.session_id)??[]).length===scene.allowed_tools.length)) {
      await selectPreset!(agents.get(request.session_id), sessionPreset(config.output, workspace, scene));
      bindScene(agents.get(request.session_id), scene);
    }
    // Source availability is metadata, never a different chat/tool pipeline.
    const sourcePending = sourcePendingFor(scene, sceneInputs);
    bindScene(agents.get(request.session_id), scene, sourcePending);
    const tools = structuredClone(schemas.get(request.session_id) ?? []);
    if (tools.length !== scene.allowed_tools.length || tools.some((tool: any) => !scene.allowed_tools.includes(tool.name)))
      throw new TaskError('scene_tools_unavailable', 'Configured MCP tool surface did not load', 409);
    if (request.mode === 'execute' && !['data_receipts_v3','management_graph_v3'].includes(scene.runtime_kind??'')) {
      if (scene.certified_tool_schemas && !certifiedSchemaMatches(scene, tools))
        throw new TaskError('execute_unavailable', 'certified_tool_schema_mismatch', 409);
      const manifest = JSON.parse(readFileSync(scene.manifest!, 'utf8'));
      const offered = new Map(tools.map((tool: any) => [tool.name, tool]));
      if (Object.entries(manifest.contracts).some(([name, contract]) => !offeredSchemaMatches(offered, name, contract)))
        throw new TaskError('execute_unavailable', 'library_tool_schema_mismatch', 409);
      if(scene.matching_policy!=='structural_only')try {
        const binding = JSON.parse(readFileSync(scene.task!, 'utf8'));
        await loopbackSimilarity(scene.embedding_endpoint!, scene.embedding_model!)(binding.intent, ['Runtime admission probe']);
      } catch { throw new TaskError('execute_unavailable', 'embedding_service_unavailable', 409); }
    }
    selections.set(request.session_id, selection);
    const snapshot = await controller.inspect(request.session_id);
    const priorHumans = new Map<string, string>();
    if (brokerMode || management) for (const event of snapshot.events) {
      if (event.type === 'user/message' && event.data.source?.kind === 'user')
        priorHumans.set(event.data.id, digest(event.data.content));
    }
    const budgetSessionId = brokerMode || management ? 'turn-' + taskId : request.session_id;
    const output = join(config.output, 'tasks', taskId); mkdirSync(output, { recursive: true, mode: 0o700 });
    const task: Task = { request, delivery, confirmation_digest: '', status: 'awaiting_confirmation',
      scene, management, selection: Object.freeze({ ...selection }), tools, workspace, scene_options: options, scene_inputs: sceneInputs, source_pending: sourcePending, scope_sha256: scopeDigest(workspace, scene),
      manifest_sha256: fileSha(scene.manifest), binding_sha256: fileSha(scene.task),
      entrypoint, created_at: utc(), failure: null, fallback_reason: null, answer: '', output,
      humans: priorHumans, current_humans: new Set(), sources,
      model_option: chosenModel, reasoning_effort: chosenReasoning, budget_session_id: budgetSessionId,
      source_task_id: firstSources ? taskId : previousTask?.source_task_id ?? previousTask?.request.task_id ?? taskId,
      stats: { tool_calls: 0, tool_errors: 0, llm_decisions: 0, motif_attempts: 0, shadow_candidates: 0, verified_skips: 0,
        upstream_requests: 0, model_requests: 0, actual_paid_usd: config.provider_mode === 'mock' ? 0 : null } };
    for (const filename of ['events.jsonl', 'motif-audit.jsonl']) writeFileSync(join(output, filename), '', { mode: 0o600 });
    await control('/tasks/register', { task_id: taskId, session_id: budgetSessionId,
      budget_usd: request.budget_usd, model: chosenModel.model,...(management?{job_file:management.binding.job_file,ledger_file:join(output,'ledger.jsonl')}:{}) });
    json(join(output, 'budget-route.json'), { session_id: request.session_id, budget_session_id: budgetSessionId });
    if(management){
      await control('/tasks/alias',{session_id:budgetSessionId,alias_session_id:request.session_id});
      if(chosenModel.model!=='deepseek-flash'||chosenReasoning!=='off')throw new TaskError('model_not_allowed','文件管理沿用原DeepSeek Flash/Off配置');
      management.rsi=await managementBridge(management.config,{action:'enroll',directory:management.binding.directory,output,session_id:request.session_id,budget_usd:request.budget_usd});
      management.live=attachManagementRuntime(task,management.rsi,row=>audit(task,row));
      management.acceptance=managementAcceptance(task);
      management.status=await managementBridge(management.config,{action:'status'});
    }
    boundSessions.add(request.session_id); saveOwnership();
    tasks.set(taskId, task); progress.set(taskId, createTaskProgress()); sessions.set(request.session_id, taskId); requests.set(request.request_id, taskId);
    json(join(output, 'session-header.json'), snapshot.meta);
    if(management)json(join(output,'native-prefix.json'),snapshot.events);
    else for (const event of snapshot.events) appendFileSync(join(output, 'events.jsonl'), JSON.stringify(event) + '\n', { mode: 0o600 });
    updateDraft(task);
    indexedTasks.push(taskId); saveTaskIndex(); return task;
  }
  function updateDraft(task: Task) {
    if(task.scene.binding_policy && task.request.mode!=='baseline' && !task.source_pending && task.scene_inputs.length){
      const manifest=JSON.parse(readFileSync(task.scene.manifest!,'utf8'));
      const binding=task.scene.binding_policy==='ppt_uploaded_sources_v1' ? bindUploadedPptTask(task.workspace,task.scene_inputs.filter(row=>['.pdf','.pptx'].includes(extname(row.file).toLowerCase())),task.request,manifest,task.source_task_id)
        : bindUploadedSourceTask(task.workspace,task.scene_inputs,task.request,manifest);
      json(join(task.output,'bound-motif-task.json'),binding);
      task.bound_binding_sha256=fileSha(join(task.output,'bound-motif-task.json'));
    }
    task.confirmation_digest = digest({ task_id: task.request.task_id, request: task.request.request_sha256,
      delivery: task.delivery, sources: task.sources, schemas: task.tools, scene: task.scene.id,
      scene_sha256: task.scene.config_sha256, instructions: instructionsFor(task.scene, task.source_pending), selection: task.selection,
      manifest_sha256: task.manifest_sha256, binding_sha256: task.binding_sha256,
      certified_tool_schemas_sha256: task.scene.certified_tool_schemas_sha256,
      bound_binding_sha256: task.bound_binding_sha256, certification_sha256:task.scene.certification_sha256,
      ...(task.management?{continuous_learning:task.management.status,management_operations:task.management.operations??0}:{}),
      scene_options: task.scene_options, scene_inputs: task.scene_inputs, scope_sha256: task.scope_sha256, user_id: principal,
      provider_mode: config.provider_mode, max_output_tokens: config.max_output_tokens });
    task.confirmation_digest = digest({ confirmation: task.confirmation_digest,
      provider: task.model_option.provider, model: task.model_option.model, reasoning_effort: task.reasoning_effort ?? null });
    json(join(task.output, 'task.json'), task.request);
    json(join(task.output, 'effective-config.json'), { ...view(task), selection: task.selection, tools: task.tools,
      scenario: task.scene.scenario, scenario_version: task.scene.scenario_version,
      instructions: instructionsFor(task.scene, task.source_pending), instructions_sha256: sha(instructionsFor(task.scene, task.source_pending) ?? ''),
      certified_tool_schemas_sha256: task.scene.certified_tool_schemas_sha256, diagnostic: task.scene.diagnostic ?? false,
      bound_binding_sha256:task.bound_binding_sha256,certification_sha256:task.scene.certification_sha256,
      binding_policy:task.scene.binding_policy,matching_policy:task.scene.matching_policy,
      certification_scope:task.scene.certification_scope,quality_cost_promoted:task.scene.quality_cost_promoted,
      allowed_tools: task.scene.allowed_tools, offered_allowed_tools: task.scene.allowed_tools,
      workspace: task.workspace, scope_sha256: task.scope_sha256,
      runtime_file_locks:task.scene.runtime_file_locks,
      tool_schemas_sha256: digest(task.tools), reasoning_effort: task.reasoning_effort ?? null, compression: false,
      budget: { task_usd: task.request.budget_usd, task_requests: config.request_limit === 0 ? null : config.request_limit,
        run_usd: config.run_budget_usd, run_requests: config.run_request_limit === 0 ? null : config.run_request_limit, reset_history: false },
      run_config: '../../effective-config.json', manifest_sha256: task.manifest_sha256, binding_sha256: task.binding_sha256, scene_registry_sha256: config.scene_registry_sha256 });
    record(task);
  }
  function configureMotif(task: Task) {
    if (task.request.mode === 'baseline') return;
    const parts = task.request.content, scene = task.scene;
    if(scene.runtime_kind==='data_receipts_v3'||scene.runtime_kind==='paper_shadow_v1'){
      try{
        if(fileSha(scene.runtime_library)!==scene.runtime_library_sha256)throw Error('existing_library_changed');
        const library=JSON.parse(readFileSync(scene.runtime_library!,'utf8'));
        task.interceptor=scene.runtime_kind==='data_receipts_v3'
          ? dataInterceptor(library,task.workspace,task.request.mode,row=>audit(task,row))
          : paperShadowInterceptor(library,task.tools,row=>audit(task,row));
        audit(task,{kind:'existing_library_loaded',runtime_kind:scene.runtime_kind,sha256:scene.runtime_library_sha256,mode:task.request.mode,new_training:false});
      }catch(error:any){task.fallback_reason=error.message;audit(task,{kind:'motif_fallback',reason:error.message});}
      return;
    }
    const availableTools = new Map(task.tools.map(tool => [tool.name, tool]));
    const pinned = (path: string, expected: string | null) => { const bytes = readFileSync(path); if (sha(bytes) !== expected) throw Error('Motif binding version changed'); return JSON.parse(bytes.toString('utf8')); };
    if (!scene.manifest || !scene.task) task.fallback_reason = scene.rsi_unavailable_reason ?? 'no_certified_library';
    else if (!scene.diagnostic && !scene.certified_tool_schemas) task.fallback_reason = 'no_certified_tool_schemas';
    else if (scene.certified_tool_schemas && !certifiedSchemaMatches(scene, task.tools)) task.fallback_reason = 'certified_tool_schema_mismatch';
    else if (scene.matching_policy==='structural_only' && executeUnavailable(scene))task.fallback_reason='runtime_bundle_certification_invalid';
    else if (scene.matching_policy!=='structural_only' && !scene.embedding_endpoint) task.fallback_reason = 'no_embedding_service';
    else if (scene.binding_policy && !task.bound_binding_sha256)task.fallback_reason='rsi_requires_approved_sources';
    else if (!scene.binding_policy && (parts.length !== 1 || parts[0].type !== 'text' || task.sources.length ||
        sha(parts[0].text.trim()) !== scene.certified_input_sha256)) task.fallback_reason = 'input_not_certified_for_library';
    else try {
      const manifest = pinned(scene.manifest, task.manifest_sha256);
      if (Object.entries(manifest.contracts).some(([name, contract]) => !offeredSchemaMatches(availableTools, name, contract))) throw Error('library_tool_schema_mismatch');
      const binding = scene.binding_policy ? pinned(join(task.output,'bound-motif-task.json'),task.bound_binding_sha256!) : pinned(scene.task, task.binding_sha256);
      binding.session_id = task.request.session_id; binding.task_id = task.request.task_id;
      json(join(task.output, 'bound-motif-task.json'), binding);
      task.interceptor = createOnlineInterceptor({ manifest,
        task: binding, mode: task.request.mode, minSimilarity: 0.8, minMargin: 0.1,
        similarity: scene.matching_policy==='structural_only' ? structuralOnlySimilarity : loopbackSimilarity(scene.embedding_endpoint!, scene.embedding_model ?? 'fixture-vectors-not-a-semantic-model'),
        audit: (row: unknown) => audit(task, row) });
    } catch (error) {
      task.interceptor = undefined; task.fallback_reason = (error as Error).message === 'library_tool_schema_mismatch' ? 'library_tool_schema_mismatch' : 'no_valid_certified_library';
      audit(task, { kind: 'motif_library_invalid', error_type: (error as Error).name });
    }
    if (task.fallback_reason) audit(task, { kind: 'motif_fallback', reason: task.fallback_reason });
  }
  async function submit(task: Task, confirmation: unknown, signal: AbortSignal) {
    if (confirmation !== task.confirmation_digest) throw new TaskError('confirmation_changed', 'Input/configuration changed; preview and confirm again', 409);
    if (task.status !== 'awaiting_confirmation') return view(task, true); // exact retry never reruns the Agent
    if (digest(schemas.get(task.request.session_id)) !== digest(task.tools) ||
        scopeDigest(task.workspace, task.scene) !== task.scope_sha256 ||
        (task.scene.runtime_file_locks && Object.entries(task.scene.runtime_file_locks).some(([path,expected])=>fileSha(path)!==expected)) ||
        (task.scene.tool_schemas && fileSha(task.scene.tool_schemas) !== task.scene.certified_tool_schemas_sha256) ||
        fileSha(task.scene.manifest) !== task.manifest_sha256 || fileSha(task.scene.task) !== task.binding_sha256 ||
        (task.scene.runtime_library && fileSha(task.scene.runtime_library)!==task.scene.runtime_library_sha256)) {
      throw new TaskError('confirmation_changed', 'Tools or library changed; preview a new task', 409);
    }
    if (task.request.mode === 'execute') {
      const reason = executeUnavailable(task.scene);
      if (reason) throw new TaskError('execute_unavailable', reason, 409);
      if(task.scene.binding_policy && !task.source_pending){
        if(!task.bound_binding_sha256)throw new TaskError('execute_unavailable','ppt_rsi_requires_approved_sources',409);
        if(fileSha(join(task.output,'bound-motif-task.json'))!==task.bound_binding_sha256)
          throw new TaskError('confirmation_changed','bound_motif_task_changed',409);
      }
    }
    // Source materialization/validation belongs to the selected tool call.
    // A greeting, explanation or planning turn need not prepare a report.
    requireIdle(); active = task.request.task_id; task.status = 'running'; task.started_at = utc(); record(task);
    try {
      const attachmentContext = await sceneAttachmentContext(task.workspace, task.scene_inputs);
      if (scopeDigest(task.workspace, task.scene) !== task.scope_sha256)
        throw new TaskError('confirmation_changed', '附件内容已改变，请重新发送。', 409);
      if(!task.management)configureMotif(task);else new OperationJob(fileURLToPath(new URL('../../',import.meta.url)),task.management.binding.job_file).apply('owner',{pid:process.pid});
      await control('/tasks/activate', { session_id: task.budget_session_id });
      await broker('/bind', { session_id: task.request.session_id, budget_session_id: task.budget_session_id });
      await original.prompt({ requestId: task.request.request_id, sessionId: task.request.session_id,
        mode: 'queue', content: attachmentContext ? [...task.delivery, {type:'text',text:attachmentContext}] : task.delivery }, signal);
      return view(task, true);
    } catch (error) { finish(task, 'failed', String(error)); throw error; }
  }
  async function resumeManagement(task:Task,confirmation:unknown,signal:AbortSignal){
    if(!task.management||task.status!=='interrupted'||confirmation!==task.confirmation_digest)throw new TaskError('task_not_recoverable','原任务或确认摘要不一致',409);
    requireIdle();await task.closing;
    const restored=await managementBridge(task.management.config,{action:'recover',directory:task.management.binding.directory,native_workspace:task.workspace});
    await control('/tasks/recover',{session_id:task.budget_session_id,owner_pid:process.pid});
    await control('/tasks/alias',{session_id:task.budget_session_id,alias_session_id:task.request.session_id});
    task.management.live=attachManagementRuntime(task,task.management.rsi,row=>audit(task,row));task.management.acceptance=managementAcceptance(task);
    if(restored.already_accepted){task.status='running';finish(task,'completed');await task.closing;return view(task,true);}
    await original.selectModel(modelSelection(task.request.session_id,task.model_option),signal);
    if((schemas.get(task.request.session_id)??[]).length!==task.scene.allowed_tools.length)await selectPreset!(agents.get(task.request.session_id),sessionPreset(config.output,task.workspace,task.scene));bindScene(agents.get(task.request.session_id),task.scene);
    if(digest(schemas.get(task.request.session_id))!==digest(task.tools))throw new TaskError('version_changed','恢复工具版本不一致',409);
    task.status='running';task.failure=null;task.finished_at=undefined;active=task.request.task_id;record(task);
    await control('/tasks/activate',{session_id:task.budget_session_id});await broker('/bind',{session_id:task.request.session_id,budget_session_id:task.budget_session_id});
    try{await original.prompt({requestId:randomUUID(),sessionId:task.request.session_id,mode:'queue',content:[...task.delivery,{type:'text',text:'继续原任务。先read_task查看恢复状态及已有回执，仅执行未完成步骤，禁止重复已有文件操作。原权限、预算和版本保持不变。'}]},signal);}
    catch(e){finish(task,'failed',String(e));throw e;}return view(task,true);
  }
  controller.prompt = (request: any, signal: AbortSignal) => serialize(async () => {
    await ensureOwned(request.sessionId);
    if (comparisons?.isLane(request.sessionId)) throw new TaskError('comparison_child', '请回到原对照会话继续发送，左右两侧会分别保留历史。', 409);
    if (request.mode !== 'queue') throw new TaskError('delivery_not_supported', 'Use a new queued task; steer is not task admission');
    if (!selections.has(request.sessionId)) {
      const snapshot = await controller.inspect(request.sessionId);
      const scene = scenes.find(row => row.preset === snapshot.meta.agentPreset) ??
        (legacyChatSessions.has(request.sessionId) ? sceneFor(defaults.scene) : undefined);
      if (!scene) throw new TaskError('session_not_owned', 'Session is outside this Web run');
      selections.set(request.sessionId, { ...defaults, scene: scene.id });
      saveSettings();
    }
    // A cold persisted session must resume through the public controller API so
    // agent/created reinstalls its tool restrictions and schema binding.
    if (!schemas.has(request.sessionId)) {
      const option = modelSelections.get(request.sessionId) ?? defaultModel;
      await original.selectModel(modelSelection(request.sessionId, option), signal);
      modelSelections.set(request.sessionId, option);
    }
    const content = structuredClone(request.content);
    const firstText = content.find((part: any) => part.type === 'text');
    const shortcut = firstText && parseSceneShortcut(firstText.text, scenes);
    if (shortcut) {
      if (!shortcut.text.trim() && content.length === 1) {
        await setSelection(request.sessionId, { scene: shortcut.scene });
        return { accepted: true }; // choosing a scene alone never calls the model
      }
      await setSelection(request.sessionId, { scene: shortcut.scene });
      firstText.text = shortcut.text;
    }
    const selected = selections.get(request.sessionId)!;
    if (comparisons && (config.comparison_scenes?.includes(selected.scene) || comparisons.hasSession(request.sessionId) || legacyChatSessions.has(request.sessionId) || (await controller.inspect(request.sessionId)).meta.isSeeded)) {
      const priorTask = forSession(request.sessionId);
      if (priorTask && !terminal.has(priorTask.status)) throw new TaskError('session_busy', '请等待当前回复完成或取消后再发送。', 409);
      await priorTask?.closing;
      const scene = sceneFor(selected.scene), parent = agents.get(request.sessionId);
      if (!Array.isArray(content) || !content.length || content.some((part: any) => !['text', 'file'].includes(part.type)) ||
          content.filter((part: any) => part.type === 'file').length > 8) throw new TaskError('unsupported_input', '请发送文字和最多 8 份场景资料。');
      const text = content.filter((part: any) => part.type === 'text').map((part: any) => part.text).join('\n');
      if (!text.trim()) throw new TaskError('invalid_request', '请填写任务内容。');
      const sourceFiles:Record<string,any>={};
      const files = content.filter((part: any) => part.type === 'file').map((part: any) => {
        const ref = ctx.fileUploads.resolve(parent, part.receiptId)??comparisons.sourceFor(request.sessionId,request.requestId,part.receiptId);
        if (!ref || ref.bytes > 20 * 1024 * 1024) throw new TaskError('file_receipt_not_owned', '资料回执不属于当前会话或文件过大。');
        sourceFiles[part.receiptId]=structuredClone(ref);
        return { name: ref.name, bytes: ref.bytes, digest: digest(ref) };
      });
      return comparisons.admit(request.sessionId, { ...request, content }, {
        scene: selected.scene, options: {...(scene.adapter === 'ppt' ? {allow_output:true} : {}),...(optionSelections.get(request.sessionId)?.[selected.scene] ?? {})},
        prior_context_by_lane: readBranchInputs(request.sessionId)?.context,
        presentation: config.comparison_scenes?.includes(selected.scene) ? 'paired' : 'single',
        prior_context: (await controller.inspect(request.sessionId)).events.filter((event: any) =>
          (event.type === 'user/message' && !event.data.harless_comparison) || (event.type === 'assistant/message' && !event.data.harless_branch_context)).slice(-12).map((event: any) => ({
            [event.type === 'user/message' ? 'user' : 'assistant']: (event.data.content ?? event.data.message?.content ?? []).filter((part: any) => part.type === 'text').map((part: any) => part.text).join('\n'),
          })),
        model: (modelSelections.get(request.sessionId) ?? defaultModel).model, reasoning_effort: reasoningFor(request.sessionId),
        input_sha256: digest([text, files]),source_files:sourceFiles,
      });
    }
    const task = await preview({ content, request_id: request.requestId }, request.sessionId, 'native_chat');
    await submit(task, task.confirmation_digest, signal);
    return { accepted: true };
  });
  controller.cancel = async (request: any) => {
    if (!ownedSessions.has(request.sessionId)) throw new TaskError('session_not_owned', 'Session is outside this Web run');
    const task = forSession(request.sessionId);
    const result = await original.cancel(request); if (task) finish(task, 'cancelled', 'user_cancelled'); return result;
  };
  if (config.comparison_scenes?.length) {
    const artifacts = comparisonArtifacts(config.output), taskParents = new Map<string, any>();
    comparisons = createComparisonService(config.output, principal, {
      owns: ensureOwned,
      ready: () => active === null,
      async createLane(parent, scene, lane) {
        const request = { sessionId: privateLanes.reserve(parent), agentPreset: sceneFor(scene).preset };
        privateCreations.add(request);
        const created = await controller.create(request);
        // Only the comparison Host admits child turns. Native prompt rejects direct child mutation.
        await controller.rename({ sessionId: created.sessionId, title: lane === 'baseline' ? 'Baseline' : 'Motif' });
        return created.sessionId;
      },
      async prepare(turn, lane, requestId) { return serialize(async () => {
        requireIdle(); const child = turn.lanes[lane].session_id;
        await ensureOwned(turn.session_id); await ensureOwned(child);
        if (comparisons!.parentFor(child) !== turn.session_id) throw new TaskError('comparison_scope_mismatch', '对话执行范围不匹配。', 403);
        const previous = forSession(child), content: any[] = [];
        for (const part of turn.input) {
          if (part.type === 'text') { content.push(part); continue; }
          // A failed initial attempt already froze these same parent inputs.
          // Retrying keeps that snapshot; it must not rebind upload receipts.
          if (previous) continue;
          const ref = turn.source_files?.[part.receiptId]??ctx.fileUploads.resolve(agents.get(turn.session_id), part.receiptId);
          if (!ref || ref.bytes > 20 * 1024 * 1024) throw new TaskError('file_receipt_not_owned', '资料回执不属于原会话。');
          const uploaded = await ctx.fileUploads.uploadStream({ sessionId: child, name: ref.name,
            data: ctx.attachments.readFileStream(ref), signal: new AbortController().signal });
          content.push({ type: 'file', receiptId: uploaded.receiptId });
        }
        if (!previous && !turn.input.some((part: any) => part.type === 'file')) {
          const target = sceneFor(turn.scene);
          const accepts = (name: string) => {
            const suffix = extname(name).toLowerCase();
            if (target.adapter === 'ppt') return ['.pdf','.pptx'].includes(suffix);
            if (target.id === 'research-data-analysis') return ['.csv','.tsv','.json','.txt','.md'].includes(suffix);
            if (target.id === 'paper-proofreading') return ['.pdf','.tex','.bib','.bbl','.log','.md','.txt','.json'].includes(suffix);
            if (target.adapter === 'literature') return suffix === '.pdf';
            return false;
          };
          const carried: { name: string; sha256: string }[] = [], seen = new Set<string>();
          const carry = async (name: string, bytes: Uint8Array) => {
            const hash = sha(bytes);
            if (carried.length >= 8 || bytes.length > 20 * 1024 * 1024 || seen.has(hash)) return;
            const uploaded = await ctx.fileUploads.uploadStream({ sessionId: child, name: basename(name),
              data: (async function* () { yield bytes; })(), signal: new AbortController().signal });
            content.push({ type: 'file', receiptId: uploaded.receiptId }); seen.add(hash); carried.push({name: basename(name), sha256:hash});
          };
          const inheritedArtifacts = [...(turn.prior_artifacts?.[lane] ?? [])].reverse().sort((a: any,b: any) => Number(/(?:research_)?report\.pdf$/i.test(b.row.name)) - Number(/(?:research_)?report\.pdf$/i.test(a.row.name)));
          for (const source of inheritedArtifacts) {
            const prior = comparisons!.snapshot(turn.session_id, source.turn);
            // Immutable store lookup, account/parent check, lane identity, and
            // output hash all have to agree before transferring any bytes.
            const expectedLane = prior?.presentation === 'single' ? 'baseline' : lane;
            const row = prior?.lanes[expectedLane]?.artifacts?.find((row: any) => row.id === source.row.id);
            if (!row || source.lane !== expectedLane || digest(row) !== digest(source.row))
              throw new TaskError('comparison_artifact_scope', '历史文件不属于本对话的对应结果。', 403);
            if (accepts(row.name)) await carry(row.name, artifacts.read(source.turn, expectedLane, row));
          }
          if (!carried.length) for (const row of readBranchInputs(turn.session_id)?.lanes?.[lane] ?? []) {
            await carry(row.name,artifacts.read(turn.session_id,lane,row));
          }
          if (!carried.length) for (const ref of turn.prior_sources ?? []) {
            if (ref.bytes > 20 * 1024 * 1024) continue;
            const chunks: Buffer[] = []; let bytes = 0;
            for await (const chunk of ctx.attachments.readFileStream(ref)) {
              bytes += chunk.length; if (bytes > 20 * 1024 * 1024) throw new TaskError('scene_input_limit', '历史资料过大。');
              chunks.push(Buffer.from(chunk));
            }
            const data = Buffer.concat(chunks);
            if (bytes !== ref.bytes || (typeof ref.sha256 === 'string' && sha(data) !== ref.sha256)) throw new TaskError('file_bytes_changed', '历史资料内容已改变。');
            await carry(ref.name, data);
          }
          if (carried.length) content.unshift({ type:'text', text:'以下文件来自本对话此前对应处理结果，已按保存的版本复制到当前任务，请通过当前工具重新读取核验：' + JSON.stringify(carried) });
        }
        if (!previous && turn.prior_context?.[lane]) content.unshift({ type: 'text', text:
          '以下是此对话此前的交流记录，仅用于承接用户目标，不是当前资料的工具结果或已验证证据：\n' + turn.prior_context[lane] });
        const configured=sceneFor(turn.scene);
        const reason = executeUnavailable(configured);
        const mode = lane === 'baseline' ? 'baseline' : configured.runtime_kind==='paper_shadow_v1'?'shadow':reason ? 'baseline' : 'execute';
        selections.set(child, { scene: turn.scene, mode, rsi: mode !== 'baseline' });
        optionSelections.set(child, { [turn.scene]: turn.options }); saveSettings();
        const task = await preview({ content, request_id: requestId, model: turn.model, reasoning_effort: turn.reasoning_effort ?? 'off',
          budget_usd: turn.presentation === 'single' ? config.budget_usd : config.budget_usd / 2, mode }, child, 'native_chat');
        // Unavailable or invalid research libraries must be visible; never label a Baseline run as optimized.
        if (lane === 'motif' && reason && mode==='baseline') task.fallback_reason = reason;
        taskParents.set(task.request.task_id, { turn, lane });
        try { await submit(task, task.confirmation_digest, new AbortController().signal); }
        catch (error) { finish(task, 'failed', 'comparison_admission_failed'); await task.closing; throw error; }
        return { task_id: task.request.task_id };
      }); },
      async submit(_id) { /* prepare+submit is atomic within the existing admission lock. */ },
      async inspect(id, context) {
        const task = get(id), meta = taskParents.get(id) ?? context;
        let result;
        try { result = await refresh(task); }
        catch (error) { if (!terminal.has(task.status)) throw error; result = view(task, true); }
        if (meta) return { ...result,
          ...(task.scene.adapter === 'data-report' ? bindReportAnswer({answer: result.answer ?? '', workspace: task.workspace,
            eventsPath: join(task.output, 'events.jsonl'), startedAt: task.started_at, finishedAt: task.finished_at}) : {}),
          deliveries: captureComparisonDeliveries(artifacts, { turn: meta.turn.id, lane: meta.lane,
            attempt: meta.turn.lanes[meta.lane].attempt, workspace: task.workspace,
            adapter: task.scene.adapter, status: task.status, eventsPath: join(task.output, 'events.jsonl'),
            startedAt: task.started_at, finishedAt: task.finished_at, recoverMissing: context?.recoverMissing }) };
        return result;
      },
      async cancel(id) { const task = get(id); await controller.cancel({ sessionId: task.request.session_id }); },
      async publish(parent, turn, request) {
        await ensureOwned(parent);
        if (!agents.has(parent)) {
          const option = modelSelections.get(parent) ?? defaultModel;
          await original.selectModel(modelSelection(parent, option));
        }
        const agent = agents.get(parent);
        const events=agent.session.snapshotEvents();
        const priorComparison=events.find((e:any)=>e.type==='user/message'&&e.data.harless_comparison?.id===turn.id);
        let parentTurn=priorComparison?.data.harless_comparison.turn;
        if(request&&!priorComparison){
          parentTurn=1+Math.max(0,...events.filter((e:any)=>e.type==='turn/start').map((e:any)=>e.data.turn));
          // Public durable turn events make this app-owned result a native chat
          // turn. The two child Sessions perform all actual model execution.
          agent.session.append('turn/start',{turn:parentTurn});
          if(!events.some((e:any)=>e.type==='user/message'))await controller.rename({sessionId:parent,
            title:request.content.filter((p:any)=>p.type==='text').map((p:any)=>p.text).join(' ').slice(0,80)});
        }
        if (request && !agent.session.snapshotEvents().some((e: any) => e.type === 'user/message' && e.data.source?.rpcId === request.requestId)) {
          const ids: string[] = [], content: any[] = [];
          for (const part of request.content) if (part.type === 'text') content.push(part); else {
            const ref = ctx.fileUploads.resolve(agent, part.receiptId); if (!ref) throw new TaskError('file_receipt_not_owned', '上传回执不属于当前会话。');
            ids.push(part.receiptId); content.push({ type: 'file', attachment: ref });
          }
          const message = createUserMessage({ content: await ctx.attachments.admitPromptContent(content), source: { kind: 'user', rpcId: request.requestId },
            harless_comparison:{id:turn.id,turn:parentTurn,value:turn} } as any);
          const binding = ctx.fileUploads.bindPrompt(agent, ids, request.requestId);
          try { agent.session.append('user/message', message, { surfaceOp: 'append' }); binding.commit(); }
          finally { binding[Symbol.dispose](); }
        }
        // Use extensible metadata on a standard UserMessage. Out-of-vocabulary
        // log events cannot be resumed by this pinned Harness; GET supplies live
        // progress and final results without requiring an upstream change.
        if(parentTurn&&['completed','failed','cancelled'].includes(turn.status)&&
          !agent.session.snapshotEvents().some((e:any)=>e.type==='turn/end'&&e.data.turn===parentTurn))
          agent.session.append('turn/end',{turn:parentTurn,reason:{kind:'completed'}});
      },
    });
    ctx.effect(() => () => comparisons?.dispose(), 'harless-comparison-lifetime');
    ctx.effect(() => ctx.connection.fetch.register({ path: '/api/harless/comparisons', methods: ['GET', 'POST'], requestBody: 'buffered', async fetch(request: Request) {
      const rejected = ctx.connection.requestRejection(request); if (rejected) return new Response('Unauthorized', { status: rejected });
      try {
        const url = new URL(request.url), session = url.searchParams.get('session_id')!, id = url.searchParams.get('id')!;
        if (request.method === 'GET') {
          const value: any = await comparisons!.view(session, id), lane = url.searchParams.get('lane'), file = url.searchParams.get('file');
          if (url.searchParams.get('stream') === '1' && !file) {
            let stop: (() => void) | undefined, stopTrash: (() => void) | undefined, heartbeat: ReturnType<typeof setInterval> | undefined, closed = false;
            const encoder = new TextEncoder();
            const body = new ReadableStream({
              async start(stream) {
                const close = () => { closed = true; stop?.(); stopTrash?.(); if (heartbeat) clearInterval(heartbeat); request.signal.removeEventListener('abort', close); try { stream.close(); } catch {} };
                stopTrash = trash.subscribe(() => { if (trash.isDeleted(session)) close(); });
                request.signal.addEventListener('abort', close, { once: true });
                try {
                  stop = await comparisons!.subscribe(session, id, snapshot => {
                    if (!closed) try { stream.enqueue(encoder.encode('event: snapshot\ndata: ' + JSON.stringify(publicTaskView(snapshot)) + '\n\n')); } catch { close(); }
                  });
                  if (closed || request.signal.aborted) close();
                  else heartbeat = setInterval(() => { try { stream.enqueue(encoder.encode(': keepalive\n\n')); } catch { close(); } }, 15000);
                } catch { close(); }
              },
              cancel() { closed = true; stop?.(); stopTrash?.(); if (heartbeat) clearInterval(heartbeat); },
            });
            return new Response(body, { headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no' } });
          }
          if (file) {
            const row = lane && value.lanes[lane]?.artifacts.find((item: any) => item.id === file);
            if (!row) throw new TaskError('artifact_not_found', '找不到这个结果文件。', 404);
            return new Response(artifacts.read(id, lane!, row), { headers: { 'Content-Type': 'application/octet-stream',
              'Content-Disposition': "attachment; filename*=UTF-8''" + encodeURIComponent(row.name.split('/').pop()), 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' } });
          }
          return browserJson(value, { headers: { 'Cache-Control': 'no-store' } });
        }
        const body: any = await request.json();
        const result = await serialize(async () => body.action === 'rate' ? await comparisons!.rate(body.session_id, body.id, body.lane, body.score, body.revision, body.output_sha256)
          : body.action === 'retry' ? await comparisons!.retry(body.session_id, body.id, body.lane)
          : body.action === 'cancel' ? await comparisons!.cancel(body.session_id, body.id)
          : (() => { throw new TaskError('unknown_action', '不支持这个对照操作。'); })());
        return browserJson(result, { headers: { 'Cache-Control': 'no-store' } });
      } catch (error: any) { return browserJson({ error: { code: error.code ?? 'comparison_failed', message: error.message } }, { status: error.status ?? 400 }); }
    } }), 'harless-comparison-api');
  }
  const options = resolveAdapterOptions({ baseURL: brokerMode ? config.budget_broker_endpoint + '/v1' : config.endpoint,
    reasoningEffort: 'off', ...(config.max_output_tokens == null ? {} : { maxTokens: config.max_output_tokens }) } as any);
  // resolveAdapterOptions supplies 256k when omitted; remove that application
  // default so the native adapter leaves max_tokens off the provider request.
  if (config.max_output_tokens == null) delete (options as any).maxTokens;
  ctx.effect(() => ctx.llm.registerAdapter(['deepseek-official'], new WebDeepSeekAdapter({ options: () => options,
    resolveApiKey: async () => config.provider_mode === 'mock' ? 'sss-mock-only' : process.env.DEEPSEEK_API_KEY!,
    resolveUserId: () => principal, prepareExtensions: async () => ({ fields: {}, accept: async () => {} }),
  })), 'sss-web-task-provider');
  ctx.on('agent/created', ({ agent }: any) => {
    agents.set(agent.session.id, agent);
    if (ownedSessions.has(agent.session.id)) {
      workspaceFor(agent.session.id);
      bindScene(agent, sceneFor(forSession(agent.session.id)?.scene.id ?? selections.get(agent.session.id)?.scene ?? defaults.scene), forSession(agent.session.id)?.source_pending);
    }
    agent.ctx.on('agent/turn-stopping',async({signal}:any)=>{
      const t=forSession(agent.session.id);if(!t?.management||!t.management.used)return;
      const events=readFileSync(join(t.output,'events.jsonl'),'utf8').trim().split('\n').filter(Boolean).map(s=>JSON.parse(s));
      const decision=await t.management.acceptance.stop(events,signal);
      if(decision){t.management.live.runtime.fail('acceptance_repair_requires_ordinary_harness');agent.steer(createUserMessage({content:[{type:'text',text:decision.instruction}],source:{kind:'task-acceptance-repair',session_id:agent.session.id,repair:decision.repair}}));}
    });
    agent.ctx.on('tools/execute',async(exec:any,next:any)=>{const t=forSession(agent.session.id);if(t?.management)await confirmManagementEffect(t,agent,exec);return next();});
    agent.ctx.on('tools/result',(exec:any,result:any)=>{const t=forSession(agent.session.id);t?.interceptor?.observe(agent.session.id,exec,result);if(t?.management){t.management.live.observer.result();if(t.selection.rsi&&t.request.mode==='execute')t.management.live.runtime.observe(exec,result);t.management.acceptance.observe(exec,result);t.management.used=true;}});
  }, { global: true });
  ctx.on('session/event', (session: any, event: any) => {
    const task = forSession(session.id); if (!task || task.status !== 'running') return;
    progress.get(task.request.task_id)?.event(event);
    if(task.management){
      const d=join(task.output,'native-sessions');mkdirSync(d,{recursive:true,mode:0o700});appendFileSync(join(d,session.id+'.jsonl'),JSON.stringify(event)+'\n',{mode:0o600});
      appendFileSync(join(task.output,'events.jsonl'),JSON.stringify({...event,original_seq:event.seq,actual_agent_session_id:session.id})+'\n',{mode:0o600});
    }else appendFileSync(join(task.output, 'events.jsonl'), JSON.stringify(event) + '\n', { mode: 0o600 });
    // Controller has already validated and transformed receipt/image input here.
    if (event.type === 'user/message' && event.data.source?.kind === 'user' && task.status === 'running') {
      task.humans.set(event.data.id, digest(event.data.content));
      task.current_humans.add(event.data.id);
    }
    if (event.type === 'tool/call') task.stats.tool_calls = Number(task.stats.tool_calls) + 1;
    if (event.type === 'tool/result' && event.data.message?.content?.some((part: any) => part.isError === true)) task.stats.tool_errors = Number(task.stats.tool_errors) + 1;
    if (event.type === 'assistant/message') {
      task.answer = event.data.message.content.filter((part: any) => part.type === 'text').map((part: any) => part.text).join('\n');
      json(join(task.output, 'answer.json'), event);
      writeFileSync(join(task.output, 'answer.md'), task.answer, { mode: 0o600 });
    }
    record(task);
  }, { global: true });
  ctx.on('agent/error', ({ agent, error }: any) => {
    const task = forSession(agent.session.id); if (task) finish(task, /budget|request limit|429/i.test(String(error)) ? 'budget_exhausted' : 'failed', String(error));
  }, { global: true });
  ctx.on('agent/status', ({ agent, status }: any) => {
    const task = forSession(agent.session.id); if (task?.status === 'running' && status === 'idle') finish(task, 'completed');
  }, { global: true });
  ctx.on('llm/stream', (request: any, next: any) => {
    const task = forSession(request.sessionId);
    const expectedOutput=task?.management?Math.min(config.max_output_tokens??4000,4000):(config.max_output_tokens??undefined);
    if(task?.management&&request.maxTokens===undefined)request.maxTokens=expectedOutput;
    if (!task || task.status !== 'running' || active !== task.request.task_id ||
        request.provider !== task.model_option.provider || request.model !== task.model_option.model ||
        request.reasoningEffort !== task.reasoning_effort ||
        request.maxTokens !== expectedOutput || !isAgentLoopRequest(request)) throw Error('Unapproved task model request');
    const humans = request.messages.filter((message: any) => message.role === 'user' && message.source?.kind === 'user');
    if (request.messages.some((message: any) => message.source?.kind === 'goal')) throw Error('Goal continuation is outside this task admission');
    if (!humans.some((message: any) => task.current_humans.has(message.id)) ||
        humans.some((message: any) => task.humans.get(message.id) !== digest(message.content))) throw Error('Task user envelope changed');
    // DSH omits the tools field entirely when the agent has no capabilities.
    // Treat that wire representation as the same empty schema bound at creation.
    const requestedTools = request.tools ?? [];
    if (digest(requestedTools) !== digest(task.tools)) throw Error('Tool schema version changed');
    json(join(task.output, 'model-request-config.json'), { provider: request.provider, model: request.model,
      reasoning_effort: request.reasoningEffort ?? null, reasoning_effort_sent: request.reasoningEffort !== undefined,
      max_output_tokens: request.maxTokens ?? null, output_cap_sent: request.maxTokens !== undefined,
      tools_order: requestedTools.map((tool: any) => tool.name), tools_sha256: digest(requestedTools),
      human_message_sha256: humans.map((message: any) => digest(message.content)), mode: task.request.mode });
    task.stats.llm_decisions = Number(task.stats.llm_decisions) + 1; record(task);
    const live = progress.get(task.request.task_id) ?? createTaskProgress(); progress.set(task.request.task_id, live); live.beginAttempt();
    return (async function* () {
      const stream = task.management ? task.management.live.intercept(request,next) : task.interceptor ? await task.interceptor.intercept(request.sessionId, request, next) : next();
      for await (const chunk of stream) { live.chunk(chunk); task.answer = live.snapshot().answer; yield chunk; }
    })();
  }, { global: true });
  ctx.on('dispose',()=>{for(const t of tasks.values())if(t.management&&t.status==='running'){
    const job=new OperationJob(fileURLToPath(new URL('../../',import.meta.url)),t.management.binding.job_file);if(job.load().status==='running')job.apply('pause',{reason:'host_shutdown'});
    t.status='interrupted';t.failure='server_stopped_original_task_preserved';record(t);
  }});
  const taskRoute = { methods: ['GET', 'POST'] as const, requestBody: 'buffered' as const,
    fetch: async (request: Request) => {
      try {
        if (request.method === 'GET') {
          const query=new URL(request.url).searchParams;const id=query.get('task_id');
          if(id&&query.has('artifact')){
            const task=get(id);const file=task.management?.artifacts?.find((r:any)=>r.id===query.get('artifact'));
            if(!file||fileSha(file.path)!==file.sha256)throw new TaskError('artifact_missing','整理结果文件不存在或已改变',404);
            return new Response(readFileSync(file.path),{headers:{'Content-Type':'application/octet-stream','Content-Disposition':`attachment; filename*=UTF-8''${encodeURIComponent(file.name.split('/').pop())}`,'Cache-Control':'no-store'}});
          }
          if (id) return browserJson(await refresh(get(id)), { headers: { 'Cache-Control': 'no-store' } });
          const rows = await Promise.all([...tasks.values()].filter(task => !trash.isDeleted(task.request.session_id)).map(refresh));
          const aggregate: Record<string, number> = { tasks: rows.length };
          for (const row of rows) { aggregate[row.status] = (aggregate[row.status] ?? 0) + 1;
            for (const field of ['upstream_requests', 'verified_skips', 'tool_calls', 'prompt_tokens', 'completion_tokens']) aggregate[field] = (aggregate[field] ?? 0) + Number(row.stats[field] ?? 0); }
          return browserJson({ tasks: rows, aggregate, capability_profile: config.capability_profile,
            provider_mode: config.provider_mode, model_options: modelOptions,
            default_mode: defaults.mode, budget_usd: config.budget_usd, settings: settingsView() });
        }
        const body: any = await request.json();
        const result = await serialize(async () => {
          if (body.action === 'preview') {
            if (body.session_id) trash.assertVisible(body.session_id);
            if (body.session_id && !ownedSessions.has(body.session_id)) throw new TaskError('session_not_owned', 'Session is outside this Web run');
            if (body.session_id && (comparisons?.isLane(body.session_id) || comparisons?.hasSession(body.session_id))) throw new TaskError('comparison_session', '请在原对照会话的聊天输入框发送任务。', 409);
            return view(await preview(body.request, body.session_id), true);
          }
          const task = get(body.task_id);
          if (body.action === 'resume') return resumeManagement(task,body.confirmation_digest,request.signal);
          if (body.action === 'submit') return submit(task, body.confirmation_digest, request.signal);
          if (body.action === 'cancel') { await controller.cancel({ sessionId: task.request.session_id }); return view(task, true); }
          if (body.action === 'upload') {
            if (task.status !== 'awaiting_confirmation') throw new TaskError('task_not_draft', 'Only draft tasks accept attachments', 409);
            if (task.model_option.provider === 'harless-glm') throw new TaskError('unsupported_input', 'The GLM connection currently supports text only', 400);
            if (typeof body.name !== 'string' || !body.name.length || body.name.length > 255 || /[\x00-\x1f]/.test(body.name) ||
                typeof body.data !== 'string' || body.data.length > 350000 || Buffer.from(body.data, 'base64').toString('base64') !== body.data) throw new TaskError('invalid_upload', 'Invalid file name or canonical base64');
            const data = Buffer.from(body.data, 'base64');
            if (!data.length || data.length > 256 * 1024) throw new TaskError('upload_too_large', 'File limit is 256 KiB', 413);
            const uploaded = await ctx.fileUploads.uploadStream({ sessionId: task.request.session_id,
              name: body.name, data: (async function* () { yield data; })(), signal: request.signal });
            const changed = normalizeWebTaskRequest({ content: [...task.request.content, { type: 'file', receiptId: uploaded.receiptId }],
              inputs: task.request.resources, mode: task.request.mode, budget_usd: task.request.budget_usd,
              request_id: task.request.request_id, capability_profile: task.request.capability_profile }, {
              task_id: task.request.task_id, session_id: task.request.session_id, default_mode: config.mode,
              default_budget_usd: config.budget_usd, max_budget_usd: config.budget_usd,
              default_profile: task.scene.id, allowed_profiles: [task.scene.id], max_parts: 32, max_content_bytes: 768 * 1024 });
            task.request = changed; task.delivery.push({ type: 'file', receiptId: uploaded.receiptId });
            if (task.scene.adapter) {
              task.scene_inputs = await bindSceneInputs(ctx, agents.get(task.request.session_id), task.workspace, task.scene,
                task.request.content, task.scene_options, task.delivery.filter(part => part.type === 'text').map(part => (part as any).text).join('\n'), task.request.task_id);
              task.source_pending = sourcePendingFor(task.scene, task.scene_inputs);
              await selectPreset!(agents.get(task.request.session_id), sessionPreset(config.output, task.workspace, task.scene));
              bindScene(agents.get(task.request.session_id), task.scene);
              task.scope_sha256 = scopeDigest(task.workspace, task.scene);
              if (digest(schemas.get(task.request.session_id)) !== digest(task.tools)) throw new TaskError('confirmation_changed', 'Tool schema changed', 409);
            }
            updateDraft(task); return view(task, true);
          }
          throw new TaskError('unknown_action', 'Supported actions: preview, submit, cancel, upload');
        });
        return browserJson(result, { headers: { 'Cache-Control': 'no-store' } });
      } catch (error) {
        appendFileSync(join(config.output, 'admission-errors.jsonl'), JSON.stringify({ time: utc(), error: String(error) }) + '\n', { mode: 0o600 });
        const known = error instanceof TaskError || error instanceof WebTaskRequestError || error instanceof SettingsError || error instanceof SessionTrashError;
        return browserJson({ error: { code: known ? error.code : 'task_request_failed', message: known ? String((error as Error).message) : '暂时无法开始任务，请稍后重试。' } },
          { status: error instanceof TaskError || error instanceof SessionTrashError ? error.status : 400 });
      }
    } };
  for (const path of ['/api/harless/tasks', '/api/sss/tasks']) {
    ctx.effect(() => ctx.connection.fetch.register({ ...taskRoute, path }), 'harless-tasks-api-' + path);
  }
  const settingsRoute = { methods: ['GET', 'POST'] as const, requestBody: 'buffered' as const,
    fetch: async (request: Request) => {
      try {
        const url = new URL(request.url), sessionId = url.searchParams.get('session_id') ?? undefined;
        if (request.method === 'GET') {
          const value = await serialize(async () => { if (sessionId) await ensureOwned(sessionId); const t=sessionId?forSession(sessionId):undefined;if(t?.management)t.management.status=await managementBridge(t.management.config,{action:'status'});return settingsView(sessionId); });
          return browserJson({ ...value, sessions: [...ownedSessions].filter(id => !trash.isDeleted(id)).map(session_id => ({ session_id, ...settingsView(session_id) })) }, { headers: { 'Cache-Control': 'no-store' } });
        }
        const body: any = await request.json();
        const result = await serialize(async () => {
          if (body.action === 'select') return setSelection(body.session_id, body.selection);
          if (body.action === 'select_preview_scene') return setSelection(body.session_id, { scene: body.scene_id });
          if (body.action === 'clear_preview_scene') return setSelection(body.session_id, { scene: defaultSceneId });
          if(body.action==='set_scene_options'){
            const current=settingsView(body.session_id);
            if(typeof body.session_id!=='string')throw new SettingsError('session_required','请选择所属 Session');
            const routed = Boolean(comparisons && config.comparison_scenes?.includes(current.selection.scene) && !comparisons.isLane(body.session_id));
            if (routed && (comparisons!.busy(body.session_id) || (forSession(body.session_id) && !terminal.has(forSession(body.session_id)!.status)))) throw new TaskError('session_busy', '请等待当前回复完成或取消后再调整选项。', 409);
            if (current.scene_locked && !routed) throw new TaskError('scene_requires_new_session', '场景选项已固定，请在新会话中设置。', 409);
            const options=sceneOptions(body.options,sceneFor(current.selection.scene));
            optionSelections.set(body.session_id,{...(optionSelections.get(body.session_id)??{}),[current.selection.scene]:options});
            saveSettings();return settingsView(body.session_id);
          }
          if (body.action === 'new_session') {
            if (body.inherit_session) await ensureOwned(body.inherit_session);
            const chosen = body.inherit_session ? settingsView(body.inherit_session).selection : defaults;
            const next = body.selection === undefined ? chosen : changeSelection(chosen, body.selection, scenes, executeUnavailable);
            const group = body.inherit_session && ctx.workspaceRegistry?.list().find((row: any) => row.sessionIds.includes(body.inherit_session));
            const created = await controller.create({ agentPreset: sceneFor(next.scene).preset, ...(group ? { workspaceId: group.id } : {}) });
            selections.set(created.sessionId, { ...next });
            if(body.inherit_session && optionSelections.has(body.inherit_session))optionSelections.set(created.sessionId,structuredClone(optionSelections.get(body.inherit_session)));
            saveSettings();
            return { session_id: created.sessionId, ...settingsView(created.sessionId) };
          }
          throw new SettingsError('unknown_action', 'Supported actions: select, select_preview_scene, clear_preview_scene, new_session');
        });
        return browserJson(result, { headers: { 'Cache-Control': 'no-store' } });
      } catch (error) {
        return browserJson({ error: { code: (error as any).code ?? 'settings_failed', message: String((error as Error).message) } },
          { status: error instanceof TaskError || error instanceof SessionTrashError ? error.status : 400 });
      }
    } };
  ctx.effect(() => ctx.connection.fetch.register({ ...settingsRoute, path: '/api/harless/settings' }), 'harless-settings-api');
  registerSessionTrashRoute(ctx, trash, serialize);
  ctx.effect(() => protectPublicSessionOutput(controller), 'geneloop-public-session-output');
  ctx.effect(() => protectDeletedSessions(controller, trash), 'harless-trash-session-guards');
  ctx.inject?.(['sessionQuery'], (scope: any) => scope.effect(() => protectDeletedSessionQuery(scope.sessionQuery, trash, privateLanes.isPrivate)));
  ctx.effect(() => protectDeletedSessionFiles(undefined, ctx.fileUploads, trash), 'harless-trash-upload-guards');
  ctx.inject?.(['workspaceFiles'], (scope: any) => scope.effect(() => protectDeletedSessionFiles(scope.workspaceFiles, undefined, trash)));
  if (ctx.commands) ctx.effect(() => ctx.commands.register({ name: 'harless', description: 'Choose a scene, mode, and RSI setting',
    input: { hint: 'scene | mode | rsi | list | status' },
    handler: ({ agent, rawInput }: any) => serialize(async () => {
      try {
        const id = agent.session.id, command = parseHarlessCommand(rawInput);
        settingsView(id);
        if (command.kind === 'panel') {
          return { kind: 'success', text: 'Choose a scene, mode, or RSI setting from the /harless picker.' };
        }
        if (command.kind === 'list') return { kind: 'success', text: scenes.map(scene =>
          `${scene.label} · ${scene.unavailable_reason ?? 'connected'}`).join('\n') };
        const value = command.kind === 'change' ? await setSelection(id, command.patch) : settingsView(id);
        const current = value.current_task;
        const planned = sceneFor(value.selection.scene);
        return { kind: 'success', text: `${planned.label}${planned.unavailable_reason ? ' (' + planned.unavailable_reason + ')' : ''} · Mode ${value.selection.mode === 'baseline' ? 'Origin' : value.selection.mode} · RSI ${value.selection.rsi ? 'On' : 'Off'}${current ? ` · Current task: ${current.scene} / ${current.mode} / ${current.status}` : ''}` };
      } catch (error) { return { kind: 'error', text: String((error as Error).message) }; }
    }) }), 'harless-command');
  for (const path of ['/tasks', '/sss', '/harless']) {
    ctx.effect(() => ctx.webServer.register({ kind: 'exact', path, handler: (_request: any, response: any) => {
      response.writeHead(302, { Location: '/', 'Cache-Control': 'no-store' });
      response.end();
    } }), 'harless-legacy-page-redirect-' + path);
  }
  const accountLink = process.env.HARLESS_GATEWAY_ENABLED === '1' ?
    '<script>' + readFileSync(fileURLToPath(new URL('./harless_account_link.js', import.meta.url)), 'utf8') + '</script>' : '';
  const brandScript = '<script>' + readFileSync(fileURLToPath(new URL('./geneloop_brand.js', import.meta.url)), 'utf8') + '</script>';
  const workspaceScript = '<script>' + readFileSync(fileURLToPath(new URL('./geneloop_workspaces.js', import.meta.url)), 'utf8') + '</script>';
  ctx.effect(() => ctx.webServer.tapIndex((html: string) => html
    .replace(/<title>[^<]*<\/title>/i, '<title>GeneLoop</title>')
    .replace('</head>', brandScript + workspaceScript + '</head>')
    .replace('</body>', accountLink + '</body>')), 'harless-product-presentation');
  for (const [asset, type] of [['geneloop-spiral.svg', 'image/svg+xml'], ['geneloop.jpg', 'image/jpeg']]) {
  ctx.effect(() => ctx.webServer.register({ kind: 'exact', path: '/assets/' + asset,
    handler: (request: any, response: any) => {
      if (!['GET', 'HEAD'].includes(request.method)) {
        response.writeHead(405, { Allow: 'GET, HEAD' }); response.end(); return;
      }
      response.writeHead(200, { 'Content-Type': type, 'Cache-Control': 'public, max-age=3600',
        'X-Content-Type-Options': 'nosniff' });
      response.end(request.method === 'HEAD' ? '' : readFileSync(new URL('./brand/' + asset, import.meta.url)));
    } }), 'harless-product-logo-' + asset);
  }
}
