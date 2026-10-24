/** Explicit diagnostic authority. Never connect this synthetic host to a user session. */
import {readFileSync} from 'node:fs';
import {validateRsiRecord,bytesSha256} from '../../src/adapters/rsi_protocol.ts';

export const fixtures=JSON.parse(readFileSync(new URL('./fixtures.json',import.meta.url),'utf8'));
export function fixtureRecord(kind,id){
 const value=fixtures.records.find(x=>x.record_type===kind&&(!id||x.payload.id===id));
 if(!value)throw Error('missing diagnostic fixture');
 return structuredClone(value);
}
export function diagnosticHost(task='B'){
 const request=fixtureRecord('runtime_request'),operator=fixtureRecord('operator','group-count');
 const args=structuredClone(fixtures.tasks[task==='A'?'A':'B'].arguments),hash=bytesSha256(JSON.stringify(args));
 const taskId=task==='A'?'experimental-report-A':task==='C'?'invitation-C':'registration-summary-B';
 const evidence=fixtureRecord('evidence','current-table');
 evidence.payload.task_id=taskId;evidence.payload.sha256=hash;
 request.payload.id='request-'+task;request.payload.state_version='state-'+task+'-1';
 request.payload.obligation_ref='current-semantic-choice-'+task;
 request.payload.task_id=taskId;request.payload.arguments_sha256=hash;
 request.payload.dependencies[0].sha256=hash;
 validateRsiRecord(request);validateRsiRecord(operator);validateRsiRecord(evidence);
 const host={taskId,stateVersion:request.payload.state_version,versions:structuredClone(fixtures.versions),
  operators:new Map([[operator.payload.id,{record:operator,certified:true}]]),
  currentCodeSha256:new Map([[operator.payload.id,bytesSha256(readFileSync(new URL('./group_count.py',import.meta.url)))]]),
  currentEvidence:new Map([[evidence.payload.id,evidence]]),
  obligations:new Map([[request.payload.obligation_ref,{taskId,operation:request.payload.operation,
   argumentsSha256:hash,stateVersion:request.payload.state_version,dependencies:structuredClone(request.payload.dependencies)}]]),
  grant:{id:'diagnostic-read-only-grant',taskId,stateVersion:request.payload.state_version,
   operations:[request.payload.operation],effects:['read'],revoked:false}};
 return {host,request,args};
}
