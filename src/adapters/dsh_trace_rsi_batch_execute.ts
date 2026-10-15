/** Explicitly authorized execution of frozen whole-request batches.
 * A Shadow library is evidence, not permission. The separate current local
 * authorization and two independent zero-text training witnesses are required.
 * Private artifact export additionally requires its bounded effect permission.
 */
import {appendFileSync,readFileSync} from 'node:fs';
import {join} from 'node:path';
import {randomUUID} from 'node:crypto';
import {createBatchShadowInterceptor} from './dsh_trace_rsi_batch_shadow.ts';
import {attachMotifInterceptor} from './dsh_online_motif.mjs';
import {syntheticToolStreamBatch} from '../motif_core/online_skill_runtime.mjs';
import {readBoundedFile,sha256} from './paper_triage_validation.ts';
export const name='sss-trace-rsi-batch-execute';
export const inject=['agents','llm'];
export function createBatchExecuteInterceptor({library,config,audit=()=>{}}:any):any {
 const authBytes=readBoundedFile(config.execute_authorization_path,16384),auth=JSON.parse(authBytes.toString('utf8'));
 if(config.mode!=='execute'||auth.execute_allowed!==true||auth.reset_history!==false||
    auth.execution_environment!=='local'||sha256(authBytes)!==config.execute_authorization_sha256||
    config.execute_library_digest!==library.manifest_digest)throw Error('explicit_current_execute_authorization_required');
 let last:any=null,halted=false;const attempts=new Map<number,string>();
 const record=(row:any)=>audit({...row,execution_authorized:true,mode:'execute',authorization_sha256:config.execute_authorization_sha256});
 const observer=createBatchShadowInterceptor({library,config,audit:(row:any)=>{
  if(row.kind==='prediction'||row.kind==='deferred')last=row;
  record(row);
  if(row.kind==='shadow_batch_result'&&attempts.has(row.request_ordinal)){
   const id=attempts.get(row.request_ordinal);attempts.delete(row.request_ordinal);
   if(row.verified!==true)halted=true;
   record({kind:row.verified===true?'model_request_skipped_verified':'model_request_skip_unverified',
     request_ordinal:row.request_ordinal,motif_id:row.motif_id,batch_id:id,verified:row.verified===true});
  }
 }});
 return {
  observe:observer.observe,observeDispatch:observer.observeDispatch,deferRequest:observer.deferRequest,
  async intercept(id:string,options:any,next:any):Promise<any>{
   if(id!==config.session_id||halted)return next();
   if(sha256(readBoundedFile(config.execute_authorization_path,16384))!==config.execute_authorization_sha256){
    halted=true;record({kind:'execute_deferred',reason:'authorization_changed'});return next();
   }
   return observer.intercept(id,options,async()=>{
    const p=last?.prediction,m=library.motifs.find((x:any)=>x.motif_id===p?.motif_id);
    if(!p||!m||m.training_session_count<2||new Set(m.witnesses.filter((w:any)=>w.next_text_blocks===0).map((w:any)=>w.session_id)).size<2||
       p.expected_tools.length>8||!p.expected_tools.length||
       m.batch.some((n:any)=>!['candidate_output','task_state','private_artifact_output'].includes(n.result_kind))||
       m.batch.some((n:any)=>n.result_kind==='private_artifact_output')&&auth.private_artifact_export_allowed!==true)return next();
    const batchId='rsi-execute-'+randomUUID();attempts.set(last.request_ordinal,batchId);
    record({kind:'model_request_skip_attempt',request_ordinal:last.request_ordinal,batch_id:batchId,
      motif_id:m.motif_id,tools:p.expected_tools,training_session_count:m.training_session_count});
    // Harness dispatches these actual MCP calls. Predicted outputs are never
    // injected; the shared observer checks actual dispatch, results and version.
    return syntheticToolStreamBatch(p.expected_tools.map((t:any)=>({callId:'rsi-'+randomUUID(),
      proposal:{tool:t.tool,arguments:t.arguments}})));
   });
  }
 };
}
export function apply(ctx:any):void {
 const config=JSON.parse(readFileSync(process.env.SSS_TRACE_RSI_TASK_CONFIG!,'utf8'));
 const library=JSON.parse(readFileSync(config.shadow_library,'utf8'));
 const audit=(row:any)=>appendFileSync(join(config.work,'execute.jsonl'),JSON.stringify(row)+'\n',{mode:0o600});
 const interceptor=createBatchExecuteInterceptor({library,config,audit}),names=library.tools.map((t:any)=>t.name);
 ctx.on('agent/created',({agent}:any)=>{
  agent.ctx.tools.restrict(agent.session.id===config.session_id?{allow:names}:{deny:names});
  if(agent.session.id===config.session_id)agent.ctx.on('tools/pre-execute',(exec:any,next:any)=>{
   interceptor.observeDispatch(agent.session.id,exec);return next();
  });
 });
 attachMotifInterceptor(ctx,{task:{session_id:config.session_id},promptHash:config.prompt_sha256,interceptor,
  audit:(kind:string,reason:string)=>{if(kind==='motif_gate_deferred')interceptor.deferRequest(reason);else audit({kind,reason,session_id:config.session_id});}});
}
