/** Trace-compiled local continuation prediction. No tool execution or LLM edits. */
import { closeSync, constants, existsSync, lstatSync, openSync, realpathSync, writeFileSync } from 'node:fs';
import { basename, isAbsolute, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { attachMotifInterceptor } from './dsh_online_motif.mjs';
import { canonical, digest } from './paper_rsi_program.ts';
import { runTraceTool, validateTraceFrozen } from './trace_rsi_program.ts';
import { readBoundedFile, sha256 } from './paper_triage_validation.ts';
import { observation } from '../motif_core/online_skill_runtime.mjs';
import { projectTraceInputs } from '../../scenarios/paper-submission/trace-rsi-task-server.ts';

export const name='sss-trace-rsi-shadow';
export const inject=['agents','llm'];
const P='mcp__paper_trace_rsi__';
const root=fileURLToPath(new URL('../../',import.meta.url));
const hash=(value:any)=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);
const object=(value:any)=>value!==null&&typeof value==='object'&&!Array.isArray(value);
const unsafe=new Set(['__proto__','prototype','constructor']);
const libraryFields=['schema_version','kind','execution_policy','tool_digest','candidate_sha256',
  'tools','code_files_sha256','motifs','manifest_digest'];
const motifFields=['motif_id','anchor','next','parameter_binding','witnesses','training_session_count','status'];
const witnessFields=['session_id','run_id','anchor_call_id','next_call_id','events_sha256'];
const witnessMetadata=['case_id','anchor_line','anchor_result_line','next_line','next_result_line',
  'anchor_request','next_request','anchor_text_blocks','next_text_blocks','receipt','output_sha256'];
const sourceFields=['run_id','session_id','case_id','source_version','source_files_sha256','prompt_sha256',
  'events_sha256','config_sha256','manifest_sha256','verification_sha256','requests'];
