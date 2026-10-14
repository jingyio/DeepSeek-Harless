/** Additive state guard around existing batches; no tool result is invented. */
import {readFileSync,appendFileSync} from 'node:fs';
import {join} from 'node:path';
import {digest} from './paper_rsi_program.ts';
import {sha256,readBoundedFile} from './paper_triage_validation.ts';
import {observation} from '../motif_core/online_skill_runtime.mjs';
import {createBatchShadowInterceptor} from './dsh_trace_rsi_batch_shadow.ts';
import {createBatchExecuteInterceptor} from './dsh_trace_rsi_batch_execute.ts';
import {attachMotifInterceptor} from './dsh_online_motif.mjs';
export const name='sss-trace-rsi-effect-guard';
export const inject=['agents','llm'];
const P='mcp__paper_trace_rsi__',unsafe=new Set(['__proto__','prototype','constructor']);
export function guardAllows(conditions:any,output:any):boolean {
 if(!output||typeof output!=='object'||Array.isArray(output)||!Array.isArray(conditions)||conditions.length<1||conditions.length>8)return false;
 const seen=new Set<string>();
 return conditions.every((c:any)=>{
  if(!c||Object.keys(c).length!==2||typeof c.feature!=='string'||typeof c.equals!=='boolean'||seen.has(c.feature))return false;
  seen.add(c.feature);const match=/^([^:]{1,128}):(true|empty|zero)$/.exec(c.feature);
  if(!match||unsafe.has(match[1]))return false;
  const property=Object.getOwnPropertyDescriptor(output,match[1]);
  if(!property||!Object.hasOwn(property,'value'))return false;
  const value=property.value;let feature:any;
  if(match[2]==='true'&&typeof value==='boolean')feature=value;
  if(match[2]==='empty'&&Array.isArray(value)&&value.length<=2000)feature=value.length===0;
  if(match[2]==='zero'&&typeof value==='number'&&Number.isFinite(value))feature=value===0;
  return typeof feature==='boolean'&&feature===c.equals;
 });
}
export function createEffectGuardInterceptor({library,config,audit=()=>{}}:any):any {
 const bytes=readBoundedFile(config.effect_guard_path,64000),guard=JSON.parse(bytes.toString('utf8'));
 const {manifest_digest,...body}=guard;
 if(config.effect_guard_sha256!==sha256(bytes)||config.code_files[config.effect_guard_path]!==sha256(bytes)||
  digest(body)!==manifest_digest||guard.schema_version!==1||guard.kind!=='trace_rsi_effect_guard'||
  guard.effect!=='private_current_report_export'||guard.candidate_sha256!==config.candidate_sha256||
  guard.certification?.status!=='passed'||!Array.isArray(guard.conditions)||guard.conditions.length<1||guard.conditions.length>8)
  throw Error('version_bound_certified_effect_guard_required');
 let ordinal=0,last:any=null,halted=false;
 const record=(r:any)=>audit({...r,underlying_request_ordinal:r.request_ordinal,request_ordinal:ordinal,
  effect_guard_manifest_digest:manifest_digest});
 const base=(config.mode==='execute'?createBatchExecuteInterceptor:createBatchShadowInterceptor)({library,config,audit:record});
 return {
  observeDispatch:base.observeDispatch,
  observe(id:string,exec:any,result:any){
   base.observe(id,exec,result);
   if(id===config.session_id)last={name:exec.name,output:observation(result,exec.name),
    ok:!result?.isError&&!result?.value?.isError&&!exec.signal?.aborted};
  },
  deferRequest(reason:string){ordinal++;last=null;base.deferRequest(reason);},
  async intercept(id:string,options:any,next:any):Promise<any>{
   if(id!==config.session_id)return next();ordinal++;
   try{if(sha256(readBoundedFile(config.effect_guard_path,64000))!==config.effect_guard_sha256)halted=true;}catch{halted=true;}
   const anchored=last?.name===P+config.check_name,blocked=anchored&&(!last.ok||!guardAllows(guard.conditions,last.output?.output));last=null;
   if(halted||blocked){
    record({kind:'deferred',prediction:null,reason:halted?'effect_guard_changed':'learned_effect_guard',
     state_guard_kind:'learned_typed_output_conjunction',execution_authorized:false});
    // The normal provider runs unchanged. Old lineage may cause one later
    // opportunity to be missed, a deliberate conservative fallback.
    return next();
   }
   return base.intercept(id,options,next);
  }
 };
}
export function apply(ctx:any):void {
 const config=JSON.parse(readFileSync(process.env.SSS_TRACE_RSI_TASK_CONFIG!,'utf8'));
 const library=JSON.parse(readFileSync(config.shadow_library,'utf8'));
 const audit=(row:any)=>appendFileSync(join(config.work,config.mode==='execute'?'execute.jsonl':'shadow.jsonl'),JSON.stringify(row)+'\n',{mode:0o600});
 const interceptor=createEffectGuardInterceptor({library,config,audit}),names=library.tools.map((t:any)=>t.name);
 ctx.on('agent/created',({agent}:any)=>{
  agent.ctx.tools.restrict(agent.session.id===config.session_id?{allow:names}:{deny:names});
  if(agent.session.id===config.session_id)agent.ctx.on('tools/pre-execute',(exec:any,next:any)=>{interceptor.observeDispatch(agent.session.id,exec);return next();});
 });
 attachMotifInterceptor(ctx,{task:{session_id:config.session_id},promptHash:config.prompt_sha256,interceptor,
  audit:(kind:string,reason:string)=>{if(kind==='motif_gate_deferred')interceptor.deferRequest(reason);else audit({kind,reason});}});
}
