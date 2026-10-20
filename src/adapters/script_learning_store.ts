/** Resolve one immutable, owner-bound generation; never switch a running task. */
import {readFileSync,realpathSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {digest} from '../motif_core/online_skill_runtime.mjs';

export function resolveScriptLearningSettings(settings:any,user:string){
 if(!settings.learningStore)return {settings,snapshot:null};
 const store=realpathSync(settings.learningStore),pointerPath=join(store,'latest.json');
 let raw:string;
 try{raw=readFileSync(pointerPath,'utf8');}catch(error:any){
  if(error.code==='ENOENT')return {settings,snapshot:{status:'cold_start',user}};
  throw error;
 }
 const pointer=JSON.parse(raw);
 if(pointer.user!==user)throw Error('foreign_script_library');
 function file(name:string,claimed:string,pattern:RegExp){
  if(typeof name!=='string'||!pattern.test(name)||typeof claimed!=='string')throw Error('invalid_learning_pointer');
  const path=resolve(store,name);
  if(realpathSync(path)!==path)throw Error('learning_library_symlink');
  const bytes=readFileSync(path),library=JSON.parse(bytes.toString('utf8')),{digest:actual,...body}=library;
  if(claimed!==actual||digest(body)!==claimed)throw Error('learning_pointer_digest_mismatch');
  return {path,digest:actual,sha256:createHash('sha256').update(bytes).digest('hex')};
 }
 const script=file(pointer.file,pointer.digest,/^round-[a-f0-9]+\/library\.json$/);
 const reuse=pointer.reuse_file?file(pointer.reuse_file,pointer.reuse_digest,/^round-[a-f0-9]+\/reuse-library\.json$/):null;
 if(reuse&&pointer.file.split('/')[0]!==pointer.reuse_file.split('/')[0])throw Error('mixed_learning_generations');
 return {settings:{...settings,library:script.path,...(reuse?{reuseLibrary:reuse.path}:{})},
  snapshot:{status:'loaded',user,pointer_sha256:createHash('sha256').update(raw).digest('hex'),script,reuse,
   triggered_by_task:pointer.triggered_by_task??null,parent_digest:pointer.parent_digest??null}};
}
