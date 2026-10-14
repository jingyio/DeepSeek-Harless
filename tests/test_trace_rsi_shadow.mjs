import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync, rmSync, realpathSync, symlinkSync, linkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { markAgentLoopRequest } from '@deepseek-ai/dsh-llm';
import { digest } from '../src/adapters/paper_rsi_program.ts';
import { sha256 } from '../src/adapters/paper_triage_validation.ts';
import { createTraceRsiTaskTools } from '../scenarios/paper-submission/trace-rsi-task-server.ts';
import { apply, createTraceShadowInterceptor, predictTraceCheck, validateTraceShadowLibrary } from '../src/adapters/dsh_trace_rsi_shadow.ts';

const P='mcp__paper_trace_rsi__',clone=value=>JSON.parse(JSON.stringify(value));
const object=properties=>({type:'object',properties,required:Object.keys(properties),additionalProperties:false});
const array={type:'array',items:{type:'string',maxLength:100},maxItems:2000};
function rehash(value){const {manifest_digest,...body}=value;return {...body,manifest_digest:digest(body)};}
function fixture(t){
  const work=realpathSync(mkdtempSync(join(tmpdir(),'sss-trace-shadow-')));t.after(()=>rmSync(work,{recursive:true,force:true}));
  // Handwritten synthetic program/witnesses exercise the protocol only; they are
  // not model-generation evidence or independent research-quality certification.
  const candidate={schema_version:1,name:'compare_record_keys',description:'手写合成诊断',
    input_schema:object({expected:array,reported:array}),output_schema:object({missing:array,count:{type:'integer'}}),
    program:['object',{missing:['difference',['get',['var','input'],['lit','expected']],['get',['var','input'],['lit','reported']]],
      count:['count',['get',['var','input'],['lit','reported']]]}]};
  const provenance={trace_bundle_sha256:'a'.repeat(64),source_witnesses:[{run_id:'synthetic-run',session_id:'synthetic-session',call_id:'c',events_sha256:'b'.repeat(64)}],
    proposal:{input_bindings:{expected:{file:'catalog.json',pointer:'/keys'},reported:{file:'triage.json',pointer:'/keys'}}},fixture_type:'synthetic_diagnostic'};
  const certification={status:'passed',kind:'source_replay',heldout_cases:2};
  const frozen=rehash({schema_version:1,kind:'model_generated_trace_tool',candidate,candidate_sha256:digest(candidate),
    provenance,provenance_sha256:digest(provenance),certification,certification_sha256:digest(certification)});
  const libraryPath=join(work,'tool.json'),catalogPath=join(work,'catalog.json');
  writeFileSync(libraryPath,JSON.stringify(frozen));writeFileSync(catalogPath,JSON.stringify({keys:['a','b']}));
  writeFileSync(join(work,'triage.json'),JSON.stringify({keys:['a']}));writeFileSync(join(work,'code-version.txt'),'fixed-code');
  const codePaths=['scenarios/paper-submission/trace-rsi-task-server.ts','src/adapters/trace_rsi_program.ts',
    'src/adapters/paper_rsi_program.ts','src/adapters/dsh_trace_rsi_shadow.ts'].map(path=>resolve(path));
  codePaths.push(join(work,'code-version.txt'));
  const config={work,session_id:'heldout-session',library_path:libraryPath,tool_digest:frozen.manifest_digest,
    candidate_sha256:frozen.candidate_sha256,catalog_path:catalogPath,catalog_sha256:sha256(readFileSync(catalogPath)),
    source_version:'c'.repeat(64),case_id:'synthetic_heldout',prompt_sha256:sha256('诊断修订任务'),
    source_files:{[catalogPath]:sha256(readFileSync(catalogPath))},code_files:Object.fromEntries(codePaths.map(path=>[path,sha256(readFileSync(path))]))};
  const service=createTraceRsiTaskTools(config),tools=service.definitions.map(tool=>({name:P+tool.name,parameters:tool.inputSchema}));
  const witnesses=[1,2].map(index=>({session_id:'synthetic-training-'+index,run_id:'training-'+index,
    anchor_call_id:'anchor-'+index,next_call_id:'check-'+index,events_sha256:String(index).repeat(64)}));
  const motif=anchor=>({motif_id:'trace-edge-'+anchor,anchor:P+anchor,next:P+candidate.name,parameter_binding:{input_id:'/input_id'},
    witnesses:clone(witnesses),training_session_count:2,status:'shadow_candidate'});
  const library=rehash({schema_version:1,kind:'trace_rsi_continuation_shadow',execution_policy:'shadow_only',tool_digest:config.tool_digest,
    candidate_sha256:config.candidate_sha256,tools:clone(tools),code_files_sha256:clone(config.code_files),
    motifs:[motif('read_task_state'),motif('write_report')]});
  const read=service.call('read_task_state',{}),recent=[{name:P+'read_task_state',ok:true,output:read}];
  return {work,config,frozen,library,tools,service,read,recent};
}
const observed=output=>({value:{content:[{type:'text',text:JSON.stringify(output)}]}});

