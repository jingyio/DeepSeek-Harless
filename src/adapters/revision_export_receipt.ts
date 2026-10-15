/** Engineering transport projection; the generated audit and full artifact stay
 * authoritative. Failed/unknown outputs remain complete for semantic recovery.
 */
import {digest} from './paper_rsi_program.ts';
export function revisionExportOutput(output:any,protocol?:string):any {
 if(protocol===undefined)return output;
 if(protocol!=='revision_receipt_v2')throw Error('unknown_export_result_protocol');
 const flags=['keys_match_query_items','existing_fields_preserved','top_level_preserved'];
 const errors=['arxiv_id_mismatches','extra','missing','changed_existing_records'];
 const counts=['before_count','after_count','before_duplicate_key_count','added_key_count','removed_key_count','after_duplicate_key_count'];
 const fields=[...flags,...errors,...counts,'issue_kinds'];
 const known=output&&typeof output==='object'&&!Array.isArray(output)&&
  Object.keys(output).length===fields.length&&fields.every(k=>Object.hasOwn(output,k))&&
  counts.every(k=>Number.isSafeInteger(output[k])&&output[k]>=0)&&
  Array.isArray(output.issue_kinds)&&output.issue_kinds.every((v:any)=>typeof v==='string');
 const passed=known&&flags.every(k=>output[k]===true)&&errors.every(k=>Array.isArray(output[k])&&output[k].length===0)&&output.after_duplicate_key_count===0;
 return passed?{structural_check_passed:true,audit_sha256:digest(output)}:output;
}
