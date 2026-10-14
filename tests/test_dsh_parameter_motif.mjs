import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, realpathSync, writeFileSync, readFileSync, rmSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { digest } from '../src/motif_core/online_skill_runtime.mjs';
import { createParameterInterceptor, completeRead, crossrefArguments, crossrefResult } from '../src/adapters/dsh_parameter_motif.ts';

const hash = p => createHash('sha256').update(readFileSync(p)).digest('hex');
const response = path => ({content:[{type:'text',text:'<path>'+path+'</path>\n<content>\n'+readFileSync(path,'utf8').replace(/\n$/,'').split('\n').map((s,i)=>(i+1)+': '+s).join('\n')+'\n</content>'}]});
function fixture(mode='execute', kind='read') {
  const dir=realpathSync(mkdtempSync(join(tmpdir(),'parameter-proof-')));const audit=[];
  writeFileSync(join(dir,'a.tex'),'source a\n');writeFileSync(join(dir,'b.tex'),'source b\n');
  writeFileSync(join(dir,'references.bib'),'arxiv 2501.12345 and 2502.54321');
  const params={type:'object'};
  const proto=kind==='read'?{tool:'read',contract:'complete-local-text-read-v1'}:
    {tool:'web_fetch',contract:'arxiv-page-fetch-v1',arguments:{url:{template:'https://arxiv.org/abs/{id}'}}};
  const lib={certification_scope:'parameterized_continuation_probe',motifs:[{motif_id:'m',prototype:proto,
    training_witnesses:[{run_id:'train'}],authorization:'explicit_versioned_input_binding_only'}]};lib.manifest_digest=digest(lib);
  const items=kind==='read'?['a.tex','b.tex'].map(n=>({item_id:n,file_path:n,sha256:hash(join(dir,n))})):
    ['2501.12345','2502.54321'].map(id=>({item_id:id,id,source_path:'references.bib'}));
  const binding={schema_version:1,library_digest:lib.manifest_digest,motif_id:'m',items,
    sources:[{path:'references.bib',sha256:hash(join(dir,'references.bib'))}]};
  writeFileSync(join(dir,'binding.json'),JSON.stringify(binding,null,2));
  const make=()=>createParameterInterceptor({library:lib,work:dir,sessionId:'root',bindingPath:'binding.json',
    bindingHash:hash(join(dir,'binding.json')),schemaHashes:{read:digest(params),web_fetch:digest(params)},
    toolOrder:['read','web_fetch'],mode,audit:r=>audit.push(r)});
  const runtime=make();
  const req={tools:[{name:'read',parameters:params},{name:'web_fetch',parameters:params}]};
  const arm=()=>runtime.observe('root',{name:'read',arguments:{file_path:'binding.json'}},response(join(dir,'binding.json')));
  return {dir,audit,runtime,req,arm,make};
}
test('parameter batch joins unordered results and only counts a verified whole request once',async()=>{
  const f=fixture();try{
    f.arm();const chunks=[];
    for await(const c of await f.runtime.intercept('root',f.req,()=>{throw Error('must skip')}))chunks.push(c);
    const calls=chunks.filter(c=>c.type==='tool-call-delta').reverse();assert.equal(calls.length,2);
    for (const [i,c] of calls.entries()) {
      const args=JSON.parse(c.argumentsDelta);f.runtime.observe('root',{name:'read',arguments:args,callId:c.id},response(args.file_path));
      assert.equal(f.audit.filter(r=>r.kind==='model_request_skipped_verified').length,i===0?0:1);
    }
  }finally{rmSync(f.dir,{recursive:true,force:true})}
});
test('partial reads and failed peers never certify the join; then model fallback resumes',async()=>{
  const f=fixture();try{
    f.arm();const chunks=[];for await(const c of await f.runtime.intercept('root',f.req,()=>[]))chunks.push(c);
    for(const c of chunks.filter(c=>c.type==='tool-call-delta')){
      const args=JSON.parse(c.argumentsDelta);f.runtime.observe('root',{name:'read',arguments:args,callId:c.id},{isError:true,content:[]});
    }
    assert.equal(f.audit.filter(r=>r.kind==='model_request_skipped_verified').length,0);
    assert.equal(f.audit.filter(r=>r.kind==='bypass_result_unverified').length,1);
    let providers=0;await f.runtime.intercept('root',f.req,()=>{providers++;return []});assert.equal(providers,1);
    assert.equal(completeRead({content:[{type:'text',text:'<path>'+join(f.dir,'a.tex')+'</path><content>\n1: wrong\n</content>'}]},join(f.dir,'a.tex')),false);
  }finally{rmSync(f.dir,{recursive:true,force:true})}
});
for(const change of ['source','binding','schema','order','identity']) test('parameter guard refuses changed '+change,async()=>{
  const f=fixture();try{
    f.arm();let req=f.req;
    if(change==='source')writeFileSync(join(f.dir,'references.bib'),'changed');
    if(change==='binding')writeFileSync(join(f.dir,'binding.json'),'{}');
    if(change==='schema')req={tools:[{name:'read',parameters:{changed:true}},f.req.tools[1]]};
    if(change==='order')req={tools:[...req.tools].reverse()};
    let providers=0;await f.runtime.intercept(change==='identity'?'child':'root',req,()=>{providers++;return []});
    assert.equal(providers,1);assert.equal(f.audit.filter(r=>r.kind==='motif_bypass_attempt').length,0);
  }finally{rmSync(f.dir,{recursive:true,force:true})}
});
test('shadow observes native evidence without suppressing a model request',async()=>{
  const f=fixture('shadow');try{
    f.arm();let providers=0;await f.runtime.intercept('root',f.req,()=>{providers++;return []});
    for(const n of ['b.tex','a.tex'])f.runtime.observe('root',{name:'read',arguments:{file_path:n}},response(join(f.dir,n)));
    assert.equal(providers,1);assert.equal(f.audit.filter(r=>r.kind==='shadow_result'&&r.verified).length,2);
    assert.equal(f.audit.filter(r=>r.kind==='model_request_skipped_verified').length,0);
  }finally{rmSync(f.dir,{recursive:true,force:true})}
});
test('fetch join verifies fresh collection, not historical page bytes; wrong page fails',async()=>{
  const f=fixture('execute','web_fetch');try{
    f.arm();const chunks=[];for await(const c of await f.runtime.intercept('root',f.req,()=>[]))chunks.push(c);
    for(const c of chunks.filter(c=>c.type==='tool-call-delta')){
      const args=JSON.parse(c.argumentsDelta);const id=args.url.split('/').at(-1);
      f.runtime.observe('root',{name:'web_fetch',arguments:args,callId:c.id},{content:[{type:'text',text:'Fetched '+args.url+' (HTTP 200)\narXiv: '+id+'\nTitle: fresh dynamically changed page\nAuthors: Verified publisher metadata\n'+'.'.repeat(100)}]});
    }
    assert.equal(f.audit.filter(r=>r.kind==='model_request_skipped_verified').length,1);
  }finally{rmSync(f.dir,{recursive:true,force:true})}
});
for (const bad of ['wrong_id','missing_authors','wrong_status','timeout']) test('fetch collection refuses '+bad+' and never certifies the batch',async()=>{
  const f=fixture('execute','web_fetch');try{
    f.arm();const chunks=[];for await(const c of await f.runtime.intercept('root',f.req,()=>[]))chunks.push(c);
    for(const c of chunks.filter(c=>c.type==='tool-call-delta')) {
      const args=JSON.parse(c.argumentsDelta);const id=args.url.split('/').at(-1);
      const content='Fetched '+args.url+' (HTTP '+(bad==='wrong_status'?'403':'200')+')\narXiv: '+(bad==='wrong_id'?'9999.99999':id)+'\nTitle: paper\n'+(bad==='missing_authors'?'':'Authors: author\n');
      f.runtime.observe('root',{name:'web_fetch',arguments:args,callId:c.id},{isError:bad==='timeout',content:[{type:'text',text:content}]});
    }
    assert.equal(f.audit.filter(r=>r.kind==='model_request_skipped_verified').length,0);
    assert.equal(f.audit.filter(r=>r.kind==='bypass_result_unverified').length,1);
  }finally{rmSync(f.dir,{recursive:true,force:true})}
});

