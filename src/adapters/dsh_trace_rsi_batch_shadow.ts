/** Evidence-derived complete request batches. The provider and tools always run. */
import {closeSync,constants,existsSync,lstatSync,openSync,writeFileSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {BlockAssembler} from '@deepseek-ai/dsh-llm';
import {canonical,digest} from './paper_rsi_program.ts';
import {runTraceTool,validateTraceFrozen} from './trace_rsi_program.ts';
import {readBoundedFile,sha256} from './paper_triage_validation.ts';
import {validateTraceShadowLibrary} from './dsh_trace_rsi_shadow.ts';
import {attachMotifInterceptor} from './dsh_online_motif.mjs';
import {observation} from '../motif_core/online_skill_runtime.mjs';
import {projectTraceInputs} from '../../scenarios/paper-submission/trace-rsi-task-server.ts';
import {validateRevisionPlan,renderRevisionMarkdown} from './report_patch_protocol.ts';
import {revisionExportOutput} from './revision_export_receipt.ts';

export const name='sss-trace-rsi-batch-shadow';
export const inject=['agents','llm'];
const P='mcp__paper_trace_rsi__',root=fileURLToPath(new URL('../../',import.meta.url));
const receipts=['input_id','input_sha256','report_sha256','source_version','candidate_sha256','catalog_sha256'];
const additions=['src/adapters/trace_rsi_batch_compiler.py','src/adapters/dsh_trace_rsi_batch_shadow.ts','scripts/paper-rsi-batch-shadow.py'];
const witnessFields=['session_id','run_id','case_id','anchor_call_id','events_sha256','anchor_line','anchor_result_line',
  'anchor_request','next_request','anchor_text_blocks','next_text_blocks','anchor_message_sha256','next_message_sha256',
  'next_message_line','receipt','batch'];
const itemFields=['call_id','tool','call_line','result_line','arguments_sha256','result_sha256','receipt'];
const hash=(x:any)=>typeof x==='string'&&/^[a-f0-9]{64}$/.test(x);
const object=(x:any)=>x!==null&&typeof x==='object'&&!Array.isArray(x);
const same=(a:any,b:any)=>canonical(a)===canonical(b);
const rehash=(body:any)=>({...body,manifest_digest:digest(body)});
function exact(x:any,keys:string[],reason:string):void {
  if(!object(x)||Object.keys(x).length!==keys.length||keys.some(k=>!Object.hasOwn(x,k)))throw Error(reason);
}
function jsonData(value:any,limit=256000):void {
  const seen=new Set<any>();let nodes=0;
  function visit(x:any,depth:number):void {
    if(++nodes>20000||depth>48)throw Error('batch_json_too_complex');
    if(x===null||typeof x==='string'||typeof x==='boolean')return;
    if(typeof x==='number'&&Number.isFinite(x))return;
    if(typeof x!=='object'||seen.has(x))throw Error('batch_json_required');
    const array=Array.isArray(x),proto=Object.getPrototypeOf(x),keys=Reflect.ownKeys(x);
    if(array?(proto!==Array.prototype||x.length>2000||keys.length!==x.length+1):(proto!==Object.prototype&&proto!==null))throw Error('batch_plain_json_required');
    seen.add(x);
    for(const k of keys){
      if(typeof k!=='string'||['__proto__','prototype','constructor'].includes(k))throw Error('batch_unsafe_field');
      if(array&&k==='length')continue;
      if(array&&(!/^(0|[1-9][0-9]*)$/.test(k)||Number(k)>=x.length))throw Error('batch_dense_array_required');
      const d=Object.getOwnPropertyDescriptor(x,k)!;
      if(!d.enumerable||!Object.hasOwn(d,'value'))throw Error('batch_data_fields_required');
      visit(d.value,depth+1);
    }
    seen.delete(x);
  }
  visit(value,0);if(Buffer.byteLength(JSON.stringify(value))>limit)throw Error('batch_json_too_large');
}
function readJson(path:string,limit:number):any {
  return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(readBoundedFile(path,limit)));
}
function frozenTool(config:any):any {
  const bytes=readBoundedFile(config.library_path,192000),frozen=validateTraceFrozen(JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes)));
  if(frozen.manifest_digest!==config.tool_digest||frozen.candidate_sha256!==config.candidate_sha256)throw Error('batch_frozen_tool_drift');
  return {frozen,bytes_sha256:sha256(bytes)};
}
function validateReceipt(receipt:any,session:string,candidate:string):void {
  exact(receipt,receipts,'invalid_batch_receipt');const {input_id,...base}=receipt;
  if(receipts.slice(1).some(k=>!hash(receipt[k]))||base.candidate_sha256!==candidate||
    input_id!=='trace-input-'+digest({...base,session_id:session}))throw Error('unbound_batch_receipt');
}
function fingerprint(receipt:any):string {return digest(Object.fromEntries(receipts.slice(1).map(k=>[k,receipt[k]])));}

