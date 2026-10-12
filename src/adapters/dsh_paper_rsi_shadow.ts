/** Scope/guard + live pre-request Shadow for frozen, model-generated tools. */
import { readFileSync,appendFileSync } from 'node:fs';
import { join } from 'node:path';
import { attachMotifInterceptor } from './dsh_online_motif.mjs';
import { canonical,digest,validateFrozen } from './paper_rsi_program.ts';
import { observation } from '../motif_core/online_skill_runtime.mjs';
import { sourceUnchanged,readBoundedFile,sha256 } from './paper_triage_validation.ts';
export const name='sss-paper-rsi-shadow';
export const inject=['agents','llm'];
const P='mcp__paper_rsi__';
export function predictLearnedCheck(lib:any,recent:any[],tools:any[],config:any){
  const {manifest_digest,...body}=lib;
  if(manifest_digest!==digest(body)||lib.execution_policy!=='shadow_only'||lib.tool_digest!==config.tool_digest||
    canonical(lib.tools)!==canonical(tools.map((t:any)=>({name:t.name,parameters:t.parameters})))||!sourceUnchanged(config))return null;
  if(recent.length!==1||!recent[0].ok||recent[0].name!==P+'write_report'||recent[0].output?.source_version!==config.source_version||
    recent[0].output?.candidate_sha256!==config.candidate_sha256||recent[0].output?.report_sha256!==sha256(readBoundedFile(join(config.work,'triage.json'),192000)))return null;
  const recipe=lib.motifs.find((m:any)=>m.anchor===recent[0].name&&m.next===P+'check_report_structure'&&
    m.witnesses?.length>=2&&new Set(m.witnesses.map((w:any)=>w.session_id)).size>=2&&
    m.witnesses.every((w:any)=>typeof w.session_id==='string'&&/^[a-f0-9]{64}$/.test(w.events_sha256??'')));
  if(!recipe)return null;
  return {motif_id:recipe.motif_id,expected_tools:[{tool:recipe.next,arguments:{}}],report_sha256:recent[0].output.report_sha256,
    source_version:config.source_version,execution_authorized:false};
}
export function apply(ctx:any){
  const config=JSON.parse(readFileSync(process.env.SSS_PAPER_RSI_CONFIG!,'utf8'));
  const frozen=validateFrozen(JSON.parse(readFileSync(config.library_path,'utf8')));
  if(frozen.manifest_digest!==config.tool_digest)throw Error('frozen_tool_drift');
  const lib=config.shadow_library?JSON.parse(readFileSync(config.shadow_library,'utf8')):null;
  ctx.on('agent/created',({agent}:any)=>{
    if(agent.session.id===config.session_id)agent.ctx.tools.restrict({allow:['read_report','write_report','check_report_structure'].map(n=>P+n)});
  });
  if(!lib)return;
  let recent:any[]=[],ordinal=0;
  const audit=(row:any)=>appendFileSync(join(config.work,'shadow.jsonl'),JSON.stringify({session_id:config.session_id,...row})+'\n',{mode:0o600});
  attachMotifInterceptor(ctx,{task:{session_id:config.session_id},promptHash:config.prompt_sha256,
    audit:(kind:string,reason:string)=>audit({kind,reason}),interceptor:{
      observe(_:any,exec:any,result:any){recent.push({name:exec.name,ok:!result.isError&&!exec.signal?.aborted,output:observation(result,exec.name)});},
      async intercept(_:any,options:any,next:any){let prediction=null;try{prediction=predictLearnedCheck(lib,recent,options.tools??[],config);}catch{}
        audit({kind:prediction?'prediction':'deferred',request_ordinal:++ordinal,library_digest:lib.manifest_digest,prediction});recent=[];return next();}
    }});
}
