/** Versioned learned programs. The current model owns every selection/binding. */
import {createHash, randomUUID} from 'node:crypto';
import {readFileSync, lstatSync, realpathSync, readdirSync, existsSync, mkdirSync, mkdtempSync, writeFileSync, copyFileSync, renameSync} from 'node:fs';
import {join, resolve, relative, isAbsolute, extname, posix, basename, dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {commandArgv} from './geneloop_shell.ts';
import {digest} from '../motif_core/online_skill_runtime.mjs';

const root=fileURLToPath(new URL('../../',import.meta.url));
export const artifactLocks=['src/adapters/artifact_motif_runtime.ts','src/adapters/artifact_motif_shell.ts','src/adapters/artifact_motif_web.ts','src/adapters/artifact_motif_trace.ts','src/adapters/artifact_motif_compiler.py','src/adapters/geneloop_shell.ts','src/adapters/geneloop_skill_installation.mjs','src/adapters/geneloop_delegation.ts','src/adapters/harless_web_client/index.mjs','src/adapters/dsh_web_tasks.ts','package-lock.json','scripts/learn-artifact-motifs.py','scripts/certify-artifact-motifs.mjs','scripts/run-artifact-motif.mjs','scripts/artifact-motif-web.py'];
export const hash=(value:any)=>createHash('sha256').update(value).digest('hex');
const inside=(base:string,path:string)=>{const r=relative(base,path);return !r.startsWith('..')&&!isAbsolute(r);};
const contexts=new Map<string,any>();
export function identity(p:any){return Object.fromEntries(['version','source','inputs','dependencies','input_argument_indices','output_argument_index','argument_count','language','execution_policy'].map(k=>[k,p[k]]));}
export function loadArtifactLibrary(path:string){
 const library=JSON.parse(readFileSync(path,'utf8')), {digest:claimed,...body}=library;
 if(library.kind!=='witnessed_artifact_program_library'||library.version!==1||digest(body)!==claimed||!Array.isArray(library.programs)||library.programs.length>16)throw Error('invalid_artifact_library');
 if(artifactLocks.some(p=>library.code_locks?.[p]!==hash(readFileSync(join(root,p)))))throw Error('artifact_code_changed');
 for(const p of library.programs){
  if(p.id!=='artifact_'+digest(identity(p)).slice(0,24)||p.source_sha256!==hash(p.source)||p.execution_policy!=='fresh_output_network_disabled_v1'||
   p.certification?.passed!==true||p.certification.distinct_inputs<2||p.certification.source_equivalent!==true||p.certification.program_sha256!==digest(identity(p)))throw Error('uncertified_artifact_program');
  if(p.dependencies?.ppt_master_package_sha256&&p.dependencies.ppt_master_package_sha256!==JSON.parse(readFileSync(join(root,'scenarios/ppt_master/skill-lock.json'),'utf8')).package_sha256)throw Error('artifact_public_dependency_changed');
 }
 return library;
}
export function fixedArtifactInput(workspace:string,path:string){
 if(typeof path!=='string'||!path.startsWith('/work/')||posix.resolve(path)!==path||path.includes('\\'))throw Error('artifact_input_path_invalid');
 const rel=path.slice(6),host=resolve(workspace,rel.startsWith('inputs/')?rel:rel.startsWith('outputs/')?'outputs/code/'+rel.slice(8):'code/'+rel);
 if(!inside(workspace,host)||realpathSync(host)!==host||!lstatSync(host).isFile()||lstatSync(host).isSymbolicLink()||lstatSync(host).nlink!==1||lstatSync(host).size>16_000_000)throw Error('artifact_input_not_fixed');
 return {host,path,data:readFileSync(host)};
}
function shape(v:any,depth=0):any{
 if(v===null)return 'null';if(Array.isArray(v))return v.length&&depth<2?{array:shape(v[0],depth+1)}:'array';
 if(typeof v==='object')return depth<2?{object:Object.fromEntries(Object.keys(v).sort().map(k=>[k,shape(v[k],depth+1)]))}:'object';return typeof v;
}
export function matchesArtifactInput(contract:any,path:string,data:Buffer){
 if(extname(path).toLowerCase()!==contract.suffix)return false;
 try{
  const text=new TextDecoder('utf-8',{fatal:true}).decode(data).replace(/^\uFEFF/,'');
  if(contract.format==='json')return digest(shape(JSON.parse(text)))===digest(contract.shape);
  if(contract.format==='delimited'){
   // Header grammar only; quoted/multiline headers conservatively require fallback.
   const first=text.split(/\r?\n/,1)[0];if(first.includes('"'))return false;
   return digest(first.split(contract.suffix==='.tsv'?'\t':','))===digest(contract.header);
  }
  return contract.format==='text';
 }catch{return false;}
}
export function registerArtifactContext(session:string,context:any){if(context)contexts.set(session,context);else contexts.delete(session);}
export function artifactProgramPath(library:any,program:any){return '/work/.geneloop-motifs/'+library.digest.slice(0,16)+'/'+program.id+'.py';}
export function provideArtifactPrograms(context:any){
 const dir=join(context.workspace,'code','.geneloop-motifs',context.library.digest.slice(0,16));
 mkdirSync(dir,{recursive:true,mode:0o700});
 if(realpathSync(dir)!==resolve(dir)||!lstatSync(dir).isDirectory())throw Error('artifact_cache_directory_not_fixed');
 for(const p of context.library.programs){
  const file=join(dir,p.id+'.py');
  if(!existsSync(file))writeFileSync(file,p.source,{mode:0o400,flag:'wx'});
  if(realpathSync(file)!==resolve(file)||!lstatSync(file).isFile()||lstatSync(file).nlink!==1||hash(readFileSync(file))!==p.source_sha256)throw Error('artifact_cached_source_changed');
 }
 return context;
}
function commandWords(value:string){
 const words:string[]=[];let word='',quote='',active=false;
 for(let i=0;i<value.length;i++){
  const ch=value[i];
  if(quote){if(ch===quote){quote='';active=true;}else if(ch==='\\'&&quote==='"'&&['"','\\'].includes(value[i+1]))word+=value[++i];else if(ch==='$'||ch==='`'||/[\x00\r\n]/.test(ch))throw Error('artifact_command_expansion_rejected');else word+=ch;continue;}
  if(ch==='\''||ch==='"'){quote=ch;active=true;continue;}
  if(/\s/.test(ch)){if(active||word){words.push(word);word='';active=false;}continue;}
  if(/[;&|<>$`\x00\r\n]/.test(ch))throw Error('artifact_standalone_python_required');
  if(ch==='\\'){if(++i>=value.length)throw Error('artifact_command_quote_incomplete');word+=value[i];active=true;continue;}
  word+=ch;active=true;
 }
 if(quote)throw Error('artifact_command_quote_incomplete');if(active||word)words.push(word);return words;
}
export function artifactInvocation(session:string,command:string,workdir='/work'){
 const prefix=/^cd\s+(?:\/work|'\/work'|"\/work")\s*&&\s*/;
 let transport=command.trim();const cwd=prefix.test(transport)?'/work':posix.resolve('/work',workdir);
 transport=transport.replace(prefix,'');
 const native=transport.startsWith('python ')||transport.startsWith('python3 ');
 const nativeRecipe=native&&transport.includes('.geneloop-motifs/');
 if(!transport.startsWith('geneloop-recipe ')&&!nativeRecipe){
  if(/\bgeneloop-recipe\s/.test(command))throw Error('复用命令必须单独调用 geneloop-recipe JSON；仅支持 cd /work 前缀及保留完整回执的 tail，不能混入其它命令。');
  return null;
 }
 const c=contexts.get(session);if(!c)throw Error('artifact_context_not_admitted');
 let value:any;
 if(nativeRecipe){
  const plain=transport.replace(/(?:\s+2>&1)?\s*\|\s*tail\s+-(?:n\s+)?[1-9][0-9]{0,3}\s*$/,'').replace(/\s+2>&1\s*$/,'');
  const words=commandWords(plain),path=posix.resolve(cwd,words[1]),program=c.library.programs.find((p:any)=>artifactProgramPath(c.library,p)===path);
  if(!program||words.length!==program.argument_count+2)throw Error('artifact_native_interface_changed');
  const cache=fixedArtifactInput(c.workspace,path);if(hash(cache.data)!==program.source_sha256)throw Error('artifact_cached_source_changed');
  const args=words.slice(2).map((arg:string)=>posix.resolve(cwd,arg));value={id:program.id,inputs:program.input_argument_indices.map((i:number)=>args[i]),output:args[program.output_argument_index]};
 }else{
 // The executor emits exactly one JSON receipt line. A bounded tail therefore
 // preserves the entire receipt, including embedded stdout, without truncation.
 const parsed=/^geneloop-recipe\s+(?:'([^']*)'|(\{[\s\S]*\}))(?:\s+2>&1)?(?:\s*\|\s*tail\s+-(?:n\s+)?[1-9][0-9]{0,3})?\s*$/.exec(transport);
 if(!parsed)throw Error('复用参数必须是完整JSON；仅支持独立命令、cd /work &&、2>&1 及 tail -N，不支持额外写入或其它管道。');
 const raw=parsed[1]??parsed[2];
 value=JSON.parse(raw);
 }
 if(digest(Object.keys(value).sort())!==digest(['id','inputs','output'])||!Array.isArray(value.inputs))throw Error('artifact_explicit_binding_required');
 const program=c.library.programs.find((p:any)=>p.id===value.id);if(!program||value.inputs.length!==program.inputs.length)throw Error('artifact_program_or_arity_changed');
 if(c.allowOutput!==true)throw Error('artifact_output_not_authorized');
 const bound=value.inputs.map((p:string,i:number)=>{
  const b=fixedArtifactInput(c.workspace,p),version=hash(b.data);
  if(program.inputs[i].source_origin==='uploaded_input'&&!p.startsWith('/work/inputs/'))throw Error('artifact_input_origin_changed');
  if(!matchesArtifactInput(program.inputs[i],p,b.data))throw Error('artifact_input_contract_changed');
  if(program.certification.invariant_input_versions?.[i]&&program.certification.invariant_input_versions[i]!==version)throw Error('artifact_fixed_protocol_changed');
  return {...b,sha256:version};
 });
 if(new Set(bound.map((b:any)=>b.host)).size!==bound.length)throw Error('artifact_aliased_inputs');
 if(typeof value.output!=='string'||!/^\/work\/outputs\/[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}$/.test(value.output))throw Error('artifact_new_output_directory_required');
 const destination=join(c.workspace,'outputs/code',value.output.slice(14));
 if(existsSync(destination))throw Error('artifact_output_already_exists');
 c.audit({kind:'artifact_program_selected',program_id:program.id,library_digest:c.library.digest,input_versions:bound.map((b:any)=>b.sha256),model_owned_selection:true,entry:nativeRecipe?'native_python':'recipe_json'});
 return {...c,program,bound,output:value.output,destination,nonce:randomUUID()};
}

/** Execute solely in a fresh private sandbox. No original workspace writable. */
export function runArtifactProgram(job:any){
 const {program,bound}=job;
 for(const b of bound)if(hash(readFileSync(b.host))!==b.sha256||hash(b.data)!==b.sha256)throw Error('artifact_input_version_changed');
 const base=mkdtempSync(join(job.workspace,'command-tmp','artifact-'));
 const scratch=join(base,'code'),inputs=join(base,'inputs'),outputMount=join(base,'outputs'),temp=join(base,'tmp');
 for(const p of [scratch,inputs,outputMount,temp,join(scratch,'inputs'),join(scratch,'outputs')])mkdirSync(p,{recursive:true,mode:0o700});
 const argv=job.certificationArguments?.slice()??new Array(program.argument_count),snapshots:any[]=[],extraReadonly:any[]=[];
 function virtual(value:string){
  if(typeof value!=='string'||/[\x00\r\n\\]/.test(value))throw Error('artifact_snapshot_path_invalid');
  const p=posix.resolve('/work',value);if(!p.startsWith('/work/'))throw Error('artifact_snapshot_path_outside');return p;
 }
 for(let i=0;i<bound.length;i++){
  const argIndex=program.input_argument_indices[i],path=job.certificationArguments?virtual(argv[argIndex]):bound[i].path??('/work/inputs/'+basename(bound[i].host));
  const rel=virtual(path).slice(6),host=rel.startsWith('inputs/')?join(inputs,rel.slice(7)):rel.startsWith('outputs/')?join(outputMount,rel.slice(8)):join(scratch,rel);
  if(existsSync(host))throw Error('artifact_snapshot_path_collision');
  mkdirSync(dirname(host),{recursive:true,mode:0o700});writeFileSync(host,bound[i].data,{mode:0o400});
  if(!job.certificationArguments)argv[argIndex]=path;
  snapshots.push({host,sha256:hash(readFileSync(host))});
  if(rel.startsWith('outputs/'))extraReadonly.push({host,path:virtual(path)});
 }
 if(!job.certificationArguments)argv[program.output_argument_index]=job.output??'/work/outputs/artifact-result';
 const outputVirtual=virtual(argv[program.output_argument_index]);
 if(!outputVirtual.startsWith('/work/outputs/'))throw Error('artifact_output_must_be_fresh_child');
 const output=join(outputMount,outputVirtual.slice(14));
 if(existsSync(output)||snapshots.some(b=>inside(output,b.host)||inside(b.host,output)))throw Error('artifact_io_alias_rejected');
 const operator=join(scratch,'geneloop_cached_program.py');if(existsSync(operator))throw Error('artifact_operator_path_collision');writeFileSync(operator,program.source,{mode:0o400});
 const quote=(s:string)=>"'"+s.replaceAll("'","'\\''")+"'";
 const command=[process.env.SSS_PYTHON??'python3','-I','-B','/work/geneloop_cached_program.py',...argv].map(quote).join(' ');
 const layout={work:base,scratch,inputs,outputs:outputMount,temp};
 const native=commandArgv(layout,command,'/work',undefined,undefined,true,{...job.resources,network:'none'});
 // The only writable persistent mount is this fresh unpublished output root.
 const mount=native.findIndex((s,i)=>s==='--ro-bind'&&native[i+1]===outputMount&&native[i+2]==='/work/outputs');
 if(mount<0)throw Error('artifact_sandbox_mount_changed');native[mount]='--bind';
 if(extraReadonly.length){const point=native.indexOf('--chdir');if(point<0)throw Error('artifact_sandbox_layout_changed');native.splice(point,0,...extraReadonly.flatMap(b=>['--ro-bind',b.host,b.path]));}
 const result=spawnSync(native[0],native.slice(1),{encoding:'utf8',timeout:120000,maxBuffer:1_000_000});
 if(result.error||result.status!==0)throw Error('artifact_program_failed: '+String(result.stderr??'').slice(-1400));
 for(const b of bound)if(hash(readFileSync(b.host))!==b.sha256)throw Error('artifact_input_changed_during_execution');
 const files:any[]=[];let bytes=0;
 function visit(directory:string){
  for(const name of readdirSync(directory)){
   const host=join(directory,name),stat=lstatSync(host);
   if(stat.isSymbolicLink()||stat.nlink!==1&&stat.isFile())throw Error('artifact_link_output_rejected');
   if(stat.isDirectory()){if(relative(output,host).split('/').length>5)throw Error('artifact_output_depth');visit(host);continue;}
   if(!stat.isFile()||files.length>=128||stat.size>50_000_000||(bytes+=stat.size)>100_000_000)throw Error('artifact_output_protocol_bound');
   files.push({path:relative(output,host),bytes:stat.size,sha256:hash(readFileSync(host))});
  }
 }
 visit(output);if(!files.length)throw Error('artifact_output_missing');
 for(const b of snapshots)if(hash(readFileSync(b.host))!==b.sha256)throw Error('artifact_snapshot_changed');
 const receipt={kind:'artifact_program_receipt',program_id:program.id,nonce:job.nonce,input_versions:bound.map((b:any)=>b.sha256),
  output_directory:job.output,files,stdout:result.stdout,stderr:result.stderr,semantic_quality_accepted:false};
 if(job.certification)return {receipt,output};
 const exportedSource=join(output,'geneloop_reused_program.py');
 if(existsSync(exportedSource))throw Error('artifact_program_export_collision');
 writeFileSync(exportedSource,program.source,{mode:0o600,flag:'wx'});
 files.push({path:'geneloop_reused_program.py',bytes:Buffer.byteLength(program.source),sha256:hash(program.source)});
 Object.assign(receipt,{reusable_program:{path:job.output+'/geneloop_reused_program.py',source_sha256:hash(program.source),origin:'unchanged_model_authored_historical_program'}});
 if(existsSync(job.destination))throw Error('artifact_output_changed_before_publish');
 // Source inputs are revalidated before the atomic publication; old files are never overwritten.
 for(const b of bound)if(hash(readFileSync(b.host))!==b.sha256)throw Error('artifact_input_changed_before_publish');
 renameSync(output,job.destination);
 job.audit({kind:'artifact_program_verified',program_id:program.id,input_versions:receipt.input_versions,files,source_bytes:Buffer.byteLength(program.source),semantic_quality_accepted:false});
 return {receipt,output:job.destination};
}
