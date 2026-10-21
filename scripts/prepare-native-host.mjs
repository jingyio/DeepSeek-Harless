/** Upgrade only an isolated candidate's native host rows. Never runs a service. */
import {readFileSync,writeFileSync,renameSync,unlinkSync,lstatSync,realpathSync,existsSync} from 'node:fs';
import {resolve,dirname,join,isAbsolute,relative} from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {composeNativeHost} from '../src/adapters/geneloop_native_host.mjs';

const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const inside=(root,path)=>{const rel=relative(root,path);return rel===''||!rel.startsWith('..')&&!isAbsolute(rel);};
function fixed(path,directory=false){
 if(typeof path!=='string'||!isAbsolute(path))throw Error('Configuration requires fixed absolute paths');
 const absolute=resolve(path);
 for(let cursor=absolute;;cursor=dirname(cursor)){
  if(lstatSync(cursor).isSymbolicLink())throw Error('Symlinked candidate/configuration paths are refused');
  if(dirname(cursor)===cursor)break;
 }
 const stat=lstatSync(absolute);
 if(directory?!stat.isDirectory():!stat.isFile()||stat.nlink!==1)throw Error('Configuration must use private unlinked regular files');
 if(process.platform!=='win32'&&!directory&&(stat.mode&0o077))throw Error('Configuration requires mode 600');
 if(realpathSync(absolute)!==absolute)throw Error('Configuration path alias refused');
 return absolute;
}
const read=path=>JSON.parse(readFileSync(path,'utf8'));
function references(plan){
 if(plan?.version!==1||!Array.isArray(plan.owner?.argv)||!Array.isArray(plan.gateway?.argv))throw Error('Invalid service plan');
 const positions=plan.owner.argv.flatMap((value,index)=>value==='--patch'?[index]:[]);
 if(positions.length!==1)throw Error('Exactly one owner host patch is required');
 return {patch:fixed(plan.owner.argv[positions[0]+1]),gateway:fixed(plan.gateway_config),policy:fixed(plan.owner.env?.SSS_WEB_POLICY)};
}

