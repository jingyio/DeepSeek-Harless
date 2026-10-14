import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { apply as genericApply, createOnlineInterceptor } from '../src/adapters/dsh_online_motif.mjs';
import { apply as paperApply, structuralOnlySimilarity, closedCitationBatchRead } from '../src/adapters/dsh_paper_motif.ts';
import { compileLocalPrograms, digest } from '../src/motif_core/online_skill_runtime.mjs';
import './test_citation_shadow.mjs';
import './test_paper_delivery_check.mjs';
import { evidencePermission } from '../src/adapters/dsh_paper_evidence_policy.ts';

function fixture() {
  const pin='mcp__paper_checks__pin_paper_sources', read='mcp__paper_checks__read_pinned_paper_sources';
  const artifact={motif_id:'paper-edge',certified_digest:'a'.repeat(64),tools:[pin,read],
    supporting_task_count:2,validation_task_fingerprint:'different-fixture',
    transfer_evidence:[{from_tool:pin,from_field:'source_id',to_tool:read,to_param:'source_id'}]};
  artifact.local_programs=compileLocalPrograms(artifact);
  const manifest={schema_version:1,certification_scope:'protocol_diagnostic',source_library_digest:'b'.repeat(64),
    artifacts:[artifact],contracts:{
      [pin]:{read_only:true,required_params:['case_id'],default_params:{},output_fields:['source_id','version_sha256'],description:'Pin source'},
      [read]:{read_only:true,required_params:['source_id'],default_params:{},output_fields:['version_sha256'],description:'Read source'}},
    slot_rules:{[pin]:{case_id:'clear'}},version_fields:{[pin]:'version_sha256',[read]:'version_sha256'}};
  manifest.tool_schema_hashes={[read]:digest({type:'object',required:['source_id'],properties:{source_id:{type:'string'}}})};
  manifest.manifest_digest=digest(manifest);
  const task={schema_version:1,task_id:'paper',session_id:'paper-session',intent:'Check paper',input_version:'v1',
    bindings:{[pin]:{case_id:'clear'}},source_versions:{[pin]:'v1',[read]:'v1'}};
  return {pin,read,manifest,task,tools:[{name:read,parameters:{type:'object',required:['source_id'],properties:{source_id:{type:'string'}}}}]};
}

test('diagnostic library is rejected by the ordinary production installer',()=>{
  const root=mkdtempSync(join(tmpdir(),'paper-scope-'));const saved={...process.env};
  try {
    const {manifest,task}=fixture();writeFileSync(join(root,'manifest.json'),JSON.stringify(manifest));writeFileSync(join(root,'task.json'),JSON.stringify(task));
    process.env.SSS_ONLINE_MOTIF_MANIFEST=join(root,'manifest.json');process.env.SSS_ONLINE_MOTIF_TASK=join(root,'task.json');
    assert.throws(()=>genericApply({}),/certification scope/);
    delete process.env.SSS_PAPER_MOTIF_DIAGNOSTIC;assert.throws(()=>paperApply({}),/explicit opt-in/);
  } finally {process.env=saved;rmSync(root,{recursive:true,force:true});}
});

test('closed read bypass is verified once; source drift halts continuation',async()=>{
  const {pin,read,manifest,task,tools}=fixture();const audit=[];
  const runtime=createOnlineInterceptor({manifest,task,mode:'execute',similarity:structuralOnlySimilarity,audit:r=>audit.push(r)});
  runtime.observe(task.session_id,{name:pin,callId:'pin1',arguments:{case_id:'clear'}},
    {structuredContent:{source_id:'source-'+'a'.repeat(32),version_sha256:'v1'}});
  const stream=await runtime.intercept(task.session_id,{tools},()=>{throw Error('provider must be skipped');});
  const chunks=[];for await(const chunk of stream)chunks.push(chunk);
  const call=chunks.find(r=>r.type==='tool-call-delta');assert.equal(call.name,read);
  runtime.observe(task.session_id,{name:read,callId:call.id,arguments:JSON.parse(call.argumentsDelta)},
    {structuredContent:{version_sha256:'changed'}});
  assert.equal(audit.some(r=>r.kind==='model_request_skipped_verified'),false);
  assert.equal(runtime.state(task.session_id).halted,true);
  let provider=0;await runtime.intercept(task.session_id,{tools},()=>{provider++;return [];});assert.equal(provider,1);
});

test('shadow observes but never bypasses; incompatible tool schema falls back',async()=>{
  const {pin,manifest,task,tools}=fixture();let provider=0;const audit=[];
  const runtime=createOnlineInterceptor({manifest,task,mode:'shadow',similarity:structuralOnlySimilarity,audit:r=>audit.push(r)});
  runtime.observe(task.session_id,{name:pin,callId:'pin1',arguments:{case_id:'clear'}},
    {structuredContent:{source_id:'source-'+'a'.repeat(32),version_sha256:'v1'}});
  await runtime.intercept(task.session_id,{tools},()=>{provider++;return [];});
  assert.equal(provider,1);assert.equal(audit.filter(r=>r.kind==='shadow_candidate').length,1);
  const execute=createOnlineInterceptor({manifest,task,mode:'execute',similarity:structuralOnlySimilarity});
  execute.observe(task.session_id,{name:pin,callId:'pin1',arguments:{case_id:'clear'}},
    {structuredContent:{source_id:'source-'+'a'.repeat(32),version_sha256:'v1'}});
  await execute.intercept(task.session_id,{tools:[{...tools[0],parameters:{type:'object',required:['source_id'],properties:{source_id:{type:'number'}}}}]},()=>{provider++;return [];});
  assert.equal(provider,2);
});

