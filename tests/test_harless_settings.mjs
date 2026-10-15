import test from 'node:test';
import {mkdtempSync,mkdirSync,readFileSync,writeFileSync,rmSync,realpathSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
const options={skip:!process.features?.typescript};
test('RSI defaults On, mode is independent, and unavailable Execute is guarded',options,async()=>{
 const {initialSelection,changeSelection,sceneCatalog}=await import('../src/adapters/harless_settings.ts');
 const scenes=sceneCatalog([{id:'example',label:'示例',preset:'sss-task',allowed_tools:['mcp__demo__read']}]);
 let state=initialSelection('example','shadow');
 const change=patch=>state=changeSelection(state,patch,scenes,()=>null);
 assert.equal(initialSelection('example','baseline').rsi,true);
 change({mode:'execute'});change({rsi:false});assert.equal(state.mode,'execute');
 change({mode:'baseline'});assert.equal(state.rsi,false);
 change({mode:'shadow'});assert.equal(state.rsi,false);
 change({rsi:true});assert.equal(state.mode,'shadow');
 change({mode:'baseline',rsi:true});assert.equal(state.rsi,true);
 assert.throws(()=>changeSelection(state,{mode:'execute'},scenes,()=> 'no_certified_library'),/no_certified_library/);
 assert.throws(()=>change({scene:'../../private'}),/未登记/);assert.throws(()=>change({manifest:'private'}),/只支持/);
});
test('Scene catalog rejects duplicate identity, arbitrary presets and invalid tool scope',options,async()=>{
 const {sceneCatalog}=await import('../src/adapters/harless_settings.ts');
 const scene={id:'example',label:'示例',preset:'sss-task',allowed_tools:['mcp__demo__read']};
 for(const rows of [[scene,scene],[{...scene,preset:'root'}],[{...scene,allowed_tools:['bash']}],[{...scene,id:'../../'}]])assert.throws(()=>sceneCatalog(rows));
});
test('PPT binding uses approved current versions and never guesses a source handle', {skip:!process.features?.typescript}, async()=>{
  const {bindUploadedPptTask,structuralOnlySimilarity}=await import('../src/adapters/harless_rsi_binding.ts');
  const root=realpathSync(mkdtempSync(join(tmpdir(),'ppt-binding-')));mkdirSync(join(root,'inputs'));
  try{
    const path=join(root,'inputs','paper.pdf'),data=Buffer.from('approved PDF bytes');writeFileSync(path,data);
    const version=createHash('sha256').update(data).digest('hex');
    const request={task_id:'task-a',session_id:'session-a'};
    const job={job_id:'task-a',instruction:'A new actual instruction',inputs:[{document_id:'doc_1',path,version_sha256:version}]};
    writeFileSync(join(root,'job.json'),JSON.stringify(job));
    const inputs=[{document_id:'doc_1',file:'paper.pdf',version_sha256:version}];
    const manifest={version_fields:{mcp__ppt__pin_source:'version_sha256',mcp__ppt__read_source:'version_sha256'}};
    const binding=bindUploadedPptTask(root,inputs,request,manifest);
    assert.deepEqual(binding.bindings,{});assert.equal(binding.source_versions.mcp__ppt__read_source,version);
    assert.equal(binding.task_id,'task-a');assert.equal(binding.session_id,'session-a');
    const {parseStructuredTask}=await import('../src/motif_core/online_skill_runtime.mjs');
    const certified=JSON.parse(readFileSync(new URL('../motif-libraries/ppt/online-manifest.json',import.meta.url)));
    for(const instruction of ['上下文\n当前请求','长请求'.repeat(800)]){
      job.instruction=instruction;writeFileSync(join(root,'job.json'),JSON.stringify(job));
      const actual=bindUploadedPptTask(root,inputs,request,certified);
      assert.doesNotThrow(()=>parseStructuredTask(actual,certified));
      assert.equal(JSON.parse(readFileSync(join(root,'job.json'))).instruction,instruction,'full model request is never truncated');
    }
    assert.throws(()=>bindUploadedPptTask(root,inputs,{...request,task_id:'foreign-task'},manifest),/job_scope/);
    writeFileSync(path,'changed bytes');
    assert.throws(()=>bindUploadedPptTask(root,inputs,request,manifest),/source_version/);
    await assert.rejects(structuralOnlySimilarity(),/semantic_matching_disabled/);
  }finally{rmSync(root,{recursive:true,force:true});}
});

test('Management is the public Files shortcut and the old Files token still selects the same scene',options,async()=>{
 const {sceneShortcut,parseSceneShortcut}=await import('../src/adapters/harless_settings.ts');
 const scenes=[{id:'files'},{id:'research-data-analysis'},{id:'ppt'},{id:'paper-proofreading'},{id:'new-scene'}];
 assert.equal(sceneShortcut(scenes[0]),'management');
 assert.deepEqual(parseSceneShortcut('/management 盘点上传文件',scenes),{scene:'files',text:'盘点上传文件'});
 assert.deepEqual(parseSceneShortcut('/MANAGEMENT查重',scenes),{scene:'files',text:'查重'});
 assert.deepEqual(parseSceneShortcut('/files 旧会话继续',scenes),{scene:'files',text:'旧会话继续'});
 for(const text of ['/management/report.txt','正文中的 /management','/management-other'])assert.equal(parseSceneShortcut(text,scenes),undefined);
 for(const [token,scene] of [['data','research-data-analysis'],['ppt','ppt'],['paper','paper-proofreading'],['chat','new-scene']])assert.equal(parseSceneShortcut('/'+token,scenes).scene,scene);
});