import { createSelectedParameterInterceptor } from '../src/adapters/dsh_parameter_motif.ts';
function selectedFixture(mode='execute') {
  const f=fixture(mode);
  const binding=JSON.parse(readFileSync(join(f.dir,'binding.json'),'utf8'));
  const library={certification_scope:'parameterized_continuation_probe',motifs:[{motif_id:'m',prototype:{tool:'read',contract:'complete-local-text-read-v1'},training_witnesses:[{run_id:'train'}],authorization:'explicit_versioned_input_binding_only'}]};
  library.manifest_digest=digest(library);
  const catalog={library_digest:library.manifest_digest,sources:binding.sources,read_items:binding.items,query_items:[]};
  writeFileSync(join(f.dir,'catalog.json'),JSON.stringify(catalog));
  const runtime=createSelectedParameterInterceptor({library,work:f.dir,sessionId:'root',catalogPath:'catalog.json',catalogHash:hash(join(f.dir,'catalog.json')),bindingPath:'selection.json',schemaHashes:{read:digest({type:'object'})},toolOrder:['read','web_fetch'],mode,audit:r=>f.audit.push(r)});
  const readCatalog=()=>runtime.observe('root',{name:'read',arguments:{file_path:'catalog.json'}},response(join(f.dir,'catalog.json')));
  const select=(items,overrides={})=>{
    const content=JSON.stringify({...binding,items,...overrides});
    writeFileSync(join(f.dir,'selection.json'),content);
    runtime.observe('root',{name:'write',arguments:{file_path:'selection.json',content}},{content:[]});
  };
  return {...f,runtime,catalog,readCatalog,select};
}
async function finishSelected(f,fail=false) {
  const calls=[];for await(const c of await f.runtime.intercept('root',f.req,()=>[])) if(c.type==='tool-call-delta')calls.push(c);
  for(const c of calls){const args=JSON.parse(c.argumentsDelta);f.runtime.observe('root',{name:'read',arguments:args,callId:c.id},fail?{isError:true}:response(args.file_path));}
  return calls.length;
}
test('model can select two different batches with semantic handoff after each join',async()=>{
 const f=selectedFixture();try{
  f.readCatalog();f.select([f.catalog.read_items[1]]);assert.equal(await finishSelected(f),1);
  let providers=0;await f.runtime.intercept('root',f.req,()=>{providers++;return []});assert.equal(providers,1);
  f.select([f.catalog.read_items[0]]);assert.equal(await finishSelected(f),1);
  assert.equal(f.audit.filter(r=>r.kind==='model_request_skipped_verified').length,2);
  f.select([f.catalog.read_items[0]]);assert.equal(await finishSelected(f),0);
  assert.ok(f.audit.some(r=>r.reason==='replayed selection'));
 }finally{rmSync(f.dir,{recursive:true,force:true})}
});
for(const bad of ['not_read','outside_catalog','catalog_change','source_change','wrong_sources','wrong_session'])test('selected plan refuses '+bad,async()=>{
 const f=selectedFixture();try{
  if(bad!=='not_read')f.readCatalog();
  let items=f.catalog.read_items, overrides={};
  if(bad==='outside_catalog')items=[{...items[0],item_id:'forged'}];
  if(bad==='catalog_change')writeFileSync(join(f.dir,'catalog.json'),'{}');
  if(bad==='source_change')writeFileSync(join(f.dir,'references.bib'),'changed');
  if(bad==='wrong_sources')overrides={sources:[]};
  if(bad==='wrong_session')f.runtime.observe('child',{name:'write',arguments:{file_path:'selection.json',content:'{}'}},{});
  else f.select(items,overrides);
  assert.equal(await finishSelected(f),0);assert.equal(f.audit.filter(r=>r.kind==='motif_bypass_attempt').length,0);
 }finally{rmSync(f.dir,{recursive:true,force:true})}
});
test('a failed selected batch restores model and does not poison a later distinct valid plan',async()=>{
 const f=selectedFixture();try{
  f.readCatalog();f.select([f.catalog.read_items[0]]);assert.equal(await finishSelected(f,true),1);
  let providers=0;await f.runtime.intercept('root',f.req,()=>{providers++;return []});assert.equal(providers,1);
  f.select([f.catalog.read_items[1]]);assert.equal(await finishSelected(f),1);
  assert.equal(f.audit.filter(r=>r.kind==='bypass_result_unverified').length,1);
  assert.equal(f.audit.filter(r=>r.kind==='model_request_skipped_verified').length,1);
 }finally{rmSync(f.dir,{recursive:true,force:true})}
});

