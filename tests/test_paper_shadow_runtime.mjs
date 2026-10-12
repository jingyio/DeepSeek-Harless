import test from 'node:test';
import assert from 'node:assert/strict';
import { createPaperShadowMatcher, compareShadowResponse, shadowDigest, validateShadowLibrary } from '../src/adapters/paper_shadow_runtime.ts';
import { sha256 } from '../src/adapters/paper_triage_validation.ts';

function fixture() {
  const graph={anchor:{tool:'write',ownership:'model',result:'success',artifact_binding:'arguments.file_path'},
    continuation:{tool:'check_paper_triage',arguments:{},read_only:true},artifact_role:'registered_triage_report',
    artifact_relative_path:'triage.json',handoff:'after_check_or_any_guard_failure'};
  const source_version='b'.repeat(64),code=Object.fromEntries(['src/adapters/paper_triage_validation.ts',
    'src/adapters/dsh_paper_delivery_check.ts','schemas/paper-citation-triage.schema.json'].map(p=>[p,'a'.repeat(64)]));
  const tools=Object.fromEntries(['write','edit','check_paper_triage'].map(t=>[t,'c'.repeat(64)]));
  const witness={run_id:'train',session_id:'training',input_version:'d'.repeat(64),report_sha256:'e'.repeat(64),
    anchor_request:2,check_request:3,check_status:'passed'};
  const library={schema_version:1,scope:'artifact_continuation_shadow_probe',execution_policy:'shadow_only',
    tool_schema_sha256:tools,validator_code_sha256:code,source_traces:{train:{session_id:'training',input_version:witness.input_version}},
    motifs:[{motif_id:'paper-shadow-'+shadowDigest(graph).slice(0,12),graph,training_witnesses:[witness],
      training_session_count:1,support:'single_trace_candidate',status:'shadow_candidate_not_execution_certified'}],limitations:[]};
  library.manifest_digest=shadowDigest(library);
  const config={session_id:'evaluation',source_version,work:'/task/work',source_unchanged:true,
    validator_code_sha256:code,tool_schema_sha256:tools};
  const snapshot={check:'paper_citation_triage_structure',status:'needs_repair',errors:['missing_reference_pairs'],
    report_sha256:sha256('new bytes'),source_version,semantic_quality:'not_reviewed'};
  const exec={name:'write',arguments:{file_path:'/task/work/triage.json',content:'new bytes'},call_id:'w1',
    session_id:config.session_id,ok:true,request_tool_count:1};
  return {library,config,snapshot,exec};
}
const checkCall={type:'tool-call',id:'c1',name:'check_paper_triage',arguments:'{}'};
function prediction(f) {
  const m=createPaperShadowMatcher(f.library,f.config);m.binding(f.config.session_id,f.config.source_version,true);
  m.observe(f.exec,f.snapshot);return m.takePrediction();
}
test('current write binds a local readonly prediction, both pass and repair preserve model ownership',()=>{
  const f=fixture(),p=prediction(f);assert.equal(p.execution_authorized,false);
  assert.equal(compareShadowResponse(p,[checkCall],f.snapshot).whole_request,true);
  const changed={...f.snapshot,status:'passed',errors:[]};
  assert.equal(compareShadowResponse(p,[checkCall],changed).whole_request,false);
  f.snapshot=changed;assert.equal(compareShadowResponse(prediction(f),[checkCall],changed).whole_request,true);
});
test('narration, new semantic content and mixed calls cannot inflate whole-request counts',()=>{
  const f=fixture(),p=prediction(f);
  for(const content of [[checkCall,{type:'text',text:'I will check now.'}],
    [checkCall,{type:'text',text:'This paper is formally published.'}],
    [checkCall,{type:'tool-call',name:'web_fetch',arguments:'{}'}]])
    assert.equal(compareShadowResponse(p,content,f.snapshot).whole_request,false);
  assert.equal(compareShadowResponse(p,[checkCall,{type:'text',text:' '}],f.snapshot).whole_request,true);
});
test('stale snapshots, failed/mixed/external mutations and missing bindings suppress predictions',()=>{
  for(const mutate of [f=>f.snapshot.source_version='f'.repeat(64),f=>f.snapshot.report_sha256='f'.repeat(64),
    f=>f.exec.ok=false,f=>f.exec.aborted=true,f=>f.exec.request_tool_count=2,
    f=>f.exec.arguments.file_path='../triage.json',f=>f.exec.arguments.file_path='/other/triage.json',
    f=>f.config.source_unchanged=false]) {
    const f=fixture();mutate(f);assert.equal(prediction(f),null);
  }
  const f=fixture(),m=createPaperShadowMatcher(f.library,f.config);m.observe(f.exec,f.snapshot);
  assert.equal(m.takePrediction(),null);
});
test('failed refresh and unknown interleaving invalidate pending local continuations',()=>{
  for(const action of [m=>m.binding('evaluation','b'.repeat(64),false),
    m=>m.observe({session_id:'evaluation',name:'web_fetch',ok:true},null)]) {
    const f=fixture(),m=createPaperShadowMatcher(f.library,f.config);
    m.binding('evaluation',f.config.source_version,true);m.observe(f.exec,f.snapshot);action(m);
    assert.equal(m.takePrediction(),null);
  }
});
test('digest, protocol and schema/code version changes fail closed',()=>{
  const f=fixture(),bad=structuredClone(f.library);bad.execution_policy='execute';bad.manifest_digest=shadowDigest(
    Object.fromEntries(Object.entries(bad).filter(([k])=>k!=='manifest_digest')));
  assert.throws(()=>validateShadowLibrary(bad));
  for(const field of ['tool_schema_sha256','validator_code_sha256']) {
    const config=structuredClone(f.config);config[field][Object.keys(config[field])[0]]='f'.repeat(64);
    assert.throws(()=>createPaperShadowMatcher(f.library,config),/drift/);
  }
  f.library.motifs[0].graph.continuation.read_only=false;
  assert.throws(()=>validateShadowLibrary(f.library));
});
