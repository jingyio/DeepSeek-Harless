import test from 'node:test';
import assert from 'node:assert/strict';
import {analyzePdfPages,pdfVisionClient} from '../src/adapters/geneloop_pdf_vision.ts';

test('PDF visual analysis binds page pixels, captions, body and adjacent text without leaking images',async()=>{
  const file={name:'paper.pdf',sha256:'a'.repeat(64),pages:[
    {page:1,text:'previous body'},
    {page:2,source_id:'versioned-page-2',captions:['Figure 1: score'],text:'current body',visual_present:true,image:{media_type:'image/jpeg',data:'YWJj',sha256:'b'.repeat(64),width:1800,height:2400}},
    {page:3,text:'next body'},
  ]};
  let calls=0;
  const result=await analyzePdfPages({files:[file]},async parts=>{
    calls++;assert.match(parts[0].text,/previous body/);assert.match(parts[0].text,/next body/);
    assert.match(parts[0].text,/Figure 1: score/);assert.match(parts[0].text,/current body/);
    assert.equal(parts[1].image_url.url,'data:image/jpeg;base64,YWJj');
    return JSON.stringify({source_id:'versioned-page-2',page:2,image_observed:true,observations:'像素观察：Beta 43，Alpha 17。',unreadable:[]});
  },'compare');
  assert.equal(calls,1);assert.equal(result.files[0].visual_content_reviewed,true);
  assert.equal(file.pages[1].visual_analysis_model,'deepseek-flash');
  assert.equal(file.pages[1].rendered_image.sha256,'b'.repeat(64));
  assert.equal(JSON.stringify(result).includes('YWJj'),false);
});

test('vision failures remain partial and cancellation stops before further calls',async()=>{
  const pages=[1,2].map(page=>({page,visual_present:true,image:{media_type:'image/jpeg',data:'YWJj'}}));
  const result=await analyzePdfPages({files:[{pages}]},async()=>{throw Error('private upstream detail');},'');
  assert.deepEqual(result.files[0].visual_review,{total_pages:2,reviewed_pages:0});
  assert.equal(result.files[0].visual_content_reviewed,false);
  assert.equal(JSON.stringify(result).includes('private upstream'),false);
  const abort=new AbortController();abort.abort();let calls=0;
  await assert.rejects(analyzePdfPages({files:[{pages:[{}]}]},async()=>{calls++;return '';},'',abort.signal));
  assert.equal(calls,0);
  assert.throws(()=>pdfVisionClient('https://external/v1','session-any','key'),/owning admitted/);
});

test('HTTP success cannot certify a missing image, wrong page, or unstructured model answer',async()=>{
 for(const answer of ['saw the chart',JSON.stringify({source_id:'right',page:2,image_observed:true,observations:'wrong page',unreadable:[]}),
  JSON.stringify({source_id:'right',page:1,image_observed:false,observations:'no pixels',unreadable:[]})]){
  const page={page:1,source_id:'right',visual_present:true,image:{media_type:'image/jpeg',data:'YWJj'}};
  await analyzePdfPages({files:[{pages:[page]}]},async()=>answer,'');
  assert.equal(page.visual_content_reviewed,false);assert.equal(page.visual_analysis,undefined);
 }
});
