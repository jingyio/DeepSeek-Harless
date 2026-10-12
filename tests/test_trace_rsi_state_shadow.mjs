/** Synthetic protocol diagnostics. No model-generation or savings claim. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,readFileSync,writeFileSync,rmSync,realpathSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {digest} from '../src/adapters/paper_rsi_program.ts';
import {sha256} from '../src/adapters/paper_triage_validation.ts';
import {createTraceRsiTaskTools} from '../scenarios/paper-submission/trace-rsi-task-server.ts';
import {createStateShadowInterceptor,validateStateShadowLibrary} from '../src/adapters/dsh_trace_rsi_state_shadow.ts';

const P='mcp__paper_trace_rsi__',FEATURE='prior_same_input_check',clone=x=>JSON.parse(JSON.stringify(x));
const rehash=value=>{const {manifest_digest,...body}=value;return {...body,manifest_digest:digest(body)};};
const observed=value=>({value:{content:[{type:'text',text:JSON.stringify(value)}]}});
function fixture(t){
  const work=realpathSync(mkdtempSync(join(tmpdir(),'sss-state-shadow-')));t.after(()=>rmSync(work,{recursive:true,force:true}));
  const schema={type:'object',properties:{rows:{type:'array',items:{type:'string'}}},required:['rows'],additionalProperties:false};
  const candidate={schema_version:1,name:'replay_rows',description:'合成诊断',input_schema:schema,output_schema:schema,program:['var','input']};
  const provenance={trace_bundle_sha256:'a'.repeat(64),source_witnesses:[{run_id:'synthetic',session_id:'synthetic-learning',call_id:'s',events_sha256:'b'.repeat(64)}],
    proposal:{input_bindings:{rows:{file:'triage.json',pointer:'/rows'}}}};
  const certification={status:'passed',kind:'source_replay',heldout_cases:2};
  const frozen=rehash({schema_version:1,kind:'model_generated_trace_tool',candidate,candidate_sha256:digest(candidate),provenance,
    provenance_sha256:digest(provenance),certification,certification_sha256:digest(certification)});
  const libraryPath=join(work,'tool.json'),catalogPath=join(work,'catalog.json');
  writeFileSync(libraryPath,JSON.stringify(frozen));writeFileSync(catalogPath,'{}');writeFileSync(join(work,'triage.json'),JSON.stringify({rows:['a']}));
  const paths=['scenarios/paper-submission/trace-rsi-task-server.ts','src/adapters/paper_rsi_program.ts','src/adapters/trace_rsi_program.ts','src/adapters/dsh_trace_rsi_shadow.ts'].map(p=>resolve(p));
  const extra=Object.fromEntries(['src/adapters/trace_rsi_state_compiler.py','src/adapters/dsh_trace_rsi_state_shadow.ts','scripts/paper-rsi-state-shadow.py'].map(p=>[resolve(p),sha256(readFileSync(p))]));
  const baseCodes=Object.fromEntries(paths.map(p=>[p,sha256(readFileSync(p))]));
  const config={work,library_path:libraryPath,catalog_path:catalogPath,catalog_sha256:sha256(readFileSync(catalogPath)),source_version:'c'.repeat(64),
    session_id:'heldout',case_id:'synthetic-heldout',tool_digest:frozen.manifest_digest,candidate_sha256:frozen.candidate_sha256,
    prompt_sha256:'d'.repeat(64),code_files:{...baseCodes,...extra},source_files:{[catalogPath]:sha256(readFileSync(catalogPath))}};
  const service=createTraceRsiTaskTools(config),read=service.call('read_task_state',{}),{report,input,input_id,...receipt}=read;
  const tools=service.definitions.map(t=>({name:P+t.name,parameters:t.inputSchema})),sources={};
  for(const i of [1,2])sources['r'+i]={run_id:'r'+i,session_id:'training'+i,case_id:'synthetic'+i,source_version:config.source_version,
    source_files_sha256:clone(config.source_files),prompt_sha256:config.prompt_sha256,events_sha256:String(i).repeat(64),
    config_sha256:'a'.repeat(64),manifest_sha256:'b'.repeat(64),verification_sha256:'d'.repeat(64),requests:Object.fromEntries([1,2,3,4,5,6].map(n=>[n+'.json','e'.repeat(64)]))};
  const motifs=['read_task_state','write_report'].map((anchor,index)=>({motif_id:'edge'+index,anchor:P+anchor,next:P+candidate.name,
    parameter_binding:{input_id:'/input_id'},training_session_count:2,status:'shadow_candidate',witnesses:[1,2].map(i=>({
      session_id:'training'+i,run_id:'r'+i,case_id:'synthetic'+i,anchor_call_id:anchor+i,next_call_id:'check'+anchor+i,events_sha256:String(i).repeat(64),
      anchor_line:2+index*7,anchor_result_line:3+index*7,next_line:5+index*7,next_result_line:6+index*7,
      anchor_request:1+index*2,next_request:2+index*2,anchor_text_blocks:1,next_text_blocks:1,
      receipt:{input_id:'trace-input-'+digest({...receipt,session_id:'training'+i}),...receipt},output_sha256:digest(input)}))}));
  const base=rehash({schema_version:1,kind:'trace_rsi_continuation_shadow',execution_policy:'shadow_only',tool_digest:config.tool_digest,
    candidate_sha256:config.candidate_sha256,tools,code_files_sha256:baseCodes,motifs,sources});
  const derived=rehash({...base,code_files_sha256:config.code_files});
  const guards=motifs.map((m,index)=>{
    const observations=m.witnesses.map(w=>({session_id:w.session_id,run_id:w.run_id,anchor_call_id:w.anchor_call_id,anchor_request:w.anchor_request,
      events_sha256:w.events_sha256,receipt:w.receipt,features:{[FEATURE]:false},continues:true,next_request:w.next_request,next_tools:[m.next],next_text_blocks:1}));
    if(index===0)observations.push({...clone(observations[0]),anchor_call_id:'terminal-read',anchor_request:5,next_request:6,next_tools:[],features:{[FEATURE]:true},continues:false});
    return {motif_id:m.motif_id,status:index===0?'learned_condition':'no_negative_evidence',condition:index===0?{feature:FEATURE,equals:false}:null,
      observations,positive_count:2,negative_count:index===0?1:0};
  });
  const library=rehash({schema_version:1,kind:'trace_rsi_state_shadow',execution_policy:'shadow_only',base_library:base,derived_library:derived,guards,
    feature_protocol:{name:FEATURE,key_fields:Object.keys(receipt),scope:'current_session_successful_generated_check'},observer_additions_sha256:extra,
    limitations:['手写合成诊断，不是正常模型轨迹。']});
  return {config,service,library,tools,read};
}
async function request(f,interceptor){let calls=0;await interceptor.intercept(f.config.session_id,{tools:f.tools},()=>{calls++;return 'native';});assert.equal(calls,1);}
function observe(f,interceptor,name,args,output){interceptor.observe(f.config.session_id,{name:P+name,arguments:args,callId:'diagnostic'},observed(output));}

test('learned guard keeps fresh input checks and suppresses repeat checks on unchanged versions',async t=>{
  const f=fixture(t),audit=[],i=createStateShadowInterceptor({...f,audit:r=>audit.push(r)});
  observe(f,i,'read_task_state',{},f.read);await request(f,i);
  assert.equal(audit.at(-1).kind,'prediction');assert.equal(audit.at(-1).state_features[FEATURE],false);
  const checked=f.service.call('replay_rows',{input_id:f.read.input_id});observe(f,i,'replay_rows',{input_id:f.read.input_id},checked);
  assert.equal(audit.at(-1).kind,'shadow_result');assert.equal(audit.at(-1).verified,true);
  await request(f,i);observe(f,i,'read_task_state',{},f.service.call('read_task_state',{}));await request(f,i);
  assert.equal(audit.at(-1).kind,'deferred');assert.equal(audit.at(-1).reason,'learned_state_guard');assert.equal(audit.at(-1).state_features[FEATURE],true);
});

test('changed report versions become fresh; failed checks never create completion facts',async t=>{
  const f=fixture(t),audit=[],i=createStateShadowInterceptor({...f,audit:r=>audit.push(r)});
  observe(f,i,'replay_rows',{input_id:f.read.input_id},f.service.call('replay_rows',{input_id:f.read.input_id}));await request(f,i);
  const written=f.service.call('write_report',{report_sha256:f.read.report_sha256,report:{rows:['b']}});
  observe(f,i,'write_report',{report_sha256:f.read.report_sha256,report:{rows:['b']}},written);await request(f,i);
  assert.equal(audit.at(-1).kind,'prediction');assert.equal(audit.at(-1).state_features[FEATURE],false);
  i.observe(f.config.session_id,{name:P+'replay_rows',arguments:{input_id:written.input_id}}, {isError:true});await request(f,i);
  observe(f,i,'read_task_state',{},f.service.call('read_task_state',{}));await request(f,i);
  assert.equal(audit.at(-1).kind,'prediction');assert.equal(audit.at(-1).state_features[FEATURE],false);
});

test('conditions must follow positive and negative witnesses; core implementation cannot migrate',t=>{
  const f=fixture(t);assert.doesNotThrow(()=>validateStateShadowLibrary(f.library,f.config));
  for(const mutate of [x=>{x.guards[0].condition.equals=true;},x=>{x.guards[0].negative_count=2;},x=>{x.guards[0].observations[2].continues=true;},
    x=>{x.guards[0].observations[2].events_sha256='e'.repeat(64);},x=>{x.derived_library.motifs[0].next=P+'write_report';},x=>{x.execution_policy='execute';}]){
    const bad=clone(f.library);mutate(bad);assert.throws(()=>validateStateShadowLibrary(rehash(bad),f.config));
  }
});

test('history is scoped to the configured session and an altered library cannot keep predicting',async t=>{
  const f=fixture(t),audit=[],i=createStateShadowInterceptor({...f,audit:r=>audit.push(r)});
  i.observe('foreign',{name:P+'replay_rows',arguments:{input_id:f.read.input_id}},observed(f.service.call('replay_rows',{input_id:f.read.input_id})));
  observe(f,i,'read_task_state',{},f.read);await request(f,i);assert.equal(audit.at(-1).kind,'prediction');
  f.library.guards[0].status='ambiguous_state';observe(f,i,'read_task_state',{},f.read);await request(f,i);
  assert.equal(audit.at(-1).kind,'deferred');
});
