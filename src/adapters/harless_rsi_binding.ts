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

/** Bind a witnessed pin/read continuation to this Session's admitted uploads. */
export function bindApprovedUploadedReadTask(workspace:string,inputs:any[],request:any,manifest:any,sceneId:string){
  const pairs:Record<string,[string,string]>={
    'paper-proofreading':['mcp__paper_checks__pin_paper_sources','mcp__paper_checks__read_pinned_paper_sources'],
    'research-data-analysis':['mcp__data_analysis__pin_dataset','mcp__data_analysis__read_pinned_dataset_summary'],
  };
  const pair=pairs[sceneId];
  if(!pair || !inputs.length || inputs.length>(sceneId==='paper-proofreading'?16:8))
    throw Error('uploaded_rsi_requires_approved_sources');
  const citationEdge:[string,string,string]=[
    'mcp__paper_checks__pin_paper_citations','mcp__paper_checks__read_pinned_paper_citations','source_id'];
  const bibliographyEdge:[string,string,string]=[
    'mcp__paper_checks__collect_current_local_citation_evidence',
    'mcp__paper_checks__read_pinned_bibliography_first_page','source_id'];
  const documentEdge:[string,string,string]=[
    'mcp__paper_checks__pin_document','mcp__paper_checks__read_pinned_document','source_id'];
  const allowed=[{tools:pair,field:'source_id'},
    ...(sceneId==='paper-proofreading'?[{tools:citationEdge.slice(0,2),field:citationEdge[2]},
      {tools:bibliographyEdge.slice(0,2),field:bibliographyEdge[2]},
      {tools:documentEdge.slice(0,2),field:documentEdge[2]}]:[])];
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
     }) || (sceneId==='paper-proofreading' && seen.has(documentEdge.slice(0,2).join('|'))
        ? seen.size!==1 : !seen.has(pair.join('|'))) ||
     Object.keys(manifest.version_fields??{}).sort().join('|')!==
       [...new Set(manifest.artifacts.flatMap((a:any)=>a.tools))].sort().join('|') ||
     Object.values(manifest.version_fields??{}).some(value=>value!=='version_sha256'))
    throw Error('uploaded_rsi_binding_tools_unsupported');
  if(seen.has(documentEdge.slice(0,2).join('|')) && !paperDocumentFirstPageContracts(manifest))
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
  const intent=(request.content??[]).filter((row:any)=>row.type==='text').map((row:any)=>row.text).join('\n');
  return {schema_version:1,task_id:request.task_id,session_id:request.session_id,
    intent:bindingIntent(intent),
    input_version:sha(JSON.stringify(names.map(name=>[name,approved.files[name]]))),bindings:{},
    source_versions:{...(seen.has(pair.join('|'))?{[pair[0]]:'@observed',[pair[1]]:'@from_anchor'}:{}),
      ...(seen.has(documentEdge.slice(0,2).join('|'))?{
        [documentEdge[0]]:'@observed',
        [documentEdge[1]]:'@from_anchor',
      }:{}),
      ...(seen.has(citationEdge.slice(0,2).join('|'))?{
        [citationEdge[0]]:'@observed',
        [citationEdge[1]]:'@from_anchor',
      }:{}),
      ...(seen.has(bibliographyEdge.slice(0,2).join('|'))?{
        [bibliographyEdge[0]]:'@observed',
        [bibliographyEdge[1]]:'@from_anchor',
      }:{})}};
}

function paperDocumentFirstPageContracts(manifest:any,pair=['mcp__paper_checks__pin_document','mcp__paper_checks__read_pinned_document']):boolean{
  const pin=manifest?.contracts?.[pair[0]];
  const read=manifest?.contracts?.[pair[1]];
  return !!(pin?.read_only===true && pin.observed_anchor===true &&
    Array.isArray(pin.required_params) && pin.required_params.join(',')==='name,sha256' &&
    pin.default_params && typeof pin.default_params==='object' && !Array.isArray(pin.default_params) &&
    Object.keys(pin.default_params).length===0 &&
    read?.read_only===true && Array.isArray(read.required_params) &&
    read.required_params.join(',')==='source_id' &&
    read.default_params && typeof read.default_params==='object' && !Array.isArray(read.default_params) &&
    Object.keys(read.default_params).join(',')==='page' && read.default_params.page===1);
}

