import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,rmSync,realpathSync,linkSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,dirname} from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {composeNativeHost} from '../src/adapters/geneloop_native_host.mjs';
import {prepareNativeHost} from '../scripts/prepare-native-host.mjs';
const hash=value=>createHash('sha256').update(value).digest('hex');
const write=(file,value)=>writeFileSync(file,JSON.stringify(value,null,2)+'\n',{mode:0o600});
const read=file=>JSON.parse(readFileSync(file,'utf8'));
const flat=rows=>rows.flatMap(row=>[row,...(row.insert?flat(row.insert):[])]);

function fixture(t){
 const base=realpathSync(mkdtempSync(join(tmpdir(),'geneloop-native-host-')));t.after(()=>rmSync(base,{recursive:true,force:true}));
 const state=join(base,'service'),source=join(base,'candidate-code'),priorSource=join(base,'active-code'),candidateDir=join(base,'candidate'),priorDir=join(base,'active');
 for(const path of [state,source,priorSource,candidateDir,priorDir])mkdirSync(path,{mode:0o700});
 function release(directory,root){
  const configPath=join(directory,'gateway.json'),policyPath=join(directory,'owner-policy.json'),patchPath=join(directory,'owner.patch.yml');
  const sourceUri=pathToFileURL(join(root,'src')).href+'/',patch=[{id:'llm-retry',disabled:true},
   {id:'web-runtime',config:{openBrowser:false,trustedHosts:['app.example.com']}},
   {insert:[{id:'geneloop-shell',name:sourceUri+'adapters/geneloop_shell.ts'},
    {id:'geneloop-web-search',name:sourceUri+'adapters/geneloop_web_search.ts'}]}];
  const config={sourceDir:join(root,'src'),memberSceneDeployment:{projectRoot:root},memberPatch:patch,
   memberPolicy:{output:'/user/tasks'},dataDir:join(base,'accounts'),membersDir:join(base,'members'),
   adminToken:'PRIVATE_DIAGNOSTIC_CREDENTIAL',apiKey:'UNCHANGED_DIAGNOSTIC_CREDENTIAL',port:33101,ownerPort:33102,scopedBudgetPort:33115};
  const policy={output:join(base,'tasks'),budget_usd:null,request_limit:null,control_token:'PRIVATE_DIAGNOSTIC_CONTROL',command_resources:{projectRoot:root}};
  const plan={version:1,source_sha:'a'.repeat(40),state_dir:state,gateway_config:configPath,owner_output:policy.output,
   owner:{argv:[process.execPath,'existing-runtime','--patch',patchPath],cwd:join(base,'work'),env:{SSS_WEB_POLICY:policyPath,HOME:join(base,'home'),DSH_HOME:join(base,'dsh')}},
   gateway:{argv:[process.execPath,join(root,'scripts/harless_gateway.mjs'),configPath],cwd:root,env:{}}};
  const planPath=join(directory,'service.json');write(configPath,config);write(policyPath,policy);write(patchPath,patch);write(planPath,plan);
  return {planPath,configPath,policyPath,patchPath,plan,config,patch};
 }
 const current=release(priorDir,priorSource),candidate=release(candidateDir,source);
 write(join(state,'current.json'),{plan:current.plan,rollback_plan:current.planPath,processes:{}});
 write(join(state,'previous.json'),{plan:current.planPath});
 return {base,state,source,priorSource,current,candidate};
}

test('native host composition is idempotent, preserves shell/search and has one provider per native seam',t=>{
 const f=fixture(t),uri=pathToFileURL(join(f.source,'src')).href+'/',before=JSON.stringify(f.candidate.patch);
 const patch=composeNativeHost([...f.candidate.patch,{id:'fs-sandbox',name:'@deepseek-ai/dsh-fs-sandbox'},
  {id:'llm-retry',disabled:true},{insert:[{id:'geneloop-native-work',name:uri+'adapters/geneloop_native_work.ts'}]}],join(f.source,'src'));
 assert.equal(JSON.stringify(f.candidate.patch),before);assert.deepEqual(composeNativeHost(patch,join(f.source,'src')),patch);
 const rows=flat(patch);for(const id of ['llm-retry','compaction-basic','command-compact','goal','goal-round-driver','fs-sandbox','subprocess','geneloop-native-work'])assert.equal(rows.filter(row=>row.id===id).length,1,id);
 assert.equal(rows.find(row=>row.id==='llm-retry').disabled,false);assert.equal(rows.find(row=>row.id==='command-compact').disabled,false);
 assert.equal(rows.find(row=>row.id==='goal').disabled,true);assert.equal(rows.find(row=>row.id==='compaction-basic').disabled,true);
 for(const id of ['geneloop-shell','geneloop-web-search','web-runtime'])assert.deepEqual(rows.find(row=>row.id===id),flat(f.candidate.patch).find(row=>row.id===id));
 assert.equal(rows.find(row=>row.id==='fs-sandbox').name,uri+'adapters/geneloop_fs.ts');
});