const receiptFields=['input_id','input_sha256','report_sha256','source_version','candidate_sha256','catalog_sha256'];
function exact(value:any,keys:string[],reason:string):void {
  if(!object(value)||Object.keys(value).length!==keys.length||keys.some(key=>!Object.hasOwn(value,key)))throw Error(reason);
}
function fields(value:any,required:string[],optional:string[],reason:string):void {
  const allowed=new Set([...required,...optional]);
  if(!object(value)||required.some(key=>!Object.hasOwn(value,key))||Object.keys(value).some(key=>!allowed.has(key)))throw Error(reason);
}
function hashMap(value:any,limit:number):boolean {
  return object(value)&&Object.keys(value).length>0&&Object.keys(value).length<=limit&&Object.values(value).every(hash);
}
function jsonData(value:any,limit=256000):void {
  let nodes=0;const ancestors=new Set<any>();
  function visit(value:any,depth:number):void {
    if(++nodes>20000||depth>48)throw Error('shadow_json_too_complex');
    if(value===null||typeof value==='string'||typeof value==='boolean')return;
    if(typeof value==='number'){if(!Number.isFinite(value))throw Error('shadow_non_json_number');return;}
    if(typeof value!=='object'||ancestors.has(value))throw Error('shadow_non_json_value');
    const array=Array.isArray(value),prototype=Object.getPrototypeOf(value),keys=Reflect.ownKeys(value);
    if(array?prototype!==Array.prototype||value.length>2000||keys.length!==value.length+1:
      prototype!==Object.prototype&&prototype!==null)throw Error('shadow_plain_json_required');
    ancestors.add(value);
    for(const key of keys){
      if(typeof key!=='string'||unsafe.has(key))throw Error('shadow_unsafe_field');
      if(array&&key==='length')continue;
      if(array&&(!/^(0|[1-9][0-9]*)$/.test(key)||Number(key)>=value.length))throw Error('shadow_dense_array_required');
      const d=Object.getOwnPropertyDescriptor(value,key)!;
      if(!d.enumerable||!Object.hasOwn(d,'value'))throw Error('shadow_json_data_property_required');
      visit(d.value,depth+1);
    }
    ancestors.delete(value);
  }
  visit(value,0);
  if(Buffer.byteLength(JSON.stringify(value))>limit)throw Error('shadow_json_too_large');
}
function readJson(path:string,limit:number):any {
  return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(readBoundedFile(path,limit)));
}
function frozenTool(config:any):any {
  const bytes=readBoundedFile(config.library_path,192000),frozen=validateTraceFrozen(JSON.parse(
    new TextDecoder('utf-8',{fatal:true}).decode(bytes)));
  if(frozen.manifest_digest!==config.tool_digest||frozen.candidate_sha256!==config.candidate_sha256)throw Error('frozen_trace_tool_drift');
  if(['read_task_state','write_report'].includes(frozen.candidate.name))throw Error('trace_shadow_tool_name_collision');
  return {frozen,bytes_sha256:sha256(bytes)};
}
function validateConfig(config:any):void {
  jsonData(config,64000);
  if(!object(config)||['work','session_id','library_path','catalog_path','case_id'].some(key=>
    typeof config[key]!=='string'||!config[key])||!isAbsolute(config.work)||
    ['tool_digest','candidate_sha256','source_version','prompt_sha256','catalog_sha256'].some(key=>!hash(config[key])))throw Error('invalid_trace_shadow_config');
  if(resolve(config.work)!==realpathSync(config.work)||!lstatSync(config.work).isDirectory())throw Error('trace_shadow_plain_work_required');
  if(!object(config.source_files)||!Object.keys(config.source_files).length||Object.keys(config.source_files).length>256||
    !object(config.code_files)||Object.keys(config.code_files).length>64||
    [config.source_files,config.code_files].some(map=>Object.entries(map).some(([path,value])=>
      !isAbsolute(path)||resolve(path)!==path||path===join(config.work,'triage.json')||!hash(value))))throw Error('invalid_trace_shadow_file_maps');
  for(const suffix of ['scenarios/paper-submission/trace-rsi-task-server.ts','src/adapters/trace_rsi_program.ts','src/adapters/paper_rsi_program.ts'])
    if(!Object.keys(config.code_files).some(path=>path.replace(/\\/g,'/').endsWith(suffix)))throw Error('trace_shadow_code_bindings_required');
  const catalog=resolve(config.catalog_path);
  if(basename(catalog)!=='catalog.json'||config.source_files[catalog]!==config.catalog_sha256)throw Error('trace_shadow_catalog_binding_required');
}
function filesCurrent(config:any):boolean {
  try {
    let bytes=0;
    for(const [path,expected]of Object.entries(config.source_files)){
      const data=readBoundedFile(isAbsolute(path)?path:resolve(config.work,path),50000000);bytes+=data.length;
      if(bytes>50000000||sha256(data)!==expected)return false;
    }
    for(const [path,expected]of Object.entries(config.code_files))
      if(sha256(readBoundedFile(isAbsolute(path)?path:resolve(root,path),2000000))!==expected)return false;
    return true;
  }catch{return false;}
}
function toolNames(frozen:any,config:any=null):string[] {
  if(config?.patch_library_path){
    if(!isAbsolute(config.patch_library_path)||!hash(config.patch_library_sha256)||
      config.code_files[config.patch_library_path]!==config.patch_library_sha256)throw Error('unbound_compact_tool_library');
    return [P+'read_task_state',P+(config.write_protocol==='full_report'?'write_report':'apply_revision_plan'),P+frozen.candidate.name,P+'export_revision_report'];
  }
  return [P+'read_task_state',P+'write_report',P+frozen.candidate.name];
}

