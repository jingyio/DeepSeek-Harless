/** Synthetic no-provider protocol checks; not learned traces or quality evidence. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {createOnlineInterceptor} from '../src/adapters/dsh_online_motif.mjs';
import {compileLocalPrograms,digest} from '../src/adapters/online_motif_frontier.mjs';
import {closedPaperDocumentFirstPage} from '../src/adapters/harless_rsi_binding.ts';

const pin='mcp__paper_checks__pin_document',read='mcp__paper_checks__read_pinned_document';
const version='a'.repeat(64),source='source-'+'b'.repeat(32);
function fixture(){
 const manifest={schema_version:1,source_library_digest:'c'.repeat(64),
  artifacts:[{motif_id:'free-document-protocol',certified_digest:'d'.repeat(64),tools:[pin,read],
   supporting_task_count:2,validation_task_fingerprint:'free-protocol-only',
   transfer_evidence:[{from_tool:pin,from_field:'source_id',to_tool:read,to_param:'source_id'}]}],
  contracts:{
   [pin]:{read_only:true,observed_anchor:true,required_params:['name','sha256'],default_params:{},
    output_fields:['source_id','version_sha256'],description:'Pin approved document'},
   [read]:{read_only:true,required_params:['source_id'],default_params:{page:1},
    output_fields:['source_id','version_sha256'],description:'Read pinned document page'},
  },slot_rules:{},version_fields:{[pin]:'version_sha256',[read]:'version_sha256'}};
 for(const artifact of manifest.artifacts)artifact.local_programs=compileLocalPrograms(artifact);
 manifest.manifest_digest=digest(manifest);
 const task={schema_version:1,task_id:'free-current-task',session_id:'free-current-session',
  intent:'Read an uploaded document',input_version:'current-approved-byte-set',bindings:{},
  source_versions:{[pin]:'@observed',[read]:'@from_anchor'}};
 const tools=[{name:read,description:'Read pinned document page',parameters:{type:'object',
  properties:{source_id:{type:'string'},page:{type:'integer',default:1}},required:['source_id']}}];
 const audits=[];
 const core=createOnlineInterceptor({manifest,task,mode:'execute',audit:row=>audits.push(row),closedContinuation:closedPaperDocumentFirstPage,
  similarity:async()=>{throw Error('a closed document read must not call embeddings');}});
 const observe=(session=task.session_id,result={structuredContent:{source_id:source,version_sha256:version}})=>
  core.observe(session,{name:pin,callId:'model-selected-source',arguments:{name:'paper.docx',sha256:version}},result);
 return {core,task,tools,audits,observe};
}

test('Paper document continuation reuses only page one and counts savings after a matching real result',async()=>{
 const f=fixture();let modelCalls=0;
 const next=()=>{modelCalls++;return 'ordinary model';};
 assert.equal(await f.core.intercept(f.task.session_id,{tools:f.tools},next),'ordinary model');
 f.observe();const stream=await f.core.intercept(f.task.session_id,{tools:f.tools},next);
 const chunks=[];for await(const chunk of stream)chunks.push(chunk);
 const call=chunks.find(row=>row.type==='tool-call-delta');assert.ok(call);
 assert.equal(call.name,read);assert.deepEqual(JSON.parse(call.argumentsDelta),{source_id:source,page:1});
 assert.equal(modelCalls,1);assert.equal(f.audits.some(row=>row.kind==='model_request_skipped_verified'),false);
 f.core.observe(f.task.session_id,{name:read,callId:call.id,arguments:{source_id:source,page:1}},
  {structuredContent:{source_id:source,version_sha256:version,text:'actual tool bytes'}});
 assert.equal(f.audits.filter(row=>row.kind==='model_request_skipped_verified').length,1);
 assert.equal(await f.core.intercept(f.task.session_id,{tools:f.tools},next),'ordinary model','reuse cannot invent page two or repeat the same read');
});

for(const issue of ['foreign-session','invalid-source','invalid-version','failed-pin','schema-drift','write-barrier']){
 test(`Paper ${issue} returns to the ordinary model without a verified skip`,async()=>{
  const f=fixture();let tools=f.tools;
  if(issue==='foreign-session')f.observe('another-session');
  else if(issue==='invalid-source')f.observe(f.task.session_id,{structuredContent:{source_id:'foreign-handle',version_sha256:version}});
  else if(issue==='invalid-version')f.observe(f.task.session_id,{structuredContent:{source_id:source,version_sha256:'stale'}});
  else if(issue==='failed-pin')f.observe(f.task.session_id,{isError:true,structuredContent:{source_id:source,version_sha256:version}});
  else f.observe();
  if(issue==='schema-drift')tools=[{...f.tools[0],parameters:{...f.tools[0].parameters,required:['source_id','new_required']}}];
  if(issue==='write-barrier')f.core.observe(f.task.session_id,{name:'mcp__paper_checks__export_review_report',callId:'model-owned-write',arguments:{}},
   {structuredContent:{delivered:true}});
  let modelCalls=0;assert.equal(await f.core.intercept(f.task.session_id,{tools},()=>{modelCalls++;return 'ordinary model';}),'ordinary model');
  assert.equal(modelCalls,1);assert.equal(f.audits.some(row=>row.kind==='model_request_skipped_verified'),false);
 });
}

for(const issue of ['wrong-source-arguments','wrong-version-result','failed-read']){
 test(`Paper ${issue} invalidates the attempted reuse and resumes the model`,async()=>{
  const f=fixture();f.observe();let modelCalls=0;
  const next=()=>{modelCalls++;return 'ordinary model';};
  const chunks=[];for await(const chunk of await f.core.intercept(f.task.session_id,{tools:f.tools},next))chunks.push(chunk);
  const call=chunks.find(row=>row.type==='tool-call-delta');assert.ok(call);
  f.core.observe(f.task.session_id,{name:read,callId:call.id,arguments:{source_id:issue==='wrong-source-arguments'?'source-'+'c'.repeat(32):source,page:1}},
   {isError:issue==='failed-read',structuredContent:{source_id:source,version_sha256:issue==='wrong-version-result'?'c'.repeat(64):version}});
  assert.equal(f.audits.some(row=>row.kind==='model_request_skipped_verified'),false);
  assert.ok(f.audits.some(row=>row.kind==='bypass_result_unverified'));
  assert.equal(await f.core.intercept(f.task.session_id,{tools:f.tools},next),'ordinary model');
  assert.equal(modelCalls,1);
 });
}