/** Integrity binds the declared evidence; it does not authenticate its author. */
export function validateBatchShadowLibrary(library:any,config:any):any {
  jsonData(library);jsonData(config,64000);
  const required=['schema_version','kind','execution_policy','tool_digest','candidate_sha256','tools',
    'code_files_sha256','code_additions_sha256','motifs','sources','manifest_digest'];
  const allowed=new Set([...required,'rejected','scope','limitations','export_result_protocol']);
  if(!object(library)||required.some(k=>!Object.hasOwn(library,k))||Object.keys(library).some(k=>!allowed.has(k)))throw Error('invalid_batch_library');
  const {manifest_digest,...body}=library;
  if(library.schema_version!==1||library.kind!=='trace_rsi_batch_continuation_shadow'||library.execution_policy!=='shadow_only'||
    !hash(manifest_digest)||digest(body)!==manifest_digest)throw Error('unbound_batch_library');
  const extra=library.code_additions_sha256;
  if(!object(extra)||Object.keys(extra).length!==additions.length||
    additions.some(suffix=>!Object.hasOwn(extra,resolve(root,suffix)))||
    Object.entries(extra).some(([p,h])=>!hash(h)||Object.hasOwn(library.code_files_sha256??{},p))||
    !same({...library.code_files_sha256,...extra},config.code_files))throw Error('batch_additions_only');
  // Reuse the public source, tool-schema and task-config validator. No synthetic
  // continuation is inserted: this adaptation has an empty Motif collection.
  if(library.export_result_protocol!==config.export_result_protocol||
    library.export_result_protocol!==undefined&&library.export_result_protocol!=='revision_receipt_v2')throw Error('batch_export_protocol_mismatch');
  const {code_additions_sha256,export_result_protocol,...compatible}=body;
  validateTraceShadowLibrary(rehash({...compatible,kind:'trace_rsi_continuation_shadow',
    code_files_sha256:config.code_files,motifs:[]}),config);
  const frozen=frozenTool(config).frozen,names=library.tools.map((t:any)=>t.name),check=P+frozen.candidate.name;
  if(!Array.isArray(library.motifs)||library.motifs.length>2000)throw Error('invalid_batch_motifs');
  const ids=new Set<string>();
  for(const motif of library.motifs){
    exact(motif,['motif_id','anchor','batch','witnesses','training_session_count','support','status'],'invalid_batch_motif');
    if(typeof motif.motif_id!=='string'||!/^trace-rsi-batch-[a-f0-9]{16}$/.test(motif.motif_id)||ids.has(motif.motif_id)||
      !names.includes(motif.anchor)||motif.status!=='shadow_candidate'||!Array.isArray(motif.batch)||motif.batch.length<1||motif.batch.length>64||
      !Array.isArray(motif.witnesses)||motif.witnesses.length<1||motif.witnesses.length>2000)throw Error('invalid_batch_motif');
    for(const node of motif.batch){
      if(node.result_kind==='candidate_output'){
        exact(node,['tool','arguments_binding','result_kind'],'invalid_batch_descriptor');
        if(node.tool!==check||!same(node.arguments_binding,{input_id:'/input_id'}))throw Error('invalid_batch_candidate_binding');
      }else if(node.result_kind==='private_artifact_output'){
        exact(node,['tool','arguments_binding','result_kind','effect'],'invalid_artifact_descriptor');
        if(node.tool!==P+'export_revision_report'||node.effect!=='private_current_report_export'||
          config.private_export_policy!=='current_task_revision_report_only'||
          !same(node.arguments_binding,{input_id:'/input_id'}))throw Error('bounded_private_artifact_contract_required');
      }else if(node.result_kind==='task_state'){
        exact(node,['tool','arguments','result_kind'],'invalid_batch_descriptor');
        const schema=library.tools.find((t:any)=>t.name===node.tool)?.parameters;
        if(!names.includes(node.tool)||node.tool===check||!same(node.arguments,{})||schema?.type!=='object'||
          !same(schema.properties,{})||!same(schema.required??[],[])||schema.additionalProperties!==false)throw Error('batch_readonly_contract_required');
      }else throw Error('unsupported_batch_result_contract');
    }
    if(motif.motif_id!=='trace-rsi-batch-'+digest({anchor:motif.anchor,batch:motif.batch}).slice(0,16))throw Error('batch_graph_identity_mismatch');
    const sessions=new Set<string>(),seen=new Set<string>();
    for(const witness of motif.witnesses){
      exact(witness,witnessFields,'invalid_batch_witness');
      const source=library.sources[witness.run_id],key=canonical([witness.session_id,witness.run_id,witness.anchor_call_id]);
      if(['session_id','run_id','case_id','anchor_call_id'].some(k=>typeof witness[k]!=='string'||!witness[k]||witness[k].length>1024)||
        ['events_sha256','anchor_message_sha256','next_message_sha256'].some(k=>!hash(witness[k]))||
        ['anchor_line','anchor_result_line','anchor_request','next_request','next_message_line'].some(k=>!Number.isInteger(witness[k])||witness[k]<1)||
        ['anchor_text_blocks','next_text_blocks'].some(k=>!Number.isInteger(witness[k])||witness[k]<0)||
        witness.next_request!==witness.anchor_request+1||!(witness.anchor_line<witness.anchor_result_line&&witness.anchor_result_line<witness.next_message_line)||
        !source||source.session_id!==witness.session_id||source.case_id!==witness.case_id||source.events_sha256!==witness.events_sha256||
        witness.next_request>Object.keys(source.requests).length||seen.has(key)||
        !Array.isArray(witness.batch)||witness.batch.length!==motif.batch.length)throw Error('unbound_batch_witness');
      validateReceipt(witness.receipt,witness.session_id,config.candidate_sha256);
      if(source.source_version!==witness.receipt.source_version||!Object.entries(source.source_files_sha256).some(([p,h])=>
        p.replace(/\\/g,'/').endsWith('/catalog.json')&&h===witness.receipt.catalog_sha256))throw Error('batch_source_receipt_mismatch');
      let last=witness.next_message_line;const callIds=new Set<string>([witness.anchor_call_id]);
      for(const [i,item]of witness.batch.entries()){
        const node=motif.batch[i];exact(item,node.result_kind==='candidate_output'?[...itemFields,'output_sha256']:itemFields,'invalid_batch_item');
        const args=node.result_kind==='task_state'?{}:{input_id:witness.receipt.input_id};
        if(typeof item.call_id!=='string'||!item.call_id||item.call_id.length>1024||callIds.has(item.call_id)||item.tool!==node.tool||
          !Number.isInteger(item.call_line)||item.call_line<=last||!Number.isInteger(item.result_line)||item.result_line<=item.call_line||
          !hash(item.result_sha256)||item.arguments_sha256!==digest(args)||
          node.result_kind==='candidate_output'&&!hash(item.output_sha256)||!same(item.receipt,witness.receipt))throw Error('unbound_batch_item');
        last=item.call_line;callIds.add(item.call_id);
      }
      seen.add(key);sessions.add(witness.session_id);
    }
    if(motif.training_session_count!==sessions.size||motif.support!==(sessions.size>=2?'repeated_sessions':'single_session_candidate'))throw Error('batch_independent_sessions_required');
    ids.add(motif.motif_id);
  }
  return library;
}

