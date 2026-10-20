import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync,mkdtempSync,realpathSync,writeFileSync,readFileSync,rmSync,symlinkSync,mkdirSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {Context} from '@deepseek-ai/cordis';
import {rgPath} from '@vscode/ripgrep';
import {buildGlobCommand,buildGrepCommand,apply} from '@deepseek-ai/dsh-tool-fs-search';
import GeneLoopSubprocessRuntime,{nativeSearchArgs} from '../src/adapters/geneloop_fs_search.ts';
import {commandLayout} from '../src/adapters/geneloop_shell.ts';
const linux={skip:process.platform!=='linux'||!existsSync('/usr/bin/bwrap')};
const session='session-11111111-1111-4111-8111-111111111111';
test('native rg admission accepts only exact upstream glob/grep templates, including literal shell characters',()=>{
 for(const args of [buildGlobCommand({pattern:'*.png',path:'/work/outputs'}),buildGrepCommand({pattern:"x'; echo injection",path:'.',include:'*.md'})])
  assert.deepEqual(nativeSearchArgs([rgPath,'--no-config',...args]).args,args);
 for(const args of [buildGlobCommand({pattern:'inputs/*'}),buildGrepCommand({pattern:'alpha'})]){
  const admitted=nativeSearchArgs([rgPath,'--no-config',...args]);
  assert.equal(admitted.path,'.');assert.deepEqual(admitted.args,[...args,'--','.']);
 }
 for(const args of [[rgPath,'--pre=cat','--','/work'],[rgPath,'--no-config','--files','--follow','--','/work'],
  ['/usr/bin/rg','--no-config',...buildGlobCommand({pattern:'*',path:'.'})],
  [rgPath,'--no-config','--json','--regexp=x','--pre=cat','--','.']])assert.throws(()=>nativeSearchArgs(args));
});
test('upstream glob/grep run in the same Session bwrap, hide credentials/foreign files, and retain readable paths',linux,async()=>{
 const root=realpathSync(mkdtempSync(join(tmpdir(),'geneloop-fs-search-'))),ctx=new Context();
 const oldSocket=process.env.GENELOOP_COMMAND_SOCKET;delete process.env.GENELOOP_COMMAND_SOCKET;
 try{
  const layout=commandLayout(root,session),foreign=join(root,'foreign-secret.txt');writeFileSync(foreign,'OUTSIDE_SECRET');
  writeFileSync(join(layout.inputs,'notes.txt'),'current source alpha\n');writeFileSync(join(layout.outputs,'page.txt'),'current output alpha\n');
  ctx.provide('agents',{currentInitiator:()=>({session:{id:session,header:{cwd:join(root,'session-header')}}})});
  const runtime=new GeneLoopSubprocessRuntime(ctx,{output:root});const definitions=new Map();
  const plugin={subprocess:runtime,systemPrompt:{section(){},getSectionOrder(){return 0;}},
   tools:{register(def){definitions.set(def.name,def);},get(name){return definitions.get(name);}},get(){return undefined;},on(){}};
  await apply(plugin,{sampleOverCapGlobResults:false,globMaxResults:100,grepMaxMatches:250,grepMaxLineBytes:2000,
   searchMetaMaxBytes:65536,rawOutputMaxBytes:1048576,graceMs:300,stderrMaxBytes:65536,timeoutMs:15000});
  const exec={signal:new AbortController().signal,agent:{session:{id:session,header:{cwd:join(root,'session-header')}}}};
  const glob=await definitions.get('glob').execute({pattern:'*.txt',path:'/work'},exec);
  const globText=JSON.stringify(glob);assert.ok(globText.includes('/work/inputs/notes.txt'));assert.ok(globText.includes('/work/outputs/page.txt'));
  assert.ok(!globText.includes(foreign));
  const defaultGlob=await definitions.get('glob').execute({pattern:'inputs/*.txt'},exec);
  assert.ok(JSON.stringify(defaultGlob).includes('/work/inputs/notes.txt'),'upstream omitted path searches this Session root');
  const defaultGrep=await definitions.get('grep').execute({pattern:'current source alpha'},exec);
  assert.ok(JSON.stringify(defaultGrep).includes('current source alpha'));
  const grep=await definitions.get('grep').execute({pattern:'alpha',path:'/work'},exec);
  assert.ok(JSON.stringify(grep).includes('current source alpha'));
  assert.ok(!JSON.stringify(grep).includes('OUTSIDE_SECRET'));
  await assert.rejects(definitions.get('grep').execute({pattern:'OUTSIDE_SECRET',path:foreign},exec));
  symlinkSync(foreign,join(layout.scratch,'link.txt'));
  await assert.rejects(definitions.get('grep').execute({pattern:'.',path:'/work/link.txt'},exec));
  const safe=await definitions.get('grep').execute({pattern:'OUTSIDE_SECRET',path:'/work'},exec);
  assert.ok(!JSON.stringify(safe).includes('OUTSIDE_SECRET\n'));
  await definitions.get('grep').execute({pattern:"x';touch /work/outputs/injected;#",path:'/work/outputs'},exec);
  assert.equal(existsSync(join(layout.outputs,'injected')),false);
  assert.equal(readFileSync(foreign,'utf8'),'OUTSIDE_SECRET');
 }finally{oldSocket===undefined?delete process.env.GENELOOP_COMMAND_SOCKET:process.env.GENELOOP_COMMAND_SOCKET=oldSocket;rmSync(root,{recursive:true,force:true});}
});
test('native search can use the existing private command socket without nested namespaces',linux,async()=>{
 const {startCommandBroker}=await import('../src/adapters/geneloop_command_broker.ts');
 const root=realpathSync(mkdtempSync(join(tmpdir(),'geneloop-fs-search-socket-'))),ctx=new Context();
 const layout=commandLayout(root,session);writeFileSync(join(layout.outputs,'report.txt'),'search via socket\n');
 const broker=await startCommandBroker({output:root,python:process.env.SSS_PYTHON??'/usr/bin/python3',node:process.execPath});
 const oldSocket=process.env.GENELOOP_COMMAND_SOCKET;process.env.GENELOOP_COMMAND_SOCKET=broker.socketPath;
 try{
  ctx.provide('agents',{currentInitiator:()=>({session:{id:session,header:{cwd:'/work'}}})});
  const runtime=new GeneLoopSubprocessRuntime(ctx,{output:root});
  const handle=runtime.spawn({argv:[rgPath,'--no-config',...buildGrepCommand({pattern:'socket',path:'/work/outputs'})],cwd:'/work',
   stdio:{stdin:'ignore',stdout:{maxBytes:65536},stderr:{maxBytes:65536}},graceMs:300});
  assert.equal((await handle.done).exitCode,0);assert.ok(handle.collected.stdout.readFrom(0).text.includes('search via socket'));
  assert.ok(await handle.waitForExit(AbortSignal.timeout(3000)));
 }finally{oldSocket===undefined?delete process.env.GENELOOP_COMMAND_SOCKET:process.env.GENELOOP_COMMAND_SOCKET=oldSocket;broker.close();rmSync(root,{recursive:true,force:true});}
});
