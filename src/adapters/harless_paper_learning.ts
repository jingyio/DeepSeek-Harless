/** Connect existing Web traces, the offline compiler and next-task library selection. */
import {spawn} from 'node:child_process';
import {createHash,randomUUID} from 'node:crypto';
import {existsSync,lstatSync,mkdirSync,readFileSync,realpathSync,renameSync,writeFileSync} from 'node:fs';
import {dirname,isAbsolute,join,relative,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import type {Scene} from './harless_settings.ts';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const hash=(bytes:any)=>createHash('sha256').update(bytes).digest('hex');
const inside=(parent:string,path:string)=>{const r=relative(parent,path);return r!==''&&!r.startsWith('..')&&!isAbsolute(r);};
const read=(path:string)=>JSON.parse(readFileSync(path,'utf8'));
function write(path:string,value:any){const temp=path+'.'+randomUUID()+'.tmp';writeFileSync(temp,JSON.stringify(value,null,2),{mode:0o600});renameSync(temp,path);}
function checked(parent:string,path:string){
  const full=resolve(path);
  if(!inside(parent,full)||realpathSync(full)!==full||lstatSync(full).isSymbolicLink()||!lstatSync(full).isFile())throw Error('learning_path_invalid');
  return full;
}
export function createPaperLearning(config:{output:string;user:string;scope:string;python?:string;taskIds:()=>string[]}){
  const output=realpathSync(config.output);
  const store=join(output,'learning',hash(config.user+'\0'+config.scope));
  let running:Promise<void>|undefined,again=false;
  const enabled=Boolean(config.python);
  const status=(value:any)=>{try{mkdirSync(store,{recursive:true,mode:0o700});if(realpathSync(store)===store)write(join(store,'status.json'),value);}catch{}};
  async function run(){
    mkdirSync(store,{recursive:true,mode:0o700});
    if(realpathSync(store)!==store)throw Error('learning_store_redirected');
    const request=join(store,'request.json');
    write(request,{schema_version:1,output,user:config.user,scope:config.scope,task_ids:config.taskIds()});
    await new Promise<void>((done,fail)=>{
      const env:any={PATH:process.env.PATH,PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8'};
      for(const name of ['SYSTEMROOT','WINDIR','TMP','TEMP','TMPDIR'])if(process.env[name])env[name]=process.env[name];
      const child=spawn(config.python!,[join(root,'scripts/learn-web-paper-tasks.py'),'--request',request],{cwd:root,env,stdio:['ignore','pipe','pipe']});
      let log='';const collect=(bytes:any)=>{if(log.length<128000)log+=String(bytes);};
      child.stdout.on('data',collect);child.stderr.on('data',collect);
      const timeout=setTimeout(()=>child.kill(),120000);
      child.on('error',fail);child.on('close',code=>{
        clearTimeout(timeout);
        try{write(join(store,'worker-log.json'),{code,log});code===0?done():fail(Error('learning_compiler_failed'));}
        catch(error){fail(error);}
      });
    });
  }
  return {
    schedule(){
      if(!enabled)return;
      again=true;if(running)return;
      running=(async()=>{while(again){again=false;try{await run();}catch(error){status({status:'failed',reason:(error as Error).message});}}})().finally(()=>{running=undefined;});
    },
    async idle(){await running;},
    resolve(scene:Scene):Scene{
      if(!enabled||scene.id!=='paper-proofreading'||!existsSync(join(store,'latest.json')))return scene;
      try{
        const pointer=read(checked(store,join(store,'latest.json')));
        if(pointer.user!==config.user||pointer.scope!==config.scope||!/^round-[0-9]{4,}$/.test(pointer.round))throw Error('learning_pointer_invalid');
        const folder=join(store,pointer.round),path=checked(store,join(folder,'admission.json'));
        if(hash(readFileSync(path))!==pointer.admission_sha256)throw Error('learning_admission_changed');
        const admission=read(path),bundle=join(folder,'release');
        // The trusted compiler uses the same full product admission before
        // publishing. Recheck every byte/code lock, not just the pointer.
        const entry=read(checked(bundle,join(bundle,'entry.json')));
        if(entry.runtime_kind!=='paper_document_read_v1'||entry.scene!==scene.id||entry.mode!=='execute')throw Error('learning_kind_invalid');
        const required=['library.json','online-manifest.json','task.json','tool-schemas.json','certification.json','source-evidence.json','learning-report.json'];
        if(!entry.files||required.some(name=>!(/^[a-f0-9]{64}$/.test(entry.files[name]??''))))throw Error('learning_files_missing');
        for(const [name,version] of Object.entries(entry.files)){
          if(name.includes('/')||name.includes('\\')||hash(readFileSync(checked(bundle,join(bundle,name))))!==version)throw Error('learning_release_changed');
        }
        const cert=read(checked(bundle,join(bundle,'certification.json')));
        if(cert.schema_version!==1||cert.scene!==scene.id||cert.binding_policy!=='approved_uploaded_reads_v1'||
          cert.matching_policy!=='structural_only'||cert.certification_scope!=='independent_trace_structure'||
          !cert.code_locks||!Object.keys(cert.code_locks).length)throw Error('learning_certificate_invalid');
        for(const name of required.filter(name=>name!=='certification.json'))if(cert.file_locks?.[name]!==entry.files[name])throw Error('learning_file_lock_mismatch');
        for(const [name,version] of Object.entries(cert.code_locks)){
          if(hash(readFileSync(checked(root,join(root,name))))!==version)throw Error('learning_code_changed');
        }
        const info=admission.runtime;
        if(info.runtime_kind!=='paper_document_read_v1'||info.certification_sha256!==hash(readFileSync(join(bundle,'certification.json')))||
          info.runtime_library_sha256!==hash(readFileSync(join(bundle,'library.json'))))throw Error('learning_descriptor_invalid');
        const actualSchemas=read(join(bundle,'tool-schemas.json'));
        const locks=Object.fromEntries(Object.entries(cert.code_locks).map(([name,value])=>[join(root,name),value]));
        if(info.certification_path!==join(bundle,'certification.json')||info.manifest!==join(bundle,'online-manifest.json')||
          info.task!==join(bundle,'task.json')||info.tool_schemas!==join(bundle,'tool-schemas.json')||
          info.certified_tool_schemas_sha256!==entry.files['tool-schemas.json']||
          JSON.stringify(info.certified_tool_schemas)!==JSON.stringify(actualSchemas)||
          Object.keys(locks).length!==Object.keys(info.certified_code_locks??{}).length||
          Object.entries(locks).some(([name,value])=>info.certified_code_locks[name]!==value)||
          info.binding_policy!==cert.binding_policy||info.matching_policy!==cert.matching_policy||
          info.certification_scope!==cert.certification_scope||info.quality_cost_promoted!==false)throw Error('learning_descriptor_changed');
        const allowed=['runtime_kind','runtime_mode','runtime_library','runtime_library_sha256','manifest','task','tool_schemas',
          'certified_tool_schemas','certified_tool_schemas_sha256','matching_policy','binding_policy','certification_path',
          'certification_sha256','certified_code_locks','certification_scope','quality_cost_promoted'];
        const runtime=Object.fromEntries(allowed.filter(key=>key in info).map(key=>[key,info[key]]));
        for(const key of ['runtime_library','manifest','task','tool_schemas','certification_path'])checked(bundle,runtime[key]);
        const {rsi_unavailable_reason,...base}=scene;
        return {...base,...runtime,learning_version:pointer.round,config_sha256:hash(JSON.stringify([scene.config_sha256,pointer.admission_sha256]))};
      }catch(error){status({status:'rejected',reason:(error as Error).message});return scene;}
    },
  };
}
