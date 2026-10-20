/** Opt-in search experiment. The production shim/library bytes stay frozen.
 * Admission wiring mirrors geneloop_web_search; the native provider and gateway
 * remain responsible for credentials, cancellation, billing and HTTP behavior.
 */
import { appendFileSync,readFileSync,readdirSync,lstatSync,realpathSync } from 'node:fs';
import {join,resolve,relative,isAbsolute} from 'node:path';
import {createHash} from 'node:crypto';
import { DeepSeekSearchProvider } from '@deepseek-ai/dsh-web-search-deepseek';
import {createRetrievalEvidence,evidenceSearchTool} from './retrieval_evidence.ts';
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
  const enabled=process.env.SSS_RETRIEVAL_EVIDENCE==='1',memories=new Map<string,any>();
  const searchOutput=enabled?Number(process.env.SSS_RETRIEVAL_SEARCH_OUTPUT_TOKENS??4096):4096;
  if(!Number.isInteger(searchOutput)||searchOutput<128||searchOutput>4096)throw Error('bounded_search_output_required');
  function memory(agent:any){
    if(!enabled)return null;
    if(memories.has(agent.session.id))return memories.get(agent.session.id);
    const sha=(x:any)=>createHash('sha256').update(x).digest('hex');
    function active(){
      const found=readdirSync(join(policy.output,'tasks')).flatMap(id=>{
        try{const output=join(policy.output,'tasks',id),state=JSON.parse(readFileSync(join(output,'task-state.json'),'utf8'));
          return state.session_id===agent.session.id&&state.user_id===policy.user_id&&state.status==='running'&&state.scene==='paper-proofreading'?[{output,state}]:[];
        }catch{return [];}
      });
      if(found.length!==1)throw Error('search_evidence_requires_owned_paper_task');
      return found[0];
    }
    const value=createRetrievalEvidence({binding:()=>{
      const {output,state}=active(),cfg=JSON.parse(readFileSync(join(output,'effective-config.json'),'utf8'));
      if(cfg.session_id!==agent.session.id||cfg.user_id!==policy.user_id)throw Error('search_evidence_owner_changed');
      const workspace=resolve(cfg.workspace),r=relative(resolve(policy.output),workspace);
      if(r.startsWith('..')||isAbsolute(r)||realpathSync(workspace)!==workspace)throw Error('search_evidence_workspace_changed');
      const approved=readFileSync(join(workspace,'approved-inputs.json'));
      for(const [name,version]of Object.entries(JSON.parse(approved.toString()).files)){
        const p=resolve(workspace,'inputs',name);
        if(relative(join(workspace,'inputs'),p).startsWith('..')||isAbsolute(relative(join(workspace,'inputs'),p))||realpathSync(p)!==p||!lstatSync(p).isFile()||sha(readFileSync(p))!==version)throw Error('search_evidence_input_changed');
      }
      return {session:agent.session.id,task:state.task_id,user:policy.user_id,inputs:sha(approved),
        goal:sha(readFileSync(join(output,'task.json'))),model:agent.session.requestHeader()?.config.model};
    },audit:row=>{
      const {output}=active();appendFileSync(join(output,'retrieval-evidence.jsonl'),JSON.stringify({...row,at:new Date().toISOString()})+'\n',{mode:0o600});
    }});
    memories.set(agent.session.id,value);return value;
  }
  if(enabled)ctx.on('agent/created',({agent}:any)=>{
    const base=agent.ctx.tools.get('web_search',agent);
    if(!base)throw Error('native_web_search_required');
    agent.ctx.tools.register(evidenceSearchTool(base,memory(agent)));
    agent.ctx.systemPrompt.section({name:'retrieval-evidence',order:10221,text:
      '检索证据复用：web_search结果按查询保留evidence_id和来源候选。当前问题需要已有候选时，可用同一工具的reuse短参数选择；Runtime不再请求搜索模型。已有来源的事实/版本仍须读取权威页面判断，候选不足须补查。来源记录不是事实认证，不可由未搜到正式版推断不存在。'});
  },{global:true});
  if(enabled)ctx.on('agent/status',({agent,status}:any)=>{if(status==='idle')memories.delete(agent.session.id);},{global:true});
  const provider=new AdmittedSearchProvider(() => {
    const agent = ctx.agents.currentInitiator();
    if (!agent) throw Error('search requires an active owning Agent');
    const model = agent.session.requestHeader()?.config.model;
    if (!['deepseek-flash', 'deepseek-v4-flash', 'deepseek-v4-pro'].includes(model)) throw Error('search model is not configured');
    return { apiKey: process.env.DEEPSEEK_API_KEY, baseURL: `${endpoint}/search/${agent.session.id}`,
      model, apiVersion: '2023-06-01', maxTokens: searchOutput, maxUses: 3,
      recordRequest: request => agent.session.append('web/deepseek-search-llm-request', request) };
  });
  if(enabled){const search=provider.search.bind(provider);
    provider.search=async(request:any,signal:any)=>{
      const agent=ctx.agents.currentInitiator();if(!agent)throw Error('search requires an active owning Agent');
      return memory(agent)!.search(request,signal,()=>search(request,signal));
    };
  }
  ctx.web.registerSearchProvider(provider);
}
