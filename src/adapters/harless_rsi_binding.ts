/** Bind a certified read-only PPT continuation to this task's approved bytes. */
import {createHash} from 'node:crypto';
import {lstatSync,readFileSync,realpathSync} from 'node:fs';
import {join,basename} from 'node:path';
const sha=(value:string|Uint8Array)=>createHash('sha256').update(value).digest('hex');

export function bindUploadedPptTask(workspace:string,inputs:any[],request:any,manifest:any){
  if(!inputs.length || inputs.length>8)throw Error('ppt_rsi_requires_approved_sources');
  const job=JSON.parse(readFileSync(join(workspace,'job.json'),'utf8'));
  if(job.job_id!==request.task_id || !Array.isArray(job.inputs) || job.inputs.length!==inputs.length)
    throw Error('ppt_rsi_job_scope_mismatch');
  const inputRoot=realpathSync(join(workspace,'inputs'));
  for(const row of inputs){
    if(typeof row.file!=='string' || basename(row.file)!==row.file || row.file.startsWith('.'))throw Error('ppt_rsi_source_scope_mismatch');
    const source=job.inputs.find((r:any)=>r.document_id===row.document_id);
    const path=join(inputRoot,row.file);
    if(!source || source.version_sha256!==row.version_sha256 || realpathSync(source.path)!==path ||
       lstatSync(path).isSymbolicLink() || realpathSync(path)!==path || !lstatSync(path).isFile() ||
       lstatSync(path).nlink!==1 || sha(readFileSync(path))!==row.version_sha256)throw Error('ppt_rsi_source_version_mismatch');
  }
  const versions=[...new Set(inputs.map(row=>row.version_sha256))].sort();
  const tools=Object.keys(manifest.version_fields);
  if(tools.some(tool=>!['mcp__ppt__pin_source','mcp__ppt__read_source'].includes(tool)) || tools.length!==2)
    throw Error('ppt_rsi_binding_tools_unsupported');
  return {schema_version:1,task_id:request.task_id,session_id:request.session_id,
    intent:job.instruction.slice(0,1000),input_version:sha(JSON.stringify(inputs)),bindings:{},
    source_versions:Object.fromEntries(tools.map(tool=>[tool,versions.length===1?versions[0]:versions]))};
}

export const structuralOnlySimilarity=async():Promise<number[]>=>{throw Error('semantic_matching_disabled_by_certification');};
