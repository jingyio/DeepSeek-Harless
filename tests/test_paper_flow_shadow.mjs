import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync,writeFileSync,rmSync,realpathSync } from 'node:fs';
import { tmpdir } from 'node:os';
import {join} from 'node:path';
import {predictFlow,validateFlowLibrary} from '../src/adapters/dsh_paper_flow_shadow.ts';
import {shadowDigest} from '../src/adapters/paper_shadow_runtime.ts';
import {snapshotSource} from '../src/adapters/paper_triage_validation.ts';
const P='mcp__paper_checks__';

test('shadow binds current handles, rejects source/schema drift and defers competing learned batches',()=>{
 const root=realpathSync(mkdtempSync(join(tmpdir(),'sss-flow-')));
 try{
  writeFileSync(join(root,'main.tex'),'\\cite{public}');
  const config={case_id:'new',source_root:root,source_files:snapshotSource(root),source_version:'a'.repeat(64),work:root};
  const tools=[{name:P+'read_pinned_citation_records',parameters:{type:'object'}}];
  const graph={anchor:[P+'read_pinned_paper_citations'],anchor_result:'success',nodes:[{tool:tools[0].name,
    bindings:{citation_id:{source_fields:[{tool:P+'read_pinned_paper_citations',field:'citation_id'}]}}}]};
  const motif={motif_id:'paper-flow-'+shadowDigest(graph).slice(0,12),graph,training_witnesses:[{run_id:'r',session_id:'s'}],training_session_count:1};
  const lib={schema_version:1,scope:'source_bound_readonly_batch_shadow',execution_policy:'shadow_only',motifs:[motif],
   source_traces:{r:{session_id:'s'}},tool_order:tools.map(t=>t.name),tool_schema_sha256:Object.fromEntries(tools.map(t=>[t.name,shadowDigest(t.parameters)]))};
  lib.manifest_digest=shadowDigest(lib);validateFlowLibrary(lib);
  const current={name:graph.anchor[0],ok:true,arguments:{},output:{version_sha256:config.source_version,citation_id:'source-'+'b'.repeat(32)}};
  const result=predictFlow(lib,config,[current],tools,true);
  assert.equal(result.expected_tools[0].arguments.citation_id,current.output.citation_id);assert.equal(result.execution_authorized,false);
  const completed=new Map([[JSON.stringify({arguments:{citation_id:current.output.citation_id},tool:tools[0].name}),{}]]);
  assert.equal(predictFlow(lib,config,[current],tools,true,null,completed).reason,'no_learned_guarded_edge');
  assert.equal(predictFlow(lib,config,[{...current,ok:false}],tools,true).reason,'no_learned_guarded_edge');
  assert.equal(predictFlow(lib,config,[current],[{...tools[0],parameters:{type:'string'}}],true).reason,'tool_or_source_drift');
  assert.equal(predictFlow({...lib,motifs:[motif,motif]},config,[current],tools,true).reason,'ambiguous_local_branches');
  const readTools=[{name:'read_current_triage',parameters:{type:'object'}}];
  const g={anchor:['check_paper_triage'],anchor_result:'needs_repair',artifact:'triage.json',nodes:[{tool:'read_current_triage',bindings:{}}]};
  const other={...lib,tool_order:['read_current_triage'],tool_schema_sha256:{read_current_triage:shadowDigest(readTools[0].parameters)},motifs:[{...motif,graph:g}]};
  const check={name:'check_paper_triage',ok:true,call_id:'check',output:{status:'needs_repair',source_version:config.source_version,report_sha256:'b'.repeat(64)}};
  const snap={source_version:config.source_version,call_id:'check',report_sha256:'b'.repeat(64)};
  assert.equal(predictFlow(other,config,[check],readTools,true,snap).expected_tools[0].tool,'read_current_triage');
  assert.equal(predictFlow(other,config,[check],readTools,true,{...snap,report_sha256:'c'.repeat(64)}).reason,'no_learned_guarded_edge');
  assert.equal(predictFlow(other,config,[{...check,output:{...check.output,status:'passed'}}],readTools,true,snap).reason,'no_learned_guarded_edge');
  writeFileSync(join(root,'main.tex'),'changed');assert.equal(predictFlow(lib,config,[current],tools,true).reason,'tool_or_source_drift');
 }finally{rmSync(root,{recursive:true,force:true});}
});
