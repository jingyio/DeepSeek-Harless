/** Product On/Off labels over DeepSeek's native, validated effort IDs. */
import { DeepSeekAdapter } from '@deepseek-ai/dsh-llm-deepseek';
import type { LlmResolvedModelInfo } from '@deepseek-ai/dsh-llm';

export type WebReasoningEffort = 'off' | 'high';
export type WebModelOption = { provider: string; model: string; label: string; available: boolean;
  reasoning_unavailable?: Partial<Record<WebReasoningEffort, string>> };

/** Filter installed native metadata, without inventing model capabilities. */
export function webDeepSeekModels<T extends {id: string; name?: string}>(native: readonly T[], configured: readonly WebModelOption[]): T[] {
  return configured.filter(row => row.available && row.provider === 'deepseek-official').map(row => {
    const model = native.find(item => item.id === row.model);
    if (!model || !['deepseek-flash', 'deepseek-v4-pro'].includes(model.id))
      throw new Error('Configured DeepSeek model is not supported by the installed provider');
    return {...model, name: row.label};
  });
}

export function webReasoningAvailability(option: WebModelOption, value: unknown = 'off'): WebReasoningEffort | undefined {
  const effort = webReasoningEffort(option.provider, value);
  const reason = effort && option.reasoning_unavailable?.[effort];
  if (reason) throw new Error(reason);
  return effort;
}

export function webReasoningEffort(provider: string, value: unknown = 'off'): WebReasoningEffort | undefined {
  if (provider === 'harless-glm') {
    if (value === undefined || value === 'off') return undefined;
    throw new Error('The configured GLM connection does not expose a reasoning toggle');
  }
  if (provider === 'deepseek-official' && (value === 'off' || value === 'high')) return value;
  throw new Error('Unsupported reasoning mode');
}

function productModes(model: LlmResolvedModelInfo, configured: readonly WebModelOption[]): LlmResolvedModelInfo {
  const unavailable = configured.find(row => row.provider === model.provider && row.model === model.id)?.reasoning_unavailable;
  const efforts = model.reasoning?.efforts.filter(row => row.id === 'off' || row.id === 'high')
    .map(row => ({ ...row, name: (row.id === 'high' ? 'On' : 'Off') + (unavailable?.[row.id as WebReasoningEffort] ? '（当前预算不可用）' : ''),
      description: unavailable?.[row.id as WebReasoningEffort] ?? (row.id === 'high' ? '启用推理，由模型思考后回答。' : '关闭推理，直接回答。') }));
  if (!efforts?.some(row => row.id === 'off') || !efforts.some(row => row.id === 'high'))
    throw new Error('DeepSeek deployment must support both reasoning modes');
  return { ...model, reasoning: { efforts, defaultEffort: efforts.find(row => row.id === 'off')!.id } };
}

/** Keep provider serialization in the installed adapter; customize discovery only. */
export class WebDeepSeekAdapter extends DeepSeekAdapter {
  private configuredModels: readonly WebModelOption[];
  constructor(config: ConstructorParameters<typeof DeepSeekAdapter>[0], models: readonly WebModelOption[] = []) {
    super(config); this.configuredModels = models;
  }
  override async resolveModel(...args: Parameters<DeepSeekAdapter['resolveModel']>) {
    return productModes(await super.resolveModel(...args), this.configuredModels);
  }
  override async prepareCall(...args: Parameters<DeepSeekAdapter['prepareCall']>) {
    const prepared = await super.prepareCall(...args);
    return { ...prepared, model: productModes(prepared.model, this.configuredModels) };
  }
}
