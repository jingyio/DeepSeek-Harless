import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, mkdirSync, readFileSync, readdirSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {managementFileContent, bindSceneInputs} from '../src/adapters/file_task_scope.ts';

const scene = {id:'files', adapter:'files', runtime_kind:'management_graph_v3'};
const sha = value => createHash('sha256').update(value).digest('hex');
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64');
function fixture() {
  const root = mkdtempSync(join(tmpdir(), 'management-uploads-')); mkdirSync(join(root,'inputs'));
  const receipts = new Map(), batches = [], uploads = [];
  const agent = {session:{id:'own-session'}};
  const ctx = {
    attachments:{
      async admitPromptContent(parts) { batches.push(structuredClone(parts)); return parts.map(() => ({type:'image',attachment:{id:'normalized-preview'}})); },
      async *readFileStream(ref) { yield receipts.get(ref.attachmentId).data; },
    },
    fileUploads:{
      async uploadStream(request) {
        const chunks=[]; for await(const chunk of request.data) chunks.push(chunk);
        const data=Buffer.concat(chunks), receiptId='receipt-'+receipts.size;
        const ref={attachmentId:receiptId, name:request.name, bytes:data.length};
        receipts.set(receiptId,{owner:request.sessionId, data, ref}); uploads.push(request.sessionId);
        return {receiptId, file:ref};
      },
      resolve(owner,id) { const row=receipts.get(id); return row?.owner===owner.session.id ? row.ref : undefined; },
    },
  };
  return {root,agent,ctx,batches,uploads,close:()=>rmSync(root,{recursive:true,force:true})};
}

test('management admits images as owned file bytes and preserves mixed input order and original request', async () => {
  const f=fixture(); try {
    const textFile=await f.ctx.fileUploads.uploadStream({sessionId:f.agent.session.id,name:'notes.txt',data:(async function*(){yield Buffer.from('notes');})()});
    const content=[{type:'text',text:'按类型整理'}, {type:'image',name:'figure.png',mediaType:'image/png',data:png.toString('base64')}, {type:'file',receiptId:textFile.receiptId}];
    const original=structuredClone(content), converted=await managementFileContent(f.ctx,f.agent,scene,content);
    assert.deepEqual(content,original); assert.deepEqual(converted.map(p=>p.type),['text','file','image','file']);
    assert.deepEqual(converted[2],content[1]); // Native visual pixels are retained.
    assert.equal(f.batches.length,1); assert.equal(f.batches[0].length,1); assert.deepEqual(f.uploads,['own-session','own-session']);
    const bound=await bindSceneInputs(f.ctx,f.agent,f.root,scene,converted,{allow_output:true},'按类型整理','task-1');
    assert.deepEqual(bound.map(p=>p.name),['figure.png','notes.txt']);
    assert.equal(bound[0].version_sha256,sha(png)); assert.deepEqual(readFileSync(join(f.root,'inputs/figure.png')),png);
    assert.equal(readFileSync(join(f.root,'inputs/notes.txt'),'utf8'),'notes');
  } finally { f.close(); }
});

test('native image validation and source-count rejection precede file receipts and workspace writes', async () => {
  const f=fixture(); try {
    const image={type:'image',name:'broken.png',mediaType:'image/png',data:'AAAA'};
    f.ctx.attachments.admitPromptContent=async()=>{throw Error('native_image_rejected');};
    await assert.rejects(managementFileContent(f.ctx,f.agent,scene,[image]),/native_image_rejected/);
    await assert.rejects(managementFileContent(f.ctx,f.agent,scene,Array(9).fill(image)),/scene_input_limit/);
    assert.deepEqual(f.uploads,[]); assert.deepEqual(readdirSync(join(f.root,'inputs')),[]);
  } finally { f.close(); }
});

test('other scenes retain native image handling and text-only management needs no image service', async () => {
  const content=[{type:'image',mediaType:'image/png',data:png.toString('base64')}];
  for (const other of [{id:'chat'}, {id:'ppt', adapter:'ppt', runtime_kind:'ppt_read_v1'},
    {id:'research-data-analysis', runtime_kind:'data_receipts_v3'}])
    assert.equal(await managementFileContent({}, {}, other, content),content);
  const text=[{type:'text',text:'继续原任务'}]; assert.equal(await managementFileContent({}, {}, scene, text),text);
});

test('converted receipts cannot transfer to another session or overwrite colliding filenames', async () => {
  const f=fixture(); try {
    const image={type:'image',name:'same.png',mediaType:'image/png',data:png.toString('base64')};
    const converted=await managementFileContent(f.ctx,f.agent,scene,[image,image]);
    await assert.rejects(bindSceneInputs(f.ctx,{session:{id:'foreign'}},f.root,scene,converted,{},'整理','task-2'),/file_receipt_not_owned/);
    await assert.rejects(bindSceneInputs(f.ctx,f.agent,f.root,scene,converted,{},'整理','task-2'),/duplicate_scene_filename/);
    assert.deepEqual(readdirSync(join(f.root,'inputs')),[]);
  } finally { f.close(); }
});

test('unnamed images receive distinct bounded filenames', async () => {
  const f=fixture(); try {
    const image={type:'image',mediaType:'image/png',data:png.toString('base64')};
    const converted=await managementFileContent(f.ctx,f.agent,scene,[image,image]);
    const bound=await bindSceneInputs(f.ctx,f.agent,f.root,scene,converted,{},'只检查','task-3');
    assert.deepEqual(bound.map(row=>row.name),['image_1.png','image_2.png']);
    assert.deepEqual(bound.map(row=>row.version_sha256),[sha(png),sha(png)]);
  } finally { f.close(); }
});