test('compact binding pins the exact catalog bytes instead of copying source list',async()=>{
 const f=selectedFixture();try{
  f.readCatalog();f.select([f.catalog.read_items[0]],{schema_version:2,catalog_sha256:hash(join(f.dir,'catalog.json')),sources:undefined});
  assert.equal(await finishSelected(f),1);
  assert.equal(f.audit.filter(r=>r.kind==='model_request_skipped_verified').length,1);
 }finally{rmSync(f.dir,{recursive:true,force:true})}
});
for(const bad of ['catalog_hash','write_content','symlink'])test('compact selection refuses '+bad,async()=>{
 const f=selectedFixture();try{
  f.readCatalog();
  if(bad==='symlink'){rmSync(join(f.dir,'a.tex'));symlinkSync('/etc/hosts',join(f.dir,'a.tex'));}
  const content=JSON.stringify({schema_version:2,catalog_sha256:bad==='catalog_hash'?'0'.repeat(64):hash(join(f.dir,'catalog.json')),library_digest:f.catalog.library_digest,motif_id:'m',items:[f.catalog.read_items[0]]});
  writeFileSync(join(f.dir,'selection.json'),content);
  f.runtime.observe('root',{name:'write',arguments:{file_path:'selection.json',content:bad==='write_content'?'{}':content}},{content:[]});
  assert.equal(await finishSelected(f),0);
 }finally{rmSync(f.dir,{recursive:true,force:true})}
});

