/** Experimental executor; production GeneLoopShell and its certificates stay frozen. */
import {readFileSync} from 'node:fs';
import {isAbsolute,relative,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {LocalBashExecutor} from '@deepseek-ai/dsh-bash-local';
import {commandArgv as linuxArgv,commandLayout} from './geneloop_shell.ts';
import {localScriptArgv} from './script_motif_macos.ts';
import {consumeScriptGrant,prepareCacheInvocation} from './script_motif_runtime.ts';
export function scriptArgv(layout:any,command:string,cwd:string,readOnly=false,resources:any={}){
 const python=process.env.SSS_PYTHON??'/usr/bin/python3';
 if(process.platform==='darwin')return localScriptArgv(layout,command,cwd,python,process.execPath,readOnly,resources);
 const args=linuxArgv(layout,command,cwd,python,process.execPath,readOnly,resources);
 if(resources.ephemeralTemp){
  const index=args.findIndex((v,i)=>v==='--bind'&&args[i+1]===layout.temp&&args[i+2]==='/tmp');
  if(index<0)throw Error('script_temp_mount_changed');args.splice(index,3,'--tmpfs','/tmp');
 }
 return args;
}
const inside=(root:string,path:string)=>{const r=relative(root,path);return !r.startsWith('..')&&!isAbsolute(r);};
export default class ScriptMotifShell extends LocalBashExecutor {
 get sandboxMode(){return 'workspace-write' as const;}
 resolve(request:any):any{
  const agent=this.ctx.get('agents')?.currentInitiator();if(!agent)throw Error('command requires an active owning Agent');
  if(process.env.GENELOOP_COMMAND_SOCKET)throw Error('script experiment requires a direct isolated executor');
  const policy=JSON.parse(readFileSync(process.env.SSS_WEB_POLICY!,'utf8'));
  const layout=commandLayout(policy.output,agent.session.id),requested=request.workdir??'/work',header=agent.session.header.cwd;
  const cwd=requested==='/work'||requested.startsWith('/work/')?resolve(requested):header&&inside(header,requested)?resolve('/work',relative(header,requested)):!isAbsolute(requested)?resolve('/work',requested):'';
  if(!cwd||!inside('/work',cwd))throw Error('command working directory must stay inside /work');
  const body=consumeScriptGrant(agent.session.id,request.command)||prepareCacheInvocation(agent.session.id,request.command);
  const spec=super.resolve({...request,workdir:layout.scratch,env:{},dshEnv:{},sandboxPolicy:undefined});
  spec.geneloopArgv=body&&typeof body==='object'?[process.execPath,fileURLToPath(new URL('../../scripts/run-certified-script.mjs',import.meta.url)),Buffer.from(JSON.stringify(body)).toString('base64')]:scriptArgv(layout,body||request.command,cwd,!!body||request.sandboxPolicy?.mode==='read-only',
    {...policy.command_resources,...(body?{network:'none',ephemeralTemp:true}:{})});
  return spec;
 }
 run(spec:any){if(!spec.geneloopArgv)throw Error('unresolved script executor');return this.runArgv(spec,spec.geneloopArgv);}
 start(spec:any){if(!spec.geneloopArgv)throw Error('unresolved script executor');return this.startArgv(spec,spec.geneloopArgv);}
}
