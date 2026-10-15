import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,readFileSync,writeFileSync,rmSync,realpathSync,symlinkSync,linkSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {markAgentLoopRequest} from '@deepseek-ai/dsh-llm';
import {digest} from '../src/adapters/paper_rsi_program.ts';
import {sha256} from '../src/adapters/paper_triage_validation.ts';
import {createTraceRsiTaskTools} from '../scenarios/paper-submission/trace-rsi-task-server.ts';
import {apply,createBatchShadowInterceptor,validateBatchShadowLibrary} from '../src/adapters/dsh_trace_rsi_batch_shadow.ts';
import {createBatchExecuteInterceptor} from '../src/adapters/dsh_trace_rsi_batch_execute.ts';
import {renderRevisionMarkdown} from '../src/adapters/report_patch_protocol.ts';

const P='mcp__paper_trace_rsi__',clone=x=>JSON.parse(JSON.stringify(x));
const receiptFields=['input_id','input_sha256','report_sha256','source_version','candidate_sha256','catalog_sha256'];
const object=properties=>({type:'object',properties,required:Object.keys(properties),additionalProperties:false});
const array={type:'array',items:{type:'string',maxLength:100},maxItems:2000};
const rehash=value=>{const {manifest_digest,...body}=value;return {...body,manifest_digest:digest(body)};};
const observed=value=>({value:{content:[{type:'text',text:JSON.stringify(value)}]}});
const receipt=value=>Object.fromEntries(receiptFields.map(k=>[k,value[k]]));
function graph(motif){motif.motif_id='trace-rsi-batch-'+digest({anchor:motif.anchor,batch:motif.batch}).slice(0,16);}
test('export projection protocol is bound to the frozen library, not silently switched',t=>{
 const f=fixture(t);
 f.library=rehash({...f.library,export_result_protocol:'revision_receipt_v2'});
 assert.throws(()=>validateBatchShadowLibrary(f.library,f.config),/batch_export_protocol_mismatch/);
 f.config.export_result_protocol='revision_receipt_v2';
 assert.doesNotThrow(()=>validateBatchShadowLibrary(f.library,f.config));
 f.config.export_result_protocol='unknown';
 f.library=rehash({...f.library,export_result_protocol:'unknown'});
 assert.throws(()=>validateBatchShadowLibrary(f.library,f.config),/batch_export_protocol_mismatch/);
});
function fixture(t,order=['check','read'],artifact=false){
  const work=realpathSync(mkdtempSync(join(tmpdir(),'sss-batch-shadow-')));t.after(()=>rmSync(work,{recursive:true,force:true}));
  // Handwritten synthetic protocol fixtures are diagnostic, not model-generated
  // programs, real trajectory evidence, quality certification or savings data.
  const candidate={schema_version:1,name:'compare_record_keys',description:'手写合成批次诊断',
    input_schema:object({expected:array,reported:array}),output_schema:object({missing:array}),
    program:['object',{missing:['difference',['get',['var','input'],['lit','expected']],['get',['var','input'],['lit','reported']]]}]};
  const provenance={trace_bundle_sha256:'a'.repeat(64),source_witnesses:[{run_id:'synthetic',session_id:'fixture',call_id:'c',events_sha256:'b'.repeat(64)}],
    proposal:{input_bindings:{expected:{file:'catalog.json',pointer:'/keys'},reported:{file:'triage.json',pointer:'/keys'}}}};
  if(artifact){
    candidate.input_schema.properties.before_report=object({keys:array});candidate.input_schema.required.push('before_report');
    provenance.proposal.input_bindings.before_report={file:'catalog.json',pointer:'/initial_report'};
  }
  const certification={status:'passed',kind:'source_replay',heldout_cases:2};
  const frozen=rehash({schema_version:1,kind:'model_generated_trace_tool',candidate,candidate_sha256:digest(candidate),
    provenance,provenance_sha256:digest(provenance),certification,certification_sha256:digest(certification)});
  const libraryPath=join(work,'tool.json'),catalogPath=join(work,'catalog.json');
  writeFileSync(libraryPath,JSON.stringify(frozen));writeFileSync(catalogPath,JSON.stringify({keys:['a','b'],...(artifact?{initial_report:{keys:['a']}}:{})}));
  writeFileSync(join(work,'triage.json'),JSON.stringify({keys:['a']}));writeFileSync(join(work,'code.txt'),'baseline-code');
  const basePaths=['scenarios/paper-submission/trace-rsi-task-server.ts','src/adapters/trace_rsi_program.ts',
    'src/adapters/paper_rsi_program.ts','src/adapters/dsh_trace_rsi_shadow.ts'].map(p=>resolve(p));basePaths.push(join(work,'code.txt'));
  const additions=['src/adapters/trace_rsi_batch_compiler.py','src/adapters/dsh_trace_rsi_batch_shadow.ts','scripts/paper-rsi-batch-shadow.py'];
  const code_files_sha256=Object.fromEntries(basePaths.map(p=>[p,sha256(readFileSync(p))]));
  const code_additions_sha256=Object.fromEntries(additions.map(p=>[resolve(p),sha256(readFileSync(resolve(p)))]));
  const config={work,session_id:'synthetic-heldout',library_path:libraryPath,tool_digest:frozen.manifest_digest,candidate_sha256:frozen.candidate_sha256,
    catalog_path:catalogPath,catalog_sha256:sha256(readFileSync(catalogPath)),source_version:'c'.repeat(64),case_id:'diagnostic-heldout',
    prompt_sha256:sha256('批次诊断任务'),source_files:{[catalogPath]:sha256(readFileSync(catalogPath))},code_files:{...code_files_sha256,...code_additions_sha256}};
  if(artifact){
    code_files_sha256[libraryPath]=sha256(readFileSync(libraryPath));config.code_files[libraryPath]=code_files_sha256[libraryPath];
    Object.assign(config,{patch_library_path:libraryPath,patch_library_sha256:code_files_sha256[libraryPath],write_protocol:'full_report',
      private_export_policy:'current_task_revision_report_only'});
  }
  const original=createTraceRsiTaskTools(config),service={definitions:[...original.definitions],call:(name,args)=>{
    if(name!=='export_revision_report')return original.call(name,args);
    const state=original.call('read_task_state',{}),checked=original.call(candidate.name,{input_id:state.input_id});
    assert.deepEqual(args,{input_id:state.input_id});
    const markdown=renderRevisionMarkdown(state.input.before_report,state.report,checked.output);
    writeFileSync(join(work,'revision-report.md'),markdown);
    return {...receipt(state),artifact_name:'revision-report.md',artifact_sha256:sha256(markdown),
      scope:'structural_revision_not_full_bibliography_verification',output:checked.output};
  }};
  if(artifact)service.definitions.push({name:'export_revision_report',inputSchema:object({input_id:{type:'string'}})});
  const tools=service.definitions.map(d=>({name:P+d.name,parameters:d.inputSchema}));
  const read=service.call('read_task_state',{}),checkName=P+candidate.name,sources={};
  const descriptors={check:{tool:checkName,arguments_binding:{input_id:'/input_id'},result_kind:'candidate_output'},
    read:{tool:P+'read_task_state',arguments:{},result_kind:'task_state'},
    artifact:{tool:P+'export_revision_report',arguments_binding:{input_id:'/input_id'},result_kind:'private_artifact_output',effect:'private_current_report_export'}};
  const motif={anchor:P+'read_task_state',batch:order.map(k=>clone(descriptors[k])),witnesses:[],training_session_count:2,
    support:'repeated_sessions',status:'shadow_candidate'};graph(motif);
  for(let i=1;i<=2;i++){
    const session_id='synthetic-training-'+i,run_id='run-'+i,base=receipt(read);delete base.input_id;
    const r={input_id:'trace-input-'+digest({...base,session_id}),...base},events_sha256=String(i).repeat(64);
    const content=order.map((k,j)=>({type:'tool-call',id:`call-${i}-${j}`,name:descriptors[k].tool,
      arguments:JSON.stringify(k==='read'?{}:{input_id:r.input_id})}));
    const witness={session_id,run_id,case_id:'fixture-'+i,anchor_call_id:'anchor-'+i,events_sha256,
      anchor_line:2,anchor_result_line:3,anchor_request:1,next_request:2,anchor_text_blocks:1,next_text_blocks:0,
      anchor_message_sha256:digest([{type:'text',text:'诊断旁白'}]),next_message_sha256:digest(content),next_message_line:5,receipt:r,
      batch:order.map((k,j)=>{
        const output=k==='check'?{...r,output:{missing:['b']}}:k==='artifact'?{...r,artifact_name:'revision-report.md',
          artifact_sha256:sha256(renderRevisionMarkdown(read.input.before_report,read.report,{missing:['b']})),
          scope:'structural_revision_not_full_bibliography_verification',output:{missing:['b']}}:{report:read.report,input:read.input,...r};
        return {call_id:content[j].id,tool:descriptors[k].tool,call_line:6+j,result_line:8+j,
          arguments_sha256:digest(k==='read'?{}:{input_id:r.input_id}),result_sha256:digest(output),receipt:r,
          ...(k==='check'?{output_sha256:digest(output.output)}:{})};
      })};
    motif.witnesses.push(witness);
    sources[run_id]={run_id,session_id,case_id:witness.case_id,source_version:config.source_version,source_files_sha256:clone(config.source_files),
      prompt_sha256:config.prompt_sha256,events_sha256,config_sha256:'d'.repeat(64),manifest_sha256:'e'.repeat(64),verification_sha256:'f'.repeat(64),
      requests:{'1.json':'a'.repeat(64),'2.json':'b'.repeat(64)}};
  }
  const library=rehash({schema_version:1,kind:'trace_rsi_batch_continuation_shadow',execution_policy:'shadow_only',tool_digest:config.tool_digest,
    candidate_sha256:config.candidate_sha256,tools,code_files_sha256,code_additions_sha256,motifs:[motif],sources,
    scope:'synthetic_diagnostic',limitations:['合成协议测试，不作真实行为或节省证据。'],rejected:{}});
  return {work,config,frozen,service,tools,read,library,checkName};
}
function setup(f){
  const rows=[],runtime=createBatchShadowInterceptor({library:f.library,config:f.config,audit:r=>rows.push(r)});
  const anchor={name:P+'read_task_state',arguments:{},callId:'live-anchor'};
  runtime.observe(f.config.session_id,anchor,observed(f.read));
  return {runtime,rows,options:{tools:f.tools,messages:[{role:'user',content:[{type:'text',text:'完整保留'}]}]}};
}

