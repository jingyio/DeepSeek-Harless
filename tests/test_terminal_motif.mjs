import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash,randomUUID} from 'node:crypto';
import {mkdirSync,mkdtempSync,writeFileSync,rmSync,readFileSync,symlinkSync} from 'node:fs';
import {resolve,join} from 'node:path';
import {markAgentLoopRequest} from '@deepseek-ai/dsh-llm';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';
import {validateTerminalPolicy,validateTerminalTask,verifyRepairReceipt} from '../src/motif_core/terminal_receipt_policy.ts';
import {createTerminalGate} from '../src/adapters/dsh_entry_motif.ts';
const ROOT=resolve('.'),tool='mcp__literature_pdf_repair__submit_claim_repair',schema={type:'object',properties:{}};
const hash=p=>createHash('sha256').update(readFileSync(p)).digest('hex');
function fixture(){
 const dir=mkdtempSync(join(ROOT,'.local/terminal-test-')),input=join(dir,'input'),output=join(dir,'output'),pdf=join(dir,'pdf');
 for(const p of [input,output,pdf])mkdirSync(p);writeFileSync(join(pdf,'one.pdf'),'fixture-pdf-bytes');
 const inventory={root:pdf,papers:[{paper_id:'p',filename:'one.pdf',pdf_sha256:hash(join(pdf,'one.pdf')),bytes:17}]};
 const task={question:'fixture',sources:inventory},evidence={draft:{}},request={input_sha256:digest(evidence),claim_ids:['claim:p:method']};
 function save(p,v){writeFileSync(p,JSON.stringify(v));}
 save(join(input,'evidence.json'),evidence);save(join(input,'pdf-input-snapshot.json'),{task});save(join(input,'repair-targets.json'),request);
 const versions=[{path:'src/motif_core/terminal_receipt_policy.ts',sha256:hash('src/motif_core/terminal_receipt_policy.ts')}];
 const frame={schema_version:1,session_id:'s',task_id:'t',input_version:digest(evidence),task_sha256:digest(task),request_version:digest(request),policy_sha256:digest({}),
  target_ids:request.claim_ids,target_ids_sha256:digest(request.claim_ids),pdf_inventory:inventory,artifact_root:output,version_files:versions,execution_version_sha256:digest(versions),
  input_files:['evidence.json','pdf-input-snapshot.json','repair-targets.json'].map(n=>({path:join(input,n),sha256:hash(join(input,n))})),
  prompt_sha256:createHash('sha256').update('Review the selected claims').digest('hex')};
 const payload={task_sha256:frame.task_sha256,original_evidence_sha256:frame.input_version,status:'preview',gaps:[]};
 const audit={input_sha256:frame.input_version,task_sha256:frame.task_sha256,repair_request_sha256:frame.request_version,
  target_claim_ids:frame.target_ids,policy:{},revised_evidence_sha256:digest(payload),decisions:[{claim_id:frame.target_ids[0],verdict:'supported'}],changed_claim_ids:[],unresolved_claim_ids:[]};
 const receipt={input_sha256:frame.input_version,artifact:join(output,'revised-evidence.json'),artifact_sha256:digest(payload),audit:join(output,'claim-review.json'),audit_sha256:digest(audit),
  status:'preview',target_count:1,changed_claim_count:0,unresolved_claim_ids:[],gap_count:0};save(receipt.artifact,payload);save(receipt.audit,audit);
 const artifact={kind:'task_terminal_receipt',status:'trace_validated_read_only',schema_sha256:digest(schema),source_task_fingerprints:['a','b'],validation_task_fingerprint:'new',tools:[tool],
  terminal:{kind:'receipt_then_finish',receipt_contract:'claim_repair_v1',tool,statuses:['preview'],max_targets:100,output:'verified_status_json',provider_requests:0}};
 artifact.certified_digest=digest(artifact);const policy={schema_version:1,format:'sss-terminal-receipt-v1',source_library_digest:'a'.repeat(64),execution_version_sha256:frame.execution_version_sha256,artifact};policy.policy_digest=digest(policy);
 const args={decisions:[],synthesis_hypothesis:'fixture'},cid='original-call',exec={callId:cid,name:tool,arguments:args};
 const human={id:'u',role:'user',source:{kind:'user'},content:[{type:'text',text:'Review the selected claims'}]};
 const messages=[human,{role:'assistant',content:[{type:'tool-call',id:cid,name:tool,arguments:JSON.stringify(args)}]},
  {role:'user',source:{kind:'tool',callId:cid},content:[{type:'tool-result',toolCallId:cid,content:[{type:'text',text:JSON.stringify(receipt)}]}]}];
 const req=()=>markAgentLoopRequest(Object.freeze({sessionId:'s',messages,tools:[{name:tool,parameters:schema}]}));
 return {dir,input,output,pdf,frame,policy,receipt,payload,audit,args,exec,messages,req,save};
}
async function consume(s){const a=[];for await(const c of s)a.push(c);return a;}
test('actual receipt fields and current sources produce a transparent stop with zero provider calls',async()=>{
 const f=fixture();try{
  validateTerminalPolicy(f.policy);validateTerminalTask(f.frame,f.policy);assert.equal(verifyRepairReceipt(f.receipt,f.frame).status,'preview');
  const log=[],g=createTerminalGate(f.policy,f.frame,r=>log.push(r));let calls=0;const next=()=>{calls++;return(async function*(){})();};
  await consume(g.intercept(f.req(),next,true));assert.equal(calls,1); // No trusted tool callback yet.
  g.observe(f.exec,{value:{structuredContent:f.receipt}});const chunks=await consume(g.intercept(f.req(),next,true));
  assert.equal(calls,1);assert.equal(chunks.at(-1).reason.kind,'stop');
  assert.equal(JSON.parse(chunks.find(c=>c.type==='text-delta').text).producer,'certified_terminal_runtime');
  assert.equal(log.filter(r=>r.kind==='terminal_model_request_bypassed_verified').length,1);
  await consume(g.intercept(f.req(),next,true));assert.equal(calls,2);
 }finally{rmSync(f.dir,{recursive:true,force:true});}
});
for(const change of ['artifact','audit','input','pdf','added_pdf','wrong_counts','target','symlink','version','schema','mixed','followup','failed'])test('terminal falls back on '+change,async()=>{
 const f=fixture();try{
  const log=[],g=createTerminalGate(f.policy,f.frame,r=>log.push(r));let calls=0;const next=()=>{calls++;return(async function*(){})();};
  await consume(g.intercept(f.req(),next,true));g.observe(f.exec,{value:{structuredContent:f.receipt}});
  if(change==='artifact')f.save(f.receipt.artifact,{...f.payload,gaps:[{}]});
  if(change==='audit')f.save(f.receipt.audit,{...f.audit,changed_claim_ids:['unapproved']});
  if(change==='input')writeFileSync(join(f.input,'repair-targets.json'),'{}');
  if(change==='pdf')writeFileSync(join(f.pdf,'one.pdf'),'changed-file');
  if(change==='added_pdf')writeFileSync(join(f.pdf,'extra.pdf'),'extra');
  if(change==='wrong_counts'){f.receipt.gap_count=1;g.observe(f.exec,{value:{structuredContent:f.receipt}});}
  if(change==='target')f.frame.target_ids.push('unapproved'); // After validation: live guard still binds audit/targets.
  if(change==='symlink'){rmSync(f.receipt.artifact);symlinkSync(f.receipt.audit,f.receipt.artifact);}
  if(change==='version')f.frame.version_files[0].sha256='e'.repeat(64);
  if(change==='schema')f.policy.artifact.schema_sha256='e'.repeat(64);
  if(change==='mixed')f.messages[1].content.push({...f.messages[1].content[0],id:'another'});
  if(change==='followup')f.messages.push({role:'user',source:{kind:'user'},content:[{type:'text',text:'Do another task'}]});
  if(change==='failed')g.observe(f.exec,{isError:true});
  await consume(g.intercept(f.req(),next,true));assert.equal(calls,2);
  assert.equal(log.filter(r=>r.kind==='terminal_model_request_bypassed_verified').length,0);
 }finally{rmSync(f.dir,{recursive:true,force:true});}
});
