/** Official DSH search provider through the existing per-turn accounting route. */
import { readFileSync } from 'node:fs';
import { DeepSeekSearchProvider } from '@deepseek-ai/dsh-web-search-deepseek';
import {resolveExecutionAgent} from './geneloop_delegation.ts';
export const name = 'geneloop-web-search';
export const inject = ['web', 'agents'];
class AdmittedSearchProvider extends DeepSeekSearchProvider {
  // Tool discovery runs before a turn has an Agent initiator. Authorization
  // belongs to search(), whose option resolver requires the active Session.
  available() { return Boolean(process.env.DEEPSEEK_API_KEY); }
}
export function apply(ctx: any) {
  const policy = JSON.parse(readFileSync(process.env.SSS_WEB_POLICY!, 'utf8'));
  const endpoint=policy.budget_broker_endpoint ? policy.budget_broker_endpoint+'/v1' : policy.endpoint;
  if (!/^http:\/\/127\.0\.0\.1:\d+\/v1$/.test(endpoint)) throw Error('search requires the admitted model gateway');
  ctx.web.registerSearchProvider(new AdmittedSearchProvider(() => {
    const initiator = ctx.agents.currentInitiator();
    if (!initiator) throw Error('search requires an active owning Agent');
    const agent=resolveExecutionAgent(ctx,initiator);
    const model = agent.session.requestHeader()?.config.model;
    if (!['deepseek-flash', 'deepseek-v4-flash', 'deepseek-v4-pro'].includes(model)) throw Error('search model is not configured');
    return { apiKey: process.env.DEEPSEEK_API_KEY, baseURL: `${endpoint}/search/${agent.session.id}`,
      model, apiVersion: '2023-06-01', maxTokens: 4096, maxUses: 3,
      recordRequest: request => agent.session.append('web/deepseek-search-llm-request', request) };
  }));
}