function executeSetup(f,artifactAllowed=false){
  const authPath=join(f.work,'execute-authorization.json');
  writeFileSync(authPath,JSON.stringify({execute_allowed:true,reset_history:false,execution_environment:'local',private_artifact_export_allowed:artifactAllowed}));
  f.config={...f.config,mode:'execute',execute_authorization_path:authPath,
    execute_authorization_sha256:sha256(readFileSync(authPath)),execute_library_digest:f.library.manifest_digest};
  const rows=[],runtime=createBatchExecuteInterceptor({library:f.library,config:f.config,audit:r=>rows.push(r)});
  runtime.observe(f.config.session_id,{name:P+'read_task_state',arguments:{},callId:'anchor'},observed(f.read));
  return {runtime,rows,authPath};
}
async function executeCalls(f,runtime,next){
  const chunks=[];for await(const chunk of await runtime.intercept(f.config.session_id,{tools:f.tools},next))chunks.push(chunk);
  return chunks.filter(c=>c.type==='block-end'&&c.block?.type==='tool-call').map(c=>c.block);
}
test('explicit execute dispatches actual readonly calls and verifies one whole skipped request',async t=>{
  const f=fixture(t),{runtime,rows}=executeSetup(f);let provider=0;
  const calls=await executeCalls(f,runtime,async()=>{provider++;return chunksFor([]);});
  assert.equal(provider,0);assert.deepEqual(calls.map(c=>c.name),f.library.motifs[0].batch.map(n=>n.tool));
  for(const c of calls){
    const exec={name:c.name,arguments:JSON.parse(c.arguments),callId:c.id};runtime.observeDispatch(f.config.session_id,exec);
    runtime.observe(f.config.session_id,exec,observed(f.service.call(c.name.slice(P.length),exec.arguments)));
  }
  assert.equal(rows.filter(r=>r.kind==='model_request_skipped_verified').length,1);
  assert.equal(rows.filter(r=>r.kind==='model_request_skip_unverified').length,0);
});
test('execute refuses text-bearing training, changed authorization and changed source before skipping',async t=>{
  for(const kind of ['text','authorization','source']){
    const f=fixture(t);
    if(kind==='text'){f.library.motifs[0].witnesses[0].next_text_blocks=1;f.library=rehash(f.library);}
    const {runtime,rows,authPath}=executeSetup(f);
    if(kind==='authorization')writeFileSync(authPath,readFileSync(authPath).toString()+' ');
    if(kind==='source')writeFileSync(f.config.catalog_path,'{}');
    let provider=0;await executeCalls(f,runtime,async()=>{provider++;return chunksFor([]);});
    assert.equal(provider,1);assert.equal(rows.filter(r=>r.kind==='model_request_skip_attempt').length,0);
  }
});
test('mixed narration evidence is retained; two independent pure-tool witnesses are still required',async t=>{
  const f=fixture(t),lib=clone(f.library),m=lib.motifs[0];
  const w=clone(m.witnesses[0]);w.anchor_call_id='additional-anchor';w.next_text_blocks=1;
  m.witnesses.push(w);f.library=rehash(lib);
  const {runtime,rows}=executeSetup(f);let provider=0;
  await executeCalls(f,runtime,async()=>{provider++;return chunksFor([]);});
  assert.equal(provider,0);assert.equal(rows.filter(r=>r.kind==='model_request_skip_attempt').length,1);
  assert.equal(f.library.motifs[0].witnesses.length,3);
  const f2=fixture(t);f2.library.motifs[0].witnesses[0].next_text_blocks=1;f2.library=rehash(f2.library);
  const s=executeSetup(f2);provider=0;await executeCalls(f2,s.runtime,async()=>{provider++;return chunksFor([]);});assert.equal(provider,1);
});
test('unverified execute result disables all later takeover and retains the failure',async t=>{
  const f=fixture(t),{runtime,rows}=executeSetup(f);
  const calls=await executeCalls(f,runtime,async()=>chunksFor([]));
  for(const c of calls){const exec={name:c.name,arguments:JSON.parse(c.arguments),callId:c.id};
    runtime.observeDispatch(f.config.session_id,exec);runtime.observe(f.config.session_id,exec,{isError:true,value:null});}
  assert.equal(rows.filter(r=>r.kind==='model_request_skip_unverified').length,1);
  let provider=0;await executeCalls(f,runtime,async()=>{provider++;return chunksFor([]);});assert.equal(provider,1);
});
test('private artifact effect needs separate permission and verifies actual file bytes',async t=>{
  for(const allowed of [false,true]){
    const f=fixture(t,['artifact'],true),{runtime,rows}=executeSetup(f,allowed),before=readFileSync(join(f.work,'triage.json'));
    let provider=0;const calls=await executeCalls(f,runtime,async()=>{provider++;return chunksFor([]);});
    assert.equal(provider,allowed?0:1);
    for(const c of calls){const exec={name:c.name,arguments:JSON.parse(c.arguments),callId:c.id};
      runtime.observeDispatch(f.config.session_id,exec);runtime.observe(f.config.session_id,exec,observed(f.service.call(c.name.slice(P.length),exec.arguments)));}
    assert.equal(rows.filter(r=>r.kind==='model_request_skipped_verified').length,allowed?1:0);
    assert.deepEqual(readFileSync(join(f.work,'triage.json')),before);
  }
});
test('missing, corrupt, symlink and hardlink artifacts cannot verify a skipped request',async t=>{
  for(const fault of ['missing','corrupt','symlink','hardlink']){
    const f=fixture(t,['artifact'],true),{runtime,rows}=executeSetup(f,true),calls=await executeCalls(f,runtime,async()=>chunksFor([]));
    const c=calls[0],exec={name:c.name,arguments:JSON.parse(c.arguments),callId:c.id};
    runtime.observeDispatch(f.config.session_id,exec);
    const output=f.service.call(c.name.slice(P.length),exec.arguments),path=join(f.work,output.artifact_name),other=join(f.work,'other.md');
    writeFileSync(other,readFileSync(path));rmSync(path);
    if(fault==='corrupt')writeFileSync(path,'changed');
    if(fault==='symlink')symlinkSync(other,path);
    if(fault==='hardlink')linkSync(other,path);
    runtime.observe(f.config.session_id,exec,observed(output));
    assert.equal(rows.filter(r=>r.kind==='model_request_skip_unverified').length,1,fault);
    assert.equal(rows.filter(r=>r.kind==='model_request_skipped_verified').length,0,fault);
    let provider=0;await executeCalls(f,runtime,async()=>{provider++;return chunksFor([]);});assert.equal(provider,1);
  }
});
test('artifact descriptor rejects arbitrary paths, effects and missing task policy',t=>{
  const f=fixture(t,['artifact'],true);
  for(const change of [n=>{n.effect='write_report';},n=>{n.tool=P+'write_report';},n=>{n.arguments_binding={input_id:'/input_id',path:'/tmp/report'};}]){
    const lib=clone(f.library);change(lib.motifs[0].batch[0]);graph(lib.motifs[0]);assert.throws(()=>validateBatchShadowLibrary(rehash(lib),f.config));
  }
  assert.throws(()=>validateBatchShadowLibrary(f.library,{...f.config,private_export_policy:'arbitrary_export'}));
});
function callsFor(f){return f.library.motifs[0].batch.map((n,i)=>({call_id:'live-'+i,name:n.tool,
  arguments:n.result_kind==='task_state'?{}:{input_id:f.read.input_id}}));}