test('paper opt-in recognises only the source-owned citation batch, never arbitrary ID continuations',()=>{
  const target='mcp__paper_checks__read_pinned_citation_records';
  const edge={from_tool:'mcp__paper_checks__read_pinned_paper_citations',from_field:'citation_id',to_tool:target,to_param:'citation_id'};
  const manifest={artifacts:[{motif_id:'learned',transfer_evidence:[edge]}],contracts:{[target]:{read_only:true,required_params:['citation_id'],default_params:{}}}};
  const row={motif_id:'learned',tool:target,version_relation:'same_source',code_node_ids:[],arguments:{citation_id:'source-'+'a'.repeat(32)}};
  assert.equal(closedCitationBatchRead(row,manifest),true);
  assert.equal(closedCitationBatchRead({...row,arguments:{citation_id:'invented'}},manifest),false);
  assert.equal(closedCitationBatchRead({...row,arguments:{citation_id:row.arguments.citation_id,keys:['chosen-by-model']}},manifest),false);
  assert.equal(closedCitationBatchRead({...row,tool:'mcp__other__read_pinned_result'},manifest),false);
  assert.equal(closedCitationBatchRead({...row,code_node_ids:['transform']},manifest),false);
  edge.from_field='semantic_choice';assert.equal(closedCitationBatchRead(row,manifest),false);
});

test('learned three-node batch dereference remains deferred by default and closes under paper opt-in',async()=>{
  const pin='mcp__paper_checks__pin_paper_citations', inspect='mcp__paper_checks__read_pinned_paper_citations', read='mcp__paper_checks__read_pinned_citation_records';
  const artifact={motif_id:'batch-chain',certified_digest:'a'.repeat(64),tools:[pin,inspect,read],supporting_task_count:2,
    validation_task_fingerprint:'heldout',transfer_evidence:[
      {from_tool:pin,from_field:'source_id',to_tool:inspect,to_param:'source_id'},
      {from_tool:inspect,from_field:'citation_id',to_tool:read,to_param:'citation_id'}]};
  artifact.local_programs=compileLocalPrograms(artifact);
  const manifest={schema_version:1,source_library_digest:'b'.repeat(64),artifacts:[artifact],contracts:{
    [pin]:{read_only:true,required_params:['case_id'],default_params:{},output_fields:['source_id','version_sha256'],description:'Pin'},
    [inspect]:{read_only:true,required_params:['source_id'],default_params:{},output_fields:['citation_id','version_sha256'],description:'Inspect'},
    [read]:{read_only:true,required_params:['citation_id'],default_params:{},output_fields:['version_sha256'],description:'Read'}},
    slot_rules:{[pin]:{case_id:'sample'}},version_fields:Object.fromEntries([pin,inspect,read].map(n=>[n,'version_sha256']))};
  manifest.manifest_digest=digest(manifest);
  const task={schema_version:1,task_id:'batch',session_id:'s',intent:'Cited scope',input_version:'v',bindings:{[pin]:{case_id:'sample'}},
    source_versions:{[pin]:'v',[inspect]:'v',[read]:'v'}};
  const tool={name:read,parameters:{type:'object',required:['citation_id'],properties:{citation_id:{type:'string'}}}};
  let provider=0;
  for(const enabled of [false,true]) {
    const runtime=createOnlineInterceptor({manifest,task,mode:'execute',similarity:structuralOnlySimilarity,
      ...(enabled?{closedContinuation:closedCitationBatchRead}:{})});
    runtime.observe('s',{name:pin,callId:'p',arguments:{case_id:'sample'}},{structuredContent:{source_id:'source-'+'a'.repeat(32),version_sha256:'v'}});
    runtime.observe('s',{name:inspect,callId:'i',arguments:{source_id:'source-'+'a'.repeat(32)}},{structuredContent:{citation_id:'source-'+'b'.repeat(32),version_sha256:'v'}});
    const stream=await runtime.intercept('s',{tools:[tool]},()=>{provider++;return [];});
    const chunks=[];for await(const chunk of stream)chunks.push(chunk);
    if(enabled) {
      const call=chunks.find(c=>c.type==='tool-call-delta');assert.equal(call.name,read);
      assert.deepEqual(JSON.parse(call.argumentsDelta),{citation_id:'source-'+'b'.repeat(32)});
    } else assert.equal(chunks.length,0);
  }
  assert.equal(provider,1);
});

test('bounded evidence permits public evidence and its own report, rejects coding, cross-case and original writes',()=>{
  const root=mkdtempSync(join(tmpdir(),'citation-policy-'));
  try {
    assert.equal(evidencePermission({name:'web_fetch',arguments:{url:'https://arxiv.org/abs/2401.02954'}},root,'manuscript'),undefined);
    assert.equal(evidencePermission({name:'write',arguments:{file_path:'triage.json'}},root,'manuscript'),undefined);
    assert.ok(evidencePermission({name:'bash',arguments:{command:'pwd'}},root,'manuscript'));
    assert.ok(evidencePermission({name:'write',arguments:{file_path:'../source/main.tex'}},root,'manuscript'));
    assert.match(evidencePermission({name:'mcp__paper_checks__pin_paper_citations',arguments:{case_id:'abstract'}},root,'manuscript'), /case_id="manuscript"/);
    assert.equal(evidencePermission({name:'mcp__paper_checks__pin_paper_citations',arguments:{case_id:'manuscript'}},root,'manuscript'),undefined);
  } finally {rmSync(root,{recursive:true,force:true});}
});