function currentState(config:any,toolBytes:string):any {
  function files():void {
    let total=0;
    for(const [path,expected]of Object.entries(config.source_files)){
      const bytes=readBoundedFile(path,50000000);total+=bytes.length;
      if(total>50000000||sha256(bytes)!==expected)throw Error('batch_source_drift');
    }
    for(const [path,expected]of Object.entries(config.code_files))if(sha256(readBoundedFile(path,2000000))!==expected)throw Error('batch_code_drift');
  }
  files();const tool=frozenTool(config);
  if(tool.bytes_sha256!==toolBytes)throw Error('batch_tool_file_drift');
  const reportPath=join(config.work,'triage.json');if(lstatSync(reportPath).nlink!==1)throw Error('batch_private_report_required');
  const catalogBytes=readBoundedFile(config.catalog_path,192000),reportBytes=readBoundedFile(reportPath,192000),decoder=new TextDecoder('utf-8',{fatal:true});
  const catalog=JSON.parse(decoder.decode(catalogBytes)),report=JSON.parse(decoder.decode(reportBytes));
  const input=projectTraceInputs(catalog,report,tool.frozen.provenance?.proposal?.input_bindings);
  const base={input_sha256:digest(input),report_sha256:sha256(reportBytes),source_version:config.source_version,
    candidate_sha256:config.candidate_sha256,catalog_sha256:sha256(catalogBytes)};
  const receipt={input_id:'trace-input-'+digest({...base,session_id:config.session_id}),...base};
  const output=runTraceTool(tool.frozen.candidate,input);
  files();if(sha256(readBoundedFile(reportPath,192000))!==base.report_sha256||sha256(readBoundedFile(config.catalog_path,192000))!==base.catalog_sha256||
    frozenTool(config).bytes_sha256!==toolBytes)throw Error('batch_snapshot_changed');
  let artifact:any=null;
  if(config.private_export_policy==='current_task_revision_report_only'){
    const markdown=renderRevisionMarkdown(input.before_report,report,output);
    artifact={...receipt,artifact_name:'revision-report.md',artifact_sha256:sha256(Buffer.from(markdown)),
      scope:'structural_revision_not_full_bibliography_verification',output:revisionExportOutput(output,config.export_result_protocol)};
  }
  return {receipt,input,report,artifact,check:{...receipt,output},read:{report,input,...receipt},fingerprint:fingerprint(receipt)};
}

