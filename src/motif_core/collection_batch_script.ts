/** Explicit handwritten baseline; no learned library, witnesses, or certification claim. */
import {digest} from './online_skill_runtime.mjs';
import {createGuardedCollectionExecutor} from './collection_read_policy.ts';
const prefix='mcp__file_management__';
export const scriptGraph={source_tool:prefix+'select_files',pin_tool:prefix+'pin_file',read_tool:prefix+'read_file',
 gather_tool:prefix+'collect_reads',selection:'actual_model_selected_members',array_field:'files',identity_field:'file_id',
 pin_param:'file_id',read_param:'source_id',gather_param:'source_ids',max_targets:32,max_batch:8,
 stop:'semantic_handoff_after_complete_gather'};
export function validateCollectionScript(s:any){
 const unsigned=Object.fromEntries(Object.entries(s??{}).filter(([k])=>k!=='script_digest'));
 const names=[scriptGraph.source_tool,scriptGraph.pin_tool,scriptGraph.read_tool,scriptGraph.gather_tool];
 if(s?.schema_version!==1||s.format!=='sss-collection-script-v1'||s.origin!=='handwritten_no_library'
  ||digest(unsigned)!==s.script_digest||digest(s.graph)!==digest(scriptGraph)||digest(s.tools)!==digest(names)
  ||! /^[a-f0-9]{64}$/.test(s.execution_version_sha256??'')||Object.keys(s.tool_schema_sha256??{}).length!==4
  ||names.some(n=>! /^[a-f0-9]{64}$/.test(s.tool_schema_sha256[n]??'')))throw new TypeError('invalid handwritten script configuration');
 return s;
}
export function createCollectionScriptController(script:any,task:any,audit:(r:any)=>void){
 validateCollectionScript(script);
 // Sharing the exact dispatch and guards controls scheduling differences; provenance is the experimental variable.
 const config={execution_version_sha256:script.execution_version_sha256,artifact:{graph:script.graph,
  tools:script.tools,tool_schema_sha256:script.tool_schema_sha256}};
 const record=(r:any)=>{const {policy_digest,certified_digest,...row}=r;
  audit({...row,kind:r.kind==='collection_model_request_bypassed_verified'?'collection_script_batch_verified':
    r.kind.replace('collection_motif_','collection_script_'),script_digest:script.script_digest});};
 return createGuardedCollectionExecutor(config,task,record);
}
