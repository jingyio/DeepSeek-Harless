/** Bounded private file evidence at native tool boundaries, never a public log. */
import {appendFileSync,mkdirSync,writeFileSync,readFileSync,readdirSync,lstatSync,realpathSync,existsSync} from 'node:fs';
import {join,relative,resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {digest} from '../motif_core/online_skill_runtime.mjs';
const sha=(x:any)=>createHash('sha256').update(x).digest('hex');
export function createReuseTrace(workspace:string,output:string){
 const directory=join(output,'reuse-evidence');mkdirSync(directory,{recursive:true,mode:0o700});
 const pending=new Map<string,any>();
 function snapshot(){
  const files:Record<string,any>={};let bytes=0,count=0,complete=true;
  function visit(path:string,depth=0){
   if(depth>5||count>=256){complete=false;return;}
   let rows;try{rows=readdirSync(path,{withFileTypes:true});}catch{return;}
   for(const row of rows){
    if(row.name.startsWith('.')||row.isSymbolicLink())continue;
    const child=join(path,row.name);
    if(row.isDirectory()){visit(child,depth+1);continue;}
    if(!row.isFile()||!/[.](?:py|json|tex|bib|bbl|md|txt|csv|tsv)$/.test(row.name))continue;
    const size=lstatSync(child).size;
    if(size>1000000||bytes+size>8000000||++count>256){complete=false;continue;}
    if(realpathSync(child)!==resolve(child)){complete=false;continue;}
    const data=readFileSync(child),hash=sha(data);bytes+=data.length;
    if(!existsSync(join(directory,hash)))writeFileSync(join(directory,hash),data,{mode:0o600,flag:'wx'});
    files[relative(workspace,child)]={sha256:hash,bytes:data.length};
   }
  }
  visit(join(workspace,'inputs'));visit(join(workspace,'code'));visit(join(workspace,'outputs/code'));
  return {files,complete,scope:'bounded_text_files_not_all_files',bytes};
 }
 function before(execution:any){
  try{pending.set(execution.callId,{tool:execution.name,arguments_sha256:digest(execution.arguments),before:snapshot()});}catch{}
 }
 function after(execution:any,result:any){
  const row=pending.get(execution.callId);pending.delete(execution.callId);if(!row)return;
  try{appendFileSync(join(output,'reuse-boundaries.jsonl'),JSON.stringify({...row,call_id:execution.callId,after:snapshot(),result_sha256:digest(result),is_error:result?.isError===true,at:new Date().toISOString()})+'\n',{mode:0o600});}catch{}
 }
 return {before,after};
}
