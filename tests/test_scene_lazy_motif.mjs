/** Development diagnostics: no model requests or claims of optimization. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,readFileSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve,sep} from 'node:path';
import {dataInterceptor} from '../src/adapters/harless_legacy_motif.ts';

test('Data Motif delegates without files, then observes the normal tool after it materializes sources',async()=>{
 const root=mkdtempSync(join(tmpdir(),'geneloop-lazy-motif-')),events=[];
 try{
  const library=JSON.parse(readFileSync(new URL('../motif-libraries/data/library.json',import.meta.url)));
  const interceptor=dataInterceptor(library,root,'execute',event=>events.push(event));
  let ordinary=0;const next=()=>{ordinary++;return 'ordinary-model';};
  assert.equal(await interceptor.intercept('own-session',{tools:[]},next),'ordinary-model');
  assert.equal(ordinary,1);assert.deepEqual(events,[]);
  const sources=join(root,'report/sources/cases/uploaded');mkdirSync(sources,{recursive:true});
  for(const [name,value] of Object.entries({'data.csv':'x,y\n1,3\n2,5\n','study.json':'{}','task.txt':'synthetic lazy tool diagnostic'}))writeFileSync(join(sources,name),value);
  // A normal model's malformed tool args reach the original barrier only after
  // sources exist. It must still delegate, never fabricate a learned receipt.
  interceptor.observe('own-session',{name:'mcp__research_report__inspect_study',callId:'diagnostic',arguments:'{'},{isError:true});
  assert.equal(events.at(-1).reason,'model_arguments_invalid_json');
  assert.equal(await interceptor.intercept('own-session',{tools:[]},next),'ordinary-model');
  assert.equal(ordinary,2);assert.ok(!events.some(e=>e.kind==='model_request_skipped_verified'));
 }finally{assert.ok(resolve(root).startsWith(resolve(tmpdir())+sep));rmSync(root,{recursive:true,force:true});}
});
