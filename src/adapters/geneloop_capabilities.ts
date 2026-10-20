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
  { id: 'geneloop-tool-fs', name: '@deepseek-ai/dsh-tool-fs' },
  { id: 'geneloop-tool-fs-search', name: '@deepseek-ai/dsh-tool-fs-search',config:{sampleOverCapGlobResults:false} },
  { id: 'geneloop-tool-questions', name: '@deepseek-ai/dsh-tool-ask-user' },
  { id: 'geneloop-tool-todo', name: '@deepseek-ai/dsh-tool-todo',config:{allowParallelInProgress:true} },
  { id: 'geneloop-tool-skill', name: '@deepseek-ai/dsh-tool-skill' },
  { id: 'geneloop-tool-present', name: '@deepseek-ai/dsh-tool-present' },
  { id: 'geneloop-tool-subagent',name:'@deepseek-ai/dsh-tool-subagent',config:{provider:'geneloop-task',modelSelectionSettings:false,enableRunInBackground:false,backgroundMode:'one-shot'} },
];
export function sceneCertifiedTools(scene: { common_tools?: string[] }, tools: any[]) {
  const common = new Set(scene.common_tools ?? []);
  if ([...common].some(name => !COMMON_TOOLS.includes(name))) throw Error('unrecognized common tool');
  return tools.filter(tool => !common.has(tool.name));
}
