/** Private per-account command transport; commands still run in a fresh Session-only bwrap. */
import {createServer} from 'node:http';
import {spawn} from 'node:child_process';
import {mkdtempSync,chmodSync,existsSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {commandLayout,commandArgv} from './geneloop_shell.ts';

export async function startCommandBroker(options:{output:string;python:string;node:string}) {
  const directory=mkdtempSync(join(tmpdir(),'geneloop-cmd-')),socketPath=join(directory,'commands.sock');
  chmodSync(directory,0o700);
  const children=new Set<ReturnType<typeof spawn>>();
  const stop=(child:ReturnType<typeof spawn>)=>{try{if(child.pid)process.kill(-child.pid,'SIGKILL');}catch{/* already exited */}};
  const server=createServer(async(req,res)=>{
    if(req.method!=='POST'||req.url!=='/run'){res.writeHead(404);res.end();return;}
    let body='';
    try{
      for await(const chunk of req){body+=chunk;if(Buffer.byteLength(body)>1024*1024)throw Error('command request too large');}
      const value=JSON.parse(body);
      if(Object.keys(value).sort().join(',')!=='command,cwd,readOnly,session'||typeof value.command!=='string'||
        typeof value.cwd!=='string'||!/^\/work(?:\/|$)/.test(value.cwd)||value.cwd.split('/').includes('..')||
        typeof value.readOnly!=='boolean'||!/^session-[a-f0-9-]{36}$/.test(value.session)||
        !existsSync(join(options.output,'sessions',value.session,'work')))throw Error('invalid owning Session command');
      const layout=commandLayout(options.output,value.session);
      const [bin,...args]=commandArgv(layout,value.command,value.cwd,options.python,options.node,value.readOnly);
      const child=spawn(bin,args,{stdio:['ignore','pipe','pipe'],detached:true,env:{}});children.add(child);
      res.writeHead(200,{'Content-Type':'application/x-ndjson','Cache-Control':'no-store'});
      const send=(value:unknown)=>{if(!res.destroyed)res.write(JSON.stringify(value)+'\n');};
      child.stdout!.on('data',data=>send({stdout:data.toString('base64')}));
      child.stderr!.on('data',data=>send({stderr:data.toString('base64')}));
      child.once('error',()=>{send({stderr:Buffer.from('isolated command failed to start\n').toString('base64')});send({exit:1});res.end();children.delete(child);});
      child.once('close',(code,signal)=>{send({exit:code??(signal?137:1)});res.end();children.delete(child);});
      res.once('close',()=>{if(children.has(child))stop(child);});
    }catch{if(!res.headersSent)res.writeHead(400);res.end('Invalid isolated command request');}
  });
  await new Promise<void>((resolve,reject)=>{server.once('error',reject);server.listen(socketPath,resolve);});
  chmodSync(socketPath,0o600);
  return {socketPath,close(){for(const child of children)stop(child);server.close(()=>rmSync(directory,{recursive:true,force:true}));}};
}
