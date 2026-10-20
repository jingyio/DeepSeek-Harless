/** Native Harness filesystem seam for the same private execution world as Bash.
 * Paths stay logical; file descriptors pin each no-follow directory/file on Linux.
 * Model-facing read/read_image/write/edit remain the upstream tools.
 */
import {constants, lstatSync, readFileSync, realpathSync} from 'node:fs';
import {open, mkdir, rename, link, unlink, readdir} from 'node:fs/promises';
import type {FileHandle} from 'node:fs/promises';
import {isAbsolute, join, relative, resolve, posix} from 'node:path';
import {createHash, randomUUID} from 'node:crypto';
import {FileSystem, FsError, FsTargetKey} from '@deepseek-ai/dsh-fs';
import type {FsTarget, FsInfo, FsDirEntry, FsWriteIntent, FsWriteOutcome, FsVersion, FsEditRequest,
  FsEditOutcome, FsPathInfo} from '@deepseek-ai/dsh-fs';
import {LocalFileSystem} from '@deepseek-ai/dsh-fs-local';
import {commandLayout} from './geneloop_shell.ts';
import {pptMasterInstallation} from './geneloop_skill_installation.mjs';
import {resolveExecutionAgent} from './geneloop_delegation.ts';

export interface GeneLoopFsConfig {output:string;command_resources?:{pptMasterRoot?:string;projectRoot?:string}}
type Owner={session:string;config:GeneLoopFsConfig;cwd?:string};
type Mount={logical:string;host:string;writable:boolean};
type RecordTarget={owner:Owner;path:string;mount:Mount;parts:string[]};
const within=(root:string,path:string)=>{const r=relative(root,path);return r===''||(!r.startsWith('..')&&!isAbsolute(r));};
const denied=()=>new FsError('Path is outside the current Session filesystem or is not a regular unlinked entry.','FS_SANDBOX_DENIED');
const aborted=(signal?:AbortSignal)=>{if(signal?.aborted)throw new FsError('Filesystem operation was canceled.','FS_ABORTED');};
const hash=(value:string)=>createHash('sha256').update(value).digest('hex');
const fdPath=(handle:FileHandle)=>`/proc/self/fd/${handle.fd}`;
const normalizedText=(value:string)=>value.replaceAll('\r\n','\n');

/** Logical paths never accept host paths, backslashes, URI schemes or lexical escapes. */
export function geneLoopPath(path:string,cwd='/work'):string {
  if(typeof path!=='string'||!path.trim()||/[\\\x00-\x1f]/.test(path)||/^[a-z][a-z0-9+.-]*:/i.test(path))throw denied();
  if(!cwd.startsWith('/')||/[\\\x00-\x1f]/.test(cwd))throw denied();
  const logical=posix.resolve(cwd,path);
  if(!['/work','/tmp','/opt/geneloop/ppt-master'].some(root=>logical===root||logical.startsWith(root+'/')))throw denied();
  // A path may normalize inside the workspace, but may never climb above its mount.
  const raw=path.startsWith('/')?path:cwd+'/'+path;
  const isBelow=(root:string)=>raw===root||raw.startsWith(root+'/');
  const mount=isBelow('/work/inputs')?'/work/inputs':isBelow('/work/outputs')?'/work/outputs':
    isBelow('/tmp')?'/tmp':isBelow('/opt/geneloop/ppt-master')?'/opt/geneloop/ppt-master':'/work';
  let depth=0;for(const part of raw.slice(mount.length).split('/')){
    if(part==='..'){if(--depth<0)throw denied();}else if(part&&part!=='.')depth++;
  }
  return logical;
}

function fixed(path:string) {
  if(!isAbsolute(path)||realpathSync(path)!==resolve(path))throw denied();
  const stat=lstatSync(path);if(!stat.isDirectory()||stat.isSymbolicLink())throw denied();
}

/** Paths and mount ordering exactly match geneloop_shell.commandLayout/commandArgv. */
export function geneLoopMounts(config:GeneLoopFsConfig,session:string):Mount[] {
  if(!/^(?:session-[a-f0-9-]{36}|sss-[a-f0-9]{32})$/.test(session))throw denied();
  fixed(config.output);
  // User commands cannot replace these ancestors: only the code/temp/input mount interiors are exposed.
  for(const suffix of ['sessions',join('sessions',session),join('sessions',session,'work')]){
    const path=join(config.output,suffix),st=lstatSync(path,{throwIfNoEntry:false});
    if(st&&(st.isSymbolicLink()||!st.isDirectory()||realpathSync(path)!==resolve(path)))throw denied();
  }
  const layout=commandLayout(config.output,session);
  const mounts:Mount[]=[{logical:'/work/inputs',host:layout.inputs,writable:false},
    {logical:'/work/outputs',host:layout.outputs,writable:true},
    {logical:'/work',host:layout.scratch,writable:true},{logical:'/tmp',host:layout.temp,writable:true}];
  const skill=pptMasterInstallation(config.command_resources?.pptMasterRoot,config.command_resources?.projectRoot);
  if(skill)mounts.push({logical:skill.target,host:skill.source,writable:false});
  return mounts;
}