/** A closed permission check; the pin/read graph still comes from real traces. */
function closedUploadedFirstPage(row:any,manifest:any,pair:string[]):boolean{
  const [pin,read]=pair;
  if(!paperDocumentFirstPageContracts(manifest,pair) || !Array.isArray(manifest?.artifacts) ||
      manifest.artifacts.length!==1)return false;
  const artifact=manifest.artifacts[0],edge=artifact?.transfer_evidence;
  if(!artifact || typeof artifact!=='object' || Array.isArray(artifact))return false;
  const args=row?.arguments;
  return !!(row?.tool===read && row.version_relation==='same_source' &&
    Array.isArray(row.code_node_ids) && row.code_node_ids.length===0 && artifact.motif_id===row.motif_id &&
    Array.isArray(artifact.tools) && artifact.tools.join('|')===[pin,read].join('|') &&
    Array.isArray(artifact.code_nodes??[]) && (artifact.code_nodes??[]).length===0 && !artifact.code_dag &&
    Array.isArray(edge) && edge.length===1 && edge[0]?.from_tool===pin &&
    edge[0].to_tool===read && edge[0].from_field==='source_id' &&
    edge[0].to_param==='source_id' && (edge[0].version_relation??'same_source')==='same_source' &&
    args && typeof args==='object' && !Array.isArray(args) &&
    Object.keys(args).sort().join(',')==='page,source_id' && args.page===1 &&
    typeof args.source_id==='string' && /^source-[0-9a-f]{32}$/.test(args.source_id));
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
    const conversion = 'mcp__ppt_master__convert_source' in manifest.contracts;
    source_versions[tool]=contract.observed_anchor === true ? '@observed' :
      conversion ? [...new Set(inputs.map(row=>row.version_sha256))] : '@from_anchor';
  }
  return {schema_version:1,task_id:request.task_id,session_id:request.session_id,
    intent:bindingIntent(request.content.filter((p:any)=>p.type==='text').map((p:any)=>p.text).join('\n')),
    input_version:sha(JSON.stringify(inputs)),bindings:{},source_versions};
}

export const structuralOnlySimilarity=async():Promise<number[]>=>{throw Error('semantic_matching_disabled_by_certification');};

export const closedPaperDocumentFirstPage=(row:any,manifest:any)=>closedUploadedFirstPage(row,manifest,['mcp__paper_checks__pin_document','mcp__paper_checks__read_pinned_document']);
export const closedPptSourceFirstPage=(row:any,manifest:any)=>closedUploadedFirstPage(row,manifest,['mcp__ppt_master__pin_source','mcp__ppt_master__read_source_page']);

/** Permission boundary for two independently learned source-preparation edges.
 * Actual edges and bindings come from the compiler, never from this guard.
 */
export function closedPptConvertedSource(row:any,manifest:any):boolean{
  const pin='mcp__ppt_master__pin_source',convert='mcp__ppt_master__convert_source',read='mcp__ppt_master__read_converted_source';
  const pair=row?.tool===convert?[pin,convert,'source_id','source']:
    row?.tool===read?[convert,read,'converted_id','result']:null;
  if(!pair || row.version_relation!=='same_source' || !Array.isArray(row.code_node_ids) || row.code_node_ids.length)return false;
  const artifact=manifest?.artifacts?.find((a:any)=>a.motif_id===row.motif_id);
  const edge=artifact?.transfer_evidence, args=row.arguments;
  if(!artifact || artifact.tools?.join('|')!==pair.slice(0,2).join('|') ||
      (artifact.code_nodes??[]).length || artifact.code_dag || edge?.length!==1 ||
      edge[0].from_tool!==pair[0] || edge[0].to_tool!==pair[1] ||
      edge[0].from_field!==pair[2] || edge[0].to_param!==pair[2] ||
      (edge[0].version_relation??'same_source')!=='same_source')return false;
  const target=manifest.contracts?.[pair[1]], anchor=manifest.contracts?.[pair[0]];
  return !!(anchor?.read_only===true && target?.read_only===true &&
    (pair[0]!==pin || anchor.observed_anchor===true) &&
    target.required_params?.join(',')===pair[2] && target.default_params &&
    Object.keys(target.default_params).length===0 && args &&
    Object.keys(args).join(',')===pair[2] && typeof args[pair[2]]==='string' &&
    new RegExp('^'+pair[3]+'-[a-f0-9]{32}$').test(args[pair[2]]));
}
