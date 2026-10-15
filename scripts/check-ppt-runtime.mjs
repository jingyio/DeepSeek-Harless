/** Real MCP/rendering and shared Runtime protocol probe, with zero cloud calls. */
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {dirname,basename,join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {Client} from '@modelcontextprotocol/sdk/client/index.js';
import {StdioClientTransport,getDefaultEnvironment} from '@modelcontextprotocol/sdk/client/stdio.js';
import {createOnlineInterceptor} from '../src/adapters/dsh_online_motif.mjs';
import {bindUploadedPptTask,structuralOnlySimilarity} from '../src/adapters/harless_rsi_binding.ts';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const jobPath=process.argv[2];const job=JSON.parse(readFileSync(jobPath,'utf8'));
const area=dirname(jobPath);
const bundle=process.env.HARLESS_PPT_RUNTIME_BUNDLE;
const manifest=JSON.parse(readFileSync(join(bundle,'online-manifest.json'),'utf8'));
const schemas=JSON.parse(readFileSync(join(bundle,'tool-schemas.json'),'utf8'));
const inputs=job.inputs.map(row=>({...row,file:basename(row.path)}));
const task=bindUploadedPptTask(area,inputs,{task_id:job.job_id,session_id:'protocol-ppt-session'},manifest);
const client=new Client({name:'harless-ppt-protocol-probe',version:'1'},{capabilities:{}});
const env={...getDefaultEnvironment(),SSS_PPT_JOB:jobPath,SSS_PPT_DELIVERY_PYTHON:process.env.SSS_PYTHON};
for(const key of ['FONTCONFIG_FILE','FONTCONFIG_PATH'])if(process.env[key])env[key]=process.env[key];
const transport=new StdioClientTransport({command:'node',args:[join(root,'scenarios/research_ppt/dist/mcp-adapter.js'),'--web-session'],cwd:root,env,stderr:'pipe'});
transport.stderr?.on('data',()=>{});
const payload=r=>{
  if(r.isError)throw Error('Actual MCP tool failed: '+r.content?.find(x=>x.type==='text')?.text);
  return r.structuredContent ?? JSON.parse(r.content.find(x=>x.type==='text').text);
};
let toolCalls=0;
const call=async(name,args)=>{toolCalls++;return client.callTool({name,arguments:args},undefined,{timeout:180000});};
try{
  await client.connect(transport);
  const offered=new Set((await client.listTools()).tools.map(tool=>tool.name));
  const permitted=JSON.parse(readFileSync(join(root,'scenarios/research_ppt/web-scenario.json'),'utf8')).allowed_tools;
  assert.ok(permitted.every(name=>offered.has(name.replace('mcp__ppt__',''))),'actual MCP must offer the complete registered surface');
  const args={document_id:'doc_1'},pin=await call('pin_source',args),source=payload(pin);
  const exec={name:'mcp__ppt__pin_source',callId:'observed-pin',arguments:args};
  const audits=[];let delegations=0;
  const next=()=>{delegations++;return (async function*(){})();};
  const make=mode=>createOnlineInterceptor({manifest,task,mode,similarity:structuralOnlySimilarity,audit:row=>audits.push({...row,probe_mode:mode})});
  const shadow=make('shadow');shadow.observe(task.session_id,exec,pin);
  for await(const _ of await shadow.intercept(task.session_id,{tools:schemas},next)){}
  assert.equal(delegations,1);assert.equal(toolCalls,1);
  assert.equal(audits.filter(r=>r.kind==='shadow_candidate').length,1);
  const execute=make('execute');execute.observe(task.session_id,exec,pin);
  for await(const event of await execute.intercept(task.session_id,{tools:schemas},next)){
    if(event.type==='block-end' && event.block?.type==='tool-call'){
      const tool=event.block,args=JSON.parse(tool.arguments);
      assert.equal(tool.name,'mcp__ppt__read_source');assert.equal(args.source_id,source.source_id);
      const result=await call('read_source',args);
      execute.observe(task.session_id,{name:tool.name,callId:tool.id,arguments:args},result);
    }
  }
  assert.equal(delegations,1);
  assert.equal(audits.filter(r=>r.kind==='model_request_skipped_verified').length,1);
  const rendered=payload(await call('build_delivery',{plan:{title:'交付环境诊断',template:job.template,
    slides:[{title:'真实资料与原生交付',layout:'content',bullets:['两个种子的试验仍需要独立复现。'],
      sources:[{source_id:source.source_id,page:1}],notes:'固定合成计划，仅验证机械交付，不是模型生成或科研质量验收。'}]}}));
  writeFileSync(join(area,'probe-delivery.json'),JSON.stringify(rendered,null,2)+'\n',{mode:0o600});
  assert.equal(rendered.delivered,true);
  const report={model_requests:0,scope:'actual_mcp_rendering_and_runtime_protocol_not_model_quality',
    protocol_shadow_candidates:1,protocol_verified_batches:1,shadow_tool_calls:0,
    delivered:true,delivery:rendered,audits};
  writeFileSync(join(area,'probe-result.json'),JSON.stringify(report,null,2)+'\n',{mode:0o600});
  console.log(JSON.stringify({model_requests:0,delivered:true,protocol_shadow_candidates:1,protocol_verified_batches:1}));
}finally{await client.close();}
