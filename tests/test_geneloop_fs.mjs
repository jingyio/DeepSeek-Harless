import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,realpathSync,mkdirSync,writeFileSync,readFileSync,rmSync,symlinkSync,linkSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {rename,symlink,unlink,writeFile} from 'node:fs/promises';
import {Context} from '@deepseek-ai/cordis';
import GeneLoopFileSystem,{geneLoopPath,geneLoopMounts} from '../src/adapters/geneloop_fs.ts';
const linux={skip:process.platform!=='linux'};
const session='session-11111111-1111-4111-8111-111111111111',other='session-22222222-2222-4222-8222-222222222222';
function fixture(){
 const root=realpathSync(mkdtempSync(join(tmpdir(),'geneloop-fs-'))),ctx=new Context();let owner=session;
 ctx.provide('agents',{currentInitiator:()=>owner?{session:{id:owner,header:{cwd:join(root,'workspace-header')}}}:undefined});
 const fs=new GeneLoopFileSystem(ctx,{output:root});
 const mounts=geneLoopMounts({output:root},session);
 const host=logical=>{const m=mounts.find(m=>logical===m.logical||logical.startsWith(m.logical+'/'));return join(m.host,logical.slice(m.logical.length));};
 return {root,fs,ctx,mounts,host,owner(value){owner=value;},clean(){rmSync(root,{recursive:true,force:true});}};
}
test('logical paths normalize aliases while refusing host paths, URIs and mount escapes',()=>{
 for(const [path,cwd,expected]of [['outputs/a.svg','/work','/work/outputs/a.svg'],['./a.txt','/work','/work/a.txt'],
  ['/tmp/checker/a.json',undefined,'/tmp/checker/a.json'],['a/../b','/work/outputs','/work/outputs/b']])
  assert.equal(geneLoopPath(path,cwd),expected);
 for(const path of ['/etc/passwd','/home/a/.env','C:\\secret','file:///work/a','/work/../../etc/passwd',
  '/work/inputs/../code','/work/outputs/../../inputs/a','/tmp/../etc','/work/a\0b','/work/a\\b'])
  assert.throws(()=>geneLoopPath(path),e=>e.code==='FS_SANDBOX_DENIED',path);
});
test('mounts match Bash and reject foreign session identifiers and linked ancestors',()=>{
 const f=fixture();try{
  assert.equal(f.host('/work/outputs/a'),join(f.root,'sessions',session,'work','outputs','code','a'));
  assert.equal(f.host('/work/a'),join(f.root,'sessions',session,'work','code','a'));
  assert.equal(f.mounts.find(m=>m.logical==='/work/inputs').writable,false);
  assert.throws(()=>geneLoopMounts({output:f.root},'../other'));
 }finally{f.clean();}
});
test('native filesystem fails closed on unsupported execution platforms',{skip:process.platform==='linux'},async()=>{
 const f=fixture();try{await assert.rejects(f.fs.resolve('/work/a'),e=>e.code==='FS_SANDBOX_DENIED');}finally{f.clean();}
});
test('Linux filesystem reads inputs, writes output/code/temp, and preserves native stale/edit semantics',linux,async()=>{
 const f=fixture();try{
  writeFileSync(f.host('/work/inputs/source.txt'),'ORIGINAL\r\n');
  const input=await f.fs.resolve('/work/inputs/source.txt');
  assert.equal(await f.fs.readText(input),'ORIGINAL\r\n');
  await assert.rejects(f.fs.writeText(input,'bad'),e=>e.code==='FS_SANDBOX_DENIED');
  for(const path of ['/work/outputs/nested/report.txt','/work/tool.py','/tmp/result.txt']){
   const target=await f.fs.resolve(path);await f.fs.writeText(target,'alpha\r\nbeta\r\n',{kind:'createIfAbsent'});
   const version=(await f.fs.stat(target)).version;
   assert.equal(await f.fs.readText(target),'alpha\r\nbeta\r\n');
   await assert.rejects(f.fs.writeText(target,'bad',{kind:'createIfAbsent'}),e=>e.code==='FS_NOT_OBSERVED');
   const edit=await f.fs.editText(target,{oldString:'beta',newString:'gamma',replaceAll:false},{version});
   assert.equal(edit.after,'alpha\ngamma\n');assert.equal(await f.fs.readText(target),'alpha\r\ngamma\r\n');
   await assert.rejects(f.fs.writeText(target,'stale',{kind:'replaceIfVersion',version}),e=>e.code==='FS_STALE_VERSION');
   await assert.rejects(f.fs.writeText(target,'read only',undefined,undefined,{mode:'read-only'}),e=>e.code==='FS_SANDBOX_DENIED');
  }
  assert.deepEqual((await f.fs.listDir(await f.fs.resolve('/work'))).map(x=>x.name),['inputs','outputs','tool.py']);
  assert.equal(readFileSync(f.host('/work/inputs/source.txt'),'utf8'),'ORIGINAL\r\n');
  writeFileSync(f.host('/work/large.txt'),'x'.repeat(10*1024*1024));
  const large=await f.fs.resolve('/work/large.txt');
  assert.equal((await f.fs.writeText(large,'replacement')).before,null,'native overwrite diff basis stays bounded');
 }finally{f.clean();}
});
test('byte limits, ranges, streaming, missing entries, cancellation and ownership are enforced',linux,async()=>{
 const f=fixture();try{
  const target=await f.fs.resolve('sample.txt');await f.fs.writeText(target,'0123456789');
  assert.equal(Buffer.from(await f.fs.readByteRange(target,{offset:3,length:4})).toString(),'3456');
  await assert.rejects(f.fs.readBytes(target,undefined,4),e=>e.code==='FS_TOO_LARGE');
  let text='';for await(const chunk of await f.fs.streamText(target))text+=chunk;assert.equal(text,'0123456789');
  assert.equal(await f.fs.stat(await f.fs.resolve('/work/absent')),undefined);
  assert.equal(f.fs.processPathFromHostPath(f.host('/work/sample.txt')),'/work/sample.txt');
  assert.equal(f.fs.processPathFromHostPath(join(f.root,'foreign-account','secret')),undefined);
  const canceled=new AbortController();canceled.abort();await assert.rejects(f.fs.readText(target,canceled.signal),e=>e.code==='FS_ABORTED');
  f.owner(other);await assert.rejects(f.fs.readText(target),e=>e.code==='FS_SANDBOX_DENIED');
  f.owner(null);await assert.rejects(f.fs.resolve('sample.txt'),e=>e.code==='FS_SANDBOX_DENIED');
 }finally{f.clean();}
});
test('symlinks, swapped parents, hardlinks and special entries cannot escape or disclose bytes',linux,async()=>{
 const f=fixture();try{
  const secret=join(f.root,'private-secret');writeFileSync(secret,'must-not-read');
  symlinkSync(secret,f.host('/work/link'));await assert.rejects(f.fs.resolve('/work/link'),e=>e.code==='FS_SANDBOX_DENIED');
  mkdirSync(f.host('/work/dir'));const target=await f.fs.resolve('/work/dir/secret');
  rmSync(f.host('/work/dir'),{recursive:true});symlinkSync(f.root,f.host('/work/dir'));
  await assert.rejects(f.fs.writeText(target,'bad'),e=>['FS_SANDBOX_DENIED','FS_NOT_DIRECTORY'].includes(e.code));
  linkSync(secret,f.host('/work/hard'));await assert.rejects(f.fs.resolve('/work/hard'),e=>e.code==='FS_SANDBOX_DENIED');
  assert.equal(f.fs.processPathFromHostPath(f.host('/work/link')),undefined);
  assert.equal(readFileSync(secret,'utf8'),'must-not-read');
  assert.deepEqual((await f.fs.listDir(await f.fs.resolve('/work'))).map(x=>x.name),['inputs','outputs']);
 }finally{f.clean();}
});
test('concurrent link replacement cannot make reads disclose a foreign inode or writes alter it',linux,async()=>{
 const f=fixture();try{
  const secret=join(f.root,'outside-secret'),live=f.host('/work/racy.txt');writeFileSync(secret,'foreign-private-value');writeFileSync(live,'own-value');
  const target=await f.fs.resolve('/work/racy.txt');
  let running=true;
  const attacker=(async()=>{for(let n=0;n<100&&running;n++){
   const swap=f.host('/work/swap-'+n);await symlink(secret,swap);await rename(swap,live);
   const clean=f.host('/work/clean-'+n);await writeFile(clean,'own-value');await rename(clean,live);
  }})();
  const outcomes=await Promise.all(Array.from({length:40},async()=>{
   try{const text=await f.fs.readText(target);assert.ok(text==='own-value'||text==='safe-update');return 'read';}
   catch(error){assert.ok(['FS_SANDBOX_DENIED','FS_NOT_FOUND'].includes(error.code));return 'denied';}
  }));
  await Promise.all(Array.from({length:20},async()=>{try{await f.fs.writeText(target,'safe-update');}
   catch(error){assert.ok(['FS_SANDBOX_DENIED','FS_NOT_FOUND','FS_STALE_VERSION'].includes(error.code));}}));
  running=false;await attacker;assert.equal(readFileSync(secret,'utf8'),'foreign-private-value');assert.equal(outcomes.length,40);
  const created=await f.fs.resolve('/work/new.txt');
  const writes=await Promise.allSettled(Array.from({length:8},(_,n)=>f.fs.writeText(created,'value-'+n,{kind:'createIfAbsent'})));
  assert.equal(writes.filter(row=>row.status==='fulfilled').length,1);
 }finally{f.clean();}
});
test('upstream read/write/edit/read_image use the seam and retain real image attachments',linux,async()=>{
 const f=fixture();try{
  const {LocalAttachmentStore}=await import('@deepseek-ai/dsh-attachment-local');
  const sharp=(await import('sharp')).default;
  const attachments=new LocalAttachmentStore(f.ctx,{dshHome:join(f.root,'private-home')});
  const definitions=new Map();
  const ctx={fs:f.fs,tools:{register(def){definitions.set(def.name,def);},get(name){return definitions.get(name);}},
   systemPrompt:{section(){},getSectionOrder(){return 0;}},get(name){return ({attachments,llm:{resolveModelInfo:async()=>({inputModalities:['text','image']})},
    sandboxPolicy:{resolve:()=>({mode:'workspace-write',workspaceRoot:'/work'})}})[name];},
   inject(deps,callback){callback(this);},emit(){},waterfall(name,target,exec,next){return next();}};
  const {apply}=await import('@deepseek-ai/dsh-tool-fs');
  apply(ctx,{readLimit:2000,readMaxLineLength:2000,readMaxBytes:50000,readStreamMinSize:10000});
  assert.deepEqual([...definitions.keys()],['read','read_image','write','edit']);
  const exec={signal:new AbortController().signal,agent:{session:{id:session,header:{cwd:'/work'},requestHeader:()=>({config:{provider:'deepseek-official',model:'deepseek-flash'}})}}};
  await definitions.get('write').execute({file_path:'/work/outputs/a.txt',content:'before\n'},exec);
  const read=await definitions.get('read').execute({file_path:'/work/outputs/a.txt'},exec);
  assert.ok(JSON.stringify(read).includes('before'));
  await definitions.get('edit').execute({file_path:'/work/outputs/a.txt',old_string:'before',new_string:'after'},exec);
  assert.equal(readFileSync(f.host('/work/outputs/a.txt'),'utf8'),'after\n');
  const image=await sharp({create:{width:96,height:64,channels:3,background:'#087e8b'}}).png().toBuffer();
  writeFileSync(f.host('/work/outputs/slide.png'),image);
  const value=await definitions.get('read_image').execute({file_path:'/work/outputs/slide.png'},exec);
  const blocks=definitions.get('read_image').output.render({file_path:'/work/outputs/slide.png'},value);
  assert.equal(blocks[1].type,'image');assert.ok(blocks[1].attachment.attachmentId.startsWith('sha256:'));
  const uploaded=await attachments.admitPromptContent([{type:'image',data:image.toString('base64'),mediaType:'image/png',name:'slide.png'}]);
  assert.equal(blocks[1].attachment.attachmentId,uploaded[0].attachment.attachmentId);
  const [a,b]=await Promise.all([blocks[1].attachment,uploaded[0].attachment].map(ref=>attachments.readImageRequest(ref,{maxPixels:640000,maxBytes:1048576})));
  assert.deepEqual(a.data,b.data);assert.equal(a.width,b.width);assert.equal(a.height,b.height);
  await assert.rejects(definitions.get('read_image').execute({file_path:join(f.root,'private-secret')},exec));
 }finally{f.clean();}
});