/** Digest checks bind declared evidence; they are not signatures or proof of quality. */
export function validateTraceShadowLibrary(library:any,config:any,frozen:any=null):any {
  jsonData(library);fields(library,libraryFields,['sources','rejected','scope','limitations'],'invalid_trace_shadow_library');validateConfig(config);
  frozen??=frozenTool(config).frozen;
  validateTraceFrozen(frozen);
  if(frozen.manifest_digest!==config.tool_digest||frozen.candidate_sha256!==config.candidate_sha256)throw Error('frozen_trace_tool_drift');
  const {manifest_digest,...body}=library;
  const names=toolNames(frozen,config);
  if(library.schema_version!==1||library.kind!=='trace_rsi_continuation_shadow'||library.execution_policy!=='shadow_only'||
    !hash(manifest_digest)||manifest_digest!==digest(body)||library.tool_digest!==config.tool_digest||
    library.candidate_sha256!==config.candidate_sha256||canonical(library.code_files_sha256)!==canonical(config.code_files)||
    !Array.isArray(library.tools)||library.tools.length!==names.length||!Array.isArray(library.motifs)||library.motifs.length>2000)throw Error('unbound_trace_shadow_library');
  const recordedNames=new Set<string>();
  for(const tool of library.tools){
    exact(tool,['name','parameters'],'invalid_trace_shadow_tool');
    // Harness may sort MCP tools before exposing them to the provider. Preserve
    // that observed order in the library and compare it exactly at prediction.
    if(!names.includes(tool.name)||recordedNames.has(tool.name)||!object(tool.parameters))throw Error('invalid_trace_shadow_tool_order');
    recordedNames.add(tool.name);
  }
  if(Object.hasOwn(library,'scope')&&(typeof library.scope!=='string'||!library.scope||library.scope.length>256))throw Error('invalid_trace_shadow_scope');
  if(Object.hasOwn(library,'limitations')&&(!Array.isArray(library.limitations)||library.limitations.length>32||
    library.limitations.some((value:any)=>typeof value!=='string'||value.length>800)))throw Error('invalid_trace_shadow_limitations');
  if(Object.hasOwn(library,'rejected')&&(!object(library.rejected)||Object.keys(library.rejected).length>2000||
    Object.values(library.rejected).some((value:any)=>!Number.isInteger(value)||value<0)))throw Error('invalid_trace_shadow_rejections');
  if(Object.hasOwn(library,'sources')){
    if(!object(library.sources)||Object.keys(library.sources).length<1||Object.keys(library.sources).length>256)throw Error('invalid_trace_shadow_sources');
    const sourceSessions=new Set<string>();
    for(const [id,source]of Object.entries(library.sources) as [string,any][]){
      exact(source,sourceFields,'invalid_trace_shadow_source');
      if(source.run_id!==id||['run_id','session_id','case_id'].some(key=>typeof source[key]!=='string'||!source[key]||source[key].length>1024)||
        ['source_version','prompt_sha256','events_sha256','config_sha256','manifest_sha256','verification_sha256'].some(key=>!hash(source[key]))||
        !hashMap(source.source_files_sha256,256)||!hashMap(source.requests,2000)||
        Object.keys(source.requests).some(key=>!/^\d+\.json$/.test(key))||sourceSessions.has(source.session_id))throw Error('invalid_trace_shadow_source');
      sourceSessions.add(source.session_id);
    }
  }
  const ids=new Set<string>();
  for(const motif of library.motifs){
    fields(motif,motifFields,['support'],'invalid_trace_shadow_motif');
    if(typeof motif.motif_id!=='string'||!/^[a-zA-Z0-9_-]{1,128}$/.test(motif.motif_id)||ids.has(motif.motif_id)||
      !names.slice(0,2).includes(motif.anchor)||motif.next!==names[2]||motif.status!=='shadow_candidate'||
      canonical(motif.parameter_binding)!==canonical({input_id:'/input_id'})||!Array.isArray(motif.witnesses)||
      motif.witnesses.length<1||motif.witnesses.length>2000)throw Error('invalid_trace_shadow_motif');
    const sessions=new Set<string>(),witnesses=new Set<string>();
    for(const witness of motif.witnesses){
      fields(witness,witnessFields,witnessMetadata,'invalid_trace_shadow_witness');
      if(!hash(witness.events_sha256)||witnessFields.slice(0,4).some(key=>typeof witness[key]!=='string'||
        !witness[key]||witness[key].length>1024)||witness.anchor_call_id===witness.next_call_id)throw Error('invalid_trace_shadow_witness');
      const key=canonical([witness.run_id,witness.session_id,witness.anchor_call_id,witness.next_call_id]);
      if(witnesses.has(key))throw Error('duplicate_trace_shadow_witness');witnesses.add(key);sessions.add(witness.session_id);
      const extended=witnessMetadata.some(field=>Object.hasOwn(witness,field));
      if(extended){
        if(witnessMetadata.some(field=>!Object.hasOwn(witness,field))||typeof witness.case_id!=='string'||!witness.case_id||witness.case_id.length>1024||
          !hash(witness.output_sha256)||['anchor_line','anchor_result_line','next_line','next_result_line','anchor_request','next_request'].some(field=>
            !Number.isInteger(witness[field])||witness[field]<1)||['anchor_text_blocks','next_text_blocks'].some(field=>
            !Number.isInteger(witness[field])||witness[field]<0)||!(witness.anchor_line<witness.anchor_result_line&&
            witness.anchor_result_line<witness.next_line&&witness.next_line<witness.next_result_line)||
          witness.next_request!==witness.anchor_request+1)throw Error('invalid_trace_shadow_request_witness');
        exact(witness.receipt,receiptFields,'invalid_trace_shadow_receipt_witness');
        const {input_id,...base}=witness.receipt;
        if(receiptFields.slice(1).some(field=>!hash(witness.receipt[field]))||base.candidate_sha256!==config.candidate_sha256||
          input_id!=='trace-input-'+digest({...base,session_id:witness.session_id}))throw Error('invalid_trace_shadow_receipt_witness');
      }
      if(library.sources){
        const source=library.sources[witness.run_id];
        if(!extended||!source||source.session_id!==witness.session_id||source.events_sha256!==witness.events_sha256||
          source.case_id!==witness.case_id||source.source_version!==witness.receipt.source_version||
          !Object.entries(source.source_files_sha256).some(([path,sha])=>path.replace(/\\/g,'/').endsWith('/catalog.json')&&sha===witness.receipt.catalog_sha256))
          throw Error('unbound_trace_shadow_source_witness');
      }
    }
    if(motif.training_session_count!==sessions.size||Object.hasOwn(motif,'support')&&
      motif.support!==(sessions.size>=2?'repeated_sessions':'single_session_candidate'))throw Error('independent_trace_shadow_sessions_required');
    ids.add(motif.motif_id);
  }
  return library;
}

