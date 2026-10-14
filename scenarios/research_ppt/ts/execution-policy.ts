/** 固定实验执行边界；普通脚本复用，不是学习得到的 Motif。 */
import { randomUUID } from 'node:crypto';
import { AdapterRejected, digest, object, type Obj } from './delivery-adapter.js';

export const EXECUTION_POLICY_VERSION = 'research-ppt-execution-v17.1';
export const COMPOSED_TOOL_NAMES = ['build_delivery', 'render_delivery', 'revise_delivery'] as const;
export const RECOVERY_TOOL_NAMES = ['read_pending_plan', 'repair_pending_plan'] as const;
export type ExecutionStrategy = 'legacy_model_selected' | 'baseline_steps' | 'host_delivery';
export interface ExecutionHost {
  guard(): Promise<void>;
  audit(kind: string, data: Obj): Promise<void>;
  renderDelivery(plan: unknown): Promise<Obj>;
  reviseDelivery(deckId: string, updates: unknown): Promise<Obj>;
  restyleDelivery(sourceId: string, template: string): Promise<Obj>;
}

const GENERATE_STEPS = ['render_deck', 'inspect_deck', 'validate_deck', 'deliver_deck'];
const REVISE_STEPS = ['revise_deck', 'inspect_deck', 'validate_deck', 'deliver_deck'];
const RESTYLE_STEPS = ['restyle_deck', 'inspect_deck', 'validate_deck', 'deliver_deck'];
const ROUTES = [
  { request_tool: 'render_deck', host_script: 'render_delivery', backend_steps: GENERATE_STEPS },
  { request_tool: 'revise_deck', host_script: 'revise_delivery', backend_steps: REVISE_STEPS },
  { request_tool: 'restyle_deck', host_script: 'restyle_delivery', backend_steps: RESTYLE_STEPS },
  { request_tool: 'repair_pending_plan', host_script: 'render_delivery', backend_steps: GENERATE_STEPS },
];

function reject(code: string, message: string): never { throw new AdapterRejected(code, message); }
function exact(args: Obj, fields: string[]): void {
  if (fields.some(field => !Object.hasOwn(args, field)) || Object.keys(args).some(field => !fields.includes(field)))
    reject('invalid_arguments', '宿主脚本只接受该工具公开的完整参数，不接收额外执行指令。');
}

/** 缺省只用于旧任务兼容；新的对照必须显式冻结 baseline_steps/host_delivery。 */
export class ExecutionPolicy {
  readonly strategy: ExecutionStrategy;
  private readonly evidence: Obj;
  constructor(config: unknown) {
    if (config === undefined) this.strategy = 'legacy_model_selected';
    else {
      if (!object(config) || config.schema_version !== 1 || typeof config.strategy !== 'string'
        || Object.keys(config).some(key => !['schema_version', 'strategy'].includes(key))
        || !['baseline_steps', 'host_delivery'].includes(String(config.strategy)))
        reject('invalid_execution_policy', 'execution_policy 必须是 schema_version=1 与显式 baseline_steps/host_delivery 策略。');
      this.strategy = config.strategy as ExecutionStrategy;
    }
    const value: Obj = {
      schema_version: 1, policy_version: EXECUTION_POLICY_VERSION, strategy: this.strategy,
      config_sha256: digest(config ?? null),
      disabled_tools: this.strategy === 'legacy_model_selected' ? [] : [...COMPOSED_TOOL_NAMES],
      disabled_recovery_tools: this.strategy === 'host_delivery' ? [] : [...RECOVERY_TOOL_NAMES],
      local_plan_recovery: this.strategy === 'host_delivery',
      host_routes: this.strategy === 'host_delivery' ? structuredClone(ROUTES) : [],
      model_selects_host_script: this.strategy === 'legacy_model_selected', automatic_retry: false, automatic_content_change: false,
      scope: 'fixed_host_execution_policy_not_learned_rsi',
    };
    this.evidence = { ...value, policy_sha256: digest(value) };
  }
  snapshot(): Obj { return structuredClone(this.evidence); }

