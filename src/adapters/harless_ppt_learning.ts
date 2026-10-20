/** Account-local PPT learning; the existing task runner remains the only model loop. */
import {spawn} from 'node:child_process';
import {createHash,randomUUID} from 'node:crypto';
import {appendFileSync,existsSync,lstatSync,mkdirSync,readFileSync,realpathSync,renameSync,writeFileSync} from 'node:fs';
import {dirname,isAbsolute,join,relative,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import type {Scene} from './harless_settings.ts';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const hash=(bytes:any)=>createHash('sha256').update(bytes).digest('hex');
const read=(path:string)=>JSON.parse(readFileSync(path,'utf8'));
const inside=(parent:string,path:string)=>{const rel=relative(parent,path);return rel!==''&&!rel.startsWith('..')&&!isAbsolute(rel);};
function checked(parent:string,path:string){
  const full=resolve(path),stat=lstatSync(full);
  if(!inside(parent,full)||realpathSync(full)!==full||stat.isSymbolicLink()||!stat.isFile()||stat.nlink!==1)throw Error('ppt_learning_path_invalid');
  return full;
}
function write(path:string,value:any){const tmp=path+'.'+randomUUID()+'.tmp';writeFileSync(tmp,JSON.stringify(value),{mode:0o600,flag:'wx'});renameSync(tmp,path);}
export function createPptLearning(config:{output:string;user:string;scope:string;python?:string;taskIds:()=>string[]}){
  const output=realpathSync(config.output),store=join(output,'learning','ppt-'+hash(config.user+'\0'+config.scope));
  let running:Promise<void>|undefined,again=false;
  const enabled=Boolean(config.python);
  function ensure(){mkdirSync(store,{recursive:true,mode:0o700});if(realpathSync(store)!==store)throw Error('ppt_learning_store_redirected');}
  function status(value:any){try{ensure();write(join(store,'status.json'),value);}catch{}}
  async function run(){
    ensure();write(join(store,'request.json'),{schema_version:1,output,user:config.user,scope:config.scope,task_ids:config.taskIds(),automatic_structural_learning:true});
    await new Promise<void>((done,fail)=>{
      const env:any={PATH:process.env.PATH,PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8'};
      for(const name of ['SYSTEMROOT','WINDIR','TMP','TEMP','TMPDIR'])if(process.env[name])env[name]=process.env[name];
      const child=spawn(config.python!,[join(root,'scripts/learn-web-ppt-tasks.py'),'--request',join(store,'request.json')],{cwd:root,env,stdio:['ignore','pipe','pipe']});
      let log='';child.stdout.on('data',b=>{if(log.length<128000)log+=String(b);});child.stderr.on('data',b=>{if(log.length<128000)log+=String(b);});
      const timer=setTimeout(()=>child.kill(),120000);child.on('error',error=>{clearTimeout(timer);fail(error);});
      child.on('close',code=>{clearTimeout(timer);try{write(join(store,'worker-log.json'),{code,log});code===0?done():fail(Error('ppt_learning_compiler_failed'));}catch(error){fail(error);}});
    });
  }
  const manager={
    schedule(){if(!enabled)return;again=true;if(running)return;running=(async()=>{while(again){again=false;try{await run();}catch(error){
      status({status:'failed',reason:(error as Error).message});
      try{ensure();write(join(store,'suspended.json'),{reason:'worker_failed'});}catch{/* A missing store already fails closed. */}
    }}})().finally(()=>{running=undefined;});},
    async idle(){await running;},
    negativeFeedback(snapshot:any){if(enabled&&snapshot?.scene==='ppt'){
      ensure();write(join(store,'suspended.json'),{reason:'negative_feedback'});
      write(join(store,'feedback-version.json'),{version:randomUUID()});manager.schedule();
    }},
    review(snapshot:any,body:any){
      if(!enabled)throw Error('ppt_learning_unavailable');
      const lane=snapshot?.lanes?.[body.lane],quality=body.quality;
      if(snapshot?.scene!=='ppt'||!['baseline','motif'].includes(body.lane)||!lane||lane.status!=='completed'||
        !lane.output_sha256||lane.output_sha256!==body.output_sha256||!lane.artifacts?.some((a:any)=>/\.pptx$/i.test(a.name)))throw Error('ppt_learning_review_version_changed');
      if(typeof body.allow_learning!=='boolean'||!quality||Object.keys(quality).sort().join(',')!=='scientific,usable,visual'||
        Object.values(quality).some(v=>typeof v!=='boolean')||typeof body.human_minutes!=='number'||!Number.isFinite(body.human_minutes)||body.human_minutes<0||body.human_minutes>100000)
        throw Error('ppt_learning_review_invalid');
      ensure();const journal=join(store,'reviews.jsonl');if(existsSync(journal))checked(store,journal);
      // Suspend before recording a withdrawal/negative review: the next task
      // cannot race the background worker and inherit revoked evidence.
      const veto=!body.allow_learning||Object.values(quality).includes(false);
      if(veto)write(join(store,'suspended.json'),{reason:'review_changed'});
      const event={schema_version:1,id:randomUUID(),user:config.user,scope:config.scope,comparison_id:snapshot.id,lane:body.lane,
        output_sha256:lane.output_sha256,quality,allow_learning:body.allow_learning,human_minutes:body.human_minutes,at:new Date().toISOString()};
      appendFileSync(journal,JSON.stringify(event)+'\n',{mode:0o600});
      // Change the generation after persisting the veto. An older worker can
      // never re-enable its stale snapshot even if it finishes concurrently.
      if(veto)write(join(store,'feedback-version.json'),{version:randomUUID()});
      manager.schedule();return {recorded:true,learning_allowed:body.allow_learning};
    },
    resolve(scene:Scene):Scene{
      if(!enabled||scene.id!=='ppt'||scene.ppt_execution_strategy!=='ppt_master'||!existsSync(join(store,'selected.json'))||existsSync(join(store,'suspended.json')))return scene;
      try{
        const pointer=read(checked(store,join(store,'selected.json')));
        const feedback=join(store,'feedback-version.json');
        if((pointer.feedback_version??null)!==(existsSync(feedback)?hash(readFileSync(checked(store,feedback))):null))throw Error('ppt_learning_feedback_changed');
        if(pointer.user!==config.user||pointer.scope!==config.scope||!/^round-[0-9]{4,}$/.test(pointer.round)||!['probation','active'].includes(pointer.phase))throw Error('ppt_learning_pointer_invalid');
        const folder=join(store,pointer.round),path=checked(folder,join(folder,'admission.json'));
        if(hash(readFileSync(path))!==pointer.admission_sha256)throw Error('ppt_learning_admission_changed');
        const admission=read(path),bundle=join(folder,'release'),info=admission.runtime;
        if(admission.user!==config.user||admission.scope!==config.scope)throw Error('ppt_learning_owner_changed');
        for(const [name,version] of Object.entries(admission.evidence_locks??{}))if(hash(readFileSync(checked(output,join(output,name))))!==version)throw Error('ppt_learning_evidence_changed');
        if(!Object.keys(admission.evidence_locks??{}).length)throw Error('ppt_learning_evidence_missing');
        if(pointer.phase==='active'){
          const promoted=checked(folder,join(folder,'promotion.json'));
          if(hash(readFileSync(promoted))!==pointer.promotion_sha256)throw Error('ppt_learning_promotion_changed');
          const promotion=read(promoted);
          if(promotion.round!==pointer.round||hash(readFileSync(checked(folder,join(folder,'evaluation.json'))))!==promotion.evaluation_sha256||!Object.keys(promotion.evidence_locks??{}).length)throw Error('ppt_learning_evaluation_changed');
          for(const [name,version] of Object.entries(promotion.evidence_locks))if(hash(readFileSync(checked(output,join(output,name))))!==version)throw Error('ppt_learning_evaluation_changed');
        }
        const entry=read(checked(bundle,join(bundle,'entry.json'))),cert=read(checked(bundle,join(bundle,'certification.json')));
        if(entry.runtime_kind!=='ppt_master_v2'||entry.scene!=='ppt'||entry.mode!=='execute'||cert.binding_policy!=='ppt_master_sources_v1'||cert.matching_policy!=='structural_only'||cert.certification_scope!=='independent_trace_structure')throw Error('ppt_learning_kind_invalid');
        const required=['library.json','online-manifest.json','task.json','tool-schemas.json','certification.json','source-evidence.json','learning-report.json'];
        if(required.some(name=>!(/^[a-f0-9]{64}$/.test(entry.files?.[name]??''))))throw Error('ppt_learning_files_missing');
        for(const [name,version] of Object.entries(entry.files)){
          if(name.includes('/')||name.includes('\\')||hash(readFileSync(checked(bundle,join(bundle,name))))!==version)throw Error('ppt_learning_release_changed');
        }
        for(const name of required.filter(n=>n!=='certification.json'))if(cert.file_locks?.[name]!==entry.files[name])throw Error('ppt_learning_file_lock_changed');
        if(!Object.keys(cert.code_locks??{}).length)throw Error('ppt_learning_code_missing');
        for(const [name,version] of Object.entries(cert.code_locks))if(hash(readFileSync(checked(root,join(root,name))))!==version)throw Error('ppt_learning_code_changed');
        const locks=Object.fromEntries(Object.entries(cert.code_locks).map(([name,v])=>[join(root,name),v]));
        const paths={runtime_library:'library.json',manifest:'online-manifest.json',task:'task.json',tool_schemas:'tool-schemas.json',certification_path:'certification.json'};
        for(const [key,name] of Object.entries(paths))if(info[key]!==join(bundle,name))throw Error('ppt_learning_descriptor_changed');
        if(info.runtime_kind!=='ppt_master_v2'||info.runtime_mode!=='execute'||info.runtime_library_sha256!==entry.files['library.json']||info.certification_sha256!==hash(readFileSync(join(bundle,'certification.json')))||
          info.certified_tool_schemas_sha256!==entry.files['tool-schemas.json']||JSON.stringify(info.certified_tool_schemas)!==JSON.stringify(read(join(bundle,'tool-schemas.json')))||
          JSON.stringify(info.certified_code_locks)!==JSON.stringify(locks)||info.binding_policy!==cert.binding_policy||info.matching_policy!==cert.matching_policy||info.certification_scope!==cert.certification_scope||info.quality_cost_promoted!==false)throw Error('ppt_learning_descriptor_changed');
        const {rsi_unavailable_reason,...base}=scene;
        return {...base,...info,learning_version:pointer.round,learning_phase:pointer.phase,config_sha256:hash(JSON.stringify([scene.config_sha256,pointer.admission_sha256,pointer.phase]))};
      }catch(error){status({status:'rejected',reason:(error as Error).message});return scene;}
    },
  };
  return manager;
}