function currentState(config:any,expectedToolBytes?:string):any {
  if(!filesCurrent(config))throw Error('trace_shadow_source_or_code_drift');
  const {frozen,bytes_sha256}=frozenTool(config);
  if(expectedToolBytes&&bytes_sha256!==expectedToolBytes)throw Error('trace_shadow_tool_file_drift');
  const catalogBytes=readBoundedFile(config.catalog_path,192000),reportBytes=readBoundedFile(join(config.work,'triage.json'),192000);
  if(lstatSync(join(config.work,'triage.json')).nlink!==1)throw Error('trace_shadow_private_report_required');
  const decoder=new TextDecoder('utf-8',{fatal:true}),catalog=JSON.parse(decoder.decode(catalogBytes)),report=JSON.parse(decoder.decode(reportBytes));
  const input=projectTraceInputs(catalog,report,frozen.provenance?.proposal?.input_bindings);
  const base={input_sha256:digest(input),report_sha256:sha256(reportBytes),source_version:config.source_version,
    candidate_sha256:frozen.candidate_sha256,catalog_sha256:sha256(catalogBytes)};
  const receipt={input_id:'trace-input-'+digest({...base,session_id:config.session_id}),...base};
  const output=runTraceTool(frozen.candidate,input);
  if(!filesCurrent(config)||sha256(readBoundedFile(join(config.work,'triage.json'),192000))!==base.report_sha256||
    sha256(readBoundedFile(config.catalog_path,192000))!==base.catalog_sha256||frozenTool(config).bytes_sha256!==bytes_sha256)
    throw Error('trace_shadow_snapshot_changed');
  return {frozen,report,input,receipt,expected_result:{...receipt,output}};
}
function prediction(library:any,recent:any[],tools:any[],config:any,expectedToolBytes?:string):any {
  if(!Array.isArray(recent)||recent.length!==1||recent[0]?.ok!==true||!object(recent[0]?.output)||
    ![P+'read_task_state',P+'write_report'].includes(recent[0].name)||!Array.isArray(tools))return null;
  const state=currentState(config,expectedToolBytes);validateTraceShadowLibrary(library,config,state.frozen);
  if(canonical(library.tools)!==canonical(tools.map(tool=>({name:tool.name,parameters:tool.parameters}))))return null;
  const row=recent[0],motifs=library.motifs.filter((motif:any)=>motif.anchor===row.name&&motif.training_session_count>=2);
  if(motifs.length!==1||receiptFields.some(key=>row.output[key]!==state.receipt[key])||
    !/^trace-input-[a-f0-9]{64}$/.test(row.output.input_id))return null;
  if(row.name===P+'read_task_state'&&(canonical(row.output.report)!==canonical(state.report)||canonical(row.output.input)!==canonical(state.input)))return null;
  return {motif_id:motifs[0].motif_id,training_session_count:motifs[0].training_session_count,
    expected_tools:[{tool:motifs[0].next,arguments:{input_id:state.receipt.input_id}}],
    expected_result:state.expected_result,execution_authorized:false};
}
export function predictTraceCheck(library:any,recent:any[],tools:any[],config:any):any {
  try {validateConfig(config);return prediction(library,recent,tools,config);}catch{return null;}
}

