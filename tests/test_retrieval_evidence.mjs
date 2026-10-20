import test from 'node:test';
import assert from 'node:assert/strict';
import {Context} from '@deepseek-ai/cordis';
import {ToolRuntime} from '@deepseek-ai/dsh-tools';
import {applyWebSearchTool} from '@deepseek-ai/dsh-tool-web';
import {createRetrievalEvidence,evidenceSearchTool} from '../src/adapters/retrieval_evidence.ts';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,rmSync,realpathSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {createHash} from 'node:crypto';

function fixture(){
 let scope={task:'a',input:'v1',goal:'verify metadata'},at=1000,calls=0;
 const audit=[],raw={sources:Array.from({length:12},(_,i)=>({url:`https://example.org/${i}`,title:`Candidate ${i}`})),truncated:false};
 const memory=createRetrievalEvidence({binding:()=>scope,audit:x=>audit.push(x),now:()=>at,ttlMs:100});
 const search=query=>memory.search({query},undefined,async()=>{calls++;return structuredClone(raw);});
 return {memory,audit,search,get calls(){return calls;},set scope(x){scope=x;},set time(x){at=x;}};
}
test('exact reuse skips the provider, but does not promote candidates to verified facts or share mutable data',async()=>{
 const f=fixture(),first=await f.search('title author'),id=f.audit[0].evidence_id;
 first.sources[0].title='mutated';const second=await f.search('title author');
 assert.equal(f.calls,1);assert.equal(second.sources[0].title,'Candidate 0');assert.match(second.content,/"fact_verified":false/);
 assert.match(second.content,RegExp(id));assert.equal(f.audit.at(-1).avoided_search_requests,1);
});
test('semantic reuse is explicit, mixed batches query fresh only, and stale/foreign handles fall back',async()=>{
 const f=fixture();await f.search('title author');const id=f.audit[0].evidence_id;let dispatched;
 const execute=(args)=>f.memory.execute(args,{},async a=>{dispatched=a;return {sources:[],truncated:false};});
 const result=await execute({queries:['same work venue question','another work'],reuse:[{query_index:0,evidence_id:id}]});
 assert.deepEqual(dispatched,{queries:['another work']});assert.match(result.content,/same work venue question/);
 assert.equal(f.audit.at(-1).match,'model_selected_candidates');
 f.time=1101;await execute({queries:['same work venue question'],reuse:[{query_index:0,evidence_id:id}]});
 assert.deepEqual(dispatched,{queries:['same work venue question']});assert.equal(f.audit.at(-1).reason,'unknown_expired_or_changed_evidence');
});
test('input, task or goal changes invalidate cached evidence; aborted and failed search never populate it',async()=>{
 const f=fixture();await f.search('q');f.scope={task:'a',input:'v2',goal:'verify metadata'};await f.search('q');assert.equal(f.calls,2);
 f.scope={task:'b',input:'v2',goal:'verify metadata'};await f.search('q');assert.equal(f.calls,3);
 f.scope={task:'b',input:'v2',goal:'new question'};await f.search('q');assert.equal(f.calls,4);
 const abort=new AbortController();abort.abort();await assert.rejects(f.memory.search({query:'q'},abort.signal,async()=>assert.fail()));
 await assert.rejects(f.memory.search({query:'failed'},undefined,async()=>{throw Error('network');}));
 await f.search('failed');assert.equal(f.calls,5);
});
test('capture rejects unsafe source shapes, bounds overflow and preserves the native result on rejection',async()=>{
 const f=fixture(),bad={sources:[{url:'file:///private'}],truncated:false};
 assert.equal(await f.memory.search({query:'bad'},undefined,async()=>bad),bad);
 assert.equal(f.audit.at(-1).kind,'retrieval_evidence_capture_rejected');
 await assert.rejects(f.memory.execute({queries:['q'],reuse:[{query_index:2,evidence_id:'x'}]}, {},async()=>assert.fail()));
});
test('duplicate selections never claim more skips than the native deduplicated query batch',async()=>{
 const f=fixture();await f.search('q');const id=f.audit[0].evidence_id;
 await f.memory.execute({queries:['q','q'],reuse:[{query_index:0,evidence_id:id},{query_index:1,evidence_id:id}]},{},async()=>assert.fail());
 assert.equal(f.audit.filter(x=>x.kind==='retrieval_evidence_reused').reduce((n,r)=>n+r.avoided_search_requests,0),1);
});
test('native schema and batch renderer preserve per-query sources beyond the combined eight-source cap',async t=>{
 const f=fixture(),ctx=new Context();ctx.systemPrompt={section(){},getSectionOrder(){return 1;},tools(){}};
 const tools=new ToolRuntime(ctx);ctx.web={search:req=>f.search(req.query)};
 applyWebSearchTool(ctx,8,4,30000,false);const original=tools.get('web_search');
 const shadow=evidenceSearchTool(original,f.memory);
 assert.ok(shadow.parameters.properties.reuse);assert.deepEqual(shadow.parameters.required,original.parameters.required);
 // A scoped shadow is exercised in the live Harness below; this diagnostic
 // registers its identical definition under another local name.
 const dispose=tools.register({...shadow,name:'evidence_search'});t.after(dispose);
 const exec=args=>tools.execute({name:'evidence_search',arguments:args,callId:'test',signal:new AbortController().signal});
 const first=await exec({queries:['q1','q2']});assert.equal(first.isError,false);
 const text=first.content.map(p=>p.text??'').join('\n');assert.match(text,/Candidate 11/);assert.match(text,/"original_query":"q2"/);
 const id=f.audit.find(x=>x.kind==='retrieval_evidence_captured').evidence_id;
 const reused=await exec({queries:['venue question'],reuse:[{query_index:0,evidence_id:id}]});
 assert.equal(reused.isError,false);assert.equal(f.calls,2);assert.match(reused.content[0].text,/"reused":true/);
});
test('experimental provider binds real approved input bytes and refuses foreign owners or changed files',async()=>{
 const root=realpathSync(mkdtempSync(join(tmpdir(),'retrieval-owner-'))),saved={};
 for(const key of ['SSS_RETRIEVAL_EVIDENCE','SSS_WEB_POLICY','SSS_RETRIEVAL_SEARCH_OUTPUT_TOKENS','DEEPSEEK_API_KEY'])saved[key]=process.env[key];
 const fetch=globalThis.fetch;
 try{
  const task=join(root,'tasks','task-a'),work=join(root,'sessions','owned','work');mkdirSync(task,{recursive:true});mkdirSync(join(work,'inputs'),{recursive:true});
  const hash=x=>createHash('sha256').update(x).digest('hex');writeFileSync(join(work,'inputs','source.txt'),'original');
  writeFileSync(join(work,'approved-inputs.json'),JSON.stringify({files:{'source.txt':hash('original')}}));
  const state={session_id:'owned',user_id:'owner',status:'running',scene:'paper-proofreading',task_id:'task-a'};
  writeFileSync(join(task,'task-state.json'),JSON.stringify(state));writeFileSync(join(task,'effective-config.json'),JSON.stringify({session_id:'owned',user_id:'owner',workspace:work}));writeFileSync(join(task,'task.json'),'{}');
  process.env.SSS_RETRIEVAL_EVIDENCE='1';process.env.SSS_RETRIEVAL_SEARCH_OUTPUT_TOKENS='128';process.env.DEEPSEEK_API_KEY='diagnostic';process.env.SSS_WEB_POLICY=join(root,'policy.json');
  writeFileSync(process.env.SSS_WEB_POLICY,JSON.stringify({output:root,user_id:'owner',endpoint:'http://127.0.0.1:12345/v1'}));
  let provider,created,dispatches=0;const agent={session:{id:'owned',requestHeader:()=>({config:{model:'deepseek-flash'}}),append(){}}};
  const {apply}=await import('../src/adapters/retrieval_web_search.ts');
  apply({on:(event,fn)=>{if(event==='agent/created')created=fn;},web:{registerSearchProvider:p=>provider=p},agents:{currentInitiator:()=>agent}});
  assert.equal(typeof created,'function');
  globalThis.fetch=async(_url,options)=>{dispatches++;assert.equal(JSON.parse(options.body).max_tokens,128);return new Response(JSON.stringify({content:[{type:'web_search_tool_result',content:[{type:'web_search_result',url:'https://example.org/source'}]}]}));};
  await provider.search({query:'actual source question'});await provider.search({query:'actual source question'});assert.equal(dispatches,1);
  assert.match(readFileSync(join(task,'retrieval-evidence.jsonl'),'utf8'),/retrieval_evidence_reused/);
  writeFileSync(join(work,'inputs','source.txt'),'changed');await assert.rejects(provider.search({query:'actual source question'}),/input_changed/);
  writeFileSync(join(work,'inputs','source.txt'),'original');writeFileSync(join(task,'task-state.json'),JSON.stringify({...state,user_id:'foreign'}));
  await assert.rejects(provider.search({query:'actual source question'}),/owned_paper_task/);assert.equal(dispatches,1);
 }finally{globalThis.fetch=fetch;for(const [k,v]of Object.entries(saved))v===undefined?delete process.env[k]:process.env[k]=v;rmSync(root,{recursive:true,force:true});}
});
