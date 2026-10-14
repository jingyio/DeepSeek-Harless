/** Deployment adapter: native Harness PTC worker runs in a no-network container. */
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { randomUUID } from 'node:crypto';
import { CodeRuntime } from '@deepseek-ai/dsh-code-runtime';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const runner = resolve(root,'src/adapters/dsh_code_container_runner.mjs');
const defaultImage = 'node:22.22.2-bookworm-slim';
export function runContainer(request: any, image = defaultImage): Promise<any> {
  if (!/^node@sha256:[a-f0-9]{64}$/.test(image) && image !== defaultImage) throw Error('unapproved code runtime image');
  return new Promise(resolveResult => {
    const name = 'sss-ptc-' + randomUUID();
    const child = spawn('docker',['run','--rm','-i','--name',name,'--pull=never','--network=none','--read-only',
      '--cap-drop=ALL','--security-opt=no-new-privileges','--memory=256m','--pids-limit=64','--user=65534:65534',
      '--tmpfs=/tmp:rw,noexec,nosuid,size=16m',
      '--mount',`type=bind,source=${root}/node_modules,target=/app/node_modules,readonly`,
      '--mount',`type=bind,source=${runner},target=/app/runner.mjs,readonly`,
      '--workdir=/tmp',image,'node','/app/runner.mjs'],{stdio:['pipe','pipe','pipe']});
    let settled = false, bytes = 0, stderr = '', nextId = 1;
    const reader = createInterface({input:child.stdout});
    const cleanup = () => { spawn('docker',['rm','-f',name],{stdio:'ignore'}).on('error',()=>{}); child.kill(); };
    const done = (result: any) => {
      if(settled)return;settled=true;clearTimeout(timer);request.signal?.removeEventListener('abort',abort);
      reader.close(); cleanup(); resolveResult(result);
    };
    const abort = () => done({error:{kind:'abort',message:'Code run cancelled'},logs:[]});
    const timer = setTimeout(()=>done({error:{kind:'timeout',message:'Container wall deadline'},logs:[]}),65000);
    if(request.signal?.aborted){abort();return;} request.signal?.addEventListener('abort',abort,{once:true});
    child.stderr.on('data',(value:Buffer)=> {stderr=(stderr+value.toString()).slice(-2000);});
    child.stdin.on('error',()=>{});
    child.on('error',error=>done({error:{kind:'worker-exit',message:String(error)},logs:[]}));
    child.on('close',code=> {if(!settled)done({error:{kind:'worker-exit',message:`container exited ${code}: ${stderr}`},logs:[]});});
    reader.on('line',async text=> {
      try {
        bytes+=Buffer.byteLength(text);if(bytes>4*1024*1024)throw Error('container protocol output limit');
        const row=JSON.parse(text);
        if(row.type==='done') {if(!row.result||typeof row.result!=='object')throw Error('bad result');done(row.result);return;}
        if(row.type!=='call'||row.id!==nextId++||typeof row.global!=='string'||typeof row.member!=='string')throw Error('invalid dispatch frame');
        const namespace=request.bindings.find((n:any)=>n.global===row.global);
        if(!namespace||!Object.hasOwn(namespace.functions,row.member))throw Error('binding is outside current run');
        try {const value=await namespace.functions[row.member](row.args);
          if(!settled)child.stdin.write(JSON.stringify({type:'response',id:row.id,value})+'\n');}
        catch(error){if(!settled)child.stdin.write(JSON.stringify({type:'response',id:row.id,error:String(error)})+'\n');}
      } catch(error){done({error:{kind:'exception',message:String(error)},logs:[]});}
    });
    child.stdin.write(JSON.stringify({type:'run',program:request.program,bindings:request.bindings.map((n:any)=>({
      global:n.global,members:Object.keys(n.functions),...(n.errorClass?{errorClass:n.errorClass}:{})}))})+'\n');
  });
}
export default class ContainerCodeRuntime extends CodeRuntime {
  language='typescript';isolation='docker-upstream-worker-thread';image:string;
  constructor(ctx:any){super(ctx);this.image=process.env.SSS_CODE_IMAGE||defaultImage;}
  run(request:any){return runContainer(request,this.image);}
}