function chunksFor(calls,{text=true,finish='tool-calls'}={}){
  const blocks=[...(text?[{type:'text',text:'保留完整科研旁白'}]:[]),...calls.map(c=>({type:'tool-call',id:c.call_id,name:c.name,arguments:JSON.stringify(c.arguments)}))];
  return [...blocks.map((block,index)=>({type:'block-end',index,block})),{type:'finish',reason:{kind:finish}}];
}
const stream=chunks=>(async function*(){yield* chunks;})();
async function predict(f,s,calls=callsFor(f),chunks=chunksFor(calls)){
  const received=[],result=await s.runtime.intercept(f.config.session_id,s.options,()=>stream(chunks));
  for await(const chunk of result)received.push(chunk);
  assert.deepEqual(received,chunks);return calls;
}
function dispatch(f,s,calls){for(const c of calls)s.runtime.observeDispatch(f.config.session_id,{callId:c.call_id,name:c.name,arguments:c.arguments});}
function value(f,c){return f.service.call(c.name.slice(P.length),c.arguments);}
function result(f,s,c,valueOverride){s.runtime.observe(f.config.session_id,{callId:c.call_id,name:c.name,arguments:c.arguments},observed(valueOverride??value(f,c)));}

test('complete witnessed batch predicts dynamic receipt and all outputs without side effects',async t=>{
  const f=fixture(t),s=setup(f),before=readFileSync(join(f.work,'triage.json')),options=clone(s.options);
  assert.equal(validateBatchShadowLibrary(f.library,f.config),f.library);
  const calls=await predict(f,s),p=s.rows.find(r=>r.kind==='prediction').prediction;
  assert.deepEqual(p.expected_tools,calls.map(c=>({tool:c.name,arguments:c.arguments})));
  assert.deepEqual(p.expected_results,[{...receipt(f.read),output:{missing:['b']}},f.read]);
  assert.equal(p.execution_authorized,false);assert.deepEqual(s.options,options);assert.deepEqual(readFileSync(join(f.work,'triage.json')),before);
  dispatch(f,s,calls);result(f,s,calls[1]);assert.equal(s.rows.some(r=>r.kind==='shadow_batch_result'),false);
  result(f,s,calls[0]);const row=s.rows.at(-1);
  assert.equal(row.kind,'shadow_batch_result');assert.equal(row.verified,true);assert.equal(row.request_ordinal,1);
  assert.ok(row.item_matches.every(m=>m.verified));assert.equal(row.actual_text_blocks,1);
  assert.equal(row.state_guard_kind,'engineering_successful_check_dedup');assert.deepEqual(readFileSync(join(f.work,'triage.json')),before);
});

