/** Learned session-state guard around the existing read-only Shadow adapter. */
import {closeSync,constants,existsSync,lstatSync,openSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {canonical,digest} from './paper_rsi_program.ts';
import {readBoundedFile} from './paper_triage_validation.ts';
import {createTraceShadowInterceptor,validateTraceShadowLibrary} from './dsh_trace_rsi_shadow.ts';
import {attachMotifInterceptor} from './dsh_online_motif.mjs';
import {observation} from '../motif_core/online_skill_runtime.mjs';

export const name='sss-trace-rsi-state-shadow';
export const inject=['agents','llm'];
const P='mcp__paper_trace_rsi__',feature='prior_same_input_check';
const receiptFields=['input_id','input_sha256','report_sha256','source_version','candidate_sha256','catalog_sha256'];
const additions=['src/adapters/trace_rsi_state_compiler.py','src/adapters/dsh_trace_rsi_state_shadow.ts','scripts/paper-rsi-state-shadow.py'];
const object=(x:any)=>x!==null&&typeof x==='object'&&!Array.isArray(x);
const hash=(x:any)=>typeof x==='string'&&/^[a-f0-9]{64}$/.test(x);
function exact(x:any,fields:string[],reason:string):void {
  if(!object(x)||Object.keys(x).length!==fields.length||fields.some(k=>!Object.hasOwn(x,k)))throw Error(reason);
}
function fingerprint(value:any):string|null {
  if(!object(value)||receiptFields.slice(1).some(k=>!hash(value[k]))||!/^trace-input-[a-f0-9]{64}$/.test(value.input_id))return null;
  return digest(Object.fromEntries(receiptFields.slice(1).map(k=>[k,value[k]])));
}
export function validateStateShadowLibrary(library:any,config:any):any {
  exact(library,['schema_version','kind','execution_policy','base_library','derived_library','guards',
    'feature_protocol','observer_additions_sha256','limitations','manifest_digest'],'invalid_state_library');
  const {manifest_digest,...body}=library;
  if(library.schema_version!==1||library.kind!=='trace_rsi_state_shadow'||library.execution_policy!=='shadow_only'||
    !hash(manifest_digest)||digest(body)!==manifest_digest||Buffer.byteLength(JSON.stringify(library))>256000)throw Error('unbound_state_library');
  validateTraceShadowLibrary(library.base_library,{...config,code_files:library.base_library.code_files_sha256});
  validateTraceShadowLibrary(library.derived_library,config);
  const stripped=(value:any)=>{const {manifest_digest,code_files_sha256,...rest}=value;return rest;};
  if(canonical(stripped(library.base_library))!==canonical(stripped(library.derived_library)))throw Error('state_extension_changed_base_evidence');
  const extra=library.observer_additions_sha256;
  if(!object(extra)||Object.keys(extra).length!==additions.length||
    additions.some(suffix=>!Object.keys(extra).some(p=>p.replace(/\\/g,'/').endsWith('/'+suffix)))||
    Object.entries(extra).some(([p,h])=>!hash(h)||Object.hasOwn(library.base_library.code_files_sha256,p))||
    canonical({...library.base_library.code_files_sha256,...extra})!==canonical(config.code_files))throw Error('observer_additions_only');
  if(canonical(library.feature_protocol)!==canonical({name:feature,key_fields:receiptFields.slice(1),scope:'current_session_successful_generated_check'}))throw Error('invalid_state_feature_protocol');
  if(!Array.isArray(library.limitations)||library.limitations.some((s:any)=>typeof s!=='string'||s.length>1000)||
    !Array.isArray(library.guards)||library.guards.length!==library.derived_library.motifs.length)throw Error('invalid_state_guards');
  const seen=new Set<string>();
  for(const guard of library.guards){
    exact(guard,['motif_id','status','condition','observations','positive_count','negative_count'],'invalid_state_guard');
    const motif=library.derived_library.motifs.find((m:any)=>m.motif_id===guard.motif_id);
    if(!motif||seen.has(guard.motif_id)||!Array.isArray(guard.observations)||guard.observations.length>2000)throw Error('unbound_state_guard');
    seen.add(guard.motif_id);let positives:any[]=[],negatives:any[]=[];const observed=new Set<string>();
    for(const o of guard.observations){
      exact(o,['session_id','run_id','anchor_call_id','anchor_request','events_sha256','receipt','features','continues','next_request','next_tools','next_text_blocks'],'invalid_state_observation');
      const source=library.base_library.sources?.[o.run_id];
      const id=canonical([o.session_id,o.anchor_call_id]);
      if(!source||source.session_id!==o.session_id||source.events_sha256!==o.events_sha256||observed.has(id)||
        !Number.isInteger(o.anchor_request)||o.anchor_request<1||o.next_request!==o.anchor_request+1||
        !Number.isInteger(o.next_text_blocks)||o.next_text_blocks<0||typeof o.continues!=='boolean'||
        !Array.isArray(o.next_tools)||o.next_tools.length>1||o.next_tools.some((t:any)=>typeof t!=='string')||!fingerprint(o.receipt))throw Error('unbound_state_observation');
      exact(o.receipt,receiptFields,'invalid_state_receipt');exact(o.features,[feature],'invalid_state_features');
      const {input_id,...base}=o.receipt;
      if(typeof o.features[feature]!=='boolean'||base.source_version!==source.source_version||
        base.candidate_sha256!==config.candidate_sha256||input_id!=='trace-input-'+digest({...base,session_id:o.session_id}))throw Error('invalid_state_features');
      observed.add(id);
      const witness=motif.witnesses.find((w:any)=>w.session_id===o.session_id&&w.anchor_call_id===o.anchor_call_id);
      if(o.continues?(!witness||witness.anchor_request!==o.anchor_request||canonical(witness.receipt)!==canonical(o.receipt)||canonical(o.next_tools)!==canonical([motif.next])):
        (Boolean(witness)||o.next_tools.includes(motif.next)))throw Error('state_observation_label_mismatch');
      (o.continues?positives:negatives).push(o);
    }
    if(positives.length!==motif.witnesses.length||guard.positive_count!==positives.length||guard.negative_count!==negatives.length)throw Error('state_support_mismatch');
    const values=new Set(positives.map(o=>o.features[feature]));
    const learnt=negatives.length>0&&values.size===1&&negatives.every(o=>!values.has(o.features[feature]));
    const status=negatives.length===0?'no_negative_evidence':learnt?'learned_condition':'ambiguous_state';
    if(guard.status!==status||canonical(guard.condition)!==canonical(learnt?{feature,equals:positives[0].features[feature]}:null))throw Error('state_condition_not_learned_from_evidence');
  }
  return library;
}

export function createStateShadowInterceptor({library,config,audit=()=>{}}:any):any {
  validateStateShadowLibrary(library,config);
  const initial=digest(library),guards=new Map(library.guards.map((g:any)=>[g.motif_id,g]));
  const checked=new Set<string>(),accepted=new Set<number>();let latest:any=null,limitReached=false;
  const nextTool=library.derived_library.motifs[0]?.next;
  const forward=(row:any)=>{
    if(row.kind==='shadow_result'){if(accepted.delete(row.request_ordinal))audit({...row,state_library_digest:library.manifest_digest});return;}
    if(row.kind==='prediction'){
      const guard:any=guards.get(row.prediction.motif_id),known=typeof latest==='boolean';
      const allowed=digest(library)===initial&&!limitReached&&known&&guard&&guard.status!=='ambiguous_state'&&
        (!guard.condition||latest===guard.condition.equals);
      if(!allowed){audit({...row,kind:'deferred',prediction:null,reason:'learned_state_guard',
        state_features:{[feature]:latest},underlying_motif_id:row.prediction.motif_id,state_library_digest:library.manifest_digest});return;}
      accepted.add(row.request_ordinal);
    }
    audit({...row,state_features:{[feature]:latest},state_library_digest:library.manifest_digest});
  };
  const base=createTraceShadowInterceptor({library:library.derived_library,config,audit:forward});
  return {
    observe(id:string,exec:any,result:any):void {
      base.observe(id,exec,result);if(id!==config.session_id)return;
      const output=observation(result,exec.name),key=fingerprint(output),ok=key&&!result?.isError&&!result?.value?.isError&&!exec.signal?.aborted;
      if(!ok){checked.clear();latest=null;return;}
      if(exec.name===nextTool){
        let args:any;try{args=typeof exec.arguments==='string'?JSON.parse(exec.arguments):exec.arguments;}catch{}
        if(args?.input_id===output.input_id&&Object.hasOwn(output,'output')){
          if(checked.size>=2000)limitReached=true;else checked.add(key!);
        }else checked.clear();latest=null;
      }else if([P+'read_task_state',P+'write_report'].includes(exec.name))latest=checked.has(key!);
      else latest=null;
    },
    deferRequest(reason:string):void {base.deferRequest(reason);latest=null;},
    async intercept(id:string,options:any,next:any):Promise<any>{
      const result=await base.intercept(id,options,next);if(id===config.session_id)latest=null;return result;
    }
  };
}

export function apply(ctx:any):void {
  const path=process.env.SSS_TRACE_RSI_TASK_CONFIG;if(!path)throw Error('explicit_trace_task_config_required');
  const config=JSON.parse(readBoundedFile(path,64000).toString('utf8'));
  const library=JSON.parse(readBoundedFile(config.shadow_library,256000).toString('utf8'));
  const names=library.derived_library.tools.map((t:any)=>t.name);
  ctx.on('agent/created',({agent}:any)=>agent.ctx.tools.restrict(agent.session.id===config.session_id?{allow:names}:{deny:names}));
  const auditPath=join(config.work,'shadow.jsonl');
  const audit=(row:any)=>{
    if(existsSync(auditPath)&&(!lstatSync(auditPath).isFile()||lstatSync(auditPath).isSymbolicLink()))throw Error('invalid_state_shadow_audit');
    const fd=openSync(auditPath,constants.O_WRONLY|constants.O_APPEND|constants.O_CREAT|(constants.O_NOFOLLOW??0),0o600);
    try{writeFileSync(fd,JSON.stringify(row)+'\n');}finally{closeSync(fd);}
  };
  const interceptor=createStateShadowInterceptor({library,config,audit});
  attachMotifInterceptor(ctx,{task:{session_id:config.session_id},promptHash:config.prompt_sha256,interceptor,
    audit:(kind:string,reason:string)=>{if(kind==='motif_gate_deferred')interceptor.deferRequest(reason);else audit({kind,reason,session_id:config.session_id});}});
}
