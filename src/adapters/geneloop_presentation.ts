/** Render uploaded slides in the existing Session sandbox; no authoring/model loop. */
import {spawn} from 'node:child_process';
import {request} from 'node:http';
import {createHash,randomUUID} from 'node:crypto';
import {readFileSync,lstatSync} from 'node:fs';
import {basename,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {commandArgv,commandLayout} from './geneloop_shell.ts';

const hash=(bytes:Uint8Array)=>createHash('sha256').update(bytes).digest('hex');
const helper=()=>readFileSync(fileURLToPath(new URL('./geneloop_presentation_render.py',import.meta.url)),'utf8');
function stable(path:string) {
  const before=lstatSync(path);
  if(!before.isFile()||before.isSymbolicLink()||before.nlink!==1||before.size>20*1024*1024)throw Error('invalid presentation file');
  const bytes=readFileSync(path),after=lstatSync(path);
  if(before.ino!==after.ino||before.size!==after.size||before.mtimeMs!==after.mtimeMs)throw Error('presentation changed');
  return bytes;
}

export function renderPresentation(workspace:string,session:string,resources:any={}) {
  return async (file:any,signal?:AbortSignal)=>{
    signal?.throwIfAborted();
    if(basename(file.file)!==file.file||!/\.(pptx|ppt)$/i.test(file.name))throw Error('invalid presentation source');
    const original=join(workspace,'inputs',file.file);
    if(hash(stable(original))!==file.version_sha256)throw Error('presentation version changed');
    const directory='input-visual-'+randomUUID();
    const payload=Buffer.from(JSON.stringify({file:file.file,sha256:file.version_sha256,directory,
      suffix:file.name.toLowerCase().endsWith('.pptx')?'.pptx':'.ppt'})).toString('base64');
    // Shell operands contain only base64 or server-owned executable paths.
    const code=Buffer.from(helper()).toString('base64');
    const python=process.env.SSS_PYTHON??'/usr/bin/python3';
    if(!/^\/[a-zA-Z0-9_./-]+$/.test(python))throw Error('invalid presentation Python');
    const command=`${python} -c "import base64;exec(base64.b64decode('${code}'))" '${payload}'`;
    const output=await new Promise<string>((resolve,reject)=>{
      let stdout='',exit:number|undefined;
      const socket=process.env.GENELOOP_COMMAND_SOCKET;
      let stop:()=>void=()=>{};
      const end=(error?:Error)=>{clearTimeout(timer);signal?.removeEventListener('abort',abort);error?reject(error):exit===0?resolve(stdout):reject(Error('presentation render failed'));};
      const abort=()=>{stop();end(Error('presentation render cancelled'));};
      const timer=setTimeout(()=>{stop();end(Error('presentation render timeout'));},420000);
      signal?.addEventListener('abort',abort,{once:true});
      if(socket){
        const req=request({socketPath:socket,path:'/run',method:'POST',headers:{'Content-Type':'application/json'}},res=>{
          if(res.statusCode!==200){res.resume();end(Error('presentation sandbox unavailable'));return;}
          let pending='';res.setEncoding('utf8');
          res.on('data',chunk=>{pending+=chunk;let index;while((index=pending.indexOf('\n'))>=0){
            try{const row=JSON.parse(pending.slice(0,index));pending=pending.slice(index+1);
              if(row.stdout)stdout+=Buffer.from(row.stdout,'base64').toString('utf8');if(Number.isInteger(row.exit))exit=row.exit;
            }catch{stop();end(Error('invalid sandbox response'));return;}
          }});
          res.on('end',()=>end());res.on('error',()=>end(Error('presentation sandbox disconnected')));
        });
        stop=()=>req.destroy();req.on('error',()=>end(Error('presentation sandbox failed')));
        req.end(JSON.stringify({session,command,cwd:'/work',readOnly:false,network:'none'}));
      }else{
        try{
          const layout={...commandLayout(join(workspace,'../../..'),session)};
          if(layout.work!==workspace)throw Error('presentation workspace mismatch');
          const [bin,...args]=commandArgv(layout,command,'/work',python,process.execPath,false,{...resources,network:'none'});
          const child=spawn(bin,args,{stdio:['ignore','pipe','pipe'],env:{},detached:true});
          stop=()=>{try{if(child.pid)process.kill(-child.pid,'SIGKILL');}catch{}};
          child.stdout.on('data',chunk=>{stdout+=chunk.toString('utf8');});child.stderr.resume();
          child.once('error',()=>end(Error('presentation sandbox unavailable')));
          child.once('close',code=>{exit=code??1;end();});
        }catch{end(Error('presentation sandbox unavailable'));}
      }
    });
    signal?.throwIfAborted();
    const result=JSON.parse(output);
    const pdf=join(workspace,'code',directory,'reference.pdf');
    if(result.pdf!==`/work/${directory}/reference.pdf`||result.source_sha256!==file.version_sha256||
        hash(stable(pdf))!==result.pdf_sha256||hash(stable(original))!==file.version_sha256)throw Error('presentation derivative changed');
    if(result.normalized_source){
      if(result.normalized_source.path!==`/work/${directory}/reference.pptx`||
          hash(stable(join(workspace,'code',directory,'reference.pptx')))!==result.normalized_source.sha256)throw Error('presentation derivative changed');
    }
    return {path:pdf,sha256:result.pdf_sha256,normalized_source:result.normalized_source};
  };
}