test('native tools in the same plan batch are not executed twice by Runtime',async()=>{
 const f=selectedFixture();try{
  f.readCatalog();f.select(f.catalog.read_items);
  f.runtime.observe('root',{name:'read',arguments:{file_path:'a.tex'}},response(join(f.dir,'a.tex')));
  assert.equal(await finishSelected(f),1);
  assert.equal(f.audit.filter(r=>r.kind==='native_collection_satisfied').length,1);
  assert.equal(f.audit.find(r=>r.kind==='model_request_skipped_verified').tool_count,1);
 }finally{rmSync(f.dir,{recursive:true,force:true})}
});
test('already complete native batch returns to model without a synthetic skip',async()=>{
 const f=selectedFixture();try{
  f.readCatalog();f.select(f.catalog.read_items);
  for(const n of ['a.tex','b.tex'])f.runtime.observe('root',{name:'read',arguments:{file_path:n}},response(join(f.dir,n)));
  let providers=0;await f.runtime.intercept('root',f.req,()=>{providers++;return []});
  assert.equal(providers,1);assert.equal(f.audit.filter(r=>r.kind==='motif_bypass_attempt').length,0);
 }finally{rmSync(f.dir,{recursive:true,force:true})}
});
test('shadow verifies same-batch native tools even before the next provider request',async()=>{
 const f=selectedFixture('shadow');try{
  f.readCatalog();f.select(f.catalog.read_items);
  for(const n of ['a.tex','b.tex'])f.runtime.observe('root',{name:'read',arguments:{file_path:n}},response(join(f.dir,n)));
  assert.equal(f.audit.filter(r=>r.kind==='shadow_result'&&r.verified).length,2);
  assert.equal(await finishSelected(f),0);
 }finally{rmSync(f.dir,{recursive:true,force:true})}
});

test('duplicate model-selected identities are rejected before plan acceptance',async()=>{
 const f=selectedFixture();try{
  f.readCatalog();f.select([f.catalog.read_items[0],f.catalog.read_items[0]]);
  assert.equal(await finishSelected(f),0);
  assert.equal(f.audit.filter(r=>r.kind==='selection_accepted').length,0);
 }finally{rmSync(f.dir,{recursive:true,force:true})}
});

const crossrefProto = () => ({tool:'web_fetch',contract:'crossref-search-fetch-v1',arguments:{url:{
  base:'https://api.crossref.org/works',query:[{name:'query.bibliographic',slot:'query'},
    {name:'rows',value:'3'},{name:'select',value:'DOI,title,author'}]}}});
function crossrefFixture(mode='shadow',change=null) {
  const f=fixture(mode);const proto=crossrefProto();
  if(change==='host')proto.arguments.url.base='https://untrusted.example/works';
  writeFileSync(join(f.dir,'references.bib'),'title={An Example Study}\ntitle={A Different Study}\n');
  if(change==='brace_group')writeFileSync(join(f.dir,'references.bib'),'title={An Ex{am}ple Study}\ntitle={A {Different} Study}\n');
  if(change==='wrong_field')writeFileSync(join(f.dir,'references.bib'),'note={An Example Study}\ntitle={A Different Study}\n');
  const items=['An Example Study','A Different Study'].map(query=>({item_id:query,query,source_path:'references.bib'}));
  if(change==='unwitnessed')items[0].query='A fabricated query outside source';
  const library={certification_scope:'parameterized_continuation_probe',motifs:[{
    motif_id:'crossref',prototype:proto,training_witnesses:[{run_id:'normal'}],authorization:'explicit_versioned_input_binding_only'}]};
  library.manifest_digest=digest(library);
  const binding={schema_version:1,library_digest:library.manifest_digest,motif_id:'crossref',items,
    sources:[{path:'references.bib',sha256:hash(join(f.dir,'references.bib'))}]};
  writeFileSync(join(f.dir,'binding.json'),JSON.stringify(binding));
  f.runtime=createParameterInterceptor({library,work:f.dir,sessionId:'root',bindingPath:'binding.json',
    bindingHash:hash(join(f.dir,'binding.json')),schemaHashes:{web_fetch:digest({type:'object'})},
    toolOrder:['read','web_fetch'],mode,audit:r=>f.audit.push(r)});
  f.arm=()=>f.runtime.observe('root',{name:'read',arguments:{file_path:'binding.json'}},response(join(f.dir,'binding.json')));
  return {...f,proto,items};
}
const metadataResult = (url,items=[{DOI:'10.1234/example',title:['Candidate title needing semantic review']}]) =>
  ({content:[{type:'text',text:'Fetched '+url+' (HTTP 200)\n'+JSON.stringify({status:'ok',message:{items}})}]});
