/** Offline real namespace replay; no LLM certification calls or fabricated traces. */
import {readFileSync,writeFileSync,readdirSync,lstatSync,realpathSync} from 'node:fs';
import {join,resolve,relative,extname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {artifactLocks,hash,identity,matchesArtifactInput,runArtifactProgram} from '../src/adapters/artifact_motif_runtime.ts';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';
const root=fileURLToPath(new URL('../',import.meta.url));
function candidates(workspace,contract){
 const found=[];
 function visit(path,depth=0){
  if(depth>5)return;
  for(const file of readdirSync(path,{withFileTypes:true})){
   if(file.name.startsWith('.')||file.isSymbolicLink())continue;
   const host=join(path,file.name);
   if(file.isDirectory()){visit(host,depth+1);continue;}
   if(!file.isFile()||lstatSync(host).size>16_000_000||realpathSync(host)!==host)continue;
   const data=readFileSync(host);if(matchesArtifactInput(contract,host,data))found.push({host,data,sha256:hash(data)});
  }
 }
 for(const dir of (contract.source_origin==='uploaded_input'?['inputs']:['code','outputs/code']))visit(join(workspace,dir));
 return found;
}
function originalFiles(path){
 const rows=[];
 function visit(p){for(const f of readdirSync(p,{withFileTypes:true})){
  const h=join(p,f.name);if(f.isSymbolicLink())throw Error('historical_output_link');
  if(f.isDirectory())visit(h);else if(f.isFile())rows.push({path:relative(path,h),bytes:lstatSync(h).size,sha256:hash(readFileSync(h))});
 }}visit(path);return rows.sort((a,b)=>a.path.localeCompare(b.path));
}
export function certifyArtifactRows(rows,resources={}){
 if(rows.length<2||new Set(rows.map(r=>r.task_id)).size!==rows.length||new Set(rows.map(r=>r.scene)).size!==1)throw Error('independent_same_scene_tasks_required');
 const [held,...training]=rows,programs=[],rejected=[],seen=new Set();
 for(const row of training)for(const p of row.candidates){
  if(seen.has(p.id))continue;
  try{
   const own=p.input_argument_indices.map((index,i)=>{
    const host=p.witness.input_paths[index],data=readFileSync(host),version=p.witness.input_sha256[index];
    if(realpathSync(host)!==host||hash(data)!==version||!matchesArtifactInput(p.inputs[i],host,data))throw Error('source_input_changed');
    return {host,data,sha256:version};
   });
   const other=p.inputs.map(contract=>{const matches=candidates(held.workspace,contract);if(matches.length!==1)throw Error('heldout_input_ambiguous_or_absent');return matches[0];});
   if(digest(own.map(b=>b.sha256))===digest(other.map(b=>b.sha256)))throw Error('distinct_input_required');
   const ownText=own.map(b=>b.data.toString('utf8')).join('\n'),otherText=other.map(b=>b.data.toString('utf8')).join('\n');
   // Conservative content-leak guard in addition to sandbox isolation. This is
   // not a semantic correctness proof; current model still owns suitability.
   for(const text of p.literal_selectors??[])if(ownText.includes(text)&&!otherText.includes(text))throw Error('task_specific_content_not_parameterized');
   const cases=[];let sourceFiles;
   for(const [role,task,bound] of [['source',row,own],['certification',held,other]]){
    const job={workspace:task.workspace,program:p,bound,resources,nonce:'certification',certification:true,
     ...(role==='source'?{certificationArguments:p.witness.invocation_arguments}:{})};
    const a=runArtifactProgram(job),b=runArtifactProgram(job);
    const signature=receipt=>digest({stdout:receipt.stdout,files:receipt.files.slice().sort((x,y)=>x.path.localeCompare(y.path))});
    if(signature(a.receipt)!==signature(b.receipt))throw Error('artifact_nondeterministic');
    if(role==='source'){
     sourceFiles=a.receipt.files.slice().sort((x,y)=>x.path.localeCompare(y.path));
     if(digest(sourceFiles)!==digest(originalFiles(p.witness.original_output)))throw Error('historical_output_not_reproduced');
    }
    cases.push({role,task_id:task.task_id,inputs:bound.map(b=>b.sha256),files:a.receipt.files,stdout_sha256:hash(a.receipt.stdout)});
   }
   if(digest(cases[0].files)===digest(cases[1].files))throw Error('input_dependency_not_demonstrated');
   const {witness,...program}=p;
   programs.push({...program,certification:{passed:true,distinct_inputs:2,source_equivalent:true,program_sha256:digest(identity(p)),
    source_task_id:row.task_id,source_call_id:witness.call_id,events_sha256:witness.events_sha256,boundary_sha256:witness.boundary_sha256,
    invariant_input_versions:Object.fromEntries(own.flatMap((b,i)=>b.sha256===other[i].sha256?[[i,b.sha256]]:[])),
    output_extensions:[...new Set(sourceFiles.map(f=>extname(f.path)))],cases,semantic_quality_accepted:false}});
   seen.add(p.id);
  }catch(error){rejected.push({program_id:p.id,call_id:p.witness.call_id,reason:error.message});}
 }
 const invariantApproved=Object.fromEntries(Object.entries(held.approved_inputs??{}).filter(([name,version])=>training.every(r=>r.approved_inputs?.[name]===version)));
 const body={version:1,kind:'witnessed_artifact_program_library',scene:held.scene,programs,invariant_approved_inputs:invariantApproved,code_locks:Object.fromEntries(artifactLocks.map(p=>[p,hash(readFileSync(join(root,p)))])),
  heldout_task_id:held.task_id,compilation_model_requests:0,scope:'native_program_source_equivalence_and_distinct_input_determinism_not_semantic_quality'};
 return {library:{...body,digest:digest(body)},report:{published:programs.length,rejected,quality_cost_promoted:false}};
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const result=certifyArtifactRows(JSON.parse(readFileSync(process.argv[2],'utf8')),process.env.GENELOOP_ARTIFACT_RESOURCES?JSON.parse(process.env.GENELOOP_ARTIFACT_RESOURCES):{});
 for(const [name,value] of Object.entries(result))writeFileSync(join(process.argv[3],name+'.json'),JSON.stringify(value,null,2)+'\n',{mode:0o600,flag:'wx'});
 console.log(JSON.stringify(result.report));
}