test('trace-derived read and write edges bind current receipt and pure output without side effects',t=>{
  const f=fixture(t),before=readFileSync(join(f.work,'triage.json'));
  assert.equal(validateTraceShadowLibrary(f.library,f.config),f.library);
  const read=predictTraceCheck(f.library,f.recent,f.tools,f.config);
  assert.equal(read.execution_authorized,false);assert.deepEqual(read.expected_tools,[{tool:P+f.frozen.candidate.name,arguments:{input_id:f.read.input_id}}]);
  assert.deepEqual(read.expected_result,{input_id:f.read.input_id,input_sha256:f.read.input_sha256,report_sha256:f.read.report_sha256,
    source_version:f.read.source_version,candidate_sha256:f.read.candidate_sha256,catalog_sha256:f.read.catalog_sha256,output:{missing:['b'],count:1}});
  assert.deepEqual(readFileSync(join(f.work,'triage.json')),before);
  const written=f.service.call('write_report',{report_sha256:f.read.report_sha256,report:{keys:['a','b']}});
  const write=predictTraceCheck(f.library,[{name:P+'write_report',ok:true,output:written}],f.tools,f.config);
  assert.equal(write.expected_tools[0].arguments.input_id,written.input_id);assert.deepEqual(write.expected_result.output,{missing:[],count:2});
  const onlyWrite=rehash({...f.library,motifs:[f.library.motifs[1]]});
  assert.equal(predictTraceCheck(onlyWrite,[{name:P+'read_task_state',ok:true,output:f.service.call('read_task_state',{})}],f.tools,f.config),null);
});

test('requests require exact ordered tool schema, single successful anchor and current receipt',t=>{
  const f=fixture(t);
  assert.equal(predictTraceCheck(f.library,f.recent,[...f.tools].reverse(),f.config),null);
  const schema=clone(f.tools);schema[2].parameters.properties.input_id={type:'number'};
  assert.equal(predictTraceCheck(f.library,f.recent,schema,f.config),null);
  assert.equal(predictTraceCheck(f.library,f.recent,[...f.tools,{name:'bash',parameters:{type:'object'}}],f.config),null);
  for(const recent of [[],[{...f.recent[0],ok:false}],[...f.recent,...f.recent],
    [...f.recent,{name:'unknown',ok:true,output:{}}],[{name:P+f.frozen.candidate.name,ok:true,output:f.read}]])
    assert.equal(predictTraceCheck(f.library,recent,f.tools,f.config),null);
  for(const key of ['input_id','input_sha256','report_sha256','source_version','candidate_sha256','catalog_sha256']){
    const changed=clone(f.recent);changed[0].output[key]='wrong';
    assert.equal(predictTraceCheck(f.library,changed,f.tools,f.config),null);
  }
  const changed=clone(f.recent);changed[0].output.input.reported=['not-current'];
  assert.equal(predictTraceCheck(f.library,changed,f.tools,f.config),null);
});

test('library records the actual Harness provider order rather than assuming MCP declaration order',t=>{
  const f=fixture(t),ordered=[...f.tools].sort((a,b)=>a.name.localeCompare(b.name));
  const library=rehash({...f.library,tools:ordered});
  assert.doesNotThrow(()=>validateTraceShadowLibrary(library,f.config));
  assert.ok(predictTraceCheck(library,f.recent,ordered,f.config));
  assert.equal(predictTraceCheck(library,f.recent,[...ordered].reverse(),f.config),null);
});