test('only a complete batch passes; one successful check cannot verify the model request',async t=>{
  const f=fixture(t),s=setup(f),calls=await predict(f,s);dispatch(f,s,calls);result(f,s,calls[0]);
  assert.equal(s.rows.some(r=>r.kind==='shadow_batch_result'),false);
  await s.runtime.intercept(f.config.session_id,s.options,()=>[]);
  const row=s.rows.find(r=>r.kind==='shadow_batch_result');assert.equal(row.verified,false);
  assert.deepEqual(row.item_matches.map(m=>m.verified),[true,false]);
});

test('batch order comes from evidence and preserves differing completion order',async t=>{
  const f=fixture(t,['read','check']),s=setup(f),calls=await predict(f,s);
  assert.deepEqual(calls.map(c=>c.name),[P+'read_task_state',f.checkName]);
  dispatch(f,s,calls);for(const c of [...calls].reverse())result(f,s,c);
  assert.equal(s.rows.at(-1).verified,true);
  const f2=fixture(t),s2=setup(f2),calls2=[...callsFor(f2)].reverse();await predict(f2,s2,calls2);dispatch(f2,s2,calls2);
  for(const c of calls2)result(f2,s2,c);
  assert.equal(s2.rows.at(-1).verified,false);assert.equal(s2.rows.at(-1).declaration_match,false);
});