export function prepareNativeHost({planPath,root,apply=false}){
 const observed=new Map(),track=path=>{
  const checked=fixed(path),bytes=readFileSync(checked),digest=hash(bytes);
  if(observed.has(checked)&&observed.get(checked)!==digest)throw Error('Configuration changed during preparation');
  observed.set(checked,digest);return JSON.parse(bytes.toString('utf8'));
 };
 const sourceRoot=fixed(root,true),candidate=fixed(planPath),plan=track(candidate),refs=references(plan),directory=dirname(candidate);
 const state=fixed(plan.state_dir,true),currentPath=fixed(join(state,'current.json'));
 if(inside(state,candidate)||dirname(refs.patch)!==directory||dirname(refs.gateway)!==directory||dirname(refs.policy)!==directory)
  throw Error('Upgrade requires separate candidate configuration files beside its plan');
 [candidate,refs.patch,refs.gateway,refs.policy].forEach(track);
 const protectedPaths=new Set([currentPath]);
 const protectPlan=(value,path)=>{
  if(path)protectedPaths.add(fixed(path));
  const prior=references(value);Object.values(prior).forEach(file=>protectedPaths.add(file));
  const gateway=track(prior.gateway),priorRoot=gateway.memberSceneDeployment?.projectRoot??dirname(gateway.sourceDir);
  if(fixed(priorRoot,true)===sourceRoot)throw Error('Candidate cannot reuse active or previous source checkout');
 };
 const current=track(currentPath);
 protectPlan(current.plan);
 if(typeof current.rollback_plan!=='string')throw Error('Current rollback plan is required');
 protectPlan(track(current.rollback_plan),current.rollback_plan);
 const previousPath=join(state,'previous.json');
 if(existsSync(previousPath)){
  protectedPaths.add(fixed(previousPath));const previous=track(previousPath);
  if(typeof previous.plan!=='string')throw Error('Invalid previous release record');
  protectPlan(track(previous.plan),previous.plan);
 }
 for(const file of protectedPaths)track(file);
 if([candidate,...Object.values(refs)].some(file=>protectedPaths.has(file)))throw Error('Cannot modify active or rollback configuration');
 const config=read(refs.gateway),policy=read(refs.policy),sourceDir=join(sourceRoot,'src');
 if(config.sourceDir!==sourceDir||config.memberSceneDeployment?.projectRoot!==sourceRoot||
    policy.command_resources?.projectRoot!==sourceRoot||plan.gateway.cwd!==sourceRoot||
    !plan.gateway.argv.includes(join(sourceRoot,'scripts/harless_gateway.mjs'))||!plan.gateway.argv.includes(refs.gateway))
  throw Error('Candidate source references do not match the declared checkout');
 const activeRefs=references(current.plan),activeConfig=read(activeRefs.gateway),activePolicy=read(activeRefs.policy);
 const same=(a,b,keys)=>keys.every(key=>JSON.stringify(a?.[key])===JSON.stringify(b?.[key]));
 if(policy.output!==plan.owner_output||!same(plan,current.plan,['state_dir','owner_output'])||plan.owner.cwd!==current.plan.owner.cwd||
    !same(plan.owner.env,current.plan.owner.env,['HOME','DSH_HOME'])||
    !same(config,activeConfig,['dataDir','membersDir','ownerTokenFile','ownerPort','port','publicOrigin','adminToken','apiKey','scopedBudgetPort','upstreamBrokerPort','upstreamControlPort'])||
    !same(policy,activePolicy,['output','endpoint','control_endpoint','control_token','budget_broker_endpoint','budget_usd','run_budget_usd','request_limit','run_request_limit','max_output_tokens'])||
    !same(config.memberPolicy,activeConfig.memberPolicy,['output']))throw Error('Candidate persistent data, authentication or budget binding changed');
 const oldPatch=read(refs.patch),nextPatch=composeNativeHost(oldPatch,sourceDir);
 const nextConfig={...config,memberPatch:composeNativeHost(config.memberPatch,sourceDir)};
 const encode=value=>Buffer.from(JSON.stringify(value,null,2)+'\n');
 const changes=[[refs.patch,encode(nextPatch)],[refs.gateway,encode(nextConfig)]];
 const manifestPath=join(directory,'native-host-manifest.json');
 if(existsSync(manifestPath))throw Error('Candidate host manifest already exists; preserve prior evidence');
 const manifest={version:1,kind:'native-host-composition',applied:apply,service_started:false,service_stopped:false,
  source_sha:plan.source_sha??null,files:Object.fromEntries(changes.map(([path,bytes])=>[path,{before:observed.get(path),after:hash(bytes)}])),
  protected:Object.fromEntries([...observed].filter(([file])=>!changes.some(([path])=>path===file)))};
 if(!apply)return manifest;
 // Recheck all read configurations immediately before replacing either file.
 for(const [file,digest] of observed)if(fixed(file)!==file||hash(readFileSync(file))!==digest)throw Error('Configuration changed during preparation');
 const staged=[],originals=new Map(changes.map(([file])=>[file,readFileSync(file)]));
 try{
  for(const [file,bytes] of changes){const temp=file+'.native-'+randomUUID()+'.tmp';writeFileSync(temp,bytes,{flag:'wx',mode:0o600});staged.push([file,temp]);}
  for(const [file,temp] of staged)renameSync(temp,file);
  for(const [file,digest] of Object.entries(manifest.protected))if(hash(readFileSync(file))!==digest)throw Error('Protected configuration changed');
  writeFileSync(manifestPath,encode(manifest),{flag:'wx',mode:0o600});
 }catch(error){
  // Only restore our own replacements, never overwrite a concurrent writer.
  for(const [file,bytes] of changes)if(hash(readFileSync(file))===hash(bytes)){
   const temp=file+'.restore-'+randomUUID()+'.tmp';writeFileSync(temp,originals.get(file),{flag:'wx',mode:0o600});renameSync(temp,file);
  }
  throw error;
 }finally{for(const [,temp] of staged)if(existsSync(temp))unlinkSync(temp);}
 return manifest;
}

if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 try{
  const args=process.argv.slice(2),options={apply:false};
  for(let i=0;i<args.length;i++){
   if(args[i]==='--apply')options.apply=true;
   else if(['--plan','--root'].includes(args[i])&&args[i+1])options[args[i++]==='--plan'?'planPath':'root']=args[i];
   else throw Error('Usage: node scripts/prepare-native-host.mjs --plan ABSOLUTE_CANDIDATE --root ABSOLUTE_CHECKOUT [--apply]');
  }
  const result=prepareNativeHost(options);
  process.stdout.write(JSON.stringify({applied:result.applied,service_started:false,service_stopped:false,
   source_sha:result.source_sha,manifest_sha256:hash(JSON.stringify(result,null,2)+'\n')})+'\n');
 }catch(error){process.stderr.write('Native host preparation rejected: '+(error instanceof SyntaxError?'Invalid configuration JSON':error.message)+'\n');process.exitCode=1;}
}
