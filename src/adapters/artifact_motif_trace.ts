/** Exact private pre/post text and vector evidence; separate from old Script IR. */
import {appendFileSync,mkdirSync,writeFileSync,readFileSync,readdirSync,lstatSync,realpathSync,existsSync} from 'node:fs';
import {join,relative,resolve,sep} from 'node:path';
import {createHash} from 'node:crypto';
import {digest} from '../motif_core/online_skill_runtime.mjs';
const sha=(b:any)=>createHash('sha256').update(b).digest('hex');
export function createArtifactTrace(workspace:string,output:string){
 const directory=join(output,'reuse-evidence');mkdirSync(directory,{recursive:true,mode:0o700});
 const pending=new Map<string,any>();
 function snapshot(){
  const files:Record<string,any>={};let bytes=0,count=0,complete=true;
  function visit(path:string,depth=0){
   if(depth>6||count>=384){complete=false;return;}
   if(!existsSync(path))return;
   for(const row of readdirSync(path,{withFileTypes:true})){
    if(row.name.startsWith('.')||row.isSymbolicLink())continue;
    const child=join(path,row.name);
    if(row.isDirectory()){visit(child,depth+1);continue;}
    if(!row.isFile()||!/[.](?:py|json|tex|bib|bbl|md|txt|csv|tsv|svg)$/.test(row.name))continue;
    const stat=lstatSync(child);if(stat.size>1_000_000||bytes+stat.size>12_000_000||++count>384||realpathSync(child)!==resolve(child)){complete=false;continue;}
    const data=readFileSync(child),hash=sha(data);bytes+=data.length;
    if(!existsSync(join(directory,hash)))writeFileSync(join(directory,hash),data,{mode:0o600,flag:'wx'});
    files[relative(workspace,child).split(sep).join('/')]={sha256:hash,bytes:data.length};
   }
  }
  visit(join(workspace,'inputs'));visit(join(workspace,'code'));visit(join(workspace,'outputs/code'));
  return {files,complete,scope:'bounded_text_and_svg_files',bytes};
 }
 return {
  before(execution:any){try{pending.set(execution.callId,{tool:execution.name,arguments_sha256:digest(execution.arguments),before:snapshot()});}catch{}},
  after(execution:any,result:any){const row=pending.get(execution.callId);pending.delete(execution.callId);if(!row)return;
   try{appendFileSync(join(output,'reuse-boundaries.jsonl'),JSON.stringify({...row,call_id:execution.callId,after:snapshot(),result_sha256:digest(result),is_error:result?.isError===true,at:new Date().toISOString()})+'\n',{mode:0o600});}catch{}
  }
 };
}
