/** Bind a certified read-only PPT continuation to this task's approved bytes. */
import {createHash} from 'node:crypto';
import {lstatSync,readFileSync,realpathSync} from 'node:fs';
import {join,basename} from 'node:path';
const sha=(value:string|Uint8Array)=>createHash('sha256').update(value).digest('hex');

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
  if(tools.some(tool=>!['mcp__ppt__pin_source','mcp__ppt__read_source'].includes(tool)) || tools.length!==2)
    throw Error('ppt_rsi_binding_tools_unsupported');
  return {schema_version:1,task_id:request.task_id,session_id:request.session_id,
    intent:job.instruction.slice(0,1000),input_version:sha(JSON.stringify(inputs)),bindings:{},
    source_versions:Object.fromEntries(tools.map(tool=>[tool,versions.length===1?versions[0]:versions]))};
}

/** Bind a witnessed pin/read continuation to this Session's admitted uploads. */
export function bindApprovedUploadedReadTask(workspace:string,inputs:any[],request:any,manifest:any,sceneId:string){
  const pairs:Record<string,[string,string]>={
    'paper-proofreading':['mcp__paper_checks__pin_paper_sources','mcp__paper_checks__read_pinned_paper_sources'],
    'research-data-analysis':['mcp__data_analysis__pin_dataset','mcp__data_analysis__read_pinned_dataset_summary'],
  };
  const pair=pairs[sceneId];
  if(!pair || !inputs.length || inputs.length>8)throw Error('uploaded_rsi_requires_approved_sources');
  const citationEdge:[string,string,string]=[
    'mcp__paper_checks__pin_paper_citations','mcp__paper_checks__read_pinned_paper_citations','source_id'];
  const allowed=[{tools:pair,field:'source_id'},
    ...(sceneId==='paper-proofreading'?[{tools:citationEdge.slice(0,2),field:citationEdge[2]}]:[])];
  const seen=new Set<string>();
  if(!Array.isArray(manifest.artifacts) || !manifest.artifacts.length ||
     manifest.artifacts.some((row:any)=>{
       const key=row.tools?.join('|'),spec=allowed.find(a=>a.tools.join('|')===key);
       if(!spec || seen.has(key) || row.transfer_evidence?.length!==1 ||
          row.transfer_evidence[0].from_tool!==spec.tools[0] ||
          row.transfer_evidence[0].to_tool!==spec.tools[1] ||
          row.transfer_evidence[0].from_field!==spec.field ||
          row.transfer_evidence[0].to_param!==spec.field)return true;
       seen.add(key);return false;
     }) || !seen.has(pair.join('|')) ||
     Object.keys(manifest.version_fields??{}).sort().join('|')!==
       [...new Set(manifest.artifacts.flatMap((a:any)=>a.tools))].sort().join('|'))
    throw Error('uploaded_rsi_binding_tools_unsupported');
  const approved=JSON.parse(readFileSync(join(workspace,'approved-inputs.json'),'utf8'));
  if(!approved || typeof approved.files!=='object' ||
     Object.keys(approved.files).length!==inputs.length)throw Error('uploaded_rsi_approval_scope_mismatch');
  const root=realpathSync(join(workspace,'inputs'));
  for(const row of inputs){
    if(typeof row.file!=='string' || basename(row.file)!==row.file || row.file.startsWith('.') ||
       typeof row.version_sha256!=='string' || !/^[a-f0-9]{64}$/.test(row.version_sha256))
      throw Error('uploaded_rsi_source_scope_mismatch');
    const path=join(root,row.file),stat=lstatSync(path);
    if(stat.isSymbolicLink() || !stat.isFile() || stat.nlink!==1 || realpathSync(path)!==path ||
       approved.files[row.file]!==row.version_sha256 || sha(readFileSync(path))!==row.version_sha256)
      throw Error('uploaded_rsi_source_version_mismatch');
  }
  const names=Object.keys(approved.files).sort();
  if(names.join('|')!==inputs.map(row=>row.file).sort().join('|'))throw Error('uploaded_rsi_approval_scope_mismatch');
  const intent=(request.content??[]).filter((row:any)=>row.type==='text').map((row:any)=>row.text).join('\n').slice(0,1000);
  return {schema_version:1,task_id:request.task_id,session_id:request.session_id,
    intent:intent||'Read only this task’s approved source.',
    input_version:sha(JSON.stringify(names.map(name=>[name,approved.files[name]]))),bindings:{},
    source_versions:{[pair[0]]:'@observed',[pair[1]]:'@from_anchor',
      ...(seen.has(citationEdge.slice(0,2).join('|'))?{
        [citationEdge[0]]:'@observed',
        [citationEdge[1]]:'@from_anchor',
      }:{})}};
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
    intent:request.content.filter((p:any)=>p.type==='text').map((p:any)=>p.text).join('\n').slice(0,1000),
    input_version:sha(JSON.stringify(inputs)),bindings:{},source_versions};
}

export const structuralOnlySimilarity=async():Promise<number[]>=>{throw Error('semantic_matching_disabled_by_certification');};
