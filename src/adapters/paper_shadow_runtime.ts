/** A frozen, local continuation matcher. It has no executor and alters no tools.
 * Inputs are trusted adapter observations, never instructions from web content.
 */
import { sha256 } from './paper_triage_validation.ts';
import { readFileSync } from 'node:fs';
import { validateJsonSchemaValue } from '@deepseek-ai/dsh-tools';
const librarySchema = JSON.parse(readFileSync(new URL('../../schemas/paper-shadow-library.schema.json',import.meta.url),'utf8'));

export function canonical(value: any): string {
  if (Array.isArray(value)) return '['+value.map(canonical).join(',')+']';
  if (value !== null && typeof value === 'object')
    return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';
  return JSON.stringify(value);
}
export const shadowDigest = (value: any): string => sha256(canonical(value));
const hash = (s: any) => typeof s === 'string' && /^[a-f0-9]{64}$/.test(s);
const same = (a: any,b: any) => canonical(a) === canonical(b);
const codePaths = ['src/adapters/paper_triage_validation.ts',
  'src/adapters/dsh_paper_delivery_check.ts', 'schemas/paper-citation-triage.schema.json'];

export function validateShadowLibrary(library: any): void {
  if (validateJsonSchemaValue(librarySchema,library).length)
    throw TypeError('Invalid paper shadow library schema');
  const {manifest_digest, ...body} = library ?? {};
  if (library?.schema_version !== 1 || library.scope !== 'artifact_continuation_shadow_probe' ||
      library.execution_policy !== 'shadow_only' || shadowDigest(body) !== manifest_digest ||
      !Array.isArray(library.motifs) || !library.source_traces || !library.tool_schema_sha256 ||
      codePaths.some(p=>!hash(library.validator_code_sha256?.[p])))
    throw TypeError('Invalid frozen paper shadow library');
  const ids = new Set();
  for (const motif of library.motifs) {
    const g = motif.graph;
    const expected = {anchor:{tool:g?.anchor?.tool,ownership:'model',result:'success',
      artifact_binding:'arguments.file_path'},continuation:{tool:'check_paper_triage',arguments:{},read_only:true},
      artifact_role:'registered_triage_report',artifact_relative_path:'triage.json',
      handoff:'after_check_or_any_guard_failure'};
    const witnesses = motif.training_witnesses;
    if (!['write','edit'].includes(g?.anchor?.tool) || !same(g,expected) ||
        motif.motif_id !== 'paper-shadow-'+shadowDigest(g).slice(0,12) || ids.has(motif.motif_id) ||
        motif.status !== 'shadow_candidate_not_execution_certified' ||
        !Array.isArray(witnesses) || !witnesses.length || witnesses.some((w: any)=>
          library.source_traces[w.run_id]?.session_id !== w.session_id ||
          library.source_traces[w.run_id]?.input_version !== w.input_version ||
          !hash(w.report_sha256) || !Number.isInteger(w.anchor_request) ||
          w.check_request !== w.anchor_request+1 ||
          !['passed','needs_repair'].includes(w.check_status)) ||
        new Set(witnesses.map((w: any)=>w.session_id)).size !== motif.training_session_count ||
        motif.support !== (motif.training_session_count >= 2 ? 'repeated_trace' : 'single_trace_candidate') ||
        !hash(library.tool_schema_sha256[g.anchor.tool]) || !hash(library.tool_schema_sha256.check_paper_triage))
      throw TypeError('Unbounded or unwitnessed shadow continuation');
    ids.add(motif.motif_id);
  }
}

export function registeredArtifact(value: any, work: string): boolean {
  if (typeof value !== 'string' || value.includes('\\') || value.includes('\0') ||
      value.split('/').includes('..')) return false;
  return value === 'triage.json' || value === work.replace(/\/$/,'')+'/triage.json' || value === './triage.json';
}

export function createPaperShadowMatcher(library: any, config: any) {
  validateShadowLibrary(library);
  if (!hash(config.source_version) || !config.session_id || typeof config.work !== 'string' ||
      !same(config.validator_code_sha256, library.validator_code_sha256) ||
      !same(config.tool_schema_sha256,library.tool_schema_sha256))
    throw TypeError('Shadow binding or validator/tool version drift');
  let bound = false;
  let pending: any = null;
  function binding(session: string, version: string, valid: boolean) {
    if (session !== config.session_id) return;
    pending = null;
    bound = valid === true && version === config.source_version;
  }
  function observe(exec: any, snapshot: any) {
    if (exec.session_id !== config.session_id) return;
    pending = null;
    if (!bound || config.source_unchanged !== true || exec.ok !== true || exec.aborted ||
        exec.request_tool_count !== 1 || !registeredArtifact(exec.arguments?.file_path,config.work) ||
        snapshot?.check !== 'paper_citation_triage_structure' || snapshot.source_version !== config.source_version ||
        !hash(snapshot.report_sha256) || snapshot.semantic_quality !== 'not_reviewed' ||
        !['passed','needs_repair'].includes(snapshot.status)) return;
    const motif = library.motifs.find((m: any)=>m.graph.anchor.tool === exec.name);
    if (!motif) return;
    if (exec.name === 'write' && (typeof exec.arguments.content !== 'string' ||
        sha256(exec.arguments.content) !== snapshot.report_sha256)) return;
    pending = {motif_id:motif.motif_id, training_session_count:motif.training_session_count,
      support:motif.support, anchor_call_id:exec.call_id,
      expected_tools:[{tool:'check_paper_triage',arguments:{}}], check:snapshot,
      prediction_basis:'preceding_successful_artifact_result_only',execution_authorized:false};
  }
  function takePrediction(): any {
    const prediction = pending; pending = null; return prediction;
  }
  return {binding, observe, takePrediction};
}

export function compareShadowResponse(prediction: any, content: any, actualCheck: any): any {
  if (!prediction) return {kind:'no_prediction',whole_request:false};
  const calls = content.filter((b: any)=>b.type === 'tool-call');
  let sameTools = calls.length === 1 && calls[0].name === 'check_paper_triage';
  try {
    const args = typeof calls[0]?.arguments === 'string' ? JSON.parse(calls[0].arguments) : calls[0]?.arguments;
    sameTools = sameTools && same(args,{});
  } catch { sameTools = false; }
  if (!sameTools) return {kind:'different_next_operation',whole_request:false};
  if (!actualCheck || !same(prediction.check,actualCheck))
    return {kind:'check_result_changed_or_missing',whole_request:false};
  if (content.some((b: any)=>b.type !== 'tool-call' && !(b.type === 'text' && !b.text?.trim())))
    return {kind:'matching_local_operation_text_requires_review',whole_request:false};
  return {kind:'strict_whole_request',whole_request:true};
}
