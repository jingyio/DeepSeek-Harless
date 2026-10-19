/** Deterministic evidence-consumption diagnostics, not a model-quality claim. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {attachmentReadingIndex} from '../src/adapters/harless_attachment_reading.ts';
import {attachmentContextMessage,attachmentEvidence} from '../src/adapters/harless_attachment_context.ts';
import {publicSessionEvent} from '../src/adapters/harless_public_output.ts';

const a='a'.repeat(64),b='b'.repeat(64),image='c'.repeat(64);
const source=(sha256,origin,format='pptx')=>({name:(sha256===a?'previous.':'current.')+format,sha256,origin});
const file=(sha256,value,ocr)=>({name:'slides.pptx',sha256,format:'pptx',status:'extracted',pages:[{
 page:1,source_id:`pptx:${sha256}:slide:1`,text_method:'ooxml',rendered_ocr_text:ocr,
 rendered_image:{sha256:image},visual_content_reviewed:true,
 visual_analysis:{source_id:`pptx:${sha256}:slide:1`,page:1,image_observed:true,
  observations:`蓝色Alpha为31，紫色Beta为${value}。`,unreadable:[]},
}]});
const envelope=files=>'只读附件观察：\n'+JSON.stringify({files});
const current=files=>[{value:envelope(files),origin:'current_turn_upload'}];

test('OCR14 and pixel74 remain distinct evidence; indexing neither changes nor re-verifies source facts',()=>{
 const original=file(a,74,'Beta 14'),before=JSON.stringify(original);
 const index=attachmentReadingIndex(current([original]),[source(a,'current_turn_upload')]);
 const page=index.observations[0].pages[0];
 assert.equal(page.reading_status,'pixel_model_observation');
 assert.equal(page.pixel_observation,'蓝色Alpha为31，紫色Beta为74。');
 assert.equal(page.ocr_present,true);
 assert.equal(page.ocr_role,'approximate_retrieval_hint_original_text_retained_in_evidence');
 assert.equal(page.verification,'auxiliary_model_reading_not_independent_fact_verification');
 assert.equal(original.pages[0].rendered_ocr_text,'Beta 14');
 assert.equal(JSON.stringify(original),before,'indexing may not rewrite the low-level OCR or model observation');
});

test('current92 and historical74 are source-bound, while raw evidence remains recoverable and hidden from UI',()=>{
 const old=envelope([file(a,74,'Beta 14')]),fresh=envelope([file(b,92,'Beta 92')]);
 const task={request:{task_id:'task-b'},context_input_files:['current.pptx'],scene_inputs:[
  {name:'current.pptx',file:'current.pptx',version_sha256:b},
  {name:'previous.pptx',file:'previous.pptx',version_sha256:a},
 ]};
 const message=attachmentContextMessage(task,fresh,undefined,[old]);
 const body=JSON.parse(message.content[0].text.split('\n').slice(1).join('\n'));
 const rows=body.source_reading_index.observations;
 assert.deepEqual(rows.map(row=>[row.sha256,row.origin,row.pages[0].pixel_observation]),[
  [b,'current_turn_upload','蓝色Alpha为31，紫色Beta为92。'],
  [a,'earlier_conversation_source','蓝色Alpha为31，紫色Beta为74。'],
 ]);
 assert.equal(body.current_upload_evidence,fresh);
 assert.match(body.previous_attachment_evidence[0],/Beta 14/);
 assert.equal(attachmentEvidence([{type:'user/message',data:message}]).length,1);
 const before=JSON.stringify(message),projected=publicSessionEvent({type:'user/message',data:message});
 assert.deepEqual(projected.data.content,[]);assert.equal(JSON.stringify(message),before);
});

test('failed and successful reads remain separate, and unreadable fields survive without certification',()=>{
 const failed=file(a,74,'Beta 14');
 failed.pages[0].visual_content_reviewed=false;failed.pages[0].visual_error_code='http_503';
 const success=file(a,74,'Beta 14');success.pages[0].visual_analysis.unreadable=['小字说明看不清'];
 const index=attachmentReadingIndex(current([{name:'slides.pptx',sha256:a,format:'pptx',
  evidence_schema:'source-observations-v1',source_observations:[failed,success]}]),[source(a,'current_turn_upload')]);
 assert.equal(index.observations.length,2);
 assert.equal(index.observations[0].pages[0].reading_status,'no_valid_pixel_model_observation');
 assert.equal(index.observations[0].pages[0].error_code,'http_503');
 assert.equal(index.observations[0].pages[0].pixel_observation,undefined);
 assert.deepEqual(index.observations[1].pages[0].unreadable,['小字说明看不清']);
 assert.equal(index.observations[1].pages[0].verification,'auxiliary_model_reading_not_independent_fact_verification');
});

test('unadmitted sources, wrong source/page, unobserved images and missing pixel receipts cannot gain a readable observation',()=>{
 assert.equal(attachmentReadingIndex(current([file(a,74,'14')]),[source(b,'current_turn_upload')]),undefined);
 const mutations=[page=>page.visual_analysis.source_id=`pptx:${b}:slide:1`,page=>page.visual_analysis.page=2,
  page=>page.visual_analysis.image_observed=false,page=>delete page.rendered_image,
  page=>page.source_id='unbound-page',page=>page.visual_analysis.unreadable='none'];
 for(const mutate of mutations){
  const original=file(a,74,'14');mutate(original.pages[0]);
  const row=attachmentReadingIndex(current([original]),[source(a,'current_turn_upload')]).observations[0].pages[0];
  assert.equal(row.reading_status,'no_valid_pixel_model_observation');assert.equal(row.pixel_observation,undefined);
 }
});

test('the same source/page rules apply to PDF, DOCX and XLSX, without adding a task-specific parser',()=>{
 for(const format of ['pdf','docx','xlsx']){
  const original=file(a,74,'14');original.format=format;
  const page=original.pages[0];page.source_id=`${format}:${a}:page:1`;page.visual_analysis.source_id=page.source_id;
  const index=attachmentReadingIndex(current([original]),[source(a,'current_turn_upload',format)]);
  assert.equal(index.observations[0].format,format);assert.equal(index.observations[0].pages[0].reading_status,'pixel_model_observation');
 }
 assert.equal(attachmentReadingIndex([],[source(a,'earlier_conversation_source')]),undefined,'a greeting cannot start a new observation');
});

test('same original reupload preserves earlier success beside current failure without claiming a new verification',()=>{
 const old=file(a,74,'Beta 14'),failed=file(a,74,'Beta 14');
 failed.pages[0].visual_content_reviewed=false;failed.pages[0].visual_error_code='http_503';
 delete failed.pages[0].visual_analysis;
 const task={request:{task_id:'reupload'},context_input_files:['current.pptx'],scene_inputs:[
  {name:'current.pptx',file:'current.pptx',version_sha256:a},
 ]};
 const rawOld=envelope([old]),rawCurrent=envelope([failed]);
 const message=attachmentContextMessage(task,rawCurrent,undefined,[rawOld]);
 const body=JSON.parse(message.content[0].text.split('\n').slice(1).join('\n'));
 const records=body.source_reading_index.observations;
 assert.equal(records.length,2);
 const fresh=records.find(row=>row.origin==='current_turn_upload');
 const previous=records.find(row=>row.origin==='earlier_conversation_source');
 assert.equal(fresh.pages[0].reading_status,'no_valid_pixel_model_observation');
 assert.equal(fresh.pages[0].error_code,'http_503');
 assert.equal(previous.admitted_origin,'current_turn_upload');
 assert.equal(previous.pages[0].pixel_observation,'蓝色Alpha为31，紫色Beta为74。');
 assert.equal(previous.provenance,'evidence_context_origin_not_new_visual_execution_or_verification');
 assert.equal(previous.pages[0].verification,'auxiliary_model_reading_not_independent_fact_verification');
 assert.equal(body.current_upload_evidence,rawCurrent);
 assert.match(body.previous_attachment_evidence[0],/Beta 14/);
 const wrongFormat=attachmentReadingIndex([{value:rawOld,origin:'earlier_conversation_source'}],
  [source(a,'current_turn_upload','pdf')]);
 assert.equal(wrongFormat,undefined,'a matching digest cannot promote an incompatible source format');
});
