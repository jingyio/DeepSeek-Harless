/** Turn-scoped MCP permission boundary; the original adapter performs actual edits. */
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { CallToolRequestSchema, ListToolsRequestSchema } from '@modelcontextprotocol/sdk/types.js';
import { readFile, appendFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { object, privateFile, type Obj } from './delivery-adapter.js';
import { directEditEnvironment, previewExplicitUpdates } from './direct-edit-cli.js';

export const FEEDBACK_TOOLS = ['read_deck_plan','read_source','read_page','inspect_deck','revise_deck','validate_deck','deliver_deck'];
export function assertRevisionScope(args: Obj, deckId: string, pages: number[]) {
  if (args.deck_id !== deckId || Object.keys(args).some(k => !['deck_id','updates'].includes(k)) || !pages.length
      || !Array.isArray(args.updates) || !args.updates.length || args.updates.some(row => !object(row) || !pages.includes(Number(row.page))))
    throw Error('修订越出本条反馈的稿件或明确页码；请说明第几页或全部页面');
}
function payload(response: any): Obj {
  const value = response.structuredContent ?? JSON.parse(response.content?.find((x: any) => x.type === 'text')?.text ?? '{}');
  if (!object(value)) throw Error('原工具返回契约错误');
  if (response.isError || value.ok === false) throw Error(JSON.stringify(value));
  return value;
}
async function main() {
  const root = resolve(fileURLToPath(new URL('../../../', import.meta.url)));
  const scopePath = await privateFile(root, process.env.SSS_PPT_FEEDBACK_SCOPE ?? '');
  const scope = JSON.parse(await readFile(scopePath, 'utf8'));
  const job = await privateFile(root, scope.job), log = await privateFile(root, scope.calls_log);
  const client = new Client({name:'sss-ppt-feedback-guard',version:'1.0.0'},{capabilities:{}});
  const transport = new StdioClientTransport({command:'node',args:[resolve(root,'scenarios/research_ppt/dist/mcp-adapter.js'),'--job',job],cwd:root,
    env:directEditEnvironment(process.env.SSS_PPT_DELIVERY_PYTHON ?? 'python'),stderr:'pipe'});
  transport.stderr?.on('data', chunk => { void appendFile(scope.stderr_log,chunk,{mode:0o600}); });
  await client.connect(transport);
  const current = payload(await client.callTool({name:'read_deck_plan',arguments:{deck_id:scope.deck_id}}));
  if (current.file_sha256 !== scope.expected_sha256) throw Error('当前PPT版本已变化');
  const sourceIds = new Set((current.plan as any).slides.flatMap((s: any) => s.sources.map((r: any) => r.source_id)));
  const decks = new Set([scope.deck_id]), validations = new Set<string>();
  let revised = false, queue: Promise<any> = Promise.resolve();
  const listing = await client.listTools(), tools = FEEDBACK_TOOLS.map(name => listing.tools.find(t => t.name === name));
  if (tools.some(t => !t)) throw Error('反馈所需工具未安装');
  const server = new Server({name:'SSS bounded PPT feedback',version:'1.0.0'},{capabilities:{tools:{}}});
  server.setRequestHandler(ListToolsRequestSchema,async()=>({tools:tools as any}));
  server.setRequestHandler(CallToolRequestSchema,request=>{
    const run = queue.then(async()=>{
      const {name,arguments:args={}} = request.params;
      try {
        if (!FEEDBACK_TOOLS.includes(name)) throw Error('本反馈不允许此工具');
        if (['read_deck_plan','inspect_deck','validate_deck'].includes(name) && !decks.has(String(args.deck_id))) throw Error('稿件不属于当前对话');
        if (['read_source','read_page'].includes(name) && !sourceIds.has(args.source_id)) throw Error('来源不属于当前稿件');
        if (name === 'validate_deck' && args.deck_id === scope.deck_id) throw Error('不能用原稿验收代替新稿');
        if (name === 'deliver_deck' && !validations.has(String(args.validation_id))) throw Error('验收回执不属于本轮新稿');
        if (name === 'revise_deck') {
          if (revised) throw Error('本条反馈已产生新稿，不能再次改写');
          assertRevisionScope(args,scope.deck_id,scope.target_pages);
          previewExplicitUpdates(current.plan,args.updates,(current.plan as any).slides.length);
          const before = payload(await client.callTool({name:'read_deck_plan',arguments:{deck_id:scope.deck_id}}));
          if (before.file_sha256 !== scope.expected_sha256) throw Error('执行前稿件版本变化');
        }
        const response = await client.callTool({name,arguments:args},undefined,{timeout:300000}), value = payload(response);
        if (name === 'revise_deck') {
          const changed = (args.updates as any[]).map(row => row.page).sort((a,b)=>a-b);
          if (value.parent_deck_id !== scope.deck_id || !object(value.revision_audit) || value.revision_audit.passed !== true
              || value.revision_audit.non_target_slides_preserved !== true || value.revision_audit.shared_styles_preserved !== true
              || value.revision_audit.slide_count !== (current.plan as any).slides.length
              || JSON.stringify(value.revision_audit.changed_pages) !== JSON.stringify(changed)) throw Error('局部修订独立检查未通过');
          decks.add(String(value.deck_id)); revised = true;
          const after = payload(await client.callTool({name:'read_deck_plan',arguments:{deck_id:scope.deck_id}}));
          if (after.file_sha256 !== current.file_sha256) throw Error('原稿被改变');
        }
        if (name === 'validate_deck' && value.passed === true) validations.add(String(value.validation_id));
        await appendFile(log,JSON.stringify({name,arguments:args,value,successful:true})+'\n',{mode:0o600});
        return response;
      } catch (error) {
        await appendFile(log,JSON.stringify({name,arguments:args,successful:false,error:String((error as Error).message)})+'\n',{mode:0o600});
        return {isError:true,content:[{type:'text' as const,text:JSON.stringify({ok:false,message:String((error as Error).message)})}]};
      }
    }); queue=run.catch(()=>undefined);return run;
  });
  let closing=false;
  const close=async()=>{if(closing)return;closing=true;await server.close();await client.close();process.exit(0);};
  process.once('SIGTERM',close);process.once('SIGINT',close);process.stdin.once('end',close);
  await server.connect(new StdioServerTransport());
}
if (import.meta.main) main().catch(error=>{process.stderr.write(String(error)+'\n');process.exit(1);});
