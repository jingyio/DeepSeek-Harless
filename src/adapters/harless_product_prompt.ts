/** Trusted product identity for both newly created and resumed Web agents. */
import { readFileSync } from 'node:fs';

export function productPersona(): { prefix: string; suffix: string; includeRuntimeContext: false } {
  const value = JSON.parse(readFileSync(new URL('../../config/geneloop-persona.json', import.meta.url), 'utf8'));
  if (Object.keys(value).sort().join(',') !== 'includeRuntimeContext,prefix,suffix' ||
      typeof value.prefix !== 'string' || !value.prefix.trim() ||
      typeof value.suffix !== 'string' || !value.suffix.trim() || value.includeRuntimeContext !== false)
    throw Error('invalid GeneLoop product persona');
  return value;
}

/** Scoped shadows also replace first-party defaults in previously saved presets.
 * Keep the normal prompt assembly: scene instructions, evidence rules and tool
 * schemas retain their owners. No user content or historical messages are edited.
 */
export function bindProductPrompt(agent: any): Array<() => void> {
  const prompt = agent.ctx.systemPrompt;
  const persona = productPersona();
  const disposers: Array<() => void> = [];
  try {
    for (const section of [
      { name: 'harness:identity', order: -1000, text: persona.prefix },
      { name: 'harness:source', order: 10000, text: '' },
      { name: 'app:web-surface', order: 10100,
        text: '用户通过 GeneLoop 网页与你交互。你没有隐式的页面、路由或截图视野；只依据实际提供的内容和工具结果作答。' },
      { name: 'geneloop:product-policy', order: 10300, text: persona.suffix },
    ]) disposers.push(prompt.section(section));
    disposers.push(prompt.suppressRuntimeContext());
    return disposers;
  } catch (error) {
    for (const dispose of disposers.reverse()) dispose();
    throw error;
  }
}
