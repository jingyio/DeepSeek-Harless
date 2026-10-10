/** TEST ONLY. Replay actual Python tool receipts against the unchanged plugin.
 * The three in-memory edges/schema witnesses below are test fixtures, NOT
 * learned experimental evidence and are never exported as a Motif library.
 */
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { createRequire, registerHooks } from 'node:module';
import { resolve, dirname } from 'node:path';
import { pathToFileURL } from 'node:url';
if (process.argv[3]) {
  const dependencyRequire = createRequire(resolve(process.argv[3], 'package.json'));
  registerHooks({resolve(specifier, context, next) {
    try { return next(specifier, context); }
    catch (error) {
      if (!specifier.startsWith('@deepseek-ai/')) throw error;
      return next(pathToFileURL(dependencyRequire.resolve(specifier)).href, context);
    }
  }});
}
const {createInterceptor,digest} = await import('../research_report_agent_v3/motif_plugin.mjs');
const prefix='mcp__research_report__';
const contracts=JSON.parse(readFileSync(new URL('../research_report_agent_v3/tool_contracts.json',import.meta.url)));
const triples=[['approve_analysis','plan_id','run_analysis'],['run_analysis','analysis_id','verify_analysis'],['verify_analysis','verified_id','build_evidence']];
const artifacts=triples.map(([from,field,to])=>{
  const edge={from_tool:prefix+from,from_field:field,to_tool:prefix+to,to_param:field,
    training_evidence:[{case_id:'TEST_FIXTURE_1'},{case_id:'TEST_FIXTURE_2'}],
    certification_evidence:{case_id:'TEST_FIXTURE_3'}};
  edge.certified_digest=digest(edge);edge.motif_id='receipt-'+edge.certified_digest.slice(0,16);return edge;
});
const schemas=Object.fromEntries(triples.map(([,param,to])=>[prefix+to,
  {type:'object',required:[param],properties:{[param]:{type:'string'}}}]));
const library={schema_version:1,benchmark_version:3,kind:'benchmark_workspace_receipt_motifs',
  contracts,contracts_digest:digest(contracts),artifacts,tool_schemas:schemas,tool_schemas_digest:digest(schemas)};
library.library_digest=digest(library);
const options={tools:Object.entries(schemas).map(([name,parameters])=>({name,parameters}))};
const evidence=JSON.parse(readFileSync(process.argv[2],'utf8'));
assert.equal(evidence.kind,'TEST_FIXTURE_ONLY_actual_tool_receipts');
const results=[];
for(const scenario of evidence.scenarios){
  const audit=[];
  let fallbacks=0;
  const api=createInterceptor({library,task:scenario.task,mode:'execute',audit:row=>audit.push(row)});
  const observe=(row,callId)=>api.observe({name:prefix+row.name,callId,arguments:row.arguments},{value:{structuredContent:row.output}});
  const instruction=async()=>{
    const blocks=[];
    for await(const block of await api.intercept(options,()=>{fallbacks++;return(async function*(){})();}))blocks.push(block);
    return blocks.find(row=>row.type==='block-end' && row.block.type==='tool-call')?.block;
  };
  observe(scenario.calls[0],'TEST_FIXTURE_APPROVAL');
  for(let i=1;i<scenario.calls.length;i++){
    const actual=scenario.calls[i];
    const command=await instruction();
    if(scenario.allow){
      assert.equal(command?.name,prefix+actual.name);
      assert.deepEqual(JSON.parse(command.arguments),actual.arguments);
      observe(actual,command.id);
    }else{
      assert.equal(command,undefined,'false permission must delegate to LLM');
      observe(actual,'TEST_FIXTURE_MANUAL_'+i);
    }
  }
  assert.equal(await instruction(),undefined,'evidence frontier must return to LLM');
  const verified=audit.filter(row=>row.kind==='model_request_skipped_verified').length;
  assert.equal(verified,scenario.allow?3:0);
  assert.equal(fallbacks,scenario.allow?1:4);
  results.push({case_id:scenario.case_id,allow:scenario.allow,verified_fixture_continuations:verified,
                llm_fallback_callbacks: fallbacks,api_calls:0,audit});
}
const summary={passed:true,api_calls:0,scenarios:results.length,actual_statistical_tool_executions:18,
  verified_fixture_continuations:results.reduce((sum,row)=>sum+row.verified_fixture_continuations,0),
  disclaimer:'Test fixture library/schema and receipt replay, not learned edges, live MCP, or agent speedup evidence.',results};
writeFileSync(resolve(dirname(process.argv[2]),'diagnostic-plugin-results.json'),JSON.stringify(summary,null,2)+'\n');
console.log(JSON.stringify({passed:true,scenarios:summary.scenarios,api_calls:0,
  actual_statistical_tool_executions:18,verified_fixture_continuations:summary.verified_fixture_continuations}));