test('successful checked input stays deduplicated across later reads; changed reports rearm it',async t=>{
  const f=fixture(t),s=setup(f),calls=await predict(f,s);dispatch(f,s,calls);for(const c of calls)result(f,s,c);
  await s.runtime.intercept(f.config.session_id,s.options,()=>[]);
  s.runtime.observe(f.config.session_id,{name:P+'read_task_state',arguments:{},callId:'later-read'},observed(f.service.call('read_task_state',{})));
  await s.runtime.intercept(f.config.session_id,s.options,()=>[]);
  assert.equal(s.rows.at(-1).reason,'prior_same_input_check_engineering_guard');
  const write=f.service.call('write_report',{report_sha256:f.read.report_sha256,report:{keys:['a','b']}});
  const fresh=f.service.call('read_task_state',{});
  s.runtime.observe(f.config.session_id,{name:P+'read_task_state',arguments:{},callId:'changed-read'},observed(fresh));
  const changedCalls=callsFor(f).map(c=>({...c,arguments:c.name===f.checkName?{input_id:write.input_id}:{}}));
  await predict(f,s,changedCalls);
  const p=s.rows.at(-1).prediction;assert.deepEqual(p.expected_results[0].output,{missing:[]});assert.notEqual(p.expected_tools[0].arguments.input_id,f.read.input_id);
});

test('complete schemas and provider tool order, single successful anchor and independent sessions guard prediction',async t=>{
  const f=fixture(t);
  const variations=[x=>{x.options.tools=[...f.tools].reverse();},x=>{x.options.tools=clone(f.tools);x.options.tools[0].parameters.properties.extra={type:'string'};},
    x=>{x.runtime.observe(f.config.session_id,{name:P+'read_task_state',arguments:{},callId:'extra-anchor'},observed(f.read));},
    x=>{x.runtime.deferRequest('prompt_or_scaffold_mismatch');}];
  for(const alter of variations){const s=setup(f);alter(s);await s.runtime.intercept(f.config.session_id,s.options,()=>[]);assert.equal(s.rows.at(-1).kind,'deferred');}
  for(const kind of ['failed','aborted','old-report']){
    const s=setup(f);s.runtime.deferRequest('consume');const exec={name:P+'read_task_state',arguments:{},callId:'guarded',...(kind==='aborted'?{signal:{aborted:true}}:{})};
    const out=clone(f.read);if(kind==='old-report')out.report_sha256='0'.repeat(64);
    s.runtime.observe(f.config.session_id,exec,{...observed(out),...(kind==='failed'?{isError:true}:{})});
    await s.runtime.intercept(f.config.session_id,s.options,()=>[]);assert.equal(s.rows.at(-1).kind,'deferred');
  }
  const single=clone(f.library);single.motifs[0].witnesses.pop();single.motifs[0].training_session_count=1;single.motifs[0].support='single_session_candidate';
  f.library=rehash(single);assert.doesNotThrow(()=>validateBatchShadowLibrary(f.library,f.config));const s=setup(f);
  await s.runtime.intercept(f.config.session_id,s.options,()=>[]);assert.equal(s.rows.at(-1).kind,'deferred');
});