function mapError(error:any):never {
  if(error instanceof FsError)throw error;
  const code=error?.code;
  if(code==='ENOENT')throw new FsError('File does not exist.','FS_NOT_FOUND');
  if(code==='ENOTDIR')throw new FsError('Path is not a directory.','FS_NOT_DIRECTORY');
  if(code==='ELOOP')throw denied();
  if(code==='EACCES'||code==='EPERM')throw new FsError('Filesystem access denied.','FS_PERMISSION_DENIED');
  throw new FsError('Session filesystem operation failed.','FS_IO_ERROR');
}

export default class GeneLoopFileSystem extends FileSystem {
  private native:LocalFileSystem;
  private records=new Map<string,RecordTarget>();
  private locks=new Map<string,Promise<unknown>>();
  private configured?:GeneLoopFsConfig;
  constructor(ctx:any,config?:GeneLoopFsConfig){
    super(ctx);this.configured=config;
    // Reuse upstream UTF-8, binary, byte-range and version semantics against pinned file descriptors.
    this.native=new LocalFileSystem(ctx.isolate('fs'),{cwd:'/',diffBasisMaxBytes:10*1024*1024});
  }
  get sandboxMode(){return 'workspace-write' as const;}
  private owner():Owner {
    let active:any;try{active=resolveExecutionAgent(this.ctx)?.session;}catch{throw denied();}
    const session=active?.id;
    if(!session)throw new FsError('Filesystem requires an active owning Session.','FS_SANDBOX_DENIED');
    const config=this.configured??JSON.parse(readFileSync(process.env.SSS_WEB_POLICY!,'utf8'));
    return {session,config,cwd:active.header?.cwd};
  }
  private target(record:RecordTarget):FsTarget {
    const key=hash(record.owner.config.output+'\0'+record.owner.session+'\0'+record.path);
    this.records.set(key,record);return {targetKey:FsTargetKey(key),displayPath:record.path};
  }
  private record(target:FsTarget):RecordTarget {
    const owner=this.owner(),record=this.records.get(target.targetKey);
    if(!record||record.owner.session!==owner.session||record.owner.config.output!==owner.config.output||target.displayPath!==record.path)throw denied();
    return record;
  }
  async resolve(path:string,opts:{cwd?:string;signal?:AbortSignal}={}):Promise<FsTarget>{
    aborted(opts.signal);const owner=this.owner();
    // Upstream tools pass the Session header's host-shaped cwd. Like Bash, map
    // that one owning alias into /work; never treat it as host read authority.
    const alias=(value:string)=>owner.cwd&&isAbsolute(value)&&within(owner.cwd,value)
      ?posix.join('/work',...relative(owner.cwd,value).split(/[\\/]/)):value;
    const logical=geneLoopPath(alias(path),alias(opts.cwd??'/work'));
    const mount=geneLoopMounts(owner.config,owner.session).find(row=>logical===row.logical||logical.startsWith(row.logical+'/'));
    if(!mount)throw denied();
    const parts=logical.slice(mount.logical.length).split('/').filter(Boolean);
    const record={owner,path:logical,mount,parts};
    // Resolve remains valid for an absent write target, but never accepts existing links.
    const handle=await this.pinned(record,false,true);await handle?.close();
    return this.target(record);
  }
  processPath(target:FsTarget){return this.record(target).path;}
  processPathFromHostPath(hostPath:string):string|undefined {
    try{const owner=this.owner();if(!isAbsolute(hostPath))return undefined;
      for(const mount of geneLoopMounts(owner.config,owner.session))if(within(mount.host,hostPath)){
        const logical=posix.join(mount.logical,...relative(mount.host,hostPath).split(/[\\/]/));
        // Do not advertise links or a path hidden under another virtual mount.
        const selected=geneLoopMounts(owner.config,owner.session).find(row=>logical===row.logical||logical.startsWith(row.logical+'/'))!;
        if(selected.host!==mount.host)return undefined;
        let parent=mount.host;for(const part of relative(mount.host,hostPath).split(/[\\/]/).filter(Boolean)){
          parent=join(parent,part);const st=lstatSync(parent);if(st.isSymbolicLink()||(st.isFile()&&st.nlink!==1))return undefined;
        }
        return logical;
      }
    }catch{}return undefined;
  }
  fileUrl(target:FsTarget){return 'file://'+this.record(target).path.split('/').map(encodeURIComponent).join('/');}
  contains(parent:FsTarget,child:FsTarget){const a=this.record(parent),b=this.record(child);return a.path===b.path||b.path.startsWith(a.path+'/');}

