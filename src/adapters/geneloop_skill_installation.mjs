/** Administrator-selected immutable skill bytes, shared by MCP and Bash. */
import {readFileSync,readdirSync,lstatSync,realpathSync} from 'node:fs';
import {resolve,join,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const project=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const cached=new Map();
export function pptMasterInstallation(root, projectRoot=project){
  if(!root)return null;
  const lockPath=join(projectRoot,'scenarios/ppt_master/skill-lock.json');
  const lockBytes=readFileSync(lockPath),key=root+':'+sha(lockBytes);
  if(cached.has(key))return cached.get(key);
  if(resolve(root)!==root || realpathSync(root)!==root || lstatSync(root).isSymbolicLink())throw Error('invalid ppt-master installation');
  const lock=JSON.parse(lockBytes);
  if(lock.schema_version!==1 || lock.version!=='6.6.0' || !lock.files ||
      sha(JSON.stringify(Object.fromEntries(Object.entries(lock.files).sort(([a],[b])=>a<b?-1:a>b?1:0)))
        .replace(/[\u007f-\uffff]/g,c=>'\\u'+c.charCodeAt(0).toString(16).padStart(4,'0')))!==lock.package_sha256)
    throw Error('invalid ppt-master package lock');
  const seen=new Set();
  const walk=(directory,prefix='')=>{
    for(const entry of readdirSync(directory,{withFileTypes:true})){
      const name=prefix+entry.name,path=join(directory,entry.name);
      if(entry.isSymbolicLink())throw Error('ppt-master installation link rejected');
      if(entry.isDirectory())walk(path,name+'/');
      else if(!entry.isFile() || !Object.hasOwn(lock.files,name) || sha(readFileSync(path))!==lock.files[name])
        throw Error('ppt-master installation bytes changed: '+name);
      else seen.add(name);
    }
  };walk(root);
  if(seen.size!==Object.keys(lock.files).length)throw Error('incomplete ppt-master installation');
  const value={source:root,target:'/opt/geneloop/ppt-master',sha256:lock.package_sha256};
  cached.set(key,value);return value;
}
