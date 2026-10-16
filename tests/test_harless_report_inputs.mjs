/** Input binding diagnostics; no model calls or simulated report quality. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, mkdirSync, readFileSync, readdirSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join, resolve, sep} from 'node:path';
import {createHash} from 'node:crypto';
import {bindSceneInputs, scopeDigest} from '../src/adapters/harless_task_scope.ts';

const scene={id:'research-data-analysis',adapter:'data-report'};
function fixture(files){
 const root=mkdtempSync(join(tmpdir(),'harless-report-inputs-'));
 mkdirSync(join(root,'inputs'));
 const refs=files.map(([name,data],i)=>({name,bytes:Buffer.byteLength(data),data:Buffer.from(data),receipt:'r'+i}));
 const ctx={fileUploads:{resolve:(_agent,id)=>refs.find(r=>r.receipt===id)},
  attachments:{async *readFileStream(ref){yield ref.data;}}};
 const bind=()=>bindSceneInputs(ctx,{},root,scene,refs.map(ref=>({type:'file',receiptId:ref.receipt})),{},'按照要求生成报告','task-test');
 return {root,refs,bind,close(){assert.ok(resolve(root).startsWith(resolve(tmpdir())+sep)&&root.includes('harless-report-inputs-'));rmSync(root,{recursive:true,force:true});}};
}
test('A requirements TXT, study JSON and CSV bind together regardless of upload order',async()=>{
 const files=[['data_report_prompt.txt','请分析数据。\n检查缺失值并生成 PDF。'],['study_metadata.json','{"title":"test"}'],['synthetic_materials.csv','x,y\n1,2\n2,3\n']];
 for(const input of [files,[...files].reverse()]){
  const f=fixture(input);try{
   const rows=await f.bind();assert.equal(rows.length,3);
   const approved=JSON.parse(readFileSync(join(f.root,'approved-inputs.json'),'utf8')).files;
   for(const row of rows){const data=readFileSync(join(f.root,'inputs',row.file));assert.equal(approved[row.file],createHash('sha256').update(data).digest('hex'));}
   const request=readFileSync(join(f.root,'report/request.txt'),'utf8');
   assert.equal(request,'按照要求生成报告');
   assert.equal(readFileSync(join(f.root,'inputs',rows.find(row=>row.name===files[0][0]).file),'utf8'),files[0][1]);
   assert.equal(typeof scopeDigest(f.root,scene),'string');
  }finally{f.close();}
 }
});
test('Markdown requirements stay in the task snapshot without masquerading as a data file',async()=>{
 const f=fixture([['要求.md','## 研究目标\n比较两组。']]);try{
  const rows=await f.bind();assert.match(rows[0].file,/\.md$/);
  assert.match(readFileSync(join(f.root,'inputs',rows[0].file),'utf8'),/比较两组。/);
 }finally{f.close();}
});
test('PDF, Word, unknown binary and undecodable text are admitted with original bytes',async()=>{
 for(const file of [['paper.pdf','%PDF-1.7'],['study.docx','PK'],['archive.bin',Buffer.from([0x00,0xff])],['requirements.txt',Buffer.from([0xff,0xfe,0xfd])]]){
  const f=fixture([['data.csv','x,y\n1,2'],file]);try{
   const rows=await f.bind();assert.equal(rows.length,2);
   assert.deepEqual(readFileSync(join(f.root,'inputs',rows[1].file)),Buffer.from(file[1]));
  }finally{f.close();}
 }
});
test('PPT exposes every approved upload; the scoped parser reports unsupported contents',async()=>{
 const f=fixture([['paper.pdf','%PDF-1.7'],['requirements.docx','PK'],['unknown.bin','abc']]);try{
  const ctx={fileUploads:{resolve:(_a,id)=>f.refs.find(r=>r.receipt===id)},attachments:{async *readFileStream(ref){yield ref.data;}}};
  const rows=await bindSceneInputs(ctx,{},f.root,{id:'ppt',adapter:'ppt'},f.refs.map(ref=>({type:'file',receiptId:ref.receipt})),{allow_output:true},'create','task-test');
  assert.equal(rows.length,3);const job=JSON.parse(readFileSync(join(f.root,'job.json'),'utf8'));
  assert.deepEqual(job.inputs.map(row=>row.name),['paper.pdf','requirements.docx','unknown.bin']);assert.equal(job.allow_output,true);
  assert.equal(Object.keys(JSON.parse(readFileSync(join(f.root,'approved-inputs.json'),'utf8')).files).length,3);
 }finally{f.close();}
});