test('member composition maps top-level and inserted modules and refuses stale/traversing URIs',t=>{
 const f=fixture(t),patch=composeNativeHost(f.candidate.patch,join(f.source,'src'),{member:true});
 assert.deepEqual(composeNativeHost(patch,join(f.source,'src'),{member:true}),patch);
 assert.ok(flat(patch).filter(row=>row.name?.startsWith('file:')).every(row=>row.name.startsWith('file:///app/src/')));
 assert.equal(flat(patch).find(row=>row.id==='subprocess').name,'file:///app/src/adapters/geneloop_fs_search.ts');
 for(const name of ['file:///foreign/source/plugin.ts',pathToFileURL(join(f.source,'src')).href+'/../escape.ts'])
  assert.throws(()=>composeNativeHost([{id:'other',name}],join(f.source,'src'),{member:true}),/source|URI/);
});

test('candidate default dry-run writes nothing, explicit apply changes only native rows and hashes all preserved configuration',t=>{
 const f=fixture(t),files=[...Object.values(f.current).filter(value=>typeof value==='string'),f.candidate.planPath,f.candidate.policyPath,join(f.state,'current.json'),join(f.state,'previous.json')];
 const protectedBytes=new Map(files.map(file=>[file,readFileSync(file)]));
 const oldConfig=readFileSync(f.candidate.configPath),oldPatch=readFileSync(f.candidate.patchPath);
 const preview=prepareNativeHost({planPath:f.candidate.planPath,root:f.source});assert.equal(preview.applied,false);
 assert.deepEqual(readFileSync(f.candidate.configPath),oldConfig);assert.deepEqual(readFileSync(f.candidate.patchPath),oldPatch);
 const result=prepareNativeHost({planPath:f.candidate.planPath,root:f.source,apply:true});
 assert.equal(result.applied,true);assert.equal(result.service_started,false);assert.equal(result.service_stopped,false);
 for(const [file,bytes] of protectedBytes)assert.deepEqual(readFileSync(file),bytes);
 const actual=read(f.candidate.configPath),{memberPatch:beforePatch,...before}=f.candidate.config,{memberPatch:afterPatch,...after}=actual;
 assert.deepEqual(after,before);assert.equal(flat(afterPatch).find(row=>row.id==='llm-retry').disabled,false);
 for(const [file,value] of Object.entries(result.files))assert.equal(hash(readFileSync(file)),value.after);
 const manifest=readFileSync(join(dirname(f.candidate.planPath),'native-host-manifest.json'),'utf8');
 assert.doesNotMatch(manifest,/PRIVATE_DIAGNOSTIC|UNCHANGED_DIAGNOSTIC/);
 assert.throws(()=>prepareNativeHost({planPath:f.candidate.planPath,root:f.source,apply:true}),/manifest already exists/);
});

test('active or rollback sources, linked config, altered auth/budget, or mismatched roots are refused without writes',t=>{
 const f=fixture(t),options={planPath:f.candidate.planPath,root:f.source,apply:true};
 assert.throws(()=>prepareNativeHost({...options,root:f.priorSource}),/active or previous/);
 const old=readFileSync(f.candidate.configPath),config=read(f.candidate.configPath);
 write(f.candidate.configPath,{...config,adminToken:'changed'});const changed=readFileSync(f.candidate.configPath);
 assert.throws(()=>prepareNativeHost(options),/authentication or budget/);assert.deepEqual(readFileSync(f.candidate.configPath),changed);
 writeFileSync(f.candidate.configPath,old);
 write(f.candidate.configPath,{...config,sourceDir:join(f.base,'foreign')});assert.throws(()=>prepareNativeHost(options),/source references/);writeFileSync(f.candidate.configPath,old);
 const linked=join(f.base,'linked-patch');linkSync(f.candidate.patchPath,linked);assert.throws(()=>prepareNativeHost(options),/unlinked regular files/);
 assert.equal(read(f.candidate.patchPath).find(row=>row.id==='llm-retry').disabled,true);
});

test('launcher stdin composition and candidate dry-run CLI do not print credentials or change files',t=>{
 const f=fixture(t),helper=fileURLToPath(new URL('../src/adapters/geneloop_native_host.mjs',import.meta.url));
 const normalized=spawnSync(process.execPath,[helper,'--source-dir',join(f.source,'src')],{input:JSON.stringify(f.candidate.patch),encoding:'utf8'});
 assert.equal(normalized.status,0,normalized.stderr);assert.deepEqual(JSON.parse(normalized.stdout),composeNativeHost(f.candidate.patch,join(f.source,'src')));
 const malformed=spawnSync(process.execPath,[helper,'--source-dir',join(f.source,'src')],{input:'PRIVATE_DIAGNOSTIC_CREDENTIAL',encoding:'utf8'});
 assert.equal(malformed.status,1);assert.doesNotMatch(malformed.stderr,/PRIVATE_DIAGNOSTIC_CREDENTIAL/);
 const before=readFileSync(f.candidate.configPath),script=fileURLToPath(new URL('../scripts/prepare-native-host.mjs',import.meta.url));
 const result=spawnSync(process.execPath,[script,'--plan',f.candidate.planPath,'--root',f.source],{encoding:'utf8'});
 assert.equal(result.status,0,result.stderr);assert.equal(JSON.parse(result.stdout).applied,false);
 assert.doesNotMatch(result.stdout+result.stderr,/PRIVATE_DIAGNOSTIC|UNCHANGED_DIAGNOSTIC/);assert.deepEqual(readFileSync(f.candidate.configPath),before);
});
