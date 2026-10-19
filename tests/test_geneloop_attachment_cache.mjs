import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,readdirSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {attachmentEvidenceDirectory,cachedAttachmentEvidence} from '../src/adapters/geneloop_attachment_cache.ts';
import {sceneAttachmentContext} from '../src/adapters/harless_task_scope.ts';
import {officeEvidenceVersion} from '../src/adapters/geneloop_presentation.ts';

const digest=bytes=>createHash('sha256').update(bytes).digest('hex');
const python=process.env.SSS_PYTHON??(process.platform==='win32'?'python':'python3');

test('Office evidence versions bind actual renderer and font bytes even at unchanged paths',()=>{
  const root=mkdtempSync(join(tmpdir(),'geneloop-resource-version-'));
  const renderer=join(root,'office'),fonts=join(root,'fonts');
  mkdirSync(join(renderer,'program'),{recursive:true});mkdirSync(fonts);
  writeFileSync(join(renderer,'program','soffice.bin'),'synthetic renderer binary');
  writeFileSync(join(renderer,'program','versionrc'),'BuildVersion=one');
  writeFileSync(join(fonts,'fonts-static.conf'),'synthetic config');
  writeFileSync(join(fonts,'synthetic.ttf'),'font version one');
  const resources={rendererRoot:renderer,fontRoot:fonts},first=officeEvidenceVersion(resources);
  writeFileSync(join(fonts,'synthetic.ttf'),'font version two');
  const second=officeEvidenceVersion(resources);assert.notEqual(first,second);
  writeFileSync(join(renderer,'program','versionrc'),'BuildVersion=two');
  assert.notEqual(second,officeEvidenceVersion(resources));
});

test('shared evidence is source/version bound, coalesced and outside the writable workspace',async()=>{
  const root=mkdtempSync(join(tmpdir(),'geneloop-evidence-')),work=join(root,'work');mkdirSync(work);
  assert.throws(()=>attachmentEvidenceDirectory(work,join(work,'.cache')),/host_private/);
  const cache=attachmentEvidenceDirectory(work,join(root,'evidence'));
  const source={sha256:'a'.repeat(64),format:'.pdf'};
  let calls=0,release;
  const gate=new Promise(resolve=>{release=resolve;});
  const make=async prior=>{if(prior)return prior;calls++;await gate;return {sha256:source.sha256,text:'source evidence'};};
  const first=cachedAttachmentEvidence(cache,source,'v1',make),second=cachedAttachmentEvidence(cache,source,'v1',make);
  release();const [a,b]=await Promise.all([first,second]);
  assert.equal(calls,1);a.text='mutated caller view';assert.equal(b.text,'source evidence');
  await cachedAttachmentEvidence(cache,source,'v2',make);assert.equal(calls,2);
  await cachedAttachmentEvidence(cache,{...source,sha256:'b'.repeat(64)},'v1',async()=>({sha256:'b'.repeat(64)}));
  assert.equal(readdirSync(cache).filter(name=>name.endsWith('.json')).length,3);
});

test('a waiting lane cancels promptly without cancelling another lane source preparation',async()=>{
  const root=mkdtempSync(join(tmpdir(),'geneloop-evidence-abort-')),source={sha256:'c'.repeat(64),format:'.pdf'};
  let release;const gate=new Promise(resolve=>{release=resolve;});
  const first=cachedAttachmentEvidence(root,source,'v1',async()=>{await gate;return {sha256:source.sha256};});
  const controller=new AbortController();
  const waiting=cachedAttachmentEvidence(root,source,'v1',async value=>value,controller.signal);
  controller.abort();await assert.rejects(waiting);
  release();assert.equal((await first).sha256,source.sha256);
});

test('real parsed PDF reuses complete pages, retries failed pages and rejects changed originals',async()=>{
  const root=mkdtempSync(join(tmpdir(),'geneloop-pdf-evidence-')),workspace=join(root,'work'),inputRoot=join(workspace,'inputs');
  mkdirSync(inputRoot,{recursive:true});const path=join(inputRoot,'source.pdf');
  // Deterministic parser fixture; visual calls below are protocol diagnostics,
  // not claims of real model quality or cost savings.
  execFileSync(python,['-c',
    'import pymupdf as f,sys; p=f.open(); [(lambda x:(x.insert_text((30,40),"Page "+str(n)),x.draw_rect((30,60,90,100))))(p.new_page()) for n in (1,2)];p.save(sys.argv[1])',path]);
  const hash=digest(readFileSync(path)),input={file:'source.pdf',name:'source.pdf',version_sha256:hash};
  const previousPython=process.env.SSS_PYTHON;process.env.SSS_PYTHON=python;
  let calls=0;
  const analyze=async parts=>{
    calls++;const page=JSON.parse(parts[0].text.split('当前页来源：')[1]);
    if(calls===2)throw Error('transient failed page');
    return JSON.stringify({source_id:page.source_id,page:page.page,image_observed:true,observations:'source page content',unreadable:[]});
  };
  try{
    const first=JSON.parse((await sceneAttachmentContext(workspace,[input],{analyze})).split('\n').slice(1).join('\n'));
    assert.deepEqual(first.files[0].visual_review,{total_pages:2,reviewed_pages:1});
    const second=JSON.parse((await sceneAttachmentContext(workspace,[input],{analyze,instruction:'你好'})).split('\n').slice(1).join('\n'));
    assert.equal(calls,3);assert.equal(second.files[0].visual_content_reviewed,true);
    await sceneAttachmentContext(workspace,[input],{analyze});assert.equal(calls,3);
    assert.equal(JSON.stringify(second).includes('base64'),false);
    writeFileSync(path,'changed original');
    await assert.rejects(sceneAttachmentContext(workspace,[input],{analyze}),/version_mismatch/);
    assert.equal(calls,3);
  }finally{if(previousPython===undefined)delete process.env.SSS_PYTHON;else process.env.SSS_PYTHON=previousPython;}
});