/** Successful checks are remembered as a conservative engineering dedup guard.
 * This batch library does not claim that this condition was learned. */
export function createBatchShadowInterceptor({library,config,audit=()=>{}}:any):any {
  validateBatchShadowLibrary(library,config);const initial=digest(library),initialConfig=digest(config),toolBytes=frozenTool(config).bytes_sha256;
  const libraryBytes=config.shadow_library?sha256(readBoundedFile(config.shadow_library,256000)):null;
  const check=library.tools.find((t:any)=>t.name===P+frozenTool(config).frozen.candidate.name).name;
  const checked=new Set<string>();let exhausted=false,recent:any[]=[],pending:any=null,ordinal=0;
  const record=(row:any)=>audit({session_id:config.session_id,execution_authorized:false,
    library_digest:library.manifest_digest,state_guard_kind:'engineering_successful_check_dedup',...row});
  function stable():boolean {
    jsonData(library);jsonData(config,64000);
    return digest(library)===initial&&digest(config)===initialConfig&&(!config.shadow_library||sha256(readBoundedFile(config.shadow_library,256000))===libraryBytes);
  }
  function finish(reason?:string):void {
    if(!pending)return;
    const p=pending;pending=null;let snapshot=false;
    try{
      snapshot=stable()&&same(currentState(config,toolBytes).receipt,p.receipt);
      for(const expected of p.expected_results){
        if(expected.artifact_name!==undefined){
          const path=join(config.work,expected.artifact_name);
          if(expected.artifact_name!=='revision-report.md'||lstatSync(path).nlink!==1||
            sha256(readBoundedFile(path,512000))!==expected.artifact_sha256)snapshot=false;
        }
      }
    }catch{snapshot=false;}
    const declared=p.declarations;
    const declarationMatch=Array.isArray(declared)&&declared.length===p.expected_tools.length&&declared.every((d:any,i:number)=>
      d.name===p.expected_tools[i].tool&&same(d.arguments,p.expected_tools[i].arguments));
    const dispatchMatch=declarationMatch&&p.dispatch.length===declared.length&&p.dispatch.every((d:any,i:number)=>same(d,declared[i]));
    const itemMatches=p.expected_tools.map((tool:any,i:number)=>{
      const d=declared?.[i],observed=d?p.results.get(d.call_id):null;
      const argumentsMatch=Boolean(observed&&observed.name===tool.tool&&same(observed.arguments,tool.arguments));
      const outputMatch=Boolean(observed&&same(observed.output,p.expected_results[i]));
      return {call_id:d?.call_id??null,tool:tool.tool,arguments_match:argumentsMatch,output_match:outputMatch,
        verified:Boolean(observed?.ok&&argumentsMatch&&outputMatch)};
    });
    record({kind:'shadow_batch_result',request_ordinal:p.request_ordinal,motif_id:p.motif_id,
      verified:!reason&&!p.invalid&&snapshot&&declarationMatch&&dispatchMatch&&p.results.size===p.expected_tools.length&&itemMatches.every((m:any)=>m.verified),
      declaration_match:declarationMatch,dispatch_match:dispatchMatch,snapshot_match:snapshot,item_matches:itemMatches,
      ...(reason?{reason}:{}),...(p.message_sha256?{actual_message_sha256:p.message_sha256,actual_text_blocks:p.text_blocks}:{})});
  }
  const runtime={
    observeDispatch(id:string,exec:any):void {
      if(id!==config.session_id||!pending)return;
      try {
        const args=typeof exec.arguments==='string'?JSON.parse(exec.arguments):exec.arguments;jsonData(args,192000);
        if(pending.dispatch.length>=64)pending.invalid=true;
        else pending.dispatch.push({call_id:exec.callId,name:exec.name,arguments:args});
      }catch{pending.invalid=true;}
    },
    observe(id:string,exec:any,result:any):void {
      if(id!==config.session_id)return;
      let args:any,output:any,ok=false,state:any;
      try {
        args=typeof exec.arguments==='string'?JSON.parse(exec.arguments):exec.arguments;jsonData(args,192000);
        output=observation(result,exec.name);jsonData(output,256000);
        ok=Boolean(output)&&!result?.isError&&!result?.value?.isError&&!exec.signal?.aborted;
        if(ok&&exec.name===check){
          state=currentState(config,toolBytes);
          if(args?.input_id===state.receipt.input_id&&same(output,state.check)){
            if(checked.size>=2000&&!checked.has(state.fingerprint))exhausted=true;else checked.add(state.fingerprint);
          }
        }
      }catch{ok=false;}
      if(pending){
        if(typeof exec.callId!=='string'||pending.results.has(exec.callId)||pending.results.size>=64)pending.invalid=true;
        else pending.results.set(exec.callId,{name:exec.name,arguments:args,output,ok});
        if(pending.declarations&&pending.results.size>=pending.declarations.length)finish();
      }
      if(recent.length<65)recent.push({name:exec.name,arguments:args,output,ok,call_id:exec.callId});
    },
    deferRequest(reason:string):void {
      finish('request_gate_before_batch_completion');recent=[];
      record({kind:'deferred',request_ordinal:++ordinal,reason,prediction:null});
    },
    async intercept(id:string,options:any,next:any):Promise<any> {
      if(id!==config.session_id)return next();
      finish('next_request_before_batch_completion');
      const requestOrdinal=++ordinal;let predicted:any=null,reason='no_unique_current_batch';
      try {
        if(!stable())throw Error('batch_library_or_config_drift');
        if(!exhausted&&recent.length===1&&recent[0].ok&&same(library.tools,(options.tools??[]).map((t:any)=>({name:t.name,parameters:t.parameters})))){
          const state=currentState(config,toolBytes),row=recent[0],motifs=library.motifs.filter((m:any)=>m.anchor===row.name&&m.training_session_count>=2);
          const anchorMatches=receipts.every(k=>row.output?.[k]===state.receipt[k])&&
            (row.name===P+'read_task_state'?same(row.arguments,{})&&same(row.output,state.read):
              row.name===P+'write_report'?object(row.arguments)&&Object.keys(row.arguments).length===2&&
                hash(row.arguments.report_sha256)&&same(row.arguments.report,state.report)&&same(row.output,state.receipt):
                row.name===P+'apply_revision_plan'?object(row.arguments)&&same(Object.keys(row.arguments).sort(),['plan','report_sha256'])&&
                  Boolean(config.patch_library_path)&&hash(row.arguments.report_sha256)&&Boolean(validateRevisionPlan(row.arguments.plan))&&same(row.output,state.receipt):
                row.name===check?same(row.arguments,{input_id:state.receipt.input_id})&&same(row.output,state.check):false);
          if(motifs.length===1&&motifs[0].batch.some((n:any)=>n.result_kind==='candidate_output')&&checked.has(state.fingerprint))
            reason='prior_same_input_check_engineering_guard';
          else if(motifs.length===1&&anchorMatches){
            const motif=motifs[0];predicted={motif_id:motif.motif_id,training_session_count:motif.training_session_count,
              expected_tools:motif.batch.map((n:any)=>({tool:n.tool,arguments:n.result_kind==='task_state'?{}:{input_id:state.receipt.input_id}})),
              expected_results:motif.batch.map((n:any)=>n.result_kind==='candidate_output'?state.check:n.result_kind==='private_artifact_output'?state.artifact:state.read),execution_authorized:false};
            pending={...predicted,request_ordinal:requestOrdinal,receipt:state.receipt,dispatch:[],results:new Map(),declarations:null,invalid:false};
          }
        }
      }catch(error:any){reason=/^(batch_|invalid_|unbound_)/.test(error?.message??'')?error.message:'batch_snapshot_unavailable';}
      record({kind:predicted?'prediction':'deferred',request_ordinal:requestOrdinal,prediction:predicted,...(!predicted?{reason}:{})});
      recent=[];
      let stream:any;try{stream=await next();}catch(error){finish('provider_failed');throw error;}
      if(!predicted)return stream;
      const p=pending;
      if(!stream?.[Symbol.asyncIterator]){finish('model_declaration_unavailable');return stream;}
      // Public Harness assembler preserves the same block order as its native
      // Agent loop. Observation is bounded and never changes returned chunks.
      return (async function*(){
        const assembler=new BlockAssembler();let bytes=0,count=0,valid=true,completed=false;
        try {
          for await(const chunk of stream){
            if(valid){try{bytes+=Buffer.byteLength(JSON.stringify(chunk));if(++count>20000||bytes>2000000)valid=false;else assembler.push(chunk);}catch{valid=false;}}
            yield chunk;
          }
          completed=true;
          if(pending!==p)return;
          try {
            if(valid&&assembler.finish.kind==='tool-calls'){
              const blocks=assembler.blocks();jsonData(blocks,2000000);
              const calls=blocks.filter((b:any)=>b.type==='tool-call'),ids=new Set<string>();
              if(calls.length<1||calls.length>64)valid=false;
              p.declarations=calls.map((b:any)=>{
                if(typeof b.id!=='string'||!b.id||ids.has(b.id))valid=false;ids.add(b.id);
                const args=typeof b.arguments==='string'?JSON.parse(b.arguments):b.arguments;jsonData(args,192000);
                return {call_id:b.id,name:b.name,arguments:args};
              });
              p.message_sha256=digest(blocks);p.text_blocks=blocks.filter((b:any)=>b.type==='text'&&Boolean(b.text?.trim())).length;
            }else valid=false;
          }catch{valid=false;}
          if(!valid){p.invalid=true;finish('model_declaration_unavailable');}
          else if(p.results.size>=p.declarations.length)finish();
        }catch(error){if(pending===p)finish('provider_or_declaration_failed');throw error;}
        finally{if(!completed&&pending===p)finish('provider_stream_incomplete');}
      })();
    }
  };
  return runtime;
}

