/** No API and no execution: frozen predictions before each recorded response. */
import { readFileSync, writeFileSync, readdirSync, mkdirSync } from 'node:fs';
import { resolve, join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createPaperShadowMatcher, compareShadowResponse, shadowDigest } from '../src/adapters/paper_shadow_runtime.ts';
import { sha256 } from '../src/adapters/paper_triage_validation.ts';

const json = p=>JSON.parse(readFileSync(p,'utf8'));
const lines = p=>readFileSync(p,'utf8').split('\n').filter(s=>s.trim()).map(JSON.parse);
const argsOf = value=>typeof value === 'string' ? JSON.parse(value) : value;
const texts = block=>(block?.content??[]).filter(c=>c.type==='text').map(c=>c.text).join('\n');
function parsedCheck(block) {
  try { const v=JSON.parse(texts(block));return v?.check==='paper_citation_triage_structure'?v:null; }
  catch { return null; }
}

export function localOperation(call, result, parameterLibrary) {
  if (call.name==='mcp__paper_checks__collect_paper_citation_evidence')
    return {reuse:'engineered_composite_tool',gap:'four_internal_steps_not_yet_mined_as_local_nodes'};
  if (['write','edit'].includes(call.name))
    return {reuse:'read_only_check_after_model_owned_mutation',gap:'content_generation_and_repair_remain_semantic'};
  if (call.name==='check_paper_triage')
    return {reuse:'deterministic_structural_check',gap:'whole_request_requires_valid_preceding_prediction'};
  if (call.name==='web_fetch') {
    const url=call.arguments?.url??'',body=texts(result);
    const id=/^https:\/\/arxiv\.org\/abs\/(\d{4}\.\d{4,5}(?:v\d+)?)$/.exec(url)?.[1];
    const known=parameterLibrary?.motifs?.some(m=>m.prototype?.contract==='arxiv-page-fetch-v1');
    if (known && id && !result?.isError && body.startsWith('Fetched '+url+' (HTTP 200)') &&
        body.includes('arXiv:'+id) && /Title:\s*\S/.test(body) && /Authors:\s*\S/.test(body))
      return {reuse:'learned_parameter_contract_after_model_selection',gap:'selected_id_not_bound_before_this_request'};
    return {reuse:'uncompiled_query_or_failure',gap:url.startsWith('file:')?
      'invalid_local_read_attempt_requires_recovery':'no_typed_source_binding_or_certified_recovery_edge'};
  }
  return {reuse:'unknown',gap:'no_compiler_contract'};
}