  /** 无返回表示沿原 MCP dispatch；有返回表示宿主已经执行真实有限脚本。 */
  async dispatch(host: ExecutionHost, name: string, args: Obj, recoveredPlan?: unknown): Promise<Obj | undefined> {
    if ((RECOVERY_TOOL_NAMES as readonly string[]).includes(name) && this.strategy !== 'host_delivery') {
      await host.audit('execution_policy_tool_rejected', {policy_sha256:this.evidence.policy_sha256,
        strategy:this.strategy,name,arguments_sha256:digest(args),reason:'local_recovery_disabled',backend_called:false});
      reject('execution_policy_tool_disabled', '普通步骤路径不执行宿主草稿恢复工具。');
    }
    if (this.strategy === 'legacy_model_selected') return undefined;
    if ((COMPOSED_TOOL_NAMES as readonly string[]).includes(name)) {
      await host.audit('execution_policy_tool_rejected', {
        policy_sha256: this.evidence.policy_sha256, strategy: this.strategy, name,
        arguments_sha256: digest(args), reason: 'model_selected_composed_tools_disabled_in_controlled_comparison',
        backend_called: false,
      });
      reject('execution_policy_tool_disabled', '本次对照禁止直接选择组合工具；请提交 render_deck 的明确计划或 revise_deck 的明确页面修改。');
    }
    if (this.strategy !== 'host_delivery' || !ROUTES.some(route => route.request_tool === name)) return undefined;
    if (name === 'repair_pending_plan') {
      if (!Object.hasOwn(args,'draft_id') || !Object.hasOwn(args,'version_sha256') || recoveredPlan===undefined)
        reject('invalid_arguments', '局部恢复需要已核版本的草稿和显式修改，不能直接提供整稿执行指令。');
    } else if (name === 'render_deck') exact(args, ['plan']);
    else if (name === 'revise_deck') {
      exact(args, ['deck_id', 'updates']);
      if (typeof args.deck_id !== 'string' || !args.deck_id.trim() || args.deck_id.length > 500 || /[\x00-\x1f]/.test(args.deck_id))
        reject('invalid_arguments', 'deck_id 必须是后端返回的有界真实句柄。');
    } else {
      exact(args, ['source_id','template']);
      if (typeof args.source_id !== 'string' || !args.source_id.trim() || args.source_id.length > 500 || /[\x00-\x1f]/.test(args.source_id)
        || typeof args.template !== 'string' || !['academic','lab'].includes(args.template))
        reject('invalid_arguments', '风格转换只接受真实 source_id 与 academic/lab 模板。');
    }
    const route = ROUTES.find(route => route.request_tool === name)!;
    const executionId = randomUUID();
    const execution = {
      schema_version: 1, strategy: this.strategy, policy_sha256: this.evidence.policy_sha256,
      script_execution_id: executionId, request_tool: name, host_script: route.host_script,
      arguments_sha256: digest(args), backend_steps: [...route.backend_steps],
      mechanism: 'ordinary_bounded_host_script', model_selected_script: false,
    };
    await host.guard();
    await host.audit('host_script_started', execution);
    try {
      const response = name === 'render_deck' || name === 'repair_pending_plan'
        ? await host.renderDelivery(name === 'render_deck' ? args.plan : recoveredPlan)
        : name === 'revise_deck' ? await host.reviseDelivery(String(args.deck_id), args.updates)
        : await host.restyleDelivery(String(args.source_id), String(args.template));
      await host.guard();
      await host.audit('host_script_completed', {
        ...execution, result_sha256: digest(response), delivered: response.delivered === true,
        deck_id: response.deck_id ?? null, validation_id: response.validation_id ?? null,
        file_sha256: response.file_sha256 ?? null,
        fallback_required: response.delivered !== true, scientific_quality: 'not_reviewed',
      });
      return { ...response, execution_policy: execution };
    } catch (error) {
      await host.audit('host_script_failed', {
        ...execution, error_code: error instanceof AdapterRejected ? error.code : 'host_script_failed',
        automatic_retry: false, fallback: 'return_failure_to_model_without_changing_content',
      });
      throw error;
    }
  }
}