  /** Each component is opened relative to a pinned parent; replacement symlinks cannot escape. */
  private async pinned(record:RecordTarget,directory=false,missing=false,createParents=false):Promise<FileHandle|undefined>{
    if(process.platform!=='linux')throw new FsError('Native Session filesystem I/O requires Linux no-follow descriptors.','FS_SANDBOX_DENIED');
    let handle:FileHandle|undefined;
    try{
      handle=await open(record.mount.host,constants.O_RDONLY|constants.O_DIRECTORY|constants.O_NOFOLLOW);
      for(let i=0;i<record.parts.length;i++){
        const last=i===record.parts.length-1,path=fdPath(handle)+'/'+record.parts[i];
        if(createParents&&(!last||directory)){try{await mkdir(path,{mode:0o700});}catch(error:any){if(error.code!=='EEXIST')throw error;}}
        let next:FileHandle;try{next=await open(path,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK|(!last||directory?constants.O_DIRECTORY:0));}
        catch(error:any){if(missing&&error.code==='ENOENT'){await handle.close();return undefined;}throw error;}
        await handle.close();handle=next;
        const st=await handle.stat();if(!st.isDirectory()&&(!st.isFile()||st.nlink!==1))throw denied();
      }
      return handle;
    }catch(error){await handle?.close();return mapError(error);}
  }
  private fdTarget(handle:FileHandle,displayPath:string):FsTarget{return {targetKey:FsTargetKey(fdPath(handle)),displayPath};}
  private async reading<T>(target:FsTarget,signal:AbortSignal|undefined,read:(t:FsTarget)=>Promise<T>):Promise<T>{
    aborted(signal);const record=this.record(target),handle=await this.pinned(record);
    try{aborted(signal);return await read(this.fdTarget(handle!,record.path));}catch(error){return mapError(error);}finally{await handle?.close();}
  }
  async stat(target:FsTarget,signal?:AbortSignal):Promise<FsInfo|undefined>{
    aborted(signal);const record=this.record(target),handle=await this.pinned(record,false,true);
    try{return handle?await this.native.stat(this.fdTarget(handle,record.path),signal):undefined;}finally{await handle?.close();}
  }
  async lstat(path:string,opts?:{cwd?:string},signal?:AbortSignal):Promise<FsPathInfo|undefined>{
    return this.stat(await this.resolve(path,{...opts,signal}),signal);
  }
  readText(target:FsTarget,signal?:AbortSignal){return this.reading(target,signal,t=>this.native.readText(t,signal));}
  readBytes(target:FsTarget,signal:AbortSignal|undefined,maxBytes:number){return this.reading(target,signal,t=>this.native.readBytes(t,signal,maxBytes));}
  readByteRange(target:FsTarget,range:{offset:number;length:number},signal?:AbortSignal){return this.reading(target,signal,t=>this.native.readByteRange(t,range,signal));}
  async streamText(target:FsTarget,signal?:AbortSignal):Promise<AsyncIterable<string>>{
    this.record(target);const backend=this,native=this.native;
    return (async function*(){aborted(signal);const record=backend.record(target),handle=await backend.pinned(record);
      try{const stream=await native.streamText({targetKey:FsTargetKey(fdPath(handle!)),displayPath:record.path},signal);
        for await(const chunk of stream){aborted(signal);yield chunk;}}finally{await handle?.close();}})();
  }
  async listDir(target:FsTarget,signal?:AbortSignal):Promise<FsDirEntry[]>{
    aborted(signal);const record=this.record(target),handle=await this.pinned(record,true);
    try{
      const names=new Set(await readdir(fdPath(handle!)));
      if(record.path==='/work'){names.add('inputs');names.add('outputs');}
      const result:FsDirEntry[]=[];
      for(const name of [...names].sort()){
        aborted(signal);
        try{const child=await this.resolve(posix.join(record.path,name),{signal}),info=await this.stat(child,signal);
          if(info)result.push({name,target:child,...info});
        }catch(error){if(!(error instanceof FsError)||!['FS_SANDBOX_DENIED','FS_NOT_FOUND','FS_NOT_DIRECTORY'].includes(error.code))throw error;}
      }
      return result;
    }catch(error){return mapError(error);}finally{await handle?.close();}
  }
  private async exclusive<T>(key:string,op:()=>Promise<T>):Promise<T>{
    const previous=this.locks.get(key)??Promise.resolve();const current=previous.catch(()=>{}).then(op);
    this.locks.set(key,current);try{return await current;}finally{if(this.locks.get(key)===current)this.locks.delete(key);}
  }
  private async mutate(target:FsTarget,expected:FsWriteIntent|undefined,signal:AbortSignal|undefined,policy:any,
    transform:(before:string|null)=>{content:string;before:string|null},requireText=false):Promise<FsWriteOutcome>{
    const record=this.record(target);
    if(!record.mount.writable||!record.parts.length||policy?.mode==='read-only')throw denied();
    return this.exclusive(target.targetKey,async()=>{
      aborted(signal);this.record(target);
      const parent={...record,parts:record.parts.slice(0,-1)};
      const directory=await this.pinned(parent,true,false,true);let existing:FileHandle|undefined,temporary:FileHandle|undefined;
      const name=record.parts.at(-1)!,path=fdPath(directory!)+'/'+name,temp=fdPath(directory!)+`/.geneloop-${randomUUID()}.tmp`;
      try{
        existing=await this.pinned(record,false,true);const info=existing?await this.native.stat(this.fdTarget(existing,record.path)):undefined;
        if(info&&info.type!=='file')throw new FsError('Cannot replace a directory or special entry.','FS_NOT_REGULAR_FILE');
        if(expected?.kind==='createIfAbsent'&&info)throw new FsError('Read the existing file before replacing it.','FS_NOT_OBSERVED');
        if(expected?.kind==='replaceIfVersion'&&(!info||info.version!==expected.version))throw new FsError('File changed since its observation.','FS_STALE_VERSION');
        let before:string|null=null;
        if(existing&&(requireText||(info?.size??Infinity)<10*1024*1024)){
          try{before=await this.native.readText(this.fdTarget(existing,record.path),signal);}catch(error){if(!(error instanceof FsError)||error.code!=='FS_NOT_TEXT')throw error;}
        }
        const result=transform(before);
        temporary=await open(temp,constants.O_WRONLY|constants.O_CREAT|constants.O_EXCL|constants.O_NOFOLLOW,0o600);
        await temporary.writeFile(result.content,{encoding:'utf8',signal});await temporary.sync();
        if(existing)await temporary.chmod((await existing.stat()).mode&0o777);
        aborted(signal);
        // Revalidate immediately before publication. No operation ever follows the destination entry.
        const now=await this.pinned(record,false,true);
        try{const current=now?await this.native.stat(this.fdTarget(now,record.path)):undefined;
          if(expected?.kind==='createIfAbsent'&&current)throw new FsError('File was concurrently created.','FS_NOT_OBSERVED');
          if(info?.version!==current?.version)throw new FsError('File changed during the write.','FS_STALE_VERSION');
        }finally{await now?.close();}
        if(expected?.kind==='createIfAbsent'){
          try{await link(temp,path);}catch(error:any){if(error.code==='EEXIST')throw new FsError('File was concurrently created.','FS_NOT_OBSERVED');throw error;}
          await unlink(temp);
        }else await rename(temp,path);
        await directory!.sync();
        const version=(await this.native.stat(this.fdTarget(temporary,record.path)))!.version;
        return {operation:info?'update':'create',version,before:result.before===null?null:normalizedText(result.before),after:normalizedText(result.content)};
      }catch(error){return mapError(error);}finally{
        await temporary?.close();await existing?.close();await unlink(temp).catch(()=>{});await directory?.close();
      }
    });
  }
  writeText(target:FsTarget,content:string,expected?:FsWriteIntent,signal?:AbortSignal,policy?:any){
    return this.mutate(target,expected,signal,policy,before=>({content,before:Buffer.byteLength(content)<10*1024*1024?before:null}));
  }
  async editText(target:FsTarget,edit:FsEditRequest,expected?:{version:FsVersion},signal?:AbortSignal,policy?:any):Promise<FsEditOutcome>{
    const result=await this.mutate(target,expected?{kind:'replaceIfVersion',version:expected.version}:undefined,signal,policy,before=>{
      if(before===null)throw new FsError('Cannot edit absent or binary text.','FS_NOT_TEXT');
      const source=normalizedText(before),old=normalizedText(edit.oldString),replacement=normalizedText(edit.newString);
      if(!old)throw new FsError('old_string must not be empty.','FS_EDIT_NOT_FOUND');
      const count=source.split(old).length-1;
      if(!count)throw new FsError('old_string was not found.','FS_EDIT_NOT_FOUND');
      if(count>1&&!edit.replaceAll)throw new FsError('old_string was ambiguous.','FS_AMBIGUOUS_EDIT');
      const after=edit.replaceAll?source.split(old).join(replacement):source.replace(old,()=>replacement);
      const crlf=(before.match(/\r\n/g)??[]).length>(before.match(/(?<!\r)\n/g)??[]).length;
      return {content:crlf?after.replaceAll('\n','\r\n'):after,before:source};
    },true);
    return {version:result.version,before:result.before!,after:result.after};
  }
}
