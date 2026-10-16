import {test} from 'node:test';
import assert from 'node:assert/strict';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';
import {createPaperFlowShadowObserver,validatePaperFlowBridge} from '../src/adapters/harless_paper_flow_shadow.ts';

const P='mcp__paper_checks__';
const names=['pin_paper_citations','read_pinned_paper_citations','read_pinned_citation_records',
  'fetch_pinned_cited_preprint_metadata','fetch_pinned_formal_reference_metadata',
  'recover_pinned_formal_reference_queries'].map(name=>P+name);
const fields=['case_id','source_id','citation_id','citation_id','citation_id','citation_id'];
const schemas=names.map((name,index)=>({name,parameters:{type:'object',properties:{[fields[index]]:{type:'string'}},required:[fields[index]]}}));
const graphs=names.map((name,index)=>({anchor:index?[names[index-1]]:[],
  anchor_result:index?'success':'task_start',nodes:[{tool:name,bindings:{[fields[index]]:index
    ? {source_fields:[{tool:names[index-1],field:fields[index]}]} : {task_field:'case_id'}}}]}));
const make=()=>{
  const body={schema_version:1,kind:'paper_flow_current_shadow',execution_policy:'shadow_only',
    scene:'paper-proofreading',old_library_sha256:'0'.repeat(64),current_tool_schemas_sha256:'1'.repeat(64),
    tool_schema_hashes:Object.fromEntries(schemas.map(row=>[row.name,digest(row.parameters)])),
    source_trace_hashes:{run:'2'.repeat(64)},
    candidates:graphs.map(graph=>({motif_id:'paper-flow-'+digest(graph).slice(0,12),graph,
      training_session_count:2,witness_count:3})),
    report_migrations:[
      {legacy_motif_id:'paper-flow-1254fc79a35f',current_mapping:'stage_then_finalize',execution_policy:'model_owned_report_write'},
      {legacy_motif_id:'paper-flow-e4d6cba4afc9',current_mapping:'stage_then_finalize',execution_policy:'model_owned_report_write'},
      {legacy_motif_id:'paper-flow-f813f5b15671',current_mapping:'failed_finalize_requires_model_repair',execution_policy:'model_owned_report_write'}],
    limitations:['shadow only']};
  return {...body,manifest_digest:digest(body)};
};
const task={session_id:'session-a',task_id:'task-a',source_versions:{[names[0]]:'@observed'}};
const result=value=>({structuredContent:value});

test('migrated paper flow emits bound Shadow predictions and never a skip',()=>{
  const bridge=make(),audits=[];
  validatePaperFlowBridge(bridge,schemas);
  const observer=createPaperFlowShadowObserver(bridge,task,schemas,row=>audits.push(row));
  observer.beforeModel('session-b',schemas);
  assert.equal(audits.length,0);
  observer.beforeModel('session-a',schemas);
  assert.equal(audits[0].expected_tools[0],names[0]);
  assert.equal(audits[0].execution,false);
  observer.observe('session-a',{name:names[0],arguments:{case_id:'current'}},
    result({source_id:'source-0123456789abcdef0123456789abcdef',version_sha256:'a'.repeat(64)}));
  observer.beforeModel('session-a',schemas);
  assert.equal(audits.at(-1).expected_tools[0],names[1]);
  assert.equal(audits.filter(row=>row.kind==='model_request_skipped_verified').length,0);
});

test('tool drift, failed results and changed bindings do not become candidates',()=>{
  const bridge=make(),audits=[];
  const observer=createPaperFlowShadowObserver(bridge,task,schemas,row=>audits.push(row));
  observer.beforeModel('session-a',schemas);
  const count=audits.length;
  observer.observe('session-a',{name:names[0],arguments:{case_id:'current'}},
    {isError:true,content:[{type:'text',text:'error'}]});
  observer.beforeModel('session-a',schemas);
  assert.equal(audits.length,count);
  observer.observe('session-a',{name:names[0],arguments:{case_id:'current'}},
    result({source_id:'source-0123456789abcdef0123456789abcdef',version_sha256:'a'.repeat(64)}));
  observer.beforeModel('session-a',schemas.map((row,index)=>index?row:{...row,parameters:{type:'object'}}));
  assert.equal(audits.at(-1).reason,'current_tool_schema_changed');
  assert.throws(()=>createPaperFlowShadowObserver({...bridge,execution_policy:'execute'},task,schemas,()=>{}),
    /invalid paper flow bridge/);
});

test('current report flows remain Shadow diagnostics with model-owned repair',()=>{
  const audits=[],observer=createPaperFlowShadowObserver(make(),task,schemas,row=>audits.push(row));
  observer.observe('session-a',{name:P+'stage_current_audit',arguments:{}},
    result({staged:true,draft_sha256:'a'.repeat(64),reference_count:2,citation_check_count:6}));
  observer.beforeModel('session-a',schemas);
  assert.equal(audits.at(-1).kind,'paper_report_shadow_candidate');
  assert.equal(audits.at(-1).execution,false);
  observer.observe('session-a',{name:P+'finalize_current_audit',arguments:{}},
    result({finalized:false,validation_error:'renderer_input_duplicate_keys'}));
  observer.beforeModel('session-a',schemas);
  assert.equal(audits.at(-1).kind,'paper_report_model_handoff');
});