/** One prediction per observed result window. Every intercept forwards next(). */
export function createTraceShadowInterceptor({library=null,config,audit=()=>{}}:any):any {
  validateConfig(config);const initialTool=frozenTool(config);
  if(library)validateTraceShadowLibrary(library,config,initialTool.frozen);
  const initialLibrary=library?digest(library):null;
  const initialConfig=digest(config);
  const shadowBytes=config.shadow_library?sha256(readBoundedFile(config.shadow_library,256000)):null;
  let recent:any[]=[],ordinal=0,pending:any=null;
  function libraryCurrent():boolean {
    if(!library||digest(config)!==initialConfig)return false;
    if(digest(library)!==initialLibrary)return false;
    return !config.shadow_library||sha256(readBoundedFile(config.shadow_library,256000))===shadowBytes;
  }
  const record=(row:any)=>audit({session_id:config.session_id,execution_authorized:false,...row});
  return {
    observe(id:string,exec:any,result:any):void {
      if(id!==config.session_id)return;
      const output=observation(result,exec.name),ok=Boolean(output)&&!result?.isError&&!result?.value?.isError&&!exec.signal?.aborted;
      if(pending){
        let verified=false;
        try {
          const args=typeof exec.arguments==='string'?JSON.parse(exec.arguments):exec.arguments;
          verified=ok&&exec.name===pending.expected_tools[0].tool&&canonical(args)===canonical(pending.expected_tools[0].arguments)&&
            libraryCurrent()&&canonical(output)===canonical(pending.expected_result)&&
            canonical(currentState(config,initialTool.bytes_sha256).expected_result)===canonical(pending.expected_result);
        }catch{}
        record({kind:'shadow_result',request_ordinal:pending.request_ordinal,motif_id:pending.motif_id,
          call_id:exec.callId??null,verified});pending=null;
      }
      if(recent.length<3)recent.push({name:exec.name,ok,output});
    },
    deferRequest(reason:string):void {
      record({kind:'deferred',request_ordinal:++ordinal,reason,library_digest:library?.manifest_digest??null,prediction:null});recent=[];pending=null;
    },
    async intercept(id:string,options:any,next:any):Promise<any> {
      if(id!==config.session_id)return next();
      let predicted=null,reason='library_unavailable_or_changed';
      try {
        if(libraryCurrent()){
          predicted=prediction(library,recent,options.tools??[],config,initialTool.bytes_sha256);
          reason='no_unique_current_guarded_edge';
        }
      }catch(error:any){reason=/^(trace_|invalid_|unbound_|frozen_|independent_)/.test(error?.message??'')?error.message:'snapshot_unreadable_or_invalid';}
      const requestOrdinal=++ordinal;
      record({kind:predicted?'prediction':'deferred',request_ordinal:requestOrdinal,
        library_digest:library?.manifest_digest??null,prediction:predicted,...(!predicted?{reason}:{})});
      pending=predicted?{...predicted,request_ordinal:requestOrdinal}:null;recent=[];
      return next();
    }
  };
}

export function apply(ctx:any):void {
  const path=process.env.SSS_TRACE_RSI_TASK_CONFIG;
  if(!path)throw Error('explicit_trace_task_config_required');
  const config=readJson(path,32000);validateConfig(config);const frozen=frozenTool(config).frozen,names=toolNames(frozen,config);
  ctx.on('agent/created',({agent}:any)=>{
    agent.ctx.tools.restrict(agent.session.id===config.session_id?{allow:names}:{deny:names});
  });
  const library=config.shadow_library?readJson(config.shadow_library,256000):null;
  const auditPath=join(config.work,'shadow.jsonl');
  const audit=(row:any)=>{
    if(existsSync(auditPath)&&(!lstatSync(auditPath).isFile()||lstatSync(auditPath).isSymbolicLink()))throw Error('invalid_trace_shadow_audit_file');
    const fd=openSync(auditPath,constants.O_WRONLY|constants.O_APPEND|constants.O_CREAT|(constants.O_NOFOLLOW??0),0o600);
    try {writeFileSync(fd,JSON.stringify(row)+'\n');}finally{closeSync(fd);}
  };
  const interceptor=createTraceShadowInterceptor({library,config,audit});
  attachMotifInterceptor(ctx,{task:{session_id:config.session_id},promptHash:config.prompt_sha256,interceptor,
    audit:(kind:string,reason:string)=>{
      if(kind==='motif_gate_deferred')interceptor.deferRequest(reason);
      else audit({kind,reason,session_id:config.session_id});
    }});
}
