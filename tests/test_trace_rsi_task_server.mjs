import test from 'node:test';
import assert from 'node:assert/strict';
import { linkSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { digest } from '../src/adapters/paper_rsi_program.ts';
import { sha256 } from '../src/adapters/paper_triage_validation.ts';
import { createTraceRsiTaskTools, projectTraceInputs } from '../scenarios/paper-submission/trace-rsi-task-server.ts';

const clone=value=>JSON.parse(JSON.stringify(value));
function fixture(t) {
  const root=realpathSync(mkdtempSync(join(tmpdir(),'sss-trace-task-test-'))),work=join(root,'work');
  mkdirSync(work);t.after(()=>rmSync(root,{recursive:true,force:true}));
  // Synthetic identity program and declared witnesses verify binding/IO guards.
  // No domain algorithm, model authorship, real certification or savings claimed.
  const strings={type:'array',items:{type:'string'}},schema={type:'object',properties:{expected:strings,observed:strings},
    required:['expected','observed'],additionalProperties:false};
  const candidate={schema_version:1,name:'replay_fixture',description:'合成绑定诊断',input_schema:schema,output_schema:schema,program:['var','input']};
  const bindings={expected:{file:'catalog.json',pointer:'/data/expected'},observed:{file:'triage.json',pointer:'/references/*/key'}};
  const provenance={trace_bundle_sha256:'a'.repeat(64),fixture_type:'synthetic_diagnostic',proposal:{input_bindings:bindings},
    source_witnesses:[{run_id:'synthetic-run',session_id:'synthetic-learning',call_id:'synthetic-call',events_sha256:'b'.repeat(64)}]};
  const certification={status:'passed',kind:'source_replay',heldout_cases:2,fixture_type:'synthetic_diagnostic'};
  const body={schema_version:1,kind:'model_generated_trace_tool',candidate,candidate_sha256:digest(candidate),
    provenance,provenance_sha256:digest(provenance),certification,certification_sha256:digest(certification)};
  const frozen={...body,manifest_digest:digest(body)},libraryPath=join(root,'frozen-tool.json');
  const report={references:[{key:'a',fact:'保留科研文字'}],notes:'文字判断由模型负责'},catalog={data:{expected:['a','b']}};
  const catalogPath=join(root,'catalog.json'),reportPath=join(work,'triage.json'),sourcePath=join(root,'source.txt'),codePath=join(root,'code.txt');
  writeFileSync(libraryPath,JSON.stringify(frozen));writeFileSync(catalogPath,JSON.stringify(catalog));
  writeFileSync(reportPath,JSON.stringify(report));writeFileSync(sourcePath,'immutable source');writeFileSync(codePath,'fixed diagnostic code version');
  const config={library_path:libraryPath,work,catalog_path:catalogPath,catalog_sha256:sha256(readFileSync(catalogPath)),
    source_version:'c'.repeat(64),case_id:'synthetic-case',session_id:'synthetic-task-session',
    source_files:{[catalogPath]:sha256(readFileSync(catalogPath)),[sourcePath]:sha256(readFileSync(sourcePath))},
    code_files:{[codePath]:sha256(readFileSync(codePath))}};
  return {root,work,config,candidate,bindings,frozen,libraryPath,catalog,report,catalogPath,reportPath,sourcePath,codePath};
}
function frozenWithBindings(f,bindings) {
  const changed=clone(f.frozen);changed.provenance.proposal.input_bindings=bindings;
  changed.provenance_sha256=digest(changed.provenance);const {manifest_digest,...body}=changed;changed.manifest_digest=digest(body);
  writeFileSync(f.libraryPath,JSON.stringify(changed));
}
function base(f,input,reportBytes=readFileSync(f.reportPath)) {
  return {input_sha256:digest(input),report_sha256:sha256(reportBytes),source_version:f.config.source_version,
    candidate_sha256:digest(f.candidate),catalog_sha256:f.config.catalog_sha256};
}

test('generic frozen bindings project pointers, wildcards and fields without mutating source objects',()=>{
  const catalog={'nested/name':{rows:[{id:'a',meta:{n:1},extra:'omit'},{id:'b',meta:{n:2},extra:'omit'}]},'~label':'escaped'};
  const report={references:[{key:'x'},{key:'y'}]},before=clone(catalog);
  const input=projectTraceInputs(catalog,report,{
    chosen:{file:'catalog.json',pointer:'/nested~1name/rows',fields:['id','meta']},
    numbers:{file:'catalog.json',pointer:'/nested~1name/rows/*/meta/n'},
    last:{file:'triage.json',pointer:'/references/-1/key'},escaped:{file:'catalog.json',pointer:'/~0label'}
  });
  assert.deepEqual(input,{chosen:[{id:'a',meta:{n:1}},{id:'b',meta:{n:2}}],numbers:[1,2],last:'y',escaped:'escaped'});
  input.chosen[0].meta.n=9;assert.deepEqual(catalog,before);
  for (const bindings of [{x:{file:'../catalog.json',pointer:''}},{x:{file:'/tmp/catalog.json',pointer:''}},
    {x:{file:'catalog.json',pointer:'/constructor'}},{x:{file:'catalog.json',pointer:'/nested~1name/rows',fields:['__proto__']}},
    {x:{file:'catalog.json',pointer:'/missing'}},{x:{file:'catalog.json',pointer:'/~0label/*'}},
    {x:{file:'catalog.json',pointer:'/nested~1name/rows',fields:['missing']}}])
    assert.throws(()=>projectTraceInputs(catalog,report,bindings));
});

test('read and candidate check share real receipt hashes; unissued, forged and cross-session IDs fail',t=>{
  const f=fixture(t),tools=createTraceRsiTaskTools(f.config),input=projectTraceInputs(f.catalog,f.report,f.bindings);
  assert.deepEqual(tools.definitions.map(row=>row.name),['read_task_state','write_report',f.candidate.name]);
  const receiptBase=base(f,input),inputId='trace-input-'+digest({...receiptBase,session_id:f.config.session_id});
  assert.throws(()=>tools.call(f.candidate.name,{input_id:inputId}),/unregistered_or_stale/);
  const read=tools.call('read_task_state',{});assert.deepEqual(read.report,f.report);assert.deepEqual(read.input,input);
  assert.equal(read.input_id,inputId);for(const [key,value]of Object.entries(receiptBase))assert.equal(read[key],value);
  const check=tools.call(f.candidate.name,{input_id:read.input_id});assert.deepEqual(check.output,input);
  for(const key of ['input_id',...Object.keys(receiptBase)])assert.equal(check[key],read[key]);
  assert.throws(()=>tools.call(f.candidate.name,{input_id:'trace-input-'+'d'.repeat(64)}),/unregistered_or_stale/);
  assert.throws(()=>tools.call(f.candidate.name,{input_id:read.input_id,input}),/invalid_arguments/);
  assert.throws(()=>tools.call('read_task_state',{path:'/etc/passwd'}),/invalid_arguments/);
  const other=createTraceRsiTaskTools({...f.config,session_id:'another-task-session'}),otherRead=other.call('read_task_state',{});
  assert.notEqual(otherRead.input_id,read.input_id);assert.throws(()=>other.call(f.candidate.name,{input_id:read.input_id}),/unregistered_or_stale/);
});

test('CAS report writes preserve facts, return only the new receipt and invalidate older handles',t=>{
  const f=fixture(t),tools=createTraceRsiTaskTools(f.config),before=tools.call('read_task_state',{}),sourceBytes=readFileSync(f.catalogPath);
  const report={...f.report,references:[...f.report.references,{key:'b',fact:'由模型写入的修订'}]};
  const written=tools.call('write_report',{report_sha256:before.report_sha256,report});
  assert.deepEqual(Object.keys(written).sort(),['input_id','input_sha256','report_sha256','source_version','candidate_sha256','catalog_sha256'].sort());
  assert.deepEqual(JSON.parse(readFileSync(f.reportPath,'utf8')),report);assert.deepEqual(readFileSync(f.catalogPath),sourceBytes);
  assert.equal(written.report_sha256,sha256(readFileSync(f.reportPath)));assert.notEqual(written.input_id,before.input_id);
  assert.throws(()=>tools.call(f.candidate.name,{input_id:before.input_id}),/unregistered_or_stale/);
  assert.throws(()=>tools.call('write_report',{report_sha256:before.report_sha256,report}),/stale_report_write/);
  const checked=tools.call(f.candidate.name,{input_id:written.input_id});assert.deepEqual(checked.output,{expected:['a','b'],observed:['a','b']});
  assert.equal(checked.input_sha256,written.input_sha256);
  writeFileSync(f.reportPath,JSON.stringify({...report,notes:'外部变更'}));
  assert.throws(()=>tools.call(f.candidate.name,{input_id:written.input_id}),/stale_input_id/);
  const refresh=tools.call('read_task_state',{});assert.notEqual(refresh.input_id,written.input_id);
  assert.equal(tools.call(f.candidate.name,{input_id:refresh.input_id}).input_id,refresh.input_id);
});

test('invalid, oversized and arbitrary-path writes fail before changing the fixed private report',t=>{
  const f=fixture(t),tools=createTraceRsiTaskTools(f.config),read=tools.call('read_task_state',{}),before=readFileSync(f.reportPath);
  for (const args of [{report_sha256:'wrong',report:f.report},{report_sha256:read.report_sha256,report:[]},
    {report_sha256:read.report_sha256,report:f.report,file_path:f.catalogPath},
    {report_sha256:read.report_sha256,report:{references:[],notes:'x'.repeat(192000)}},
    {report_sha256:read.report_sha256,report:{references:[{}]}},
    {report_sha256:read.report_sha256,report:{references:[],extra:undefined}}]) {
    assert.throws(()=>tools.call('write_report',args));assert.deepEqual(readFileSync(f.reportPath),before);
  }
  assert.equal(tools.call(f.candidate.name,{input_id:read.input_id}).input_id,read.input_id);
});

test('library, immutable catalog/source and code bytes are guarded on every call',t=>{
  for(const kind of ['library','catalog','source','code']) {
    const f=fixture(t),tools=createTraceRsiTaskTools(f.config),read=tools.call('read_task_state',{});
    const path=kind==='library'?f.libraryPath:kind==='catalog'?f.catalogPath:kind==='source'?f.sourcePath:f.codePath;
    writeFileSync(path,readFileSync(path).toString('utf8')+' ');
    for (const [name,args] of [['read_task_state',{}],['write_report',{report_sha256:read.report_sha256,report:f.report}],
      [f.candidate.name,{input_id:read.input_id}]]) assert.throws(()=>tools.call(name,args),/version_changed|library_changed/);
  }
});

test('report/source symlinks, linked originals, foreign binding files and unbound catalog are refused',t=>{
  const f=fixture(t),tools=createTraceRsiTaskTools(f.config),read=tools.call('read_task_state',{});
  rmSync(f.reportPath);symlinkSync(f.catalogPath,f.reportPath);
  assert.throws(()=>tools.call('read_task_state',{}),/symlink/);
  assert.throws(()=>tools.call('write_report',{report_sha256:read.report_sha256,report:f.report}),/symlink/);
  rmSync(f.reportPath);writeFileSync(f.reportPath,JSON.stringify(f.report));
  const linked=join(f.root,'original-report.json');linkSync(f.reportPath,linked);
  assert.throws(()=>tools.call('read_task_state',{}),/private_copy/);rmSync(linked);
  const alias=join(f.root,'work-alias');symlinkSync(f.work,alias);
  assert.throws(()=>createTraceRsiTaskTools({...f.config,work:alias}),/symlink/);
  const catalogOriginal=readFileSync(f.catalogPath);rmSync(f.catalogPath);writeFileSync(join(f.root,'catalog-original.json'),catalogOriginal);
  symlinkSync(join(f.root,'catalog-original.json'),f.catalogPath);assert.throws(()=>tools.call('read_task_state',{}),/symlink/);
  rmSync(f.catalogPath);writeFileSync(f.catalogPath,catalogOriginal);
  frozenWithBindings(f,{expected:{file:'../catalog.json',pointer:'/data/expected'},observed:f.bindings.observed});
  assert.throws(()=>createTraceRsiTaskTools(f.config),/unregistered_input_binding/);
  writeFileSync(f.libraryPath,JSON.stringify(f.frozen));
  assert.throws(()=>createTraceRsiTaskTools({...f.config,source_files:{[f.sourcePath]:f.config.source_files[f.sourcePath]}}),/catalog_not_bound/);
});

test('normal revision service speaks actual MCP stdio with registered handles and no model calls',t=>{
  const f=fixture(t),configPath=join(f.root,'config.json');writeFileSync(configPath,JSON.stringify(f.config));
  const input=projectTraceInputs(f.catalog,f.report,f.bindings),inputId='trace-input-'+digest({...base(f,input),session_id:f.config.session_id});
  const requests=[
    {jsonrpc:'2.0',id:1,method:'initialize',params:{protocolVersion:'2025-06-18'}},
    {jsonrpc:'2.0',id:2,method:'tools/list'},
    {jsonrpc:'2.0',id:3,method:'tools/call',params:{name:f.candidate.name,arguments:{input_id:inputId}}},
    {jsonrpc:'2.0',id:4,method:'tools/call',params:{name:'read_task_state',arguments:{}}},
    {jsonrpc:'2.0',id:5,method:'tools/call',params:{name:f.candidate.name,arguments:{input_id:inputId}}},
    {jsonrpc:'2.0',id:6,method:'tools/call',params:{name:'write_report',arguments:{report_sha256:'wrong',report:f.report}}},
    {jsonrpc:'2.0',id:7,method:'ping'}
  ];
  const path=fileURLToPath(new URL('../scenarios/paper-submission/trace-rsi-task-server.ts',import.meta.url));
  const child=spawnSync(process.execPath,['--experimental-strip-types',path],{env:{...process.env,SSS_TRACE_RSI_TASK_CONFIG:configPath},
    input:requests.map(JSON.stringify).join('\n')+'\n',encoding:'utf8',timeout:5000});
  assert.equal(child.status,0,child.stderr);const rows=child.stdout.trim().split('\n').map(JSON.parse);
  assert.equal(rows.length,requests.length);assert.equal(rows[0].result.serverInfo.name,'paper_trace_rsi');
  assert.equal(rows[1].result.tools.length,3);assert.equal(rows[2].result.isError,true);
  const read=JSON.parse(rows[3].result.content[0].text),checked=JSON.parse(rows[4].result.content[0].text);
  assert.equal(read.input_id,inputId);assert.deepEqual(checked.output,input);assert.equal(checked.report_sha256,read.report_sha256);
  assert.equal(rows[5].result.isError,true);assert.deepEqual(rows[6].result,{});
});
