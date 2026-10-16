/** Shared native tools. Scene-specific MCP contracts remain independently certified. */
import { readFileSync } from 'node:fs';
export const COMMON_TOOLS: readonly string[] = Object.freeze(JSON.parse(readFileSync(
  new URL('../../config/geneloop-capabilities.json', import.meta.url), 'utf8')).tools);
export function commonToolDenial(call: {name: string; arguments?: any}) {
  if (call.name === 'bash' && call.arguments?.sandbox_permissions !== undefined)
    return '网页命令始终在本会话工作区隔离执行，不支持扩大权限；请根据实际错误修正命令或说明无法完成。';
}
export const commonToolRows = () => [
  { id: 'geneloop-tool-web', name: '@deepseek-ai/dsh-tool-web' },
  { id: 'geneloop-tool-bash', name: '@deepseek-ai/dsh-tool-bash' },
  { id: 'geneloop-tool-jobs', name: '@deepseek-ai/dsh-tool-jobs', config: { completionDelivery: 'quiet' } },
];
export function sceneCertifiedTools(scene: { common_tools?: string[] }, tools: any[]) {
  const common = new Set(scene.common_tools ?? []);
  if ([...common].some(name => !COMMON_TOOLS.includes(name))) throw Error('unrecognized common tool');
  return tools.filter(tool => !common.has(tool.name));
}
