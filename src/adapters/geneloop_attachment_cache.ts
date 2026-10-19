/** Host-private, content/version-bound attachment evidence, never a model plan.
 * A completed page observation is independent of a later user's question.
 * Partial rows keep their actual error and original pixels for a later retry.
 */
import {createHash,randomUUID} from 'node:crypto';
import {lstatSync,mkdirSync,readFileSync,writeFileSync,renameSync} from 'node:fs';
import {join,resolve,sep} from 'node:path';

const hash=(value:string|Uint8Array)=>createHash('sha256').update(value).digest('hex');
const running=new Map<string,Promise<any>>();

export function attachmentEvidenceDirectory(workspace:string, directory:string) {
  const work=resolve(workspace), root=resolve(directory);
  // Agent commands have write access to work. Evidence from that tree cannot
  // be trusted as a previously authenticated model observation.
  if(root===work||root.startsWith(work+sep))throw Error('attachment_cache_must_be_host_private');
  mkdirSync(root,{recursive:true,mode:0o700});
  if(lstatSync(root).isSymbolicLink()||!lstatSync(root).isDirectory())throw Error('attachment_cache_not_private_directory');
  return root;
}

export async function cachedAttachmentEvidence(directory:string, source:{sha256:string;format:string},
    pipeline:string, produce:(cached:any|undefined)=>Promise<any>, signal?:AbortSignal) {
  if(!/^[a-f0-9]{64}$/.test(source.sha256)||typeof source.format!=='string'||
      !source.format.startsWith('.')||/[\\/\0]/.test(source.format))throw Error('invalid_attachment_cache_identity');
  const key=hash(JSON.stringify({source,pipeline})), path=join(directory,key+'.json');
  // The same PDF can be admitted simultaneously by the two comparison lanes.
  // Only a live owning task performs the work; a cancelled/failed owner is not
  // reused as a successful result by the next lane.
  const previous=running.get(path);
  if(previous){
    let abort:(()=>void)|undefined;
    try{
      await Promise.race([previous,new Promise((_,reject)=>{
        abort=()=>reject(signal?.reason??Error('attachment_cache_cancelled'));
        if(signal?.aborted)abort();else signal?.addEventListener('abort',abort,{once:true});
      })]);
    }catch{/* The next owner may retry incomplete evidence. */}
    finally{if(abort)signal?.removeEventListener('abort',abort);}
    signal?.throwIfAborted();
    return cachedAttachmentEvidence(directory,source,pipeline,produce,signal);
  }
  const job=(async()=>{
    signal?.throwIfAborted();
    let cached:any;
    try {
      const stat=lstatSync(path);
      if(!stat.isFile()||stat.isSymbolicLink()||stat.nlink!==1)throw Error('invalid cache file');
      const value=JSON.parse(readFileSync(path,'utf8'));
      if(value.schema_version===1&&value.pipeline===pipeline&&value.source_sha256===source.sha256&&
        value.result?.sha256===source.sha256)cached=value.result;
    }catch{/* Missing, corrupt or obsolete cache always falls back to exact bytes. */}
    const result=await produce(cached);
    signal?.throwIfAborted();
    if(result?.sha256!==source.sha256)throw Error('attachment_cache_source_changed');
    const temporary=path+'.'+randomUUID()+'.tmp';
    writeFileSync(temporary,JSON.stringify({schema_version:1,pipeline,source_sha256:source.sha256,result}),{mode:0o600,flag:'wx'});
    renameSync(temporary,path);
    return result;
  })();
  running.set(path,job);
  try{return structuredClone(await job);}finally{if(running.get(path)===job)running.delete(path);}
}
