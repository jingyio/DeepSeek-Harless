/** Narrow adapters for native skill, todo and present; no replacement tools. */
import {readFileSync,existsSync,lstatSync,realpathSync} from 'node:fs';
import {join,resolve,relative,isAbsolute,posix} from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {parse} from 'yaml';
import {pptMasterInstallation} from './geneloop_skill_installation.mjs';
const sha=(bytes:Uint8Array)=>createHash('sha256').update(bytes).digest('hex');
const maxFileBytes=30*1024*1024;

/** Only the administrator's checked package enters the native registry. */
export function registerApprovedSkill(ctx:any,resources:{pptMasterRoot?:string;projectRoot?:string}={}) {
  const installation=pptMasterInstallation(resources.pptMasterRoot,resources.projectRoot);
  if(!installation)return ()=>{};
  const raw=readFileSync(join(installation.source,'SKILL.md'));
  // Recheck the loaded bytes even if the installation's immutable mount was cached.
  const project=resources.projectRoot??fileURLToPath(new URL('../..',import.meta.url));
  const lock=JSON.parse(readFileSync(join(project,'scenarios/ppt_master/skill-lock.json'),'utf8'));
  if(sha(raw)!==lock.files['SKILL.md'])throw Error('approved skill bytes changed');
  const matched=/^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)([\s\S]*)$/.exec(raw.toString('utf8'));
  if(!matched)throw Error('approved skill metadata missing');
  const meta=parse(matched[1]);
  if(meta?.name!=='ppt-master'||typeof meta.description!=='string'||!meta.description.trim())throw Error('approved skill metadata invalid');
  return ctx.skills.register({name:'ppt-master',description:meta.description.trim(),source:'runtime',provider:'geneloop-approved',
    resourceBase:{kind:'directory',path:installation.target},content:matched[2].trim(),
    invocation:{modelInvocable:true,userInvocable:true}});
}

export type NativeTodo={content:string;status:'pending'|'in_progress'|'completed'};
/** Same whole-list and turn-boundary semantics as the native todos projection. */
export function projectNativeTodos(previous:NativeTodo[]|null,event:any):NativeTodo[]|null {
  if(event?.type==='turn/start')return null;
  if(event?.type!=='todo/write')return previous;
  const rows=event.data?.todos;
  if(!Array.isArray(rows)||rows.some(row=>!row||typeof row.content!=='string'||!row.content.trim()||
    !['pending','in_progress','completed'].includes(row.status)))return previous;
  return rows.map(row=>({content:row.content,status:row.status}));
}

/** Present may only publish the native writable output mount, never inputs or host paths. */
export function nativePresentationPath(path:unknown):string {
  if(typeof path!=='string'||!path.trim()||/[\\\x00-\x1f]/.test(path)||/^[a-z][a-z0-9+.-]*:/i.test(path)||
    path.split('/').includes('..'))throw Error('present requires a file under /work/outputs');
  const normalized=posix.resolve('/work',path);
  if(!normalized.startsWith('/work/outputs/')||normalized.split('/').some(part=>part.startsWith('.')))
    throw Error('present requires a file under /work/outputs');
  return normalized;
}

/** Hash through the owning native filesystem before its successful delivery event.
 * The private proof is paired with deliverables/presented at artifact collection;
 * a failed or canceled call therefore cannot grant a public download.
 */
export function installNativePresentation(ctx:any) {
  ctx.tools.guard((exec:any)=>{
    if(exec.name!=='present')return;
    try {if(!exec.agent||!Array.isArray(exec.arguments?.files))throw Error();
      for(const file of exec.arguments.files)nativePresentationPath(file.path);
    }catch{return 'Only files in this conversation’s /work/outputs can be presented.';}
  });
  ctx.on('tools/execute',async(exec:any,next:any)=>{
    if(exec.name!=='present')return next();
    const result=await next();if(result.isError)return result;
    const files=[];
    for(const file of exec.arguments.files){
      const logical=nativePresentationPath(file.path),target=await ctx.fs.resolve(logical,{signal:exec.signal});
      const bytes=await ctx.fs.readBytes(target,exec.signal,maxFileBytes);
      files.push({path:file.path,name:'outputs/code/'+logical.slice('/work/outputs/'.length),sha256:sha(bytes),bytes:bytes.byteLength});
    }
    exec.signal.throwIfAborted();
    exec.agent.session.append('geneloop/presented-proof',{callId:exec.callId,files});
    return result;
  },{global:true});
}

/** Recover only task-bounded native delivery + matching bytes, not arbitrary tool prose. */
export function nativePresentedFiles(context:{workspace:string;eventsPath?:string;startedAt?:string;finishedAt?:string},verifyCurrent=true):Map<string,string> {
  const found=new Map<string,string>(),proofs=new Map<string,any[]>();
  const start=Date.parse(context.startedAt??''),end=Date.parse(context.finishedAt??'');
  if(!Number.isFinite(start)||!Number.isFinite(end)||start>end||!context.eventsPath||!existsSync(context.eventsPath))return found;
  const log=lstatSync(context.eventsPath);
  if(!log.isFile()||log.isSymbolicLink()||log.nlink!==1||log.size>32*1024*1024)return found;
  for(const line of readFileSync(context.eventsPath,'utf8').split('\n'))try{
    const event=JSON.parse(line),data=event.data;
    if(!Number.isFinite(event.time)||event.time<start||event.time>end||typeof data?.callId!=='string')continue;
    if(event.type==='geneloop/presented-proof'&&Array.isArray(data.files))proofs.set(data.callId,data.files);
    if(event.type!=='deliverables/presented'||!Array.isArray(data.files))continue;
    for(const row of proofs.get(data.callId)??[]){
      if(!data.files.some((file:any)=>file.path===row.path)||typeof row.name!=='string'||
        row.name!=='outputs/code/'+nativePresentationPath(row.path).slice('/work/outputs/'.length)||
        !/^[a-f0-9]{64}$/.test(row.sha256)||!Number.isSafeInteger(row.bytes)||row.bytes<0||row.bytes>maxFileBytes)continue;
      const root=resolve(context.workspace),path=join(root,row.name),rel=relative(root,path);
      if(rel.startsWith('..')||isAbsolute(rel))continue;
      // Artifact copying requests the immutable proof even if current bytes
      // changed, so a legacy directory scan cannot publish the changed file.
      if(!verifyCurrent){found.set(path,row.sha256);continue;}
      if(!existsSync(path))continue;
      let current=root,valid=realpathSync(root)===root&&!lstatSync(root).isSymbolicLink();
      for(const part of rel.split(/[\\/]/)){current=join(current,part);const st=lstatSync(current);if(st.isSymbolicLink()||realpathSync(current)!==current)valid=false;}
      const st=lstatSync(path);
      if(valid&&st.isFile()&&st.nlink===1&&st.size===row.bytes&&sha(readFileSync(path))===row.sha256)found.set(path,row.sha256);
    }
  }catch{/* Invalid historical events cannot grant delivery. */}
  return found;
}

export const name='geneloop-native-work';
export const inject=['skills','tools','fs'];
export function apply(ctx:any) {
  const policy=JSON.parse(readFileSync(process.env.SSS_WEB_POLICY!,'utf8'));
  registerApprovedSkill(ctx,policy.command_resources);
  installNativePresentation(ctx);
}