export function apply(ctx:any):void {
  const path=process.env.SSS_TRACE_RSI_TASK_CONFIG;if(!path)throw Error('explicit_trace_task_config_required');
  const config=readJson(path,64000),library=readJson(config.shadow_library,256000);validateBatchShadowLibrary(library,config);
  const names=library.tools.map((t:any)=>t.name),auditPath=join(config.work,'shadow.jsonl');
  const audit=(row:any)=>{
    if(existsSync(auditPath)&&(!lstatSync(auditPath).isFile()||lstatSync(auditPath).isSymbolicLink()||lstatSync(auditPath).nlink!==1))throw Error('invalid_batch_audit_file');
    const fd=openSync(auditPath,constants.O_WRONLY|constants.O_APPEND|constants.O_CREAT|(constants.O_NOFOLLOW??0),0o600);
    try{writeFileSync(fd,JSON.stringify(row)+'\n');}finally{closeSync(fd);}
  };
  const interceptor=createBatchShadowInterceptor({library,config,audit});
  ctx.on('agent/created',({agent}:any)=>{
    agent.ctx.tools.restrict(agent.session.id===config.session_id?{allow:names}:{deny:names});
    if(agent.session.id===config.session_id)agent.ctx.on('tools/pre-execute',(exec:any,next:any)=>{
      interceptor.observeDispatch(agent.session.id,exec);return next();
    });
  });
  attachMotifInterceptor(ctx,{task:{session_id:config.session_id},promptHash:config.prompt_sha256,interceptor,
    audit:(kind:string,reason:string)=>{if(kind==='motif_gate_deferred')interceptor.deferRequest(reason);else audit({kind,reason,session_id:config.session_id});}});
}
