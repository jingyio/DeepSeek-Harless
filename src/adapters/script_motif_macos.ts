/** Explicit local experiment backend. This is not a general macOS deployment. */
import {existsSync,mkdirSync,realpathSync,symlinkSync,lstatSync} from 'node:fs';
import {dirname,join} from 'node:path';

export function localScriptArgv(layout:any,command:string,cwd:string,python:string,node:string,readOnly:boolean,resources:any){
  if(process.platform!=='darwin'||process.env.SSS_LOCAL_SCRIPT_EXPERIMENT!=='1'||!existsSync('/usr/bin/sandbox-exec'))throw Error('local_script_sandbox_not_enabled');
  // The existing tool protocol uses /work. Seatbelt restricts host paths instead
  // of mounting a namespace; translate only this protocol's virtual prefixes.
  const mappings=[['/work/inputs',layout.inputs],['/work/outputs',layout.outputs],['/work',layout.scratch]];
  function translate(value:string){return value.replace(/\/work(?:\/inputs|\/outputs)?(?=\/|[\s'"),;\]]|$)/g,match=>mappings.find(([v])=>v===match)![1]);}
  for(const [name,target] of [['inputs',layout.inputs],['outputs',layout.outputs]]){
    const link=join(layout.scratch,name);
    if(!existsSync(link))symlinkSync(target,link);
    if(!lstatSync(link).isSymbolicLink()||realpathSync(link)!==realpathSync(target))throw Error('local_virtual_path_collision');
  }
  // Learned scripts get a fresh disposable temp root. Their inputs, scratch and
  // delivered outputs all remain read-only. No credentials are inherited.
  const temp=resources.ephemeralTemp?join(layout.temp,'script-'+crypto.randomUUID()):layout.temp;
  mkdirSync(temp,{recursive:true,mode:0o700});
  const roots=new Set(['/usr','/bin','/sbin','/System','/private/etc',layout.inputs,layout.scratch,layout.outputs,temp,
    dirname(dirname(python)),dirname(dirname(realpathSync(python))),dirname(dirname(realpathSync(node)))]);
  const q=(s:string)=>JSON.stringify(realpathSync(s));
  const parents=new Set<string>();
  for(const root of [...roots,process.cwd()])for(let parent=dirname(root);parent!=='/';parent=dirname(parent))parents.add(parent);
  const rules=['(version 1)','(deny default)','(allow process* signal sysctl-read mach-lookup)',
    '(allow file-read-metadata)','(allow file-read* (literal "/"))',...Array.from(parents).filter(existsSync).map(p=>`(allow file-read* (literal ${q(p)}))`),...Array.from(roots).filter(existsSync).map(p=>`(allow file-read* (subpath ${q(p)}))`),
    '(allow file-read* file-write* (literal "/dev/null") (literal "/dev/urandom") (literal "/dev/random"))',
    `(allow file-write* (subpath ${q(temp)}))`];
  if(!readOnly)rules.push(...[layout.scratch,layout.outputs].map(p=>`(allow file-write* (subpath ${q(p)}))`));
  if(resources.network!=='none')rules.push('(allow network*)');
  const env=['/usr/bin/env','-i',`HOME=${layout.scratch}`,`PATH=${dirname(python)}:${dirname(node)}:/usr/bin:/bin:/usr/sbin:/sbin`,
    `TMPDIR=${temp}`,`PYTHONDONTWRITEBYTECODE=1`,`PYTHONUTF8=1`,`LANG=en_US.UTF-8`,`NO_COLOR=1`];
  const quote=(s:string)=>"'"+s.replaceAll("'","'\\''")+"'";
  // Apple's old Bash writes heredocs to host /tmp regardless of TMPDIR. A
  // single Python heredoc has identical -c semantics and needs no such write.
  const heredoc=/(\bpython3?\s+)-\s+<<['"]?([A-Za-z_]\w*)['"]?\n([\s\S]*?)\n\2\s*$/.exec(command);
  if(heredoc)command=command.slice(0,heredoc.index)+heredoc[1]+'-c '+quote(heredoc[3]);
  const shell='cd '+quote(translate(cwd))+' && '+translate(command);
  return [...env,'/usr/bin/sandbox-exec','-p',rules.join('\n'),'/bin/bash','--noprofile','--norc','-c',shell];
}