test('learned Crossref lookup shadow observes fresh JSON without claiming title equality',async()=>{
  const f=crossrefFixture();try{
    f.arm();let providers=0;await f.runtime.intercept('root',f.req,()=>{providers++;return []});
    for(const item of f.items){const args=crossrefArguments(f.proto,item);f.runtime.observe('root',{name:'web_fetch',arguments:args},metadataResult(args.url));}
    assert.equal(providers,1);assert.equal(f.audit.filter(r=>r.kind==='shadow_result'&&r.verified).length,2);
    assert.equal(f.audit.filter(r=>r.kind==='model_request_skipped_verified').length,0);
  }finally{rmSync(f.dir,{recursive:true,force:true})}
});
test('Crossref execute joins candidate metadata and empty lookup miss before semantic return',async()=>{
  const f=crossrefFixture('execute');try{
    f.arm();const calls=[];for await(const c of await f.runtime.intercept('root',f.req,()=>[]))if(c.type==='tool-call-delta')calls.push(c);
    for(const c of calls){const args=JSON.parse(c.argumentsDelta);f.runtime.observe('root',{name:'web_fetch',arguments:args,callId:c.id},metadataResult(args.url,[]));}
    assert.equal(calls.length,2);assert.equal(f.audit.filter(r=>r.kind==='model_request_skipped_verified').length,1);
  }finally{rmSync(f.dir,{recursive:true,force:true})}
});
for(const bad of ['host','unwitnessed','wrong_field'])test('Crossref refuses '+bad+' before bypass',async()=>{
  const f=crossrefFixture('execute',bad);try{
    f.arm();let providers=0;await f.runtime.intercept('root',f.req,()=>{providers++;return []});
    assert.equal(providers,1);assert.equal(f.audit.filter(r=>r.kind==='motif_bypass_attempt').length,0);
  }finally{rmSync(f.dir,{recursive:true,force:true})}
});
test('Crossref query provenance strips BibTeX grouping without splitting words',async()=>{
  const f=crossrefFixture('shadow','brace_group');try{
    f.arm();await f.runtime.intercept('root',f.req,()=>[]);
    for(const item of f.items){const args=crossrefArguments(f.proto,item);f.runtime.observe('root',{name:'web_fetch',arguments:args},metadataResult(args.url));}
    assert.equal(f.audit.filter(r=>r.kind==='shadow_result'&&r.verified).length,2);
  }finally{rmSync(f.dir,{recursive:true,force:true})}
});
test('Crossref refuses malformed, truncated, wrong-status or wrong-request results',()=>{
  const url=crossrefArguments(crossrefProto(),{query:'An Example Study'}).url;
  const valid=metadataResult(url).content[0].text;assert.equal(crossrefResult(valid,url),true);
  for(const bad of [valid.slice(0,-1),valid.replace('(HTTP 200)','(HTTP 403)'),
    valid.replace('10.1234/example','wrong'),valid.replace('"status":"ok"','"status":"error"')])
    assert.equal(crossrefResult(bad,url),false);
  assert.equal(crossrefResult(valid,url+'&extra=1'),false);
  assert.throws(()=>crossrefArguments({...crossrefProto(),arguments:{url:{base:'https://api.crossref.org/works',query:[
    {name:'query.title',slot:'query'},{name:'rows',value:'999'},{name:'select',value:'DOI,title'}]}}},{query:'x'}));
});
test('Crossref query escaping agrees with Python for punctuation and Unicode',()=>{
  const url=crossrefArguments(crossrefProto(),{query:'A ~ * & + 中文 study'}).url;
  assert.equal(url,'https://api.crossref.org/works?query.bibliographic=A+~+%2A+%26+%2B+%E4%B8%AD%E6%96%87+study&rows=3&select=DOI%2Ctitle%2Cauthor');
});
