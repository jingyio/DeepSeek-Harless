/** Live observer: records the frozen prediction BEFORE calling the real LLM.
 * No synthetic stream, executor, result injection, or response text removal.
 */
import { readFileSync, appendFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { attachMotifInterceptor } from './dsh_online_motif.mjs';
import { observation } from '../motif_core/online_skill_runtime.mjs';
import { canonical, shadowDigest, registeredArtifact } from './paper_shadow_runtime.ts';
import { sourceUnchanged,readBoundedFile,sha256 } from './paper_triage_validation.ts';
export const name='sss-paper-flow-shadow';
export const inject=['llm','agents'];
const P='mcp__paper_checks__';
const allowed=new Map([[P+'pin_paper_citations','case_id'],[P+'read_pinned_paper_citations','source_id'],
 [P+'read_pinned_citation_records','citation_id'],[P+'fetch_pinned_cited_preprint_metadata','citation_id'],
 [P+'fetch_pinned_formal_reference_metadata','citation_id'],[P+'recover_pinned_formal_reference_queries','citation_id'],['check_paper_triage',null],['read_current_triage',null]]);
const same=(a:any,b:any)=>canonical(a)===canonical(b);

export function validateFlowLibrary(lib:any) {
 const {manifest_digest,...body}=lib;
 if(lib.schema_version!==1||lib.scope!=='source_bound_readonly_batch_shadow'||lib.execution_policy!=='shadow_only'||shadowDigest(body)!==manifest_digest||!lib.motifs?.length)throw Error('invalid frozen flow library');
 for(const m of lib.motifs){
  if(m.motif_id!=='paper-flow-'+shadowDigest(m.graph).slice(0,12)||!m.training_witnesses?.length||
   m.training_session_count!==new Set(m.training_witnesses.map((w:any)=>w.session_id)).size||
   m.training_witnesses.some((w:any)=>lib.source_traces[w.run_id]?.session_id!==w.session_id)||
   !['task_start','success','failed','needs_repair'].includes(m.graph.anchor_result)||
   !Array.isArray(m.graph.anchor)||!m.graph.nodes?.length)throw Error('unwitnessed flow recipe');
  for(const n of m.graph.nodes){
   const param=allowed.get(n.tool);
   if(!allowed.has(n.tool)||!same(Object.keys(n.bindings),param?[param]:[]))throw Error('unbounded tool/binding');
   if(param){const b=n.bindings[param];if(b.task_field!==undefined){if(n.tool!==P+'pin_paper_citations'||b.task_field!=='case_id'||m.graph.anchor_result!=='task_start')throw Error('unbounded task binding');}
    else if(!b.source_fields?.length||b.source_fields.some((f:any)=>!m.graph.anchor.includes(f.tool)||f.field!==param))throw Error('unwitnessed field flow');}
  }
 }
}

export function predictFlow(lib:any,config:any,recent:any[],tools:any[],started:boolean,snapshot:any=null,completed:Map<string,any>|null=null):any {
 const schemas=Object.fromEntries(tools.map((t:any)=>[t.name,shadowDigest(t.parameters)]));
 if(!same(schemas,lib.tool_schema_sha256)||!same(tools.map((t:any)=>t.name),lib.tool_order)||!sourceUnchanged(config))return {reason:'tool_or_source_drift'};
 const names=recent.map(r=>r.name).sort();const candidates=[];
 for(const m of lib.motifs){const g=m.graph;
  if(!same(names,g.anchor)||new Set(names).size!==names.length)continue;
  if(g.anchor_result==='task_start'){if(started||recent.length)continue;}
  else if(g.artifact){
   if(g.anchor_result==='needs_repair'){
    if(recent.length!==1||recent[0].name!=='check_paper_triage'||!recent[0].ok||recent[0].aborted||
     recent[0].output?.status!=='needs_repair'||recent[0].output?.source_version!==config.source_version||
     recent[0].output?.report_sha256!==snapshot?.report_sha256)continue;
   }else if(recent.length!==1||!registeredArtifact(recent[0].arguments?.file_path,config.work)||recent[0].aborted||recent[0].ok!==(g.anchor_result==='success'))continue;
   if(snapshot?.source_version!==config.source_version||snapshot?.call_id!==recent[0].call_id||!snapshot.report_sha256)continue;
   if(g.anchor_result==='success'&&snapshot.check!=='paper_citation_triage_structure')continue;
   if(g.anchor_result==='failed'&&snapshot.kind!=='paper_recovery_snapshot')continue;
  }else if(recent.some(r=>!r.ok||r.aborted||r.output?.version_sha256!==config.source_version))continue;
  const proposed=[];let invalid=false;
  for(const n of g.nodes){const args:any={};for(const [p,b0] of Object.entries(n.bindings)){const b:any=b0;
    if(b.task_field)args[p]=config.case_id;
    else {const values=b.source_fields.map((f:any)=>recent.find(r=>r.name===f.tool)?.output?.[f.field]);
      if(!values.length||values.some((v:any)=>typeof v!=='string'||v!==values[0]||!/^source-[a-f0-9]{32}$/.test(v))){invalid=true;break;}args[p]=values[0];}}
   proposed.push({tool:n.tool,arguments:args});}
  const frontier=completed ? proposed.filter(p=>!completed.has(canonical(p))) : proposed;
  if(!invalid&&frontier.length)candidates.push({motif_id:m.motif_id,training_session_count:m.training_session_count,expected_tools:frontier});
 }
 if(candidates.length!==1)return {reason:candidates.length?'ambiguous_local_branches':'no_learned_guarded_edge',candidates:candidates.map(c=>c.motif_id)};
 return {...candidates[0],execution_authorized:false,source_version:config.source_version,
  prediction_basis:'current_task_and_preceding_tool_results',snapshot_sha256:snapshot?.report_sha256??null,
  snapshot_status:snapshot?.status??null};
}

export function apply(ctx:any){
 const config=JSON.parse(readFileSync(process.env.SSS_PAPER_FLOW_SHADOW_CONFIG!,'utf8'));
 const lib=JSON.parse(readFileSync(config.library_path,'utf8'));validateFlowLibrary(lib);
 for(const [path,hash] of Object.entries(lib.code_sha256))if(awaitHash(join(config.project_root,path))!==hash)throw Error('flow code epoch changed');
 mkdirSync(join(config.work,'.local'),{recursive:true,mode:0o700});
 let recent:any[]=[],started=false,ordinal=0;
 const completed=config.track_completed_frontier===true?new Map<string,any>():null;
 const audit=(r:any)=>appendFileSync(join(config.work,'.local/flow-shadow.jsonl'),JSON.stringify({session_id:config.session_id,...r})+'\n',{mode:0o600});
 const interceptor={observe(id:string,exec:any,result:any){if(id===config.session_id){
  const output=observation(result,exec.name);
  recent.push({name:exec.name,arguments:exec.arguments,call_id:exec.callId,ok:!result.isError,aborted:exec.signal?.aborted===true,output});
  if(exec.name===P+'pin_paper_citations')completed?.clear();
  completed?.delete(canonical({tool:exec.name,arguments:exec.arguments}));
  if(completed&&allowed.has(exec.name)&&exec.name.startsWith(P)&&!result.isError&&!exec.signal?.aborted&&output?.version_sha256===config.source_version)
   completed.set(canonical({tool:exec.name,arguments:exec.arguments}),output);
 }},
  async intercept(_id:string,options:any,next:any){
   let snapshot=null;try {const rows=readFileSync(join(config.work,'.local/paper-delivery-check.jsonl'),'utf8').split('\n').filter(Boolean).map(l=>JSON.parse(l));snapshot=rows.findLast((r:any)=>r.session_id===config.session_id&&recent.some(x=>x.call_id===r.call_id)&&['paper_delivery_check','paper_recovery_snapshot'].includes(r.kind));}catch{}
   if(recent.length===1&&recent[0].name==='check_paper_triage'&&recent[0].output?.status==='needs_repair'){
    try {snapshot={kind:'paper_repair_read_guard',call_id:recent[0].call_id,source_version:config.source_version,
     report_sha256:sha256(readBoundedFile(join(config.work,'triage.json')))};}catch{snapshot=null;}
   }
   const prediction=predictFlow(lib,config,recent,options.tools??[],started,snapshot,completed);
   audit({kind:prediction.motif_id?'flow_shadow_prediction':'flow_shadow_deferred',request_ordinal:++ordinal,library_digest:lib.manifest_digest,...prediction});
   recent=[];started=true;return next();}};
 attachMotifInterceptor(ctx,{task:{session_id:config.session_id},promptHash:config.prompt_sha256,interceptor,audit:(kind:string,reason:string)=>audit({kind,reason})});
}
import { createHash } from 'node:crypto';
const awaitHash=(path:string)=>createHash('sha256').update(readFileSync(path)).digest('hex');