test('global provider request filenames and shared result-message lines remain compatible',t=>{
  const f=fixture(t),library=clone(f.library);
  for(const source of Object.values(library.sources))source.requests={'4638.json':'a'.repeat(64),'4641.json':'b'.repeat(64)};
  for(const w of library.motifs[0].witnesses)w.batch[0].result_line=w.batch[1].result_line;
  assert.doesNotThrow(()=>validateBatchShadowLibrary(rehash(library),f.config));
  library.motifs[0].witnesses[0].anchor_request=2;library.motifs[0].witnesses[0].next_request=3;
  assert.throws(()=>validateBatchShadowLibrary(rehash(library),f.config));
});

test('a witnessed write anchor binds the changed report without predicting any write',async t=>{
  const f=fixture(t),library=clone(f.library),motif=library.motifs[0];motif.anchor=P+'write_report';graph(motif);f.library=rehash(library);
  const s=setup(f);s.runtime.deferRequest('consume_initial_read');
  const args={report_sha256:f.read.report_sha256,report:{keys:['a','b']}},written=f.service.call('write_report',args);
  s.runtime.observe(f.config.session_id,{name:P+'write_report',arguments:args,callId:'write-anchor'},observed(written));
  const calls=callsFor(f).map(c=>({...c,arguments:c.name===f.checkName?{input_id:written.input_id}:{}}));await predict(f,s,calls);
  const p=s.rows.at(-1).prediction;assert.equal(p.expected_tools[0].arguments.input_id,written.input_id);
  assert.deepEqual(p.expected_results[0].output,{missing:[]});assert.equal(p.expected_tools.some(c=>c.tool===P+'write_report'),false);
  dispatch(f,s,calls);for(const c of [...calls].reverse())result(f,s,c);assert.equal(s.rows.at(-1).verified,true);
});

test('a successful check can anchor a witnessed read-only batch; no learned successor still defers',async t=>{
  const f=fixture(t,['read']),library=clone(f.library),motif=library.motifs[0];motif.anchor=f.checkName;graph(motif);f.library=rehash(library);
  const s=setup(f);s.runtime.deferRequest('consume_initial_read');
  const check={name:f.checkName,arguments:{input_id:f.read.input_id},callId:'successful-check'};
  s.runtime.observe(f.config.session_id,check,observed(value(f,{...check,call_id:check.callId})));
  const calls=await predict(f,s),p=s.rows.at(-1).prediction;
  assert.deepEqual(p.expected_tools,[{tool:P+'read_task_state',arguments:{}}]);assert.deepEqual(p.expected_results,[f.read]);
  dispatch(f,s,calls);for(const c of calls)result(f,s,c);assert.equal(s.rows.at(-1).verified,true);
  const f2=fixture(t),s2=setup(f2);s2.runtime.deferRequest('consume_initial_read');
  s2.runtime.observe(f2.config.session_id,{name:f2.checkName,arguments:{input_id:f2.read.input_id},callId:'check-without-learned-successor'},
    observed(f2.service.call(f2.frozen.candidate.name,{input_id:f2.read.input_id})));
  await s2.runtime.intercept(f2.config.session_id,s2.options,()=>[]);assert.equal(s2.rows.at(-1).kind,'deferred');
  s2.runtime.observe(f2.config.session_id,{name:P+'read_task_state',arguments:{},callId:'read-after-check'},observed(f2.read));
  await s2.runtime.intercept(f2.config.session_id,s2.options,()=>[]);assert.equal(s2.rows.at(-1).reason,'prior_same_input_check_engineering_guard');
});

test('unknown descriptors, unsafe properties and inconsistent evidence reject the library',t=>{
  const f=fixture(t);
  assert.throws(()=>validateBatchShadowLibrary({...f.library,manifest_digest:'0'.repeat(64)},f.config));
  const mutations=[x=>{x.execution_policy='execute';},x=>{x.motifs[0].batch[0].tool=P+'write_report';},
    x=>{x.motifs[0].batch[1].tool=P+'write_report';},x=>{x.motifs[0].batch[0].arguments_binding={input_id:'/report'};},
    x=>{x.motifs[0].batch[1].arguments={report:{}};},x=>{x.motifs[0].batch[1].result_kind='arbitrary_output';},
    x=>{x.motifs[0].witnesses[0].batch.pop();},x=>{x.motifs[0].witnesses[0].batch[0].arguments_sha256='0'.repeat(64);},
    x=>{x.motifs[0].witnesses[0].batch[1].output_sha256='0'.repeat(64);},x=>{delete x.motifs[0].witnesses[0].batch[0].output_sha256;},
    x=>{x.motifs[0].witnesses[0].batch[1].call_id=x.motifs[0].witnesses[0].batch[0].call_id;},
    x=>{x.motifs[0].witnesses[0].batch[1].call_line=5;},x=>{x.motifs[0].witnesses[0].next_message_line=2;},
    x=>{x.motifs[0].witnesses[0].next_request=3;},x=>{x.motifs[0].witnesses[0].next_text_blocks=-1;},
    x=>{x.motifs[0].witnesses[0].batch[1].receipt.input_id='wrong';},x=>{x.sources['run-1'].events_sha256='0'.repeat(64);},
    x=>{x.motifs[0].training_session_count=3;},x=>{x.motifs[0].support='independent_research_quality';},
    x=>{x.code_additions_sha256={};},x=>{x.code_files_sha256={...x.code_files_sha256,...x.code_additions_sha256};},
    x=>{x.tool_digest='0'.repeat(64);},x=>{x.motifs[0].batch.push(...Array(64).fill(x.motifs[0].batch[0]));}];
  for(const mutate of mutations){const changed=clone(f.library);mutate(changed);assert.throws(()=>validateBatchShadowLibrary(rehash(changed),f.config));}
  const danger=JSON.parse(JSON.stringify(f.library));Object.defineProperty(danger,'__proto__',{value:{},enumerable:true});
  assert.throws(()=>validateBatchShadowLibrary(danger,f.config));
  const accessor=clone(f.library);let reads=0;Object.defineProperty(accessor,'kind',{get(){reads++;return 'trace_rsi_batch_continuation_shadow';},enumerable:true});
  assert.throws(()=>validateBatchShadowLibrary(accessor,f.config));assert.equal(reads,0);
});