test('frozen continuation libraries reject tamper, side effect targets and insufficient independent witnesses',t=>{
  const f=fixture(t);
  assert.throws(()=>validateTraceShadowLibrary({...f.library,manifest_digest:'f'.repeat(64)},f.config));
  for(const mutate of [x=>{x.execution_policy='execute';},x=>{x.tools[1]=clone(x.tools[0]);},
    x=>{x.motifs[0].next=P+'write_report';},x=>{x.motifs[0].anchor='bash';},
    x=>{x.motifs[0].parameter_binding={input_id:'/report'};},x=>{x.motifs[0].witnesses.pop();},
    x=>{x.motifs[0].witnesses[1].session_id=x.motifs[0].witnesses[0].session_id;},
    x=>{x.motifs[0].training_session_count=3;},x=>{x.motifs[0].witnesses[1].events_sha256='bad';},
    x=>{x.motifs[0].status='execution_certified';},x=>{x.code_files_sha256={};},x=>{x.tool_digest='e'.repeat(64);}]){
    const changed=clone(f.library);mutate(changed);assert.throws(()=>validateTraceShadowLibrary(rehash(changed),f.config));
  }
  const competing=clone(f.library);competing.motifs.push({...clone(competing.motifs[0]),motif_id:'another-branch'});
  assert.equal(predictTraceCheck(rehash(competing),f.recent,f.tools,f.config),null);
  const single=clone(f.library);single.motifs[0].witnesses.pop();single.motifs[0].training_session_count=1;
  single.motifs[0].support='single_session_candidate';
  assert.doesNotThrow(()=>validateTraceShadowLibrary(rehash(single),f.config));
  assert.equal(predictTraceCheck(rehash(single),f.recent,f.tools,f.config),null);
});

test('compiler request and text metadata remain bound to declared source receipts',t=>{
  const f=fixture(t),value=clone(f.library),sources={};
  value.scope='different_normal_cases_same_paper';value.limitations=['合成诊断，原文本事实保留'];value.rejected={failed_edge:1};
  for(const motif of value.motifs){
    motif.support='repeated_sessions';
    for(const [index,witness]of motif.witnesses.entries()){
      const {report,input,input_id,...base}=f.read;
      witness.case_id='synthetic_case_'+index;witness.anchor_line=2;witness.anchor_result_line=3;
      witness.next_line=5;witness.next_result_line=6;witness.anchor_request=1;witness.next_request=2;
      witness.anchor_text_blocks=1;witness.next_text_blocks=1;
      witness.receipt={input_id:'trace-input-'+digest({...base,session_id:witness.session_id}),...base};
      witness.output_sha256=digest({missing:['b'],count:1});
      sources[witness.run_id]={run_id:witness.run_id,session_id:witness.session_id,case_id:witness.case_id,
        source_version:base.source_version,source_files_sha256:clone(f.config.source_files),prompt_sha256:f.config.prompt_sha256,
        events_sha256:witness.events_sha256,config_sha256:'d'.repeat(64),manifest_sha256:'e'.repeat(64),
        verification_sha256:'f'.repeat(64),requests:{'1.json':'a'.repeat(64),'2.json':'b'.repeat(64)}};
    }
  }
  value.sources=sources;const library=rehash(value);
  assert.doesNotThrow(()=>validateTraceShadowLibrary(library,f.config));
  assert.ok(predictTraceCheck(library,f.recent,f.tools,f.config));
  assert.equal(library.motifs[0].witnesses[0].next_text_blocks,1);
  for(const mutate of [x=>{x.motifs[0].witnesses[0].next_request=3;},x=>{x.motifs[0].witnesses[0].anchor_result_line=5;},
    x=>{x.motifs[0].witnesses[0].next_text_blocks=-1;},x=>{x.sources['training-1'].events_sha256='0'.repeat(64);},
    x=>{x.motifs[0].witnesses[0].receipt.input_id='trace-input-'+'0'.repeat(64);}]){
    const changed=clone(library);mutate(changed);assert.throws(()=>validateTraceShadowLibrary(rehash(changed),f.config));
  }
});

