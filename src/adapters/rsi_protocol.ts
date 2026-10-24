/** Opt-in RSI wire protocol. The authenticated host supplies all authority.
 * This module adds no model loop, shell evaluator or production default.
 */
import {createHash, randomUUID} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {assertSupportedJsonSchema, validateJsonSchemaValue} from '@deepseek-ai/dsh-tools';

const schema=JSON.parse(readFileSync(new URL('../../schemas/rsi-protocol-v1.schema.json',import.meta.url),'utf8'));
assertSupportedJsonSchema(schema);
export const bytesSha256=(value:string|Buffer)=>createHash('sha256').update(value).digest('hex');
const clone=<T>(value:T):T=>structuredClone(value);
type Version={id:string;sha256:string};
export type Versions={motif:Version;matcher:Version};
type EvidenceRef={id:string;sha256:string;version:string};
export type RsiRecord={protocol:'geneloop.rsi/v1';record_type:string;payload:any};
const sameVersion=(a:Version,b:Version)=>a.id===b.id&&a.sha256===b.sha256;
const sameVersions=(a:Versions,b:Versions)=>sameVersion(a.motif,b.motif)&&sameVersion(a.matcher,b.matcher);
const sameRefs=(a:EvidenceRef[],b:EvidenceRef[])=>a.length===b.length&&new Set(a.map(x=>x.id)).size===a.length&&
 a.every(x=>b.some(y=>x.id===y.id&&x.sha256===y.sha256&&x.version===y.version));

function wireValues(value:any,key='',depth=0){
 if(depth>64)throw Error('rsi_record_too_deep');
 if(key==='input_schema'||key==='output_schema'){assertSupportedJsonSchema(value);return;}
 if(typeof value==='number'&&(!Number.isFinite(value)||Math.abs(value)>Number.MAX_SAFE_INTEGER))throw Error('rsi_wire_number_out_of_range');
 if(key.endsWith('sha256')&&value!==null&&(typeof value!=='string'||!/^[a-f0-9]{64}$/.test(value)))throw Error('rsi_wire_digest_invalid');
 if(['id','task_id','version','operation','state_version'].includes(key)&&
  (typeof value!=='string'||!value||value.length>256))throw Error('rsi_wire_identifier_invalid');
 if(Array.isArray(value)){for(const child of value)wireValues(child,'',depth+1);}
 else if(value&&typeof value==='object')for(const [k,v]of Object.entries(value))wireValues(v,k,depth+1);
}

export function validateRsiRecord(value:unknown):RsiRecord {
 wireValues(value);
 const raw=JSON.stringify(value);
 if(!raw||Buffer.byteLength(raw)>1_000_000)throw Error('rsi_record_too_large');
 if(validateJsonSchemaValue(schema,value).length)throw Error('rsi_record_schema_invalid');
 const record=value as RsiRecord;
 if(record.record_type==='operator'){
  assertSupportedJsonSchema(record.payload.input_schema);
  assertSupportedJsonSchema(record.payload.output_schema);
 }
 return clone(record);
}
export function rsiRecord(record_type:string,payload:any):RsiRecord {
 return validateRsiRecord({protocol:'geneloop.rsi/v1',record_type,payload});
}
function payload(record:RsiRecord,kind:string){
 const checked=validateRsiRecord(record);
 if(checked.record_type!==kind)throw Error('rsi_record_kind_mismatch');
 return checked.payload;
}

export type AdmissionHost={
 taskId:string;stateVersion:string;versions:Versions;
 /** From an independently verified registry, never from the candidate request. */
 operators:Map<string,{record:RsiRecord;certified:boolean}>;
 currentCodeSha256:Map<string,string|null>;
 currentEvidence:Map<string,RsiRecord>;
 /** A current semantic selection or independently checkable task obligation. */
 obligations:Map<string,{taskId:string;operation:string;argumentsSha256:string;stateVersion:string;dependencies:EvidenceRef[]}>;
 grant:{id:string;taskId:string;stateVersion:string;operations:string[];effects:string[];revoked:boolean};
};

