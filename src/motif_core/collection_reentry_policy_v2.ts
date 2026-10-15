/** Reentry with the separately versioned prefetch-aware collection executor. */
import {validateReentryPolicy,validateReentryTask} from './collection_reentry_policy.ts';
import {createCollectionController} from './collection_read_policy_v2.ts';
export function createReentryController(policy:any,task:any,audit:(r:any)=>void){
 validateReentryPolicy(policy);validateReentryTask(task,policy);let epoch=1,halted=false;
 const make=(p:any)=>createCollectionController(p,task,(row:any)=>{
  audit({...row,library_epoch:epoch,library_role:epoch===1?'frozen_L1':'learned_L2_residual'});
  if(row.kind==='collection_model_request_bypassed_verified'&&epoch===2)audit({kind:'reentry_epoch_batch_verified',stage:row.stage,batch_id:row.batch_id,count:row.count});
 });
 let child=make(policy.parent_policy);
 const fail=(reason:string)=>{halted=true;child.fail(reason);audit({kind:'reentry_deferred',reason});};
 return {get armed(){return child.armed&&!child.done;},get done(){return epoch===2&&child.done;},get halted(){return halted||child.halted;},get pending(){return child.pending;},fail,
  observe(exec:any,result:any){
   if(halted||child.halted||epoch===2&&child.done)return;
   if(child.done){
    if(exec.name!==policy.next_policy.artifact.graph.source_tool)return;
    if(String(exec.callId).startsWith('sss-')){fail('reentry_requires_actual_model_selection');return;}
    epoch=2;child=make(policy.next_policy);
    audit({kind:'reentry_model_frontier_observed',call_id:exec.callId,parent_policy_digest:policy.parent_policy.policy_digest,next_policy_digest:policy.next_policy.policy_digest});
   }
   child.observe(exec,result);
  },propose(tools:any[],newId:()=>string){if(halted)return [];return child.propose(tools,newId);}
 };
}
