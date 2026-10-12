import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdirSync,mkdtempSync,readFileSync,realpathSync,rmSync,writeFileSync,symlinkSync,linkSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {spawnSync} from 'node:child_process';
import {digest} from '../src/adapters/paper_rsi_program.ts';
import {sha256} from '../src/adapters/paper_triage_validation.ts';
import {createPatchRsiTaskTools} from '../scenarios/paper-submission/patch-rsi-task-server.ts';
import {revisionExportOutput} from '../src/adapters/revision_export_receipt.ts';
function frozen(candidate,bindings={}){
 const provenance={trace_bundle_sha256:'a'.repeat(64),fixture_type:'synthetic_diagnostic',
  proposal:{input_bindings:bindings},source_witnesses:[{run_id:'synthetic',session_id:'s',call_id:'c',events_sha256:'b'.repeat(64)}]};
 const certification={status:'passed',kind:'source_replay',heldout_cases:2,fixture_type:'synthetic_diagnostic'};
 const body={schema_version:1,kind:'model_generated_trace_tool',candidate,candidate_sha256:digest(candidate),
  provenance,provenance_sha256:digest(provenance),certification,certification_sha256:digest(certification)};
 return {...body,manifest_digest:digest(body)};
}
function fixture(t,view=false){
 const root=realpathSync(mkdtempSync(join(tmpdir(),'sss-patch-test-'))),work=join(root,'work');mkdirSync(work);
 t.after(()=>rmSync(root,{recursive:true,force:true}));
 const report={notes:'保留顶层科研文字',references:[{key:'a',arxiv_id:'old',source_urls:['first','second']}]};
 const reportSchema={type:'object',properties:{notes:{type:'string'},references:{type:'array',items:{type:'object',
  properties:{key:{type:'string'},arxiv_id:{type:'string'},source_urls:{type:'array',items:{type:'string'}}},
  required:['key','arxiv_id','source_urls'],additionalProperties:false}}},required:['notes','references'],additionalProperties:false};
 const schema={type:'object',properties:{keys:{type:'array',items:{type:'string'}},before_report:reportSchema},required:['keys','before_report'],additionalProperties:false};
 const bindings={keys:{file:'triage.json',pointer:'/references/*/key'},before_report:{file:'catalog.json',pointer:'/initial_report'}};
 const rows=(fields)=>({type:'array',items:{type:'object',properties:fields,required:Object.keys(fields),additionalProperties:false}}),s={type:'string'};
 if(view){
  Object.assign(schema.properties,{triage_references:rows({key:s,arxiv_id:s}),
   catalog_cited_records:rows({key:s,record_path:s,arxiv_ids:{type:'array',items:s}}),
   catalog_query_items:rows({item_id:s,id:s,source_path:s})});schema.required=Object.keys(schema.properties);
  Object.assign(bindings,{triage_references:{file:'triage.json',pointer:'/references',fields:['key','arxiv_id']},
   catalog_cited_records:{file:'catalog.json',pointer:'/cited_records'},catalog_query_items:{file:'catalog.json',pointer:'/query_items'}});
 }
 // This count is intentionally a handwritten diagnostic, not an RSI result.
 const audit={schema_version:1,name:'diagnostic_audit',description:'合成绑定诊断，非质量认证',input_schema:schema,
  output_schema:view?{type:'object',properties:{before_count:{type:'integer'}},required:['before_count'],additionalProperties:false}:schema,
  program:view?['object',{before_count:['count',['get',['var','input'],['lit','keys']]]}]:['var','input']};
 const libraryPath=join(root,'audit.json'),patchPath=join(root,'patch.json'),catalogPath=join(root,'catalog.json');
 writeFileSync(libraryPath,JSON.stringify(frozen(audit,bindings)));
 // The algorithm is a public model-generated AST. This fixture supplies
 // synthetic witnesses solely to test IO and permissions without model calls.
 const patch=JSON.parse(readFileSync(new URL('../examples/rsi-tools/report-patch-v1/candidate.generated.json',import.meta.url)));
 writeFileSync(patchPath,JSON.stringify(frozen(patch)));writeFileSync(catalogPath,JSON.stringify({initial_report:report,
  cited_records:[{key:'a',record_path:'record/0',arxiv_ids:['new']}],query_items:[{item_id:'a:new',id:'new',source_path:'record/0'}]}));
 writeFileSync(join(work,'triage.json'),JSON.stringify(report));
 const config={library_path:libraryPath,patch_library_path:patchPath,patch_library_sha256:sha256(readFileSync(patchPath)),
  check_name:audit.name,work,catalog_path:catalogPath,catalog_sha256:sha256(readFileSync(catalogPath)),source_version:'c'.repeat(64),
  case_id:'diagnostic',session_id:'current-session',source_files:{[catalogPath]:sha256(readFileSync(catalogPath))},code_files:{[patchPath]:sha256(readFileSync(patchPath))}};
 if(view)config.read_context_protocol='revision_view_v1';
 return {root,work,config,report,patchPath,tools:createPatchRsiTaskTools(config)};
}
const plan=()=>({set_ids:[{key:'a',arxiv_id:'new'}],keep_once_keys:[],remove_keys:[],add_records:[]});
test('successful export projection binds the full audit; failures and unknown fields stay complete',()=>{
 const output={arxiv_id_mismatches:[],extra:[],issue_kinds:['正式版本待核验'],keys_match_query_items:true,
  missing:[],before_count:2,after_count:2,before_duplicate_key_count:1,added_key_count:1,removed_key_count:0,
  after_duplicate_key_count:0,existing_fields_preserved:true,top_level_preserved:true,changed_existing_records:[]};
 const projected=revisionExportOutput(output,'revision_receipt_v2');
 assert.deepEqual(projected,{structural_check_passed:true,audit_sha256:digest(output)});
 assert.equal(revisionExportOutput(output),output);
 for(const changed of [{missing:['a']},{existing_fields_preserved:false},{after_duplicate_key_count:1},
  {unexpected:'semantic conflict'},{before_count:-1},{keys_match_query_items:'true'}]){
  const failed={...output,...changed};assert.equal(revisionExportOutput(failed,'revision_receipt_v2'),failed);
 }
 assert.throws(()=>revisionExportOutput(output,'unknown'),/unknown_export_result_protocol/);
});
test('compact MCP preserves fields, checks current receipts and exports complete data',t=>{
 const f=fixture(t),read=f.tools.call('read_task_state',{});
 assert.deepEqual(f.tools.definitions.map(r=>r.name),['read_task_state','apply_revision_plan','diagnostic_audit','export_revision_report']);
 const written=f.tools.call('apply_revision_plan',{report_sha256:read.report_sha256,plan:plan()});
 assert.throws(()=>f.tools.call('apply_revision_plan',{report_sha256:read.report_sha256,plan:plan()}),/stale_report/);
 assert.throws(()=>f.tools.call('export_revision_report',{input_id:read.input_id}),/stale_export/);
 const artifact=f.tools.call('export_revision_report',{input_id:written.input_id});
 assert.equal(artifact.artifact_sha256,sha256(readFileSync(join(f.work,artifact.artifact_name))));
 const after=JSON.parse(readFileSync(join(f.work,'triage.json')));assert.deepEqual(after,{...f.report,references:[{...f.report.references[0],arxiv_id:'new'}]});
 assert.ok(readFileSync(join(f.work,'revision-report.md'),'utf8').includes(JSON.stringify(after,null,2)));
 assert.throws(()=>f.tools.call('write_report',{report_sha256:written.report_sha256,report:after}),/not_enabled/);
});
test('minimal revision view keeps paired source data and current generated audit while retaining full private fields',t=>{
 const f=fixture(t,true),read=f.tools.call('read_task_state',{});
 assert.deepEqual(read.view.current_rows,[{key:'a',arxiv_id:'old'}]);
 assert.deepEqual(read.view.source_records,[{key:'a',record_path:'record/0',arxiv_ids:['new']}]);
 assert.equal(read.view.audit.before_count,1);assert.ok(!JSON.stringify(read).includes('source_urls'));
 const written=f.tools.call('apply_revision_plan',{report_sha256:read.report_sha256,plan:plan()});
 const exported=f.tools.call('export_revision_report',{input_id:written.input_id});
 const text=readFileSync(join(f.work,exported.artifact_name),'utf8');assert.ok(text.includes('source_urls'));assert.ok(text.includes('保留顶层科研文字'));
});
test('patch version, unauthorized fields, artifact symlinks and hardlinks fail closed',t=>{
 const f=fixture(t),read=f.tools.call('read_task_state',{}),bytes=readFileSync(join(f.work,'triage.json'));
 assert.throws(()=>f.tools.call('apply_revision_plan',{report_sha256:read.report_sha256,plan:{...plan(),path:'/original'}}));
 assert.deepEqual(readFileSync(join(f.work,'triage.json')),bytes);
 const target=join(f.root,'untouched.txt');writeFileSync(target,'original');const artifact=join(f.work,'revision-report.md');
 symlinkSync(target,artifact);assert.throws(()=>f.tools.call('export_revision_report',{input_id:read.input_id}));
 assert.equal(readFileSync(target,'utf8'),'original');rmSync(artifact);linkSync(target,artifact);
 assert.throws(()=>f.tools.call('export_revision_report',{input_id:read.input_id}),/private_regular/);
 assert.equal(readFileSync(target,'utf8'),'original');
 writeFileSync(f.patchPath,readFileSync(f.patchPath).toString()+' ');
 assert.throws(()=>f.tools.call('apply_revision_plan',{report_sha256:read.report_sha256,plan:plan()}),/library_changed|version_changed/);
});
test('actual MCP stdio exposes the compact interface and rejects unknown tools',t=>{
 const f=fixture(t),path=join(f.root,'config.json');writeFileSync(path,JSON.stringify(f.config));
 const requests=[{jsonrpc:'2.0',id:1,method:'initialize',params:{protocolVersion:'2025-06-18'}},
 {jsonrpc:'2.0',id:2,method:'tools/list'},{jsonrpc:'2.0',id:3,method:'tools/call',params:{name:'write_report',arguments:{}}}];
 const result=spawnSync(process.execPath,['--experimental-strip-types','scenarios/paper-submission/patch-rsi-task-server.ts'],
  {env:{...process.env,SSS_TRACE_RSI_TASK_CONFIG:path},input:requests.map(JSON.stringify).join('\n')+'\n',encoding:'utf8',timeout:5000});
 assert.equal(result.status,0,result.stderr);const rows=result.stdout.trim().split('\n').map(JSON.parse);
 assert.equal(rows[1].result.tools.length,4);assert.equal(rows[2].result.isError,true);
});