test('report, source, code and tool-file drift defer prediction',t=>{
  const f=fixture(t);
  const receipt=f.service.call('write_report',{report_sha256:f.read.report_sha256,report:{keys:['b']}});
  assert.equal(predictTraceCheck(f.library,f.recent,f.tools,f.config),null);
  const recent=[{name:P+'write_report',ok:true,output:receipt}];
  assert.ok(predictTraceCheck(f.library,recent,f.tools,f.config));
  writeFileSync(f.config.catalog_path,JSON.stringify({keys:['new']}));
  assert.equal(predictTraceCheck(f.library,recent,f.tools,f.config),null);
  writeFileSync(f.config.catalog_path,JSON.stringify({keys:['a','b']}));
  writeFileSync(join(f.work,'code-version.txt'),'changed-code');
  assert.equal(predictTraceCheck(f.library,recent,f.tools,f.config),null);
  writeFileSync(join(f.work,'code-version.txt'),'fixed-code');
  const changed=clone(f.frozen);changed.candidate.description='changed';
  writeFileSync(f.config.library_path,JSON.stringify(changed));
  assert.equal(predictTraceCheck(f.library,recent,f.tools,f.config),null);
});

test('symlink and shared hardlink reports do not create a prediction',t=>{
  const f=fixture(t),path=join(f.work,'triage.json'),saved=readFileSync(path),other=join(f.work,'other-report.json');
  writeFileSync(other,saved);rmSync(path);
  symlinkSync(other,path);assert.equal(predictTraceCheck(f.library,f.recent,f.tools,f.config),null);
  rmSync(path);linkSync(other,path);assert.equal(predictTraceCheck(f.library,f.recent,f.tools,f.config),null);
});

test('interceptor forwards each provider unchanged and consumes each anchor window once',async t=>{
  const f=fixture(t),audit=[],runtime=createTraceShadowInterceptor({library:f.library,config:f.config,audit:row=>audit.push(row)});
  const options={tools:f.tools,messages:[{role:'user',content:[{type:'text',text:'保留原文'}]}]},snapshot=clone(options),sentinel={stream:'provider'},before=readFileSync(join(f.work,'triage.json'));
  let providers=0;const next=()=>{providers++;return sentinel;};
  runtime.observe('other-session',{name:P+'read_task_state'},observed(f.read));
  assert.equal(await runtime.intercept(f.config.session_id,options,next),sentinel);
  runtime.observe(f.config.session_id,{name:P+'read_task_state',callId:'a'},observed(f.read));
  assert.equal(await runtime.intercept(f.config.session_id,options,next),sentinel);
  assert.equal(audit.at(-1).kind,'prediction');assert.equal(audit.at(-1).request_ordinal,2);
  assert.equal(await runtime.intercept(f.config.session_id,options,next),sentinel);
  assert.equal(audit.at(-1).kind,'deferred');assert.equal(audit.at(-1).request_ordinal,3);
  assert.equal(providers,3);assert.deepEqual(options,snapshot);assert.deepEqual(readFileSync(join(f.work,'triage.json')),before);
  assert.equal(audit.filter(row=>row.kind==='prediction').length,1);
});

test('real observed check result is verified; an already executed check cannot rearm prediction',async t=>{
  const f=fixture(t),audit=[],runtime=createTraceShadowInterceptor({library:f.library,config:f.config,audit:row=>audit.push(row)});
  const options={tools:f.tools};
  runtime.observe(f.config.session_id,{name:P+'read_task_state'},observed(f.read));
  await runtime.intercept(f.config.session_id,options,()=>[]);
  const output=f.service.call(f.frozen.candidate.name,{input_id:f.read.input_id});
  runtime.observe(f.config.session_id,{name:P+f.frozen.candidate.name,arguments:{input_id:f.read.input_id},callId:'check'},observed(output));
  assert.equal(audit.at(-1).kind,'shadow_result');assert.equal(audit.at(-1).verified,true);
  await runtime.intercept(f.config.session_id,options,()=>[]);assert.equal(audit.at(-1).kind,'deferred');
  runtime.observe(f.config.session_id,{name:P+'read_task_state'},observed(f.read));
  await runtime.intercept(f.config.session_id,options,()=>[]);
  runtime.observe(f.config.session_id,{name:P+f.frozen.candidate.name,arguments:{input_id:f.read.input_id}},observed({...output,output:{missing:[],count:999}}));
  assert.equal(audit.at(-1).verified,false);
});