/** Re-read this host at every dispatch boundary. Similarity is never authority. */
export function admissionDecision(request:RsiRecord,host:AdmissionHost):RsiRecord {
 const q=payload(request,'runtime_request');
 const decide=(action:string,reason:string)=>rsiRecord('runtime_decision',{
  request_id:q.id,task_id:q.task_id,action,reason,versions:host.versions,
  evidence_ids:q.dependencies.map((x:EvidenceRef)=>x.id)});
 if(q.task_id!==host.taskId)return decide('reject','task_mismatch');
 if(q.state_version!==host.stateVersion)return decide('handoff','state_changed');
 if(!sameVersions(q.versions,host.versions))return decide('reject','component_version_changed');
 const entry=host.operators.get(q.operator_id);
 if(!entry)return decide('handoff','no_applicable_operator');
 const op=payload(entry.record,'operator');
 if(!entry.certified)return decide('reject','operator_not_certified');
 if(op.operation!==q.operation)return decide('reject','operation_mismatch');
 if(op.opaque||op.effect==='opaque')return decide('handoff','opaque_operation');
 if(op.effect==='external_write')return decide('reject','external_write_not_enabled');
 if(!host.currentCodeSha256.has(op.id)||host.currentCodeSha256.get(op.id)!==op.code_sha256)
  return decide('reject','operator_code_changed');
 const grant=host.grant;
 if(grant.revoked||grant.taskId!==q.task_id||grant.stateVersion!==host.stateVersion||
  !grant.operations.includes(q.operation)||!grant.effects.includes(op.effect))return decide('reject','permission_denied');
 const obligation=host.obligations.get(q.obligation_ref);
 if(!obligation)return decide('handoff','semantic_obligation_missing');
 if(obligation.taskId!==q.task_id||obligation.operation!==q.operation||
  obligation.argumentsSha256!==q.arguments_sha256||obligation.stateVersion!==host.stateVersion)
  return decide('handoff','semantic_obligation_changed');
 if(!q.dependencies.length||!sameRefs(q.dependencies,obligation.dependencies))return decide('reject','dependency_binding_mismatch');
 for(const ref of q.dependencies){
  const current=host.currentEvidence.get(ref.id);
  if(!current)return decide('handoff','current_evidence_missing');
  const evidence=payload(current,'evidence');
  if(evidence.task_id!==q.task_id||evidence.role!=='current')return decide('reject','evidence_scope_mismatch');
  if(evidence.status!=='valid'||evidence.sha256!==ref.sha256||evidence.version!==ref.version)
   return decide('handoff','evidence_invalidated');
 }
 return decide('execute','current_obligation_and_guards_verified');
}

/** The callback MUST use the normal native tool lifecycle and its live guards.
 * A returned decision is not a reusable grant. The current host is re-read here.
 */
export async function executeRsiOperation(request:RsiRecord,args:unknown,
 readHost:()=>AdmissionHost,dispatch:(operation:string,args:unknown)=>Promise<unknown>,identity:{callId?:string}={}){
 const q=payload(request,'runtime_request'),bound=clone(args),host=readHost();
 const decision=admissionDecision(request,host);
 if(decision.payload.action!=='execute')return {decision,events:[],result:null};
 const stop=(action:string,reason:string)=>({decision:rsiRecord('runtime_decision',{...decision.payload,action,reason}),events:[],result:null});
 if(bytesSha256(JSON.stringify(bound))!==q.arguments_sha256)return stop('reject','arguments_changed');
 const op=payload(host.operators.get(q.operator_id)!.record,'operator');
 if(validateJsonSchemaValue(op.input_schema,bound).length)return stop('handoff','input_schema_invalid');
 const callId=identity.callId??randomUUID();
 const event=(phase:string,output:string|null,error:string|null,sequence:number)=>rsiRecord('execution_event',{
  id:randomUUID(),task_id:q.task_id,sequence,call_id:callId,source_kind:op.source_kind,
  operation:q.operation,phase,arguments_sha256:q.arguments_sha256,result_sha256:output,
  dependencies:q.dependencies,permission_ref:host.grant.id,versions:host.versions,
  provider_call_id:null,error});
 const events=[event('started',null,null,0)];
 try{
  const result=await dispatch(q.operation,bound);
  if(validateJsonSchemaValue(op.output_schema,result).length)throw Error('rsi_output_schema_invalid');
  events.push(event('succeeded',bytesSha256(JSON.stringify(result)),null,1));
  return {decision,events,result};
 }catch(error){
  events.push(event('failed',null,error instanceof Error?error.message:'tool_failure',1));
  return {decision:rsiRecord('runtime_decision',{...decision.payload,action:'handoff',reason:'tool_execution_failed'}),events,result:null};
 }
}

export type UpdateHost={
 versions:Versions;candidateSha256:string;payloadSha256:string;
 /** Digests are of exact stored UTF-8 bytes, not cross-language reserialization. */
 approvedReports:Map<string,string>;reportSha256:string;
 evidence:Map<string,RsiRecord>;
 diagnoses:Map<string,RsiRecord>;
};

/** Validate a proposal against independently supplied evidence and review.
 * This authorizes no code evaluation; component-specific adapters own changes.
 */
export function decodeRsiRecord(bytes:string|Buffer){
 const raw=typeof bytes==='string'?Buffer.from(bytes,'utf8'):bytes;
 if(raw.byteLength>1_000_000)throw Error('rsi_record_too_large');
 return {record:validateRsiRecord(JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(raw))),sha256:bytesSha256(raw)};
}