export function auditPaperShadow(run, library, parameterLibrary=null) {
  const config=json(join(run,'manifest.json')),metrics=json(join(run,'metrics.json'));
  const checkConfig=json(join(run,'delivery-check-config.json'));
  if (config.mode!=='shadow'||config.delivery_check_mode!=='shadow'||!config.composite_evidence||
      metrics.status!=='completed'||!metrics.output_coverage_valid||!metrics.source_unchanged||
      !metrics.delivery_check_passed||checkConfig.session_id!==config.session_id||
      checkConfig.source_version!==config.input_version||Object.values(library.source_traces).some(
        s=>s.session_id===config.session_id)) throw Error('fresh-session completed shadow required');
  const receipts=readdirSync(join(run,'requests')).filter(n=>/^\d+\.json$/.test(n)).sort();
  let schemas=null;
  for(const name of receipts) {
    const row=json(join(run,'requests',name));
    const current=Object.fromEntries(row.tools.map(t=>[t.function.name,shadowDigest(t.function.parameters)]));
    if(schemas&&shadowDigest(current)!==shadowDigest(schemas))throw Error('evaluation tool schema drift');
    schemas=current;
  }
  const code=Object.fromEntries(Object.keys(library.validator_code_sha256).map(p=>[p,config.code_sha256[p]]));
  const matcher=createPaperShadowMatcher(library,{session_id:config.session_id,source_version:config.input_version,
    source_unchanged:metrics.source_unchanged,work:checkConfig.work,tool_schema_sha256:schemas,validator_code_sha256:code});
  const auditPath=join(run,'work/.local/paper-delivery-check.jsonl');
  const audit=lines(auditPath).filter(r=>r.session_id===config.session_id);
  const checks=new Map(audit.filter(r=>r.kind==='paper_delivery_check'&&r.mode==='shadow').map(r=>[r.call_id,
    Object.fromEntries(Object.entries(r).filter(([k])=>!['kind','mode','call_id','model_requests_skipped','session_id'].includes(k)))]));
  const bindings=new Map(audit.filter(r=>r.kind==='paper_evidence_bound').map(r=>[r.call_id,r.valid===true]));
  const events=lines(join(run,'session-events.jsonl')).filter(r=>r.session_id===config.session_id).map(r=>r.event);
  const calls=new Map(),declared=new Map(),rows=[];
  let active=null;
  for(const event of events) {
    const d=event.data??{};
    if(event.type==='assistant/message') {
      // Read the predictor first; neither the model response nor its later tools are inputs.
      const prediction=matcher.takePrediction();
      const content=d.message.content;
      active={ordinal:rows.length+1,prediction,content,operations:[],actual_check:null};rows.push(active);
      declared.clear();
      for(const b of content.filter(b=>b.type==='tool-call'))declared.set(b.id,{name:b.name,arguments:argsOf(b.arguments)});
    }else if(event.type==='tool/call') {
      const call={name:d.name,arguments:argsOf(d.arguments)};
      if(!active||calls.has(d.callId)||shadowDigest(declared.get(d.callId))!==shadowDigest(call))
        throw Error('model/tool identity mismatch');
      calls.set(d.callId,{...call,call_id:d.callId,request_tool_count:declared.size,row:active});
    }else if(event.type==='tool/result') {
      for(const block of d.message?.content??[]) {
        const call=calls.get(block.toolCallId);if(!call)continue;
        const ok=!d.error&&!block.isError;
        if(call.name==='mcp__paper_checks__collect_paper_citation_evidence') {
          let v=null;try{v=JSON.parse(texts(block));}catch{}
          matcher.binding(config.session_id,config.input_version,ok&&bindings.get(call.call_id)===true&&
            v?.case_id===checkConfig.case_id&&v?.version_sha256===config.input_version);
        }else matcher.observe({...call,session_id:config.session_id,ok},checks.get(call.call_id));
        if(call.name==='check_paper_triage'&&ok)call.row.actual_check=parsedCheck(block);
        call.row.operations.push({tool:call.name,call_id:call.call_id,ok,
          ...localOperation(call,block,parameterLibrary)});
      }
    }
  }
  if(rows.length!==receipts.length||rows.length!==metrics.actual_requests)throw Error('request count mismatch');
  const output=rows.map(r=>{
    const comparison=compareShadowResponse(r.prediction,r.content,r.actual_check);
    const hasText=r.content.some(b=>b.type==='text'&&b.text?.trim());
    const local=r.operations.some(o=>o.reuse!=='unknown'&&o.reuse!=='uncompiled_query_or_failure');
    return {ordinal:r.ordinal,prediction:r.prediction,comparison,text_present:hasText,operations:r.operations,
      category:comparison.whole_request?'whole_request_candidate':local?
        'local_reuse_with_model_selection_or_content':'semantic_or_uncompiled_recovery',
      text_review:hasText?'not_automatically_discardable':'no_text',
      actual_model_requests_skipped:0};
  });
  const strict=output.filter(r=>r.comparison.whole_request),predicted=output.filter(r=>r.prediction);
  return {run_id:run.split('/').at(-1),session_id:config.session_id,kind:'frozen_local_motif_shadow_replay',
    library_digest:library.manifest_digest,actual_requests:rows.length,actual_model_requests_skipped:0,
    whole_request_candidates:strict.length,whole_request_fraction:strict.length/rows.length,
    repeated_trace_whole_candidates:strict.filter(r=>r.prediction.support==='repeated_trace').length,
    single_trace_whole_candidates:strict.filter(r=>r.prediction.support==='single_trace_candidate').length,
    predictions:predicted.length,matching_local_operation_with_text:output.filter(
      r=>r.comparison.kind==='matching_local_operation_text_requires_review').length,
    prediction_mismatches:output.filter(r=>r.prediction&&r.comparison.kind==='different_next_operation').length,
    categories:Object.fromEntries(['whole_request_candidate','local_reuse_with_model_selection_or_content',
      'semantic_or_uncompiled_recovery'].map(k=>[k,output.filter(r=>r.category===k).length])),rows:output,
    source_hashes:{manifest:sha256(readFileSync(join(run,'manifest.json'))),events:sha256(readFileSync(join(run,'session-events.jsonl'))),
      audit:sha256(readFileSync(auditPath)),requests:Object.fromEntries(receipts.map(n=>[n,sha256(readFileSync(join(run,'requests',n)))]))},
    limitations:['retrospective held-out sessions previously inspected by developer, not prospective or blind',
      'same-paper drafts, no independent-paper quality claim','no tool execution or response changes',
      'read-only check equality only, bibliography semantics not reviewed']};
}

if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  const values={run:[]};
  for(let i=2;i<process.argv.length;i+=2) {
    const flag=process.argv[i],value=process.argv[i+1];
    if(!value||!['--run','--library','--parameter-library','--output'].includes(flag))throw Error('explicit input/output paths required');
    const k=flag.slice(2);if(k==='run')values.run.push(resolve(value));else values[k]=resolve(value);
  }
  const root=fileURLToPath(new URL('..',import.meta.url));
  if(!values.library||!values.output||!values.run.length||[...values.run,values.library,values.output,
    ...(values['parameter-library']?[values['parameter-library']]:[])].some(p=>!p.startsWith(join(root,'.local')+'/')))
    throw Error('private paths and at least one held-out run required');
  const library=json(values.library),parameter=values['parameter-library']?json(values['parameter-library']):null;
  if(parameter) {const {manifest_digest,...body}=parameter;if(shadowDigest(body)!==manifest_digest)throw Error('parameter library digest mismatch');}
  const results=values.run.map(run=>auditPaperShadow(run,library,parameter));
  const total=results.reduce((n,r)=>n+r.actual_requests,0),whole=results.reduce((n,r)=>n+r.whole_request_candidates,0);
  const result={kind:'frozen_paper_shadow_audit',library_digest:library.manifest_digest,
    library_file_sha256:sha256(readFileSync(values.library)),parameter_library_digest:parameter?.manifest_digest??null,
    actual_requests:total,whole_request_candidates:whole,whole_request_fraction:whole/total,
    new_model_requests:0,new_cost_usd:0,actual_model_requests_skipped:0,execution_authorized:false,results};
  mkdirSync(dirname(values.output),{recursive:true,mode:0o700});
  writeFileSync(values.output,JSON.stringify(result,null,2)+'\n',{mode:0o600,flag:'wx'});
  process.stdout.write(JSON.stringify({...result,results:results.map(({rows,source_hashes,...rest})=>rest)})+'\n');
}
