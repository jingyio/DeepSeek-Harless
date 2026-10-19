/** Use the existing upstream code runtime, isolated by the existing Docker adapter. */
import {readFileSync,writeFileSync,mkdirSync,lstatSync} from 'node:fs';
import {createHash,randomUUID} from 'node:crypto';
import {resolve,join,dirname} from 'node:path';
import {runContainer} from '../../src/adapters/dsh_code_container.ts';
const sha=(b:any)=>createHash('sha256').update(b).digest('hex');
let raw='';for await(const chunk of process.stdin)raw+=chunk;
const q=JSON.parse(raw),work=resolve(q.workspace),manifest=JSON.parse(readFileSync(join(work,'approved-inputs.json'),'utf8')).files;
const files:any[]=[];let outputBytes=0;
function source(name:string){
 if(typeof name!=='string'||!Object.hasOwn(manifest,name))throw Error('input not approved');
 const p=resolve(work,'inputs',name);if(!p.startsWith(join(work,'inputs')+'/')||lstatSync(p).isSymbolicLink()||lstatSync(p).nlink!==1)throw Error('unsafe input');
 const b=readFileSync(p);if(b.length>20*1024*1024||sha(b)!==manifest[name])throw Error('input changed');return b;
}
const runId=randomUUID();
const result=await runContainer({program:q.program,bindings:[{global:'inputs',functions:{
 list:async()=>({files:Object.entries(manifest).map(([name,sha256])=>({name,sha256}))}),
 read_text:async(a:any)=>({name:a.name,sha256:manifest[a.name],text:new TextDecoder('utf-8',{fatal:true}).decode(source(a.name))}),
 read_base64:async(a:any)=>({name:a.name,sha256:manifest[a.name],base64:source(a.name).toString('base64')})
}},{global:'outputs',functions:{write_text:async(a:any)=>{
 if(q.allow_output!==true)throw Error('this task is read-only');
 if(typeof a.name!=='string'||a.name.length>180||a.name.split('/').some((p:string)=>!p||p==='.'||p==='..')||/[\\\x00-\x1f]/.test(a.name)||typeof a.text!=='string')throw Error('invalid output');
 const b=Buffer.from(a.text);outputBytes+=b.length;if(outputBytes>2*1024*1024)throw Error('code output byte limit');
 const p=resolve(work,'outputs','code',runId,a.name),base=join(work,'outputs','code',runId);
 if(!p.startsWith(base+'/'))throw Error('output outside task');mkdirSync(dirname(p),{recursive:true,mode:0o700});
 writeFileSync(p,b,{flag:'wx',mode:0o600});const file={name:a.name,path:p,sha256:sha(b),bytes:b.length};files.push(file);return file;
}}}]},'node@sha256:9f6d5975c7dca860947d3915877f85607946403fc55349f39b4bc3688448bb6e');
process.stdout.write(JSON.stringify({runtime:'typescript/docker/upstream-worker',result,artifacts:files,
 input_sha256:manifest,program_sha256:sha(q.program),source_files_unchanged:Object.entries(manifest).every(([name,h])=>sha(source(name))===h)}));
