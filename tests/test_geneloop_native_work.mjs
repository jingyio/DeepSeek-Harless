/** Native installed tools, real local files, no provider/model requests. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,realpathSync,rmSync,linkSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {createHash,randomUUID} from 'node:crypto';
import {Context} from '@deepseek-ai/cordis';
import {AgentRegistry} from '@deepseek-ai/dsh-agent';
import {AgentLoop} from '@deepseek-ai/dsh-agent-loop';
import {SessionStore} from '@deepseek-ai/dsh-session';
import {SessionProjectionRegistry} from '@deepseek-ai/dsh-session-projection';
import {SystemPrompt} from '@deepseek-ai/dsh-system-prompt';
import {ToolRuntime} from '@deepseek-ai/dsh-tools';
import {LlmRuntime} from '@deepseek-ai/dsh-llm';
import {SkillRegistry} from '@deepseek-ai/dsh-skill';
import {LocalFileSystem} from '@deepseek-ai/dsh-fs-local';
import {apply as skillTool} from '@deepseek-ai/dsh-tool-skill';
import {apply as todoTool} from '@deepseek-ai/dsh-tool-todo';
import {apply as presentTool} from '@deepseek-ai/dsh-tool-present';
import {registerApprovedSkill,projectNativeTodos,nativePresentationPath,installNativePresentation,nativePresentedFiles} from '../src/adapters/geneloop_native_work.ts';
import {createTaskProgress} from '../src/adapters/harless_task_progress.ts';
import {comparisonArtifacts,captureComparisonDeliveries} from '../src/adapters/harless_comparison_artifacts.ts';
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');

async function fixture(){
 const root=realpathSync(mkdtempSync(join(tmpdir(),'geneloop-native-work-'))),ctx=new Context();
 new SessionStore(ctx);new AgentRegistry(ctx);new SessionProjectionRegistry(ctx);new SystemPrompt(ctx,{});new ToolRuntime(ctx,{});new LlmRuntime(ctx);new SkillRegistry(ctx);
 const loop=new AgentLoop(ctx,{agents:[]});
 // Test-only logical mapping; production uses GeneLoopFileSystem's pinned no-follow descriptors.
 class DiagnosticFileSystem extends LocalFileSystem {
   resolve(path,opts){return super.resolve(path.startsWith('/work/outputs/')?join(root,'outputs/code',path.slice('/work/outputs/'.length)):
     path.startsWith('outputs/')?join(root,'outputs/code',path.slice(8)):path,opts);}
   lstat(path,opts,signal){return super.lstat(path.startsWith('outputs/')?join(root,'outputs/code',path.slice(8)):path,opts,signal);}
 }
 new DiagnosticFileSystem(ctx,{cwd:root,diffBasisMaxBytes:1024*1024});
 skillTool(ctx);todoTool(ctx,{allowParallelInProgress:true});presentTool(ctx,{maxFiles:8});installNativePresentation(ctx);
 const agent=await loop.create('session-'+randomUUID(),{provider:'unused',model:'unused'},{cwd:root});
 agent.session.append('turn/start',{turn:1});
 const events=[],progress=createTaskProgress();
 ctx.on('session/event',(session,event)=>{if(session.id===agent.session.id){events.push(event);progress.event(event);}},{global:true});
 return {root,ctx,agent,events,progress,execute:(name,args,id=randomUUID())=>ctx.tools.execute({name,arguments:args,agent,callId:id,signal:new AbortController().signal}),
   async close(){await ctx.fiber.dispose();rmSync(root,{recursive:true,force:true});}};
}
function packageFixture(root){
 const project=join(root,'project'),skill=join(root,'approved');mkdirSync(join(project,'scenarios/ppt_master'),{recursive:true});mkdirSync(skill);
 const body='---\nname: ppt-master\ndescription: Make editable presentations\n---\n# Approved instructions\nUse scripts/build.py.\n';
 writeFileSync(join(skill,'SKILL.md'),body);
 const files={'SKILL.md':sha(Buffer.from(body))},lock={schema_version:1,version:'6.6.0',files,package_sha256:sha(Buffer.from(JSON.stringify(files)))};
 writeFileSync(join(project,'scenarios/ppt_master/skill-lock.json'),JSON.stringify(lock));
 return {pptMasterRoot:skill,projectRoot:project};
}

test('only locked administrator ppt-master is published through the actual native skill tool',async()=>{
 const f=await fixture();try{
  mkdirSync(join(f.root,'.agents/skills/unapproved'),{recursive:true});writeFileSync(join(f.root,'.agents/skills/unapproved/SKILL.md'),'unapproved');
  assert.deepEqual(await f.ctx.skills.list({cwd:f.root}),[]);
  const resources=packageFixture(f.root),dispose=registerApprovedSkill(f.ctx,resources);
  assert.deepEqual((await f.ctx.skills.list({cwd:f.root})).map(row=>row.name),['ppt-master']);
  const loaded=await f.execute('skill',{name:'ppt-master'});assert.equal(loaded.isError,false);
  assert.equal(loaded.value.resourceBase.path,'/opt/geneloop/ppt-master');assert.match(loaded.value.content,/Approved instructions/);
  assert.doesNotMatch(JSON.stringify(loaded),new RegExp(f.root.replaceAll('\\','\\\\')));
  assert.equal((await f.execute('skill',{name:'unapproved'})).isError,true);
  dispose();assert.deepEqual(await f.ctx.skills.list(),[]);
  writeFileSync(join(resources.pptMasterRoot,'SKILL.md'),'changed');assert.throws(()=>registerApprovedSkill(f.ctx,resources),/bytes changed/);
 }finally{await f.close();}
});

test('native todo_write permits parallel work and projects the latest list without inventing completion',async()=>{
 const f=await fixture();try{
  const rows=[{content:'分析数据',status:'in_progress'},{content:'检查图表',status:'in_progress'}];
  assert.equal((await f.execute('todo_write',{todos:rows})).isError,false);
  assert.deepEqual(f.ctx.sessionProjections.stateOf(f.agent.session,'todos'),rows);
  assert.deepEqual(f.progress.snapshot().todos,rows);
  assert.equal(f.progress.snapshot().progress.label,'任务清单：0/2 已完成');
  f.progress.finish('cancelled');assert.deepEqual(f.progress.snapshot().todos,rows);
  const updated=[{content:'分析数据',status:'completed'}];await f.execute('todo_write',{todos:updated});
  const snapshot=f.progress.snapshot();assert.deepEqual(snapshot.todos,updated);assert.deepEqual(createTaskProgress(snapshot).snapshot().todos,updated);
  snapshot.todos[0].content='mutated';assert.equal(f.progress.snapshot().todos[0].content,'分析数据');
  f.agent.session.append('turn/start',{turn:2});assert.equal(f.progress.snapshot().todos,null);
  assert.equal(projectNativeTodos(null,{type:'todo/write',data:{todos:[{content:'bad',status:'unknown'}]}}),null);
  await f.execute('todo_write',{todos:[{content:'读取 /home/private/server.txt',status:'in_progress'}]});
  assert.doesNotMatch(JSON.stringify(f.progress.snapshot().todos),/home\/private/);
 }finally{await f.close();}
});

test('present only accepts output paths and emits immutable task-bounded proof paired with its native event',async()=>{
 const f=await fixture();try{
  const output=join(f.root,'outputs/code');mkdirSync(output,{recursive:true});writeFileSync(join(output,'report.docx'),'first bytes');
  for(const path of ['/home/private','/work/inputs/a.csv','/work/script.py','outputs/../inputs/a','C:\\secret','file:///work/outputs/a']){
   assert.throws(()=>nativePresentationPath(path));assert.equal((await f.execute('present',{files:[{path}]})).isError,true);
  }
  assert.equal(f.events.filter(e=>e.type==='deliverables/presented').length,0);
  assert.equal((await f.execute('present',{files:[{path:'outputs/report.docx'}]},'approved-delivery')).isError,false);
  assert.equal(f.events.filter(e=>e.type==='deliverables/presented').length,1);
  const eventsPath=join(f.root,'events.jsonl');writeFileSync(eventsPath,f.events.map(e=>JSON.stringify(e)).join('\n'));
  const context={workspace:f.root,eventsPath,startedAt:new Date(Date.now()-60_000).toISOString(),finishedAt:new Date(Date.now()+60_000).toISOString()};
  const proofs=nativePresentedFiles(context);assert.equal(proofs.get(join(output,'report.docx')),sha(Buffer.from('first bytes')));
  const artifacts=comparisonArtifacts(join(f.root,'artifacts'));
  const rows=artifacts.snapshot('turn-one','baseline',0,f.root,new Set(proofs.keys()),false,new Set(proofs.keys()));
  assert.equal(rows.length,1);assert.equal(artifacts.read('turn-one','baseline',rows[0]).toString(),'first bytes');
  writeFileSync(join(output,'report.docx'),'changed');assert.equal(nativePresentedFiles(context).size,0);
  assert.equal(captureComparisonDeliveries(artifacts,{...context,turn:'changed-after-present',lane:'baseline',attempt:0,adapter:'workspace',status:'completed'}).length,0);
  // Simulate a writer swapping bytes after proof collection but before copy.
  const expected=nativePresentedFiles(context,false);assert.equal(expected.size,1);
  assert.equal(artifacts.snapshot('concurrent-writer','baseline',0,f.root,undefined,false,new Set(expected.keys()),undefined,expected).length,0);
  assert.equal(artifacts.read('turn-one','baseline',rows[0]).toString(),'first bytes');
  assert.throws(()=>artifacts.read('turn-one','motif',rows[0]));
  assert.equal(nativePresentedFiles({...context,startedAt:new Date(Date.now()+120_000).toISOString()}).size,0);
  writeFileSync(eventsPath,f.events.filter(e=>e.type!=='deliverables/presented').map(e=>JSON.stringify(e)).join('\n'));
  assert.equal(nativePresentedFiles(context).size,0);
 }finally{await f.close();}
});

test('present proof refuses hardlinks, missing native receipt, foreign workspace and cancelled calls',async()=>{
 const f=await fixture();try{
  mkdirSync(join(f.root,'outputs/code'),{recursive:true});const file=join(f.root,'outputs/code/result.txt');writeFileSync(file,'owned');
  await f.execute('present',{files:[{path:'outputs/result.txt'}]});
  const eventsPath=join(f.root,'events.jsonl');writeFileSync(eventsPath,f.events.map(e=>JSON.stringify(e)).join('\n'));
  const context={workspace:f.root,eventsPath,startedAt:new Date(0).toISOString(),finishedAt:new Date(Date.now()+1000).toISOString()};
  linkSync(file,join(f.root,'linked'));assert.equal(nativePresentedFiles(context).size,0);
  assert.equal(nativePresentedFiles({...context,workspace:join(f.root,'other')}).size,0);
  const aborted=new AbortController();aborted.abort();const before=f.events.length;
  assert.equal((await f.ctx.tools.execute({name:'present',arguments:{files:[{path:'outputs/result.txt'}]},agent:f.agent,callId:'cancelled',signal:aborted.signal})).isError,true);
  assert.equal(f.events.length,before);
 }finally{await f.close();}
});
