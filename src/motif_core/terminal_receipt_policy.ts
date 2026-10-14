/** Bounded claim-repair receipt validation and deterministic terminal state. */
import {readFileSync,lstatSync,realpathSync,readdirSync} from 'node:fs';
import {resolve,dirname,basename,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {digest,observation} from './online_skill_runtime.mjs';
const ROOT=dirname(dirname(dirname(fileURLToPath(import.meta.url))));
const hex=(v:any)=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const omit=(v:any,k:string)=>Object.fromEntries(Object.entries(v).filter(([key])=>key!==k));
const rawHash=(p:string)=>createHash('sha256').update(readFileSync(p)).digest('hex');
function regular(path:string,root:string,max=8*1024*1024){
 const p=resolve(path),base=realpathSync(root),s=lstatSync(p);
 if(!s.isFile()||s.isSymbolicLink()||s.size>max||!realpathSync(p).startsWith(base+sep))throw new Error('unbound private file');
 return p;
}
export function validateTerminalPolicy(p:any){
 const a=p?.artifact,t=a?.terminal;
 if(p?.schema_version!==1||p.format!=='sss-terminal-receipt-v1'||!hex(p.policy_digest)
  ||p.policy_digest!==digest(omit(p,'policy_digest'))||!hex(p.source_library_digest)||!hex(p.execution_version_sha256)
  ||a?.kind!=='task_terminal_receipt'||a.status!=='trace_validated_read_only'||!hex(a.schema_sha256)
  ||a.certified_digest!==digest(omit(a,'certified_digest'))||!Array.isArray(a.source_task_fingerprints)
  ||a.source_task_fingerprints.length!==2||new Set(a.source_task_fingerprints).size!==2
  ||!a.validation_task_fingerprint||a.source_task_fingerprints.includes(a.validation_task_fingerprint)
  ||t?.kind!=='receipt_then_finish'||t.receipt_contract!=='claim_repair_v1'
  ||t.tool!=='mcp__literature_pdf_repair__submit_claim_repair'||digest(a.tools)!==digest([t.tool])
  ||!Array.isArray(t.statuses)||!t.statuses.length||new Set(t.statuses).size!==t.statuses.length
  ||t.statuses.some((s:any)=>!['preview','needs_review'].includes(s))||t.max_targets!==100
  ||t.output!=='verified_status_json'||t.provider_requests!==0)throw new TypeError('invalid certified terminal policy');
 return p;
}
export function validateTerminalTask(t:any,p:any){
 if(t?.schema_version!==1||typeof t.session_id!=='string'||!t.session_id||typeof t.task_id!=='string'||!t.task_id
  ||!hex(t.input_version)||!hex(t.task_sha256)||!hex(t.request_version)||!hex(t.policy_sha256)
  ||t.execution_version_sha256!==p.execution_version_sha256||!Array.isArray(t.target_ids)||!t.target_ids.length
  ||t.target_ids.length>100||t.target_ids.some((i:any)=>typeof i!=='string'||!i||i.length>160)
  ||new Set(t.target_ids).size!==t.target_ids.length||digest(t.target_ids)!==t.target_ids_sha256
  ||typeof t.artifact_root!=='string'||!Array.isArray(t.input_files)||t.input_files.length!==3
  ||digest(t.input_files.map((f:any)=>basename(f?.path??'')).sort())!==digest(['evidence.json','pdf-input-snapshot.json','repair-targets.json'])
  ||t.input_files.some((f:any)=>typeof f.path!=='string'||!hex(f.sha256))
  ||!Array.isArray(t.version_files)||!t.version_files.length||t.version_files.length>20
  ||t.version_files.some((f:any)=>typeof f.path!=='string'||f.path.startsWith('/')||f.path.split('/').includes('..')||!hex(f.sha256))
  ||digest(t.version_files)!==t.execution_version_sha256
  ||!t.pdf_inventory||typeof t.pdf_inventory.root!=='string'||!Array.isArray(t.pdf_inventory.papers)
  ||!t.pdf_inventory.papers.length||t.pdf_inventory.papers.length>20
  ||t.pdf_inventory.papers.some((r:any)=>typeof r.filename!=='string'||basename(r.filename)!==r.filename
    ||!r.filename.endsWith('.pdf')||!hex(r.pdf_sha256)||!Number.isSafeInteger(r.bytes)||r.bytes<1||r.bytes>64*1024*1024)
  ||new Set(t.pdf_inventory.papers.map((r:any)=>r.filename)).size!==t.pdf_inventory.papers.length)
  throw new TypeError('invalid frozen terminal task');
 return t;
}
export function verifyRepairReceipt(r:any,t:any){
 try{
  const local=resolve(ROOT,'.local');
  if(t.version_files.some((f:any)=>rawHash(regular(resolve(ROOT,f.path),ROOT))!==f.sha256))return null;
  const inputs:any={};
  for(const f of t.input_files){const p=regular(f.path,local);if(rawHash(p)!==f.sha256)return null;inputs[basename(p)]=JSON.parse(readFileSync(p,'utf8'));}
  if(digest(inputs['evidence.json'])!==t.input_version||digest(inputs['pdf-input-snapshot.json'].task)!==t.task_sha256
   ||digest(inputs['repair-targets.json'])!==t.request_version||digest(inputs['repair-targets.json'].claim_ids)!==t.target_ids_sha256
   ||digest(inputs['pdf-input-snapshot.json'].task.sources)!==digest(t.pdf_inventory))return null;
  const names=readdirSync(t.pdf_inventory.root).filter((n:string)=>n.endsWith('.pdf')).sort();
  if(digest(names)!==digest(t.pdf_inventory.papers.map((r:any)=>r.filename).sort()))return null;
  for(const row of t.pdf_inventory.papers){const p=regular(resolve(t.pdf_inventory.root,row.filename),t.pdf_inventory.root,64*1024*1024);
   if(lstatSync(p).size!==row.bytes||rawHash(p)!==row.pdf_sha256)return null;}
  if(r.input_sha256!==t.input_version||!hex(r.artifact_sha256)||!hex(r.audit_sha256))return null;
  const base=realpathSync(t.artifact_root);
  if(!base.startsWith(realpathSync(local)+sep)||resolve(r.artifact)!==resolve(base,'revised-evidence.json')
   ||resolve(r.audit)!==resolve(base,'claim-review.json'))return null;
  const payload=JSON.parse(readFileSync(regular(r.artifact,base),'utf8'));
  const a=JSON.parse(readFileSync(regular(r.audit,base),'utf8'));
  if(digest(payload)!==r.artifact_sha256||digest(a)!==r.audit_sha256||payload.task_sha256!==t.task_sha256
   ||payload.original_evidence_sha256!==t.input_version||a.input_sha256!==t.input_version||a.task_sha256!==t.task_sha256
   ||a.repair_request_sha256!==t.request_version||digest(a.target_claim_ids)!==t.target_ids_sha256
   ||digest(a.policy)!==t.policy_sha256||a.revised_evidence_sha256!==r.artifact_sha256
   ||payload.status!==r.status||!Array.isArray(payload.gaps)||!Array.isArray(a.decisions)
   ||digest(a.decisions.map((d:any)=>d.claim_id))!==t.target_ids_sha256||!Array.isArray(a.changed_claim_ids)
   ||!Array.isArray(a.unresolved_claim_ids)||[...a.changed_claim_ids,...a.unresolved_claim_ids].some((id:any)=>!t.target_ids.includes(id))
   ||new Set(a.changed_claim_ids).size!==a.changed_claim_ids.length||new Set(a.unresolved_claim_ids).size!==a.unresolved_claim_ids.length
   ||a.decisions.some((d:any)=>!['supported','revised','withdrawn','not_extracted'].includes(d.verdict))
   ||digest(a.unresolved_claim_ids)!==digest(a.decisions.filter((d:any)=>['withdrawn','not_extracted'].includes(d.verdict)).map((d:any)=>d.claim_id))
   ||r.target_count!==t.target_ids.length||r.changed_claim_count!==a.changed_claim_ids.length
   ||digest(r.unresolved_claim_ids)!==digest(a.unresolved_claim_ids)||r.gap_count!==payload.gaps.length
   ||r.status!==(payload.gaps.length?'needs_review':'preview'))return null;
  return {status:r.status,target_count:r.target_count,changed_claim_count:r.changed_claim_count,
   unresolved_claim_count:a.unresolved_claim_ids.length,gap_count:r.gap_count,artifact:r.artifact,
   artifact_sha256:r.artifact_sha256,producer:'certified_terminal_runtime',scientific_truth_certified:false};
 }catch{return null;}
}
export function createTerminalController(policy:any,task:any,audit:(v:any)=>void,verify=verifyRepairReceipt){
 validateTerminalPolicy(policy);validateTerminalTask(task,policy);
 let armed:any=null,halted=false,done=false;
 return {
  get armed(){return armed;},get halted(){return halted;},get done(){return done;},
  fail(reason:string){armed=null;halted=true;audit({kind:'terminal_motif_deferred',reason});},
  observe(exec:any,result:any){
   armed=null;if(halted||done||exec.name!==policy.artifact.terminal.tool)return;
   const r=observation(result,exec.name);
   if(!r||!policy.artifact.terminal.statuses.includes(r.status))return;
   const summary=verify(r,task);if(!summary){this.fail('receipt_or_source_unverified');return;}
   armed={call_id:exec.callId,args_sha256:digest(exec.arguments),receipt:r,receipt_sha256:digest(r)};
   audit({kind:'terminal_receipt_verified',call_id:exec.callId,receipt_sha256:digest(r)});
  },
  finish(){
   if(!armed||halted||done)return null;
   const summary=verify(armed.receipt,task);if(!summary){this.fail('receipt_or_source_changed_after_publication');return null;}
   done=true;audit({kind:'terminal_model_request_bypassed_verified',call_id:armed.call_id,
    policy_digest:policy.policy_digest,receipt_sha256:armed.receipt_sha256,
    counterfactual_requests_saved_inferred:false,scientific_truth_certified:false});
   return summary;
  }
 };
}
export function terminalStream(summary:any){return(async function*(){
 const text=JSON.stringify(summary);yield {type:'block-start',index:0,blockType:'text'};
 yield {type:'text-delta',index:0,text};yield {type:'block-end',index:0,block:{type:'text',text}};
 yield {type:'finish',reason:{kind:'stop'}};
})();}