test('each failed, wrong, duplicate or unknown batch result prevents full verification',async t=>{
  for(const kind of ['failed','aborted','output','receipt','arguments','duplicate','unknown']){
    const f=fixture(t),s=setup(f),calls=await predict(f,s);dispatch(f,s,calls);
    const c=calls[0],exec={callId:c.call_id,name:c.name,arguments:c.arguments,...(kind==='aborted'?{signal:{aborted:true}}:{})};
    let out=value(f,c);if(kind==='output')out.output={missing:['bad']};if(kind==='receipt')out.catalog_sha256='0'.repeat(64);
    if(kind==='arguments')exec.arguments={input_id:'bad'};if(kind==='unknown')exec.callId='unknown';
    s.runtime.observe(f.config.session_id,exec,{...observed(out),...(kind==='failed'?{isError:true}:{})});
    if(kind==='duplicate')s.runtime.observe(f.config.session_id,exec,observed(out));
    result(f,s,calls[1]);await s.runtime.intercept(f.config.session_id,s.options,()=>[]);
    assert.equal(s.rows.find(r=>r.kind==='shadow_batch_result').verified,false,kind);
  }
});

test('dispatch order and declaration completeness cannot be inferred from completion order',async t=>{
  for(const kind of ['reversed-dispatch','no-dispatch','single-declaration','extra-declaration','stop','no-stream','bad-json']){
    const f=fixture(t),s=setup(f),calls=callsFor(f);let declared=calls;
    if(kind==='single-declaration')declared=calls.slice(0,1);
    if(kind==='extra-declaration')declared=[...calls,{call_id:'extra',name:P+'write_report',arguments:{}}];
    let chunks=chunksFor(declared,{finish:kind==='stop'?'stop':'tool-calls'});
    if(kind==='bad-json')chunks[1].block.arguments='{{';
    if(kind==='no-stream')await s.runtime.intercept(f.config.session_id,s.options,()=>[]);else await predict(f,s,declared,chunks);
    if(kind!=='no-dispatch')dispatch(f,s,kind==='reversed-dispatch'?[...calls].reverse():calls);
    for(const c of calls)result(f,s,c);await s.runtime.intercept(f.config.session_id,s.options,()=>[]);
    assert.equal(s.rows.find(r=>r.kind==='shadow_batch_result').verified,false,kind);
  }
});

test('source, baseline code, additions, tool file and library drift prevent prediction or invalidate results',async t=>{
  for(const kind of ['source','code','addition','frozen','library']){
    const f=fixture(t),shadow=join(f.work,'batch-lib.json');writeFileSync(shadow,JSON.stringify(f.library));f.config.shadow_library=shadow;
    const s=setup(f),before=readFileSync(join(f.work,'triage.json'));
    if(kind==='source')writeFileSync(f.config.catalog_path,JSON.stringify({keys:['new']}));
    if(kind==='code')writeFileSync(join(f.work,'code.txt'),'different');
    if(kind==='addition'){const p=Object.keys(f.library.code_additions_sha256)[0];f.config.code_files[p]='0'.repeat(64);}
    if(kind==='frozen')writeFileSync(f.config.library_path,'{}');
    if(kind==='library')writeFileSync(shadow,'{}');
    await s.runtime.intercept(f.config.session_id,s.options,()=>[]);assert.equal(s.rows.at(-1).kind,'deferred',kind);
    assert.deepEqual(readFileSync(join(f.work,'triage.json')),before);
  }
  const f=fixture(t),s=setup(f),calls=await predict(f,s);dispatch(f,s,calls);result(f,s,calls[0]);
  writeFileSync(join(f.work,'triage.json'),JSON.stringify({keys:['b']}));result(f,s,calls[1]);
  assert.equal(s.rows.at(-1).kind,'shadow_batch_result');assert.equal(s.rows.at(-1).verified,false);assert.equal(s.rows.at(-1).snapshot_match,false);
});

