/** Keep upstream glob/grep unchanged; route only their packaged rg through Session isolation. */
import {readFileSync,lstatSync} from 'node:fs';
import {join,isAbsolute,relative,posix} from 'node:path';
import {fileURLToPath} from 'node:url';
import {rgPath} from '@vscode/ripgrep';
import {buildGlobCommand,buildGrepCommand} from '@deepseek-ai/dsh-tool-fs-search';
import {LocalSubprocessRuntime} from '@deepseek-ai/dsh-subprocess-local';
import type {SubprocessSpawnSpec} from '@deepseek-ai/dsh-subprocess';
import {geneLoopPath,geneLoopMounts} from './geneloop_fs.ts';
import type {GeneLoopFsConfig} from './geneloop_fs.ts';
import {commandArgv,commandLayout} from './geneloop_shell.ts';
import {resolveExecutionAgent} from './geneloop_delegation.ts';

const denied=()=>new Error('Native search must stay in the current Session and use the fixed packaged ripgrep templates.');
const quote=(value:string)=>"'"+value.replaceAll("'","'\\''")+"'";
const within=(root:string,path:string)=>{const r=relative(root,path);return r===''||(!r.startsWith('..')&&!isAbsolute(r));};

/** Admit only exact argv emitted by upstream glob/grep, excluding preprocessors/follow/config options. */
export function nativeSearchArgs(argv:readonly string[]):{args:string[];path:string} {
  if(argv[0]!==rgPath||argv[1]!=='--no-config'||argv.some(value=>typeof value!=='string'||value.includes('\0')))throw denied();
  const args=argv.slice(2),separator=args.lastIndexOf('--');
  if(separator>=0&&separator!==args.length-2)throw denied();
  // The upstream tools omit both `--` and the path when the model chooses
  // their documented current-directory default. Validate that exact template
  // before adding our own explicit logical root for the isolated command.
  const explicit=separator>=0,path=explicit?args.at(-1)!:'.',root=explicit?{path}:{};
  let expected:string[];
  if(args[0]==='--files'&&args[1]?.startsWith('--glob=')){
    expected=buildGlobCommand({pattern:args[1].slice(7),...root});
  }else if(args[0]==='--json'&&args[1]?.startsWith('--regexp=')){
    expected=buildGrepCommand({pattern:args[1].slice(9),...root,...(args[2]?.startsWith('--glob=')?{include:args[2].slice(7)}:{})});
  }else throw denied();
  if(JSON.stringify(expected)!==JSON.stringify(args))throw denied();
  return {args:explicit?[...args]:[...args,'--',path],path};
}

export default class GeneLoopSubprocessRuntime extends LocalSubprocessRuntime {
  private configured?:GeneLoopFsConfig;
  constructor(ctx:any,config?:GeneLoopFsConfig){super(ctx);this.configured=typeof config?.output==='string'?config:undefined;}
  spawn(spec:SubprocessSpawnSpec){
    // Other trusted plugin subprocesses retain their existing provider behavior.
    // There is no new model-visible generic subprocess tool.
    if(spec.argv[0]!==rgPath)return super.spawn(spec);
    if(process.platform!=='linux')throw denied();
    const active=resolveExecutionAgent(this.ctx)?.session;
    if(!active)throw denied();
    const config=this.configured??JSON.parse(readFileSync(process.env.SSS_WEB_POLICY!,'utf8'));
    const checked=nativeSearchArgs(spec.argv),mounts=geneLoopMounts(config,active.id);
    const alias=(value:string)=>active.header?.cwd&&isAbsolute(value)&&within(active.header.cwd,value)
      ?posix.join('/work',...relative(active.header.cwd,value).split(/[\\/]/)):value;
    const cwd=geneLoopPath(alias(spec.cwd)),path=geneLoopPath(alias(checked.path),cwd);
    if(cwd!=='/work'&&!cwd.startsWith('/work/'))throw denied();
    // rg does not follow discovered links; reject an explicitly addressed link or hardlink too.
    const validate=(logical:string)=>{
      const mount=mounts.find(row=>logical===row.logical||logical.startsWith(row.logical+'/'));
      if(!mount)throw denied();let current=mount.host;
      for(const part of logical.slice(mount.logical.length).split('/').filter(Boolean)){
        current=join(current,part);const st=lstatSync(current);
        if(st.isSymbolicLink()||(!st.isDirectory()&&(!st.isFile()||st.nlink!==1)))throw denied();
      }
    };
    validate(cwd);validate(path);
    // Use the absolute logical root, so results stay readable even when header.cwd is host-shaped.
    checked.args[checked.args.length-1]=path;
    const command=['/opt/geneloop/rg','--no-config',...checked.args].map(quote).join(' ');
    const layout=commandLayout(config.output,active.id),socket=process.env.GENELOOP_COMMAND_SOCKET;
    const argv=socket?[process.execPath,fileURLToPath(new URL('./geneloop_command_client.mjs',import.meta.url)),socket,
      Buffer.from(JSON.stringify({session:active.id,command,cwd,readOnly:true,network:'none'})).toString('base64url')]
      :commandArgv(layout,command,cwd,undefined,undefined,true,{...config.command_resources,network:'none'});
    return super.spawn({...spec,argv,cwd:layout.scratch,env:{}});
  }
}
