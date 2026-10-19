import test from 'node:test';
import assert from 'node:assert/strict';
import {analyzePdfPages,pdfVisionClient,reusePageObservations} from '../src/adapters/geneloop_pdf_vision.ts';

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
 let index=0;
 for(const answer of ['saw the chart',JSON.stringify({source_id:'right',page:2,image_observed:true,observations:'wrong page',unreadable:[]}),
  JSON.stringify({source_id:'right',page:1,image_observed:false,observations:'no pixels',unreadable:[]})]){
  const page={page:1,source_id:'right',visual_present:true,image:{media_type:'image/jpeg',data:'YWJj'}};
  await analyzePdfPages({files:[{pages:[page]}]},async()=>answer,'');
  assert.equal(page.visual_content_reviewed,false);assert.equal(page.visual_analysis,undefined);
  assert.equal(page.visual_error_code,['malformed_json','page_mismatch','image_not_observed'][index++]);
 }
});

test('PPT style observations require actual slide pixels and retain theme evidence separately',async()=>{
 for(const style of [undefined,'Observed teal header, large white title, generous margins']){
  const page={page:1,source_id:'pptx:exact:slide:1',text:'Title',visual_present:true,style:{fonts:['Aptos']},image:{media_type:'image/jpeg',data:'YWJj',sha256:'exact-render'}};
  const file={format:'pptx',name:'reference.pptx',pages:[page],presentation_style:{coverage:'stored_declarations_not_resolved_rendering'}};
  await analyzePdfPages({files:[file]},async parts=>{
    assert.match(parts[0].text,/style_observations/);assert.match(parts[0].text,/Aptos/);
    return JSON.stringify({source_id:page.source_id,page:1,image_observed:true,observations:'Title page',unreadable:[],style_observations:style});
  },'Use the design with new content');
  assert.equal(page.visual_content_reviewed,!!style);assert.equal(page.image,undefined);
  assert.equal(page.rendered_image.sha256,'exact-render');
 }
});

test('all pages have bounded parallel visual coverage and source observations ignore the current question',async()=>{
  let active=0,peak=0,started=0,release;
  const gate=new Promise(resolve=>{release=resolve;});
  const pages=Array.from({length:7},(_,i)=>({page:i+1,source_id:`page-${i+1}`,visual_present:true,
    image:{media_type:'image/jpeg',data:'YWJj',sha256:'exact'}}));
  const progress=[];
  const run=analyzePdfPages({files:[{pages}]},async parts=>{
    assert.equal(parts[0].text.includes('UNIQUE_CURRENT_GREETING'),false);
    const current=JSON.parse(parts[0].text.split('当前页来源：')[1]);
    started++;peak=Math.max(peak,++active);await gate;active--;
    return '```json\n'+JSON.stringify({source_id:current.source_id,page:current.page,image_observed:true,observations:'当前页图表',unreadable:[]})+'\n```';
  },'UNIQUE_CURRENT_GREETING',undefined,(done,total)=>progress.push([done,total]));
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(started,3);release();await run;
  assert.equal(peak,3);assert.equal(started,7);
  assert.equal(pages.every(page=>page.visual_content_reviewed),true);
  assert.deepEqual(progress.at(-1),[7,7]);
});

test('renderer gaps are explicit and OCR retries reuse only exactly matching page pixels',async()=>{
  const page={page:1,source_id:'exact-page',visual_present:true,image:{sha256:'render-a',data:'pixels'}};
  const observed={...page,visual_content_reviewed:true,rendered_image:{sha256:'render-a'},
    visual_analysis:{source_id:'exact-page',page:1,image_observed:true,observations:'bar A=17',unreadable:[]}};
  reusePageObservations({sha256:'original',pages:[page]},{sha256:'original',pages:[observed]});
  assert.equal(page.visual_content_reviewed,true);assert.equal(page.image,undefined);
  const changed={page:1,source_id:'exact-page',visual_present:true,image:{sha256:'render-b'}};
  reusePageObservations({sha256:'original',pages:[changed]},{sha256:'original',pages:[observed]});
  assert.equal(changed.visual_content_reviewed,undefined);
  const result=await analyzePdfPages({files:[{pages:[{page:1,visual_present:true}]}]},async()=>{throw Error('not called');},'');
  assert.deepEqual(result.files[0].visual_coverage.failed_pages,[{page:1,code:'page_render_unavailable'}]);
  assert.equal(result.files[0].visual_content_reviewed,false);
});
