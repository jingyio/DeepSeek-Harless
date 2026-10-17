/** Web selection over DeepSeek's native, validated effort IDs. */
import { DeepSeekAdapter } from '@deepseek-ai/dsh-llm-deepseek';
import type { LlmResolvedModelInfo } from '@deepseek-ai/dsh-llm';

export const WEB_REASONING_EFFORTS = ['off', 'low', 'high', 'max'] as const;
export type WebReasoningEffort = typeof WEB_REASONING_EFFORTS[number];
export const WEB_REASONING_LABELS: Record<WebReasoningEffort, string> = {off:'Off', low:'Low', high:'High', max:'Max'};
export type WebModelOption = { provider: string; model: string; label: string; available: boolean;
  supported_reasoning_efforts?: readonly WebReasoningEffort[];
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
  if (effort && option.supported_reasoning_efforts && !option.supported_reasoning_efforts.includes(effort))
    throw new Error('The configured model does not support the selected reasoning effort');
  const reason = effort && option.reasoning_unavailable?.[effort];
  if (reason) throw new Error(reason);
  return effort;
}

export function webReasoningEffort(provider: string, value: unknown = 'off'): WebReasoningEffort | undefined {
  if (provider === 'harless-glm') {
    if (value === undefined || value === 'off') return undefined;
    throw new Error('The configured GLM connection does not expose a reasoning toggle');
  }
  if (provider === 'deepseek-official' && WEB_REASONING_EFFORTS.includes(value as WebReasoningEffort)) return value as WebReasoningEffort;
  throw new Error('Unsupported reasoning mode');
}

function productModes(model: LlmResolvedModelInfo, configured: readonly WebModelOption[]): LlmResolvedModelInfo {
  const option = configured.find(row => row.provider === model.provider && row.model === model.id);
  const unavailable = option?.reasoning_unavailable;
  const descriptions: Record<WebReasoningEffort, string> = {off:'关闭思考，直接回答。', low:'较低思考强度，适合简单或重视响应速度的任务。',
    high:'较高思考强度，适合复杂任务。', max:'最高思考强度，可能增加响应时间与 token 用量。'};
  // An older catalog may only list IDs. In that case retain the installed
  // adapter's native capabilities instead of assuming new API levels exist.
  const efforts = model.reasoning?.efforts.filter(row => WEB_REASONING_EFFORTS.includes(row.id as WebReasoningEffort) &&
      (!option?.supported_reasoning_efforts || option.supported_reasoning_efforts.includes(row.id as WebReasoningEffort)))
    .map(row => ({ ...row, name: WEB_REASONING_LABELS[row.id as WebReasoningEffort] + (unavailable?.[row.id as WebReasoningEffort] ? '（当前预算不可用）' : ''),
      description: unavailable?.[row.id as WebReasoningEffort] ?? descriptions[row.id as WebReasoningEffort] }));
  if (!efforts?.some(row => row.id === 'off')) throw new Error('DeepSeek deployment must support reasoning Off');
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
