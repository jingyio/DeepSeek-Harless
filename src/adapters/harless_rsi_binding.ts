/** Bind a certified read-only PPT continuation to this task's approved bytes. */
import {createHash} from 'node:crypto';
import {lstatSync,readFileSync,realpathSync} from 'node:fs';
import {join,basename} from 'node:path';
const sha=(value:string|Uint8Array)=>createHash('sha256').update(value).digest('hex');
// Structural matching uses an informational intent label. The full user text
// stays in the DSH prompt/job; only this scalar must obey the runtime contract.
const bindingIntent=(value:string)=>value.replace(/[\x00-\x20]+/g,' ').trim().slice(0,500)||'Process the approved task sources';

export function bindUploadedPptTask(workspace:string,inputs:any[],request:any,manifest:any,sourceTaskId=request.task_id){
  if(!inputs.length || inputs.length>8)throw Error('ppt_rsi_requires_approved_sources');
  const job=JSON.parse(readFileSync(join(workspace,'job.json'),'utf8'));
  if(job.job_id!==sourceTaskId || !Array.isArray(job.inputs) || job.inputs.length!==inputs.length)
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
  const sources=['mcp__ppt__pin_source','mcp__ppt__read_source'];
  const deckPages=['mcp__ppt__pin_deck_pages','mcp__ppt__read_pinned_deck_pages'];
  if(tools.some(tool=>![...sources,...deckPages].includes(tool)) || !sources.every(tool=>tools.includes(tool)) ||
      (deckPages.some(tool=>tools.includes(tool))&&!deckPages.every(tool=>tools.includes(tool))))
    throw Error('ppt_rsi_binding_tools_unsupported');
  // The adapter/Python service hash the ordered source versions with Python's
  // JSON separator. Deck page pins additionally check the current file SHA.
  const deckVersion=sha(JSON.stringify(job.inputs.map((row:any)=>row.version_sha256)).replace(/,/g,', '));
  return {schema_version:1,task_id:request.task_id,session_id:request.session_id,
    intent:bindingIntent(job.instruction),input_version:sha(JSON.stringify(inputs)),bindings:{},
    source_versions:Object.fromEntries(tools.map(tool=>[tool,deckPages.includes(tool)?deckVersion:versions.length===1?versions[0]:versions]))};
}

/** A model must choose and pin the source; certified reuse may only dereference that same handle. */
export function bindUploadedSourceTask(workspace:string,inputs:any[],request:any,manifest:any){
  if (!inputs.length || inputs.length > 8) throw Error('rsi_requires_approved_sources');
  const root = realpathSync(join(workspace,'inputs'));
  const approved = JSON.parse(readFileSync(join(workspace,'approved-inputs.json'),'utf8')).files;
  for (const row of inputs) {
    if (typeof row.file !== 'string' || basename(row.file) !== row.file || row.file.startsWith('.')) throw Error('rsi_source_scope_mismatch');
    const path=join(root,row.file), stat=lstatSync(path);
    if (!stat.isFile() || stat.isSymbolicLink() || stat.nlink!==1 || realpathSync(path)!==path ||
        approved[row.file]!==row.version_sha256 || sha(readFileSync(path))!==row.version_sha256) throw Error('rsi_source_version_mismatch');
  }
  const source_versions:any={};
  for (const [tool,contract] of Object.entries(manifest.contracts) as any[]) {
    if (!manifest.version_fields[tool]) throw Error('rsi_unversioned_contract');
    source_versions[tool]=contract.observed_anchor === true ? '@observed' : '@from_anchor';
  }
  return {schema_version:1,task_id:request.task_id,session_id:request.session_id,
    intent:bindingIntent(request.content.filter((p:any)=>p.type==='text').map((p:any)=>p.text).join('\n')),
    input_version:sha(JSON.stringify(inputs)),bindings:{},source_versions};
}

export const structuralOnlySimilarity=async():Promise<number[]>=>{throw Error('semantic_matching_disabled_by_certification');};
