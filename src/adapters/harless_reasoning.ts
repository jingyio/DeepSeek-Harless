/** Product On/Off labels over DeepSeek's native, validated effort IDs. */
import { DeepSeekAdapter } from '@deepseek-ai/dsh-llm-deepseek';
import type { LlmResolvedModelInfo } from '@deepseek-ai/dsh-llm';

export type WebReasoningEffort = 'off' | 'high';

export function webReasoningEffort(provider: string, value: unknown = 'off'): WebReasoningEffort | undefined {
  if (provider === 'harless-glm') {
    if (value === undefined || value === 'off') return undefined;
    throw new Error('The configured GLM connection does not expose a reasoning toggle');
  }
  if (provider === 'deepseek-official' && (value === 'off' || value === 'high')) return value;
  throw new Error('Unsupported reasoning mode');
}

function productModes(model: LlmResolvedModelInfo): LlmResolvedModelInfo {
  const efforts = model.reasoning?.efforts.filter(row => row.id === 'off' || row.id === 'high')
    .map(row => ({ ...row, name: row.id === 'high' ? 'On' : 'Off',
      description: row.id === 'high' ? '启用推理，由模型思考后回答。' : '关闭推理，直接回答。' }));
  if (!efforts?.some(row => row.id === 'off') || !efforts.some(row => row.id === 'high'))
    throw new Error('DeepSeek deployment must support both reasoning modes');
  return { ...model, reasoning: { efforts, defaultEffort: efforts.find(row => row.id === 'off')!.id } };
}

/** Keep provider serialization in the installed adapter; customize discovery only. */
export class WebDeepSeekAdapter extends DeepSeekAdapter {
  override async resolveModel(...args: Parameters<DeepSeekAdapter['resolveModel']>) {
    return productModes(await super.resolveModel(...args));
  }
  override async prepareCall(...args: Parameters<DeepSeekAdapter['prepareCall']>) {
    const prepared = await super.prepareCall(...args);
    return { ...prepared, model: productModes(prepared.model) };
  }
}
