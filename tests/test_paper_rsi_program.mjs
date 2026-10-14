import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,readFileSync,rmSync,realpathSync,symlinkSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {spawnSync} from 'node:child_process';
import {validateProgram,runProgram,digest,validateFrozen} from '../src/adapters/paper_rsi_program.ts';
import {createRsiTools} from '../scenarios/paper-submission/rsi-server.ts';
import {predictLearnedCheck} from '../src/adapters/dsh_paper_rsi_shadow.ts';
import {snapshotSource,sha256} from '../src/adapters/paper_triage_validation.ts';

test('pure programs cannot call host functions, use prototype paths or expand without bound',()=>{
 assert.throws(()=>validateProgram(['eval',['lit','process.exit()']]));
 assert.throws(()=>validateProgram(['constructor']));
 assert.throws(()=>runProgram(['get',['var','input'],['lit','constructor']],{}));
 assert.throws(()=>runProgram(['var','process'],{}));
 assert.equal(runProgram(['if',['lit',false],['var','undefined_variable'],['lit',42]],{}),42);
 assert.deepEqual(runProgram(['unique',['lit',[[1],[1],[2]]]],{}),[[1],[2]]);
 assert.throws(()=>runProgram(['lit',true],{x:'x'.repeat(192000)}));
 const map=['map',['get',['var','input'],['lit','x']],'v',['lit',true]];
 assert.throws(()=>runProgram(['map',['get',['var','input'],['lit','x']],'a',map],{x:Array(500).fill(1)}),/operation_limit/);
});
function fixture(){
 const root=realpathSync(mkdtempSync(join(tmpdir(),'sss-rsi-'))),source=join(root,'source');
 // Diagnostic stub only, deliberately not represented as a model-authored tool.
 const output={missing_pairs:[],unexpected_pairs:[],duplicate_pairs:[],source_mismatch:false,scope_mismatch:false,malformed:false};
 const candidate={schema_version:1,name:'check_report_structure',description:'diagnostic',program:['lit',output]};
 const body={schema_version:1,kind:'model_generated_pure_tool',candidate,candidate_sha256:digest(candidate),
  certification:{status:'passed',heldout_cases:6},provenance:{cordis_source_sha256:'a'.repeat(64)}};
 const lib={...body,manifest_digest:digest(body)};
 writeFileSync(join(root,'source.txt'),'immutable');writeFileSync(join(root,'triage.json'),'{}');
 writeFileSync(join(root,'tool.json'),JSON.stringify(lib));
 const config={work:root,library_path:join(root,'tool.json'),expected_pairs:[],source_root:root,
  source_files:snapshotSource(root),source_version:'b'.repeat(64),candidate_sha256:lib.candidate_sha256,tool_digest:lib.manifest_digest};
 // Artifacts must not participate in the input-source snapshot.
 config.source_files={'source.txt':sha256('immutable')};config.source_root=source;
 const mkdir=spawnSync(process.execPath,['-e',"require('fs').mkdirSync(process.argv[1]);require('fs').writeFileSync(process.argv[1]+'/source.txt','immutable')",source]);
 assert.equal(mkdir.status,0);return {root,config,lib};
}
test('frozen MCP tool rejects drift, stale writes, symlinks and unexpected arguments',()=>{
 const {root,config,lib}=fixture();try{
  const tools=createRsiTools(config),current=tools.call('read_report',{});
  assert.throws(()=>tools.call('check_report_structure',{path:'elsewhere'}));
  assert.throws(()=>tools.call('write_report',{report:{},previous_sha256:'wrong'}),/stale/);
  const result=tools.call('write_report',{report:{scope:'cited_arxiv_version_triage'},previous_sha256:current.report_sha256});
  assert.equal(result.report_sha256,sha256(readFileSync(join(root,'triage.json'))));
  assert.equal(tools.call('check_report_structure',{}).semantic_quality,'not_reviewed');
  assert.throws(()=>validateFrozen({...lib,candidate:{...lib.candidate,description:'changed'}}));
  writeFileSync(join(root,'source/source.txt'),'changed');assert.throws(()=>tools.call('read_report',{}),/version/);
  writeFileSync(join(root,'source/source.txt'),'immutable');rmSync(join(root,'triage.json'));symlinkSync(join(root,'source/source.txt'),join(root,'triage.json'));
  assert.throws(()=>tools.call('check_report_structure',{}),/symlink/);
 }finally{rmSync(root,{recursive:true,force:true});}
});
test('frozen service speaks real MCP stdio without model requests',()=>{
 const {root,config}=fixture();try{
  const path=join(root,'config.json');writeFileSync(path,JSON.stringify(config));
  const input=[{jsonrpc:'2.0',id:1,method:'initialize',params:{protocolVersion:'2025-06-18'}},
   {jsonrpc:'2.0',id:2,method:'tools/list'},
   {jsonrpc:'2.0',id:3,method:'tools/call',params:{name:'check_report_structure',arguments:{}}}].map(JSON.stringify).join('\n')+'\n';
  const child=spawnSync(process.execPath,['--experimental-strip-types','scenarios/paper-submission/rsi-server.ts'],
   {env:{...process.env,SSS_PAPER_RSI_CONFIG:path},input,encoding:'utf8',timeout:5000});
  assert.equal(child.status,0,child.stderr);const rows=child.stdout.trim().split('\n').map(JSON.parse);
  assert.equal(rows.length,3);assert.equal(rows[1].result.tools.length,3);
  assert.equal(JSON.parse(rows[2].result.content[0].text).semantic_quality,'not_reviewed');
 }finally{rmSync(root,{recursive:true,force:true});}
});
test('Shadow uses current report digest, frozen schema and repeated trace witnesses',()=>{
 const {root,config}=fixture();try{
  const tools=[{name:'mcp__paper_rsi__check_report_structure',parameters:{type:'object'}}];
  const body={execution_policy:'shadow_only',tool_digest:config.tool_digest,tools,
   motifs:[{anchor:'mcp__paper_rsi__write_report',next:tools[0].name,motif_id:'x',witnesses:[
    {session_id:'s1',events_sha256:'a'.repeat(64)},{session_id:'s2',events_sha256:'b'.repeat(64)}]}]};
  const lib={...body,manifest_digest:digest(body)},recent=[{name:body.motifs[0].anchor,ok:true,
   output:{source_version:config.source_version,candidate_sha256:config.candidate_sha256,report_sha256:sha256('{}')}}];
  assert.equal(predictLearnedCheck(lib,recent,tools,config).execution_authorized,false);
  assert.equal(predictLearnedCheck(lib,[{...recent[0],ok:false}],tools,config),null);
  assert.equal(predictLearnedCheck(lib,recent,[{...tools[0],parameters:{type:'string'}}],config),null);
  writeFileSync(join(root,'triage.json'),'{"new":true}');assert.equal(predictLearnedCheck(lib,recent,tools,config),null);
 }finally{rmSync(root,{recursive:true,force:true});}
});