test('symlink and shared hardlink reports fail closed',async t=>{
  for(const kind of ['symlink','hardlink']){
    const f=fixture(t),s=setup(f),path=join(f.work,'triage.json'),other=join(f.work,'other.json');writeFileSync(other,readFileSync(path));rmSync(path);
    if(kind==='symlink')symlinkSync(other,path);else linkSync(other,path);
    await s.runtime.intercept(f.config.session_id,s.options,()=>[]);assert.equal(s.rows.at(-1).kind,'deferred');
  }
});

test('one anchor window produces one prediction; foreign sessions never rearm it',async t=>{
  const f=fixture(t),rows=[],runtime=createBatchShadowInterceptor({library:f.library,config:f.config,audit:r=>rows.push(r)}),options={tools:f.tools};let providers=0;
  runtime.observe('foreign',{name:P+'read_task_state',arguments:{},callId:'foreign'},observed(f.read));
  assert.equal(await runtime.intercept('foreign',options,()=>{providers++;return 'foreign';}),'foreign');assert.equal(rows.length,0);
  await runtime.intercept(f.config.session_id,options,()=>{providers++;return [];});assert.equal(rows.at(-1).kind,'deferred');
  runtime.observe(f.config.session_id,{name:P+'read_task_state',arguments:{},callId:'anchor'},observed(f.read));
  const calls=callsFor(f),resultStream=await runtime.intercept(f.config.session_id,options,()=>{providers++;return stream(chunksFor(calls));});
  for await(const c of resultStream){}
  await runtime.intercept(f.config.session_id,options,()=>{providers++;return [];});
  assert.equal(rows.at(-1).kind,'deferred');assert.equal(rows.filter(r=>r.kind==='prediction').length,1);assert.equal(providers,4);
  assert.equal(rows.some(r=>r.kind==='model_request_skipped_verified'),false);
});

test('public plugin preserves provider stream and tool permissions while observing dispatch/result',async t=>{
  const f=fixture(t),shadow=join(f.work,'batch-lib.json'),configPath=join(f.work,'config.json');writeFileSync(shadow,JSON.stringify(f.library));
  f.config.shadow_library=shadow;writeFileSync(configPath,JSON.stringify(f.config));
  const prior=process.env.SSS_TRACE_RSI_TASK_CONFIG;process.env.SSS_TRACE_RSI_TASK_CONFIG=configPath;
  t.after(()=>{if(prior===undefined)delete process.env.SSS_TRACE_RSI_TASK_CONFIG;else process.env.SSS_TRACE_RSI_TASK_CONFIG=prior;});
  const listeners=new Map(),toolEvents=new Map(),restrictions=new Map();
  apply({on(event,cb){const rows=listeners.get(event)??[];rows.push(cb);listeners.set(event,rows);}});
  const emit=(event,value)=>{for(const cb of listeners.get(event)??[])cb(value);};
  const agent=id=>({session:{id},ctx:{tools:{restrict:value=>restrictions.set(id,value)},on(event,cb){if(id===f.config.session_id)toolEvents.set(event,cb);}}});
  emit('agent/created',{agent:agent(f.config.session_id)});emit('agent/created',{agent:agent('other')});
  const names=f.tools.map(t=>t.name);assert.deepEqual(restrictions.get(f.config.session_id),{allow:names});assert.deepEqual(restrictions.get('other'),{deny:names});
  toolEvents.get('tools/result')({name:P+'read_task_state',arguments:{},callId:'anchor'},observed(f.read));
  const calls=callsFor(f),chunks=chunksFor(calls),request=markAgentLoopRequest({sessionId:f.config.session_id,tools:f.tools,
    messages:[{id:'u',role:'user',source:{kind:'user'},content:[{type:'text',text:'批次诊断任务'}]}]});
  const saved=clone(request),received=[];let providers=0,dispatched=0;
  for await(const c of listeners.get('llm/stream')[0](request,()=>{providers++;return stream(chunks);}))received.push(c);
  for(const c of calls)await toolEvents.get('tools/pre-execute')({callId:c.call_id,name:c.name,arguments:c.arguments},()=>{dispatched++;return 'allow';});
  for(const c of [...calls].reverse())toolEvents.get('tools/result')({callId:c.call_id,name:c.name,arguments:c.arguments},observed(value(f,c)));
  assert.equal(providers,1);assert.equal(dispatched,2);assert.deepEqual(received,chunks);assert.deepEqual(clone(request),saved);
  const rows=readFileSync(join(f.work,'shadow.jsonl'),'utf8').trim().split('\n').map(JSON.parse);
  assert.equal(rows.find(r=>r.kind==='shadow_batch_result').verified,true);assert.equal(rows.filter(r=>r.kind==='prediction').length,1);
  assert.equal(rows.some(r=>r.kind==='model_request_skipped_verified'),false);
});