export function validateRsiUpdate(candidateBytes:string|Buffer,reportBytes:string|Buffer,host:UpdateHost){
 const candidate=decodeRsiRecord(candidateBytes),report=decodeRsiRecord(reportBytes);
 const c=payload(candidate.record,'candidate_patch'),r=payload(report.record,'validation_report');
 const check=(condition:boolean,reason:string)=>{if(!condition)throw Error(reason);};
 check(candidate.sha256===host.candidateSha256,'rsi_candidate_bytes_changed');
 check(report.sha256===host.reportSha256,'rsi_report_bytes_changed');
 check(c.component===(c.patch_kind==='matcher_code_patch'?'matcher':'motif'),'rsi_patch_target_mismatch');
 check(sameVersion(c.base_version,host.versions[c.component as 'motif'|'matcher']),'rsi_stale_parent');
 check(!sameVersion(c.base_version,c.next_version)&&c.base_version.id!==c.next_version.id,'rsi_new_version_required');
 check(sameVersions(c.compatible_versions,host.versions),'rsi_incompatible_components');
 check(c.payload_sha256===host.payloadSha256,'rsi_patch_payload_changed');
 const diagnosisRecord=host.diagnoses.get(c.diagnosis_id);
 check(!!diagnosisRecord,'rsi_diagnosis_missing');
 const diagnosis=payload(diagnosisRecord!,'diagnosis');
 check(diagnosis.component===c.component&&sameVersion(diagnosis.base_version,c.base_version)&&sameRefs(diagnosis.feedback,c.feedback),
  'rsi_diagnosis_binding_mismatch');
 check(r.candidate_id===c.id&&r.candidate_sha256===host.candidateSha256&&sameVersion(r.base_version,c.base_version),'rsi_report_candidate_mismatch');
 check(r.passed&&r.checks.length>0&&r.checks.every((x:any)=>x.passed),'rsi_validation_failed');
 check(host.approvedReports.get(r.id)===host.reportSha256,'rsi_report_not_independently_approved');
 check(r.independent_task_ids.length>0&&new Set(r.independent_task_ids).size===r.independent_task_ids.length&&
  r.independent_task_ids.every((id:string)=>!c.training_task_ids.includes(id)),'rsi_validation_task_overlap');
 check(c.feedback.length>0&&r.evidence.length>0,'rsi_update_evidence_missing');
 for(const [refs,role]of [[c.feedback,'feedback'],[r.evidence,'validation']] as const){
  check(new Set(refs.map((x:EvidenceRef)=>x.id)).size===refs.length,'rsi_duplicate_evidence');
  for(const ref of refs){
   const stored=host.evidence.get(ref.id);check(!!stored,'rsi_update_evidence_missing');
   const e=payload(stored!,'evidence');
   check(e.status==='valid'&&e.sha256===ref.sha256&&e.version===ref.version,'rsi_update_evidence_changed');
   check(e.role!=='test','rsi_frozen_test_prohibited');
   if(role==='validation')check(e.role==='validation'&&r.independent_task_ids.includes(e.task_id),'rsi_validation_evidence_scope');
   else check(e.role==='training'&&c.training_task_ids.includes(e.task_id),'rsi_feedback_evidence_scope');
  }
 }
 check(r.independent_task_ids.every((id:string)=>r.evidence.some((ref:EvidenceRef)=>host.evidence.get(ref.id)?.payload.task_id===id)),
  'rsi_validation_task_unwitnessed');
 return {previous:clone(host.versions),next:{...clone(host.versions),[c.component]:clone(c.next_version)}};
}

/** The adapter commits atomically against expected versions. No receipt before
 * a successful commit; the callback must retain independent native certification.
 */
export async function publishRsiUpdate(candidateBytes:string|Buffer,reportBytes:string|Buffer,
 readHost:()=>UpdateHost,commit:(change:{expected:Versions;next:Versions;payloadSha256:string})=>Promise<{versions:Versions;manifestSha256:string}>){
 const host=readHost(),versions=validateRsiUpdate(candidateBytes,reportBytes,host);
 const candidate=decodeRsiRecord(candidateBytes).record,report=decodeRsiRecord(reportBytes).record;
 const published=await commit({expected:versions.previous,next:versions.next,payloadSha256:host.payloadSha256});
 if(!sameVersions(published.versions,versions.next))throw Error('rsi_publication_version_mismatch');
 return rsiRecord('publication_receipt',{id:randomUUID(),candidate_id:candidate.payload.id,
  report_id:report.payload.id,previous_versions:versions.previous,next_versions:versions.next,manifest_sha256:published.manifestSha256});
}

export async function rollbackRsiUpdate(publicationBytes:string|Buffer,host:{current:Versions;publicationSha256:string},reason:string,
 restore:(change:{expected:Versions;next:Versions})=>Promise<{versions:Versions;manifestSha256:string}>){
 const publication=decodeRsiRecord(publicationBytes),current=host.current;
 if(publication.sha256!==host.publicationSha256)throw Error('rsi_rollback_publication_changed');
 const p=payload(publication.record,'publication_receipt');
 if(!sameVersions(current,p.next_versions))throw Error('rsi_rollback_current_version_mismatch');
 const restored=await restore({expected:clone(current),next:clone(p.previous_versions)});
 if(!sameVersions(restored.versions,p.previous_versions))throw Error('rsi_rollback_version_mismatch');
 return rsiRecord('rollback_receipt',{id:randomUUID(),publication_id:p.id,reason,
  previous_versions:clone(current),restored_versions:p.previous_versions,manifest_sha256:restored.manifestSha256});
}
