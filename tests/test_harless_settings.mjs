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
    const pages={version_fields:{...manifest.version_fields,mcp__ppt__pin_deck_pages:'version_sha256',mcp__ppt__read_pinned_deck_pages:'version_sha256'}};
    const expanded=bindUploadedPptTask(root,inputs,request,pages);
    const expectedDeck=createHash('sha256').update('["'+version+'"]').digest('hex');
    assert.equal(expanded.source_versions.mcp__ppt__read_pinned_deck_pages,expectedDeck);
    assert.notEqual(expectedDeck,version);assert.deepEqual(expanded.bindings,{});
    assert.throws(()=>bindUploadedPptTask(root,inputs,request,{version_fields:{...pages.version_fields,mcp__ppt__render_deck:'input_version'}}),/binding_tools_unsupported/);
    assert.throws(()=>bindUploadedPptTask(root,inputs,request,{version_fields:{...manifest.version_fields,mcp__ppt__pin_deck_pages:'version_sha256'}}),/binding_tools_unsupported/);
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
test('paper upload binding freezes admitted bytes and an observed read continuation', {skip:!process.features?.typescript}, async()=>{
  const {bindApprovedUploadedReadTask}=await import('../src/adapters/harless_rsi_binding.ts');
  const root=realpathSync(mkdtempSync(join(tmpdir(),'paper-binding-')));mkdirSync(join(root,'inputs'));
  try{
    const data=Buffer.from('\\documentclass{article}');
    writeFileSync(join(root,'inputs','paper.tex'),data);
    const version=createHash('sha256').update(data).digest('hex');
    writeFileSync(join(root,'approved-inputs.json'),JSON.stringify({files:{'paper.tex':version}}));
    const pin='mcp__paper_checks__pin_paper_sources',read='mcp__paper_checks__read_pinned_paper_sources';
    const manifest={version_fields:{[pin]:'version_sha256',[read]:'version_sha256'},
      artifacts:[{tools:[pin,read],transfer_evidence:[{from_tool:pin,to_tool:read,from_field:'source_id',to_param:'source_id'}]}]};
    const request={task_id:'task-a',session_id:'session-a',content:[{type:'text',text:'Check citations'}]};
    const inputs=[{file:'paper.tex',version_sha256:version}];
    const binding=bindApprovedUploadedReadTask(root,inputs,request,manifest,'paper-proofreading');
    assert.deepEqual(binding.source_versions,{[pin]:'@observed',[read]:'@from_anchor'});
    assert.equal(binding.intent,'Check citations');
    const cite='mcp__paper_checks__pin_paper_citations';
    const cited='mcp__paper_checks__read_pinned_paper_citations';
    const composite={version_fields:{...manifest.version_fields,[cite]:'version_sha256',[cited]:'version_sha256'},
      artifacts:[...manifest.artifacts,{tools:[cite,cited],transfer_evidence:[
        {from_tool:cite,to_tool:cited,from_field:'source_id',to_param:'source_id'}]}]};
    assert.deepEqual(bindApprovedUploadedReadTask(root,inputs,request,composite,'paper-proofreading').source_versions,
      {[pin]:'@observed',[read]:'@from_anchor',[cite]:'@observed',[cited]:'@from_anchor'});
    const local='mcp__paper_checks__collect_current_local_citation_evidence';
    const page='mcp__paper_checks__read_pinned_bibliography_first_page';
    const full={version_fields:{...composite.version_fields,[local]:'version_sha256',[page]:'version_sha256'},
      artifacts:[...composite.artifacts,{tools:[local,page],transfer_evidence:[
        {from_tool:local,to_tool:page,from_field:'source_id',to_param:'source_id'}]}]};
    assert.deepEqual(bindApprovedUploadedReadTask(root,inputs,request,full,'paper-proofreading').source_versions,
      {[pin]:'@observed',[read]:'@from_anchor',[cite]:'@observed',[cited]:'@from_anchor',
        [local]:'@observed',[page]:'@from_anchor'});
    const longText='完整论文\n参考文献核验'.repeat(400);
    const longRequest={...request,content:[{type:'text',text:longText}]};
    const bounded=bindApprovedUploadedReadTask(root,inputs,longRequest,full,'paper-proofreading');
    assert.ok(bounded.intent.length<=500 && !/[\x00-\x1f]/.test(bounded.intent));
    assert.equal(longRequest.content[0].text,longText,'the model request remains complete');
    const {parseStructuredTask}=await import('../src/motif_core/online_skill_runtime.mjs');
    const checked={...full,contracts:Object.fromEntries(Object.keys(full.version_fields).map(name=>
      [name,{observed_anchor:[pin,cite,local].includes(name)}]))};
    assert.doesNotThrow(()=>parseStructuredTask(bounded,checked));
    assert.throws(()=>bindApprovedUploadedReadTask(root,inputs,request,{...composite,
      artifacts:[...composite.artifacts,{tools:[cited,'mcp__paper_checks__export_current_audit_pdf'],
        transfer_evidence:[]}]},'paper-proofreading'),/tools_unsupported/);
    writeFileSync(join(root,'inputs','paper.tex'),'changed');
    assert.throws(()=>bindApprovedUploadedReadTask(root,inputs,request,manifest,'paper-proofreading'),/source_version/);
    assert.throws(()=>bindApprovedUploadedReadTask(root,inputs,request,manifest,'new-scene'),/requires_approved/);
  }finally{rmSync(root,{recursive:true,force:true});}
});
test('paper Motif binding accepts sixteen verified uploads and rejects a seventeenth', {skip:!process.features?.typescript}, async()=>{
  const {bindApprovedUploadedReadTask}=await import('../src/adapters/harless_rsi_binding.ts');
  const root=realpathSync(mkdtempSync(join(tmpdir(),'paper-full-binding-')));mkdirSync(join(root,'inputs'));
  try{
    const pin='mcp__paper_checks__pin_paper_sources',read='mcp__paper_checks__read_pinned_paper_sources';
    const manifest={version_fields:{[pin]:'version_sha256',[read]:'version_sha256'},
      artifacts:[{tools:[pin,read],transfer_evidence:[{from_tool:pin,to_tool:read,from_field:'source_id',to_param:'source_id'}]}]};
    const inputs=[];
    for(let index=0;index<17;index++){
      const file=`section-${index}.tex`,data=Buffer.from(`Section ${index}`),version=createHash('sha256').update(data).digest('hex');
      writeFileSync(join(root,'inputs',file),data);inputs.push({file,version_sha256:version});
    }
    const files=Object.fromEntries(inputs.slice(0,16).map(row=>[row.file,row.version_sha256]));
    writeFileSync(join(root,'approved-inputs.json'),JSON.stringify({files}));
    const request={task_id:'task-full',session_id:'session-full',content:[{type:'text',text:'Review full paper'}]};
    assert.equal(bindApprovedUploadedReadTask(root,inputs.slice(0,16),request,manifest,'paper-proofreading').task_id,'task-full');
    files[inputs[16].file]=inputs[16].version_sha256;
    writeFileSync(join(root,'approved-inputs.json'),JSON.stringify({files}));
    assert.throws(()=>bindApprovedUploadedReadTask(root,inputs,request,manifest,'paper-proofreading'),/requires_approved/);
  }finally{rmSync(root,{recursive:true,force:true});}
});