test('failed, aborted and multiple anchors, consumed prompt gates and absent libraries defer',async t=>{
  const f=fixture(t),options={tools:f.tools};
  for(const kind of ['failed','aborted','multiple','gate']){
    const audit=[],runtime=createTraceShadowInterceptor({library:f.library,config:f.config,audit:row=>audit.push(row)});
    const exec={name:P+'read_task_state',...(kind==='aborted'?{signal:{aborted:true}}:{})};
    runtime.observe(f.config.session_id,exec,kind==='failed'?{isError:true,...observed(f.read)}:observed(f.read));
    if(kind==='multiple')runtime.observe(f.config.session_id,exec,observed(f.read));
    if(kind==='gate')runtime.deferRequest('prompt_or_scaffold_mismatch');
    await runtime.intercept(f.config.session_id,options,()=>[]);assert.equal(audit.at(-1).kind,'deferred');
  }
  const audit=[],runtime=createTraceShadowInterceptor({config:f.config,audit:row=>audit.push(row)});
  runtime.observe(f.config.session_id,{name:P+'read_task_state'},observed(f.read));
  await runtime.intercept(f.config.session_id,options,()=>[]);assert.equal(audit.at(-1).kind,'deferred');
});

test('library and configuration mutation after installation defer with no extra writes',async t=>{
  const f=fixture(t),path=join(f.work,'shadow-library.json'),audit=[];writeFileSync(path,JSON.stringify(f.library));
  f.config.shadow_library=path;
  const runtime=createTraceShadowInterceptor({library:f.library,config:f.config,audit:row=>audit.push(row)});
  runtime.observe(f.config.session_id,{name:P+'read_task_state'},observed(f.read));writeFileSync(path,'{}');
  await runtime.intercept(f.config.session_id,{tools:f.tools},()=>[]);assert.equal(audit.at(-1).kind,'deferred');
  writeFileSync(path,JSON.stringify(f.library));
  runtime.observe(f.config.session_id,{name:P+'read_task_state'},observed(f.read));f.config.case_id='changed_case';
  await runtime.intercept(f.config.session_id,{tools:f.tools},()=>[]);assert.equal(audit.at(-1).kind,'deferred');
});

test('plugin grants only configured session tools and keeps the actual model stream intact',async t=>{
  const f=fixture(t),shadowPath=join(f.work,'shadow-library.json'),configPath=join(f.work,'task-config.json');
  writeFileSync(shadowPath,JSON.stringify(f.library));f.config.shadow_library=shadowPath;writeFileSync(configPath,JSON.stringify(f.config));
  const prior=process.env.SSS_TRACE_RSI_TASK_CONFIG;process.env.SSS_TRACE_RSI_TASK_CONFIG=configPath;
  t.after(()=>{if(prior===undefined)delete process.env.SSS_TRACE_RSI_TASK_CONFIG;else process.env.SSS_TRACE_RSI_TASK_CONFIG=prior;});
  const listeners=new Map(),restrictions=new Map();let resultListener;
  apply({on(event,callback){const entries=listeners.get(event)??[];entries.push(callback);listeners.set(event,entries);}});
  const emit=(event,value)=>{for(const callback of listeners.get(event)??[])callback(value);};
  function agent(id){return {session:{id},ctx:{tools:{restrict(value){restrictions.set(id,value);}},
    on(event,callback){if(id===f.config.session_id&&event==='tools/result')resultListener=callback;}}};}
  emit('agent/created',{agent:agent(f.config.session_id)});emit('agent/created',{agent:agent('foreign')});
  const names=f.tools.map(tool=>tool.name);
  assert.deepEqual(restrictions.get(f.config.session_id),{allow:names});assert.deepEqual(restrictions.get('foreign'),{deny:names});
  resultListener({name:P+'read_task_state'},observed(f.read));
  const request=markAgentLoopRequest({sessionId:f.config.session_id,tools:f.tools,
    messages:[{id:'user-1',role:'user',source:{kind:'user'},content:[{type:'text',text:'诊断修订任务'}]}]});
  const saved=clone(request),chunks=[{type:'text-delta',delta:'原生模型内容'}];let providers=0;
  const received=[];
  for await(const chunk of listeners.get('llm/stream')[0](request,()=>{providers++;return(async function*(){yield*chunks;})();}))received.push(chunk);
  assert.equal(providers,1);assert.deepEqual(received,chunks);assert.deepEqual(clone(request),saved);
  const rows=readFileSync(join(f.work,'shadow.jsonl'),'utf8').trim().split('\n').map(JSON.parse);
  assert.equal(rows.filter(row=>row.kind==='prediction').length,1);
  assert.equal(rows.find(row=>row.kind==='prediction').request_ordinal,1);
  assert.equal(rows.some(row=>row.kind==='model_request_skipped_verified'),false);
});
