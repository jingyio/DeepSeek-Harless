import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { ApiSessionNotFound } from '@deepseek-ai/dsh-api-session-controller';
import { createSessionTrash, protectDeletedSessions, protectDeletedSessionFiles, protectDeletedSessionQuery, registerSessionTrashRoute } from '../src/adapters/harless_session_trash.ts';

function fixture() {
  const dir = mkdtempSync(join(tmpdir(), 'geneloop-trash-')), path = join(dir, 'trash.json');
  const changes = [], owned = new Set(['parent', 'lane', 'branch', 'other']), busy = new Set();
  const host = { owns: async id => { if (!owned.has(id)) throw Object.assign(Error('找不到这个对话。'), {code:'session_not_found',status:404}); },
    isPrivate: id => id === 'lane', privateChildren: id => id === 'parent' ? ['lane'] : [], busy: ids => ids.some(id => busy.has(id)),
    describe: async id => ({title: '合成 ' + id, workspace_id:'opaque-workspace'}), changed: (id,deleted) => changes.push({id,deleted}) };
  const trash = createSessionTrash(path, 'account-a', host);
  return {dir,path,host,trash,changes,busy,close:()=>rmSync(dir,{recursive:true,force:true})};
}

test('deletion hides only the selected parent and its private lanes; bytes, visible branches and workspace survive restoration',async()=>{
  const f=fixture(); try {
    const source=join(f.dir,'shared-upload.csv'), result=join(f.dir,'retained-report.pdf');
    writeFileSync(source,'synthetic,source\n1,2');writeFileSync(result,Buffer.from([1,5,8,13]));
    const before=[readFileSync(source),readFileSync(result)];
    const receipt=await f.trash.mutate('delete','parent'); assert.equal(receipt.deleted,true);
    assert.equal(f.trash.isDeleted('parent'),true); assert.equal(f.trash.isDeleted('lane'),true);
    assert.equal(f.trash.isDeleted('branch'),false);assert.equal(f.trash.isDeleted('other'),false);
    const listing=f.trash.list();assert.deepEqual(listing.deleted_session_ids,['parent','lane']);
    assert.deepEqual(Object.keys(listing.sessions[0]).sort(),['deleted_at','session_id','title','workspace_id']);
    assert.equal(listing.sessions[0].workspace_id,'opaque-workspace');assert.deepEqual(await f.trash.mutate('delete','parent'),receipt);
    const restarted=createSessionTrash(f.path,'account-a',f.host);assert.equal(restarted.isDeleted('lane'),true);
    await restarted.mutate('restore','parent');assert.equal(restarted.isDeleted('lane'),false);assert.equal(restarted.list().sessions.length,0);
    assert.deepEqual([readFileSync(source),readFileSync(result)],before);
    assert.deepEqual(f.changes,[{id:'parent',deleted:true},{id:'parent',deleted:false}]);
  } finally {f.close();}
});

test('foreign accounts, malformed ids and direct private-lane deletion fail without changing visibility',async()=>{
  const f=fixture();try{
    for(const id of ['foreign','lane']) await assert.rejects(f.trash.mutate('delete',id),e=>e.status===404);
    for(const id of ['../../outside','',null]) await assert.rejects(f.trash.mutate('delete',id),e=>e.status===400);
    await assert.rejects(f.trash.mutate('purge','parent'),e=>e.status===400);
    await f.trash.mutate('delete','parent');assert.throws(()=>createSessionTrash(f.path,'account-b',f.host),/scope_mismatch/);
  }finally{f.close();}
});

test('running or queued private execution refuses deletion and rechecks after asynchronous description',async()=>{
  const f=fixture();try{
    f.busy.add('lane');await assert.rejects(f.trash.mutate('delete','parent'),e=>e.code==='session_busy'&&e.status===409);
    assert.equal(f.trash.list().sessions.length,0);f.busy.clear();
    f.host.describe=async()=>{f.busy.add('parent');return{title:'A'};};
    await assert.rejects(f.trash.mutate('delete','parent'),e=>e.code==='session_busy');assert.equal(f.trash.isDeleted('parent'),false);
  }finally{f.close();}
});

test('public list/search/open/fork/model/queue/upload/file APIs deny tombstoned identities',async()=>{
  const f=fixture();try{
    const calls=[], controller={};
    const methods=['inspect','resolveAgent','create','selectModel','rename','fork','prompt','attachment','updateQueue','cancel','page'];
    for(const key of methods)controller[key]=(...args)=>{calls.push(key);return args;};
    for(const key of ['list','search'])controller[key]=async()=>({items:['parent','lane','branch'].map(sessionId=>({sessionId})),nextCursor:'keep'});
    protectDeletedSessions(controller,f.trash);
    const files=Object.fromEntries(['read','readBytes','readAll','readRelated','stat','list'].map(key=>[key,()=>calls.push(key)]));
    const uploads={upload:()=>calls.push('upload'),uploadStream:()=>calls.push('uploadStream')};
    protectDeletedSessionFiles(files,uploads,f.trash);await f.trash.mutate('delete','parent');
    for(const key of methods)assert.throws(()=>controller[key](['inspect','resolveAgent'].includes(key)?'parent':{sessionId:'parent'}),ApiSessionNotFound,key);
    assert.throws(()=>controller.page({address:{kind:'session',sessionId:'parent'},throughSeq:1}),ApiSessionNotFound);
    assert.throws(()=>controller.page({address:{kind:'subagent',parentSessionId:'parent',childSessionId:'ordinary-child',mode:'one-shot'},throughSeq:1}),ApiSessionNotFound);
    assert.deepEqual((await controller.list({})).items,[{sessionId:'branch'}]);assert.equal((await controller.search({})).nextCursor,'keep');
    for(const key of Object.keys(files))assert.throws(()=>files[key]({sessionId:'lane'}),ApiSessionNotFound,key);
    assert.throws(()=>uploads.upload({session:{id:'parent'}}),ApiSessionNotFound);assert.throws(()=>uploads.uploadStream({sessionId:'parent'}),ApiSessionNotFound);
    assert.deepEqual(calls,[]);await f.trash.mutate('restore','parent');controller.page({sessionId:'parent'});assert.deepEqual(calls,['page']);
  }finally{f.close();}
});

test('an already-open native follow pauses on deletion and resumes the same binding without a duplicate snapshot',async()=>{
  const f=fixture();try{
    let following=0,closed=false;
    const controller={async *follow(request,signal){following++;try{yield{type:'snapshot',cursor:0};yield{type:'event',event:{seq:1}};
      await new Promise(resolve=>signal.addEventListener('abort',resolve,{once:true}));}finally{closed=true;}},
      async *control(){yield{type:'baseline',value:{queues:{parent:[],branch:[]},jobs:{lane:[],branch:[]},projections:{parent:{},branch:{}}}};
        yield{type:'queue',sessionId:'parent',items:[]};yield{type:'queue',sessionId:'branch',items:[]};}};
    protectDeletedSessions(controller,f.trash);const lifetime=new AbortController();
    const stream=controller.follow({address:{kind:'session',sessionId:'parent'},assistantStream:true},lifetime.signal)[Symbol.asyncIterator]();
    assert.equal((await stream.next()).value.type,'snapshot');assert.equal(following,1);
    await f.trash.mutate('delete','parent');let settled=false;const next=stream.next().then(value=>{settled=true;return value;});
    await new Promise(resolve=>setImmediate(resolve));assert.equal(settled,false,'deleted scope must not leak an event');
    await assert.rejects(controller.follow({address:{kind:'session',sessionId:'parent'}},lifetime.signal).next(),ApiSessionNotFound);
    const frames=[];for await(const frame of controller.control())frames.push(frame);
    assert.deepEqual(Object.keys(frames[0].value.queues),['branch']);assert.deepEqual(Object.keys(frames[0].value.jobs),['branch']);
    assert.deepEqual(Object.keys(frames[0].value.projections),['branch']);assert.equal(frames.length,2);assert.equal(frames[1].sessionId,'branch');
    await f.trash.mutate('restore','parent');assert.deepEqual((await next).value,{type:'event',event:{seq:1}});assert.equal(following,1);
    const end=stream.next();await new Promise(resolve=>setImmediate(resolve));lifetime.abort();assert.equal((await end).done,true);assert.equal(closed,true);
    const pausedLifetime=new AbortController();closed=false;
    const paused=controller.follow({address:{kind:'session',sessionId:'parent'}},pausedLifetime.signal)[Symbol.asyncIterator]();await paused.next();
    await f.trash.mutate('delete','parent');const pending=paused.next();await new Promise(resolve=>setImmediate(resolve));pausedLifetime.abort();
    assert.equal((await pending).done,true);assert.equal(closed,true,'disconnect also cleans up an inner follow paused by a tombstone');
  }finally{f.close();}
});

test('trash endpoint requires authentication, JSON and valid action; deleting and restoring are model-free',async()=>{
  const f=fixture();try{
    let route;registerSessionTrashRoute({effect:fn=>fn(),connection:{requestRejection:r=>r.authorized?undefined:401,fetch:{register:r=>{route=r;}}}},f.trash,fn=>fn());
    const request=(body,authorized=true,headers={'Content-Type':'application/json'})=>{const req=new Request('http://localhost/api/harless/session-trash',body===undefined?{}:{method:'POST',headers,body});req.authorized=authorized;return req;};
    assert.equal((await route.fetch(request(undefined,false))).status,401);
    assert.equal((await route.fetch(request('{}',true,{}))).status,400);assert.equal((await route.fetch(request('{'))).status,400);
    assert.equal((await route.fetch(request('x'.repeat(4097)))).status,413);
    let response=await route.fetch(request(JSON.stringify({action:'delete',session_id:'parent'})));assert.equal(response.status,200);
    assert.equal((await response.json()).deleted,true);response=await route.fetch(request());assert.equal((await response.json()).sessions.length,1);
    response=await route.fetch(request(JSON.stringify({action:'restore',session_id:'parent'})));assert.equal((await response.json()).deleted,false);
  }finally{f.close();}
});

test('native search paginates past 20 deleted/private matches, preserves visible limit and hasMore, and restores immediately',async()=>{
  // Exercise the actual pinned native search implementation, including its
  // 20-hit truncation. Only the public SessionQuery provider is a fixture.
  const require=createRequire(import.meta.url);
  const nativePackage=require.resolve('@deepseek-ai/dsh-api-session-controller/package.json');
  const {ApiSessionList}=await import(pathToFileURL(join(nativePackage,'..','lib','types','list.js')).href);
  const directory=mkdtempSync(join(tmpdir(),'geneloop-trash-search-'));
  try{
    const records=Array.from({length:42},(_,index)=>({header:{id:'session-'+index,cwd:'/synthetic'}}));
    const calls=[];
    const provider={async listSessions(){return records;},async searchSessions(request,{signal}){
      signal.throwIfAborted();calls.push(request);const offset=Number(request.cursor??0);
      // A foreign hit deliberately occupies a provider slot, but is absent
      // from listSessions and must still fail native authorization.
      const hits=[{header:{id:'foreign',cwd:'/synthetic'}},...records].map(row=>({...row,bestMatch:{sessionId:row.header.id,type:'user/message',surface:'current',snippet:'needle '+row.header.id}}));
      const end=offset+request.limit;
      return {items:hits.slice(offset,end),...(end<hits.length?{nextCursor:String(end)}:{})};
    }};
    const trash=createSessionTrash(join(directory,'trash.json'),'account-a',{
      owns:async id=>{assert.ok(records.some(row=>row.header.id===id));},isPrivate:()=>false,privateChildren:()=>[],busy:()=>false,describe:async id=>({title:id}),
    });
    for(let index=0;index<20;index++)await trash.mutate('delete','session-'+index);
    const native=new ApiSessionList({sessionProjections:{register(){}},inject(){},get:key=>key==='sessionQuery'?provider:undefined});
    const before=await native.search('needle',new AbortController().signal);assert.equal(before.items[0].sessionId,'session-0');assert.equal(before.hasMore,true);
    const dispose=protectDeletedSessionQuery(provider,trash,id=>id==='session-20');
    const result=await native.search('needle',new AbortController().signal);
    assert.equal(result.items.length,20);assert.equal(result.items[0].sessionId,'session-21');assert.equal(result.items.at(-1).sessionId,'session-40');assert.equal(result.hasMore,true);
    assert.ok(result.items.every(row=>row.sessionId!=='foreign'));assert.ok(calls.some(row=>row.cursor!==undefined));
    records.splice(22); // exactly one visible matching conversation remains
    const single=await native.search('needle',new AbortController().signal);
    assert.deepEqual(single,{items:[{sessionId:'session-21',snippet:'needle session-21'}],hasMore:false});
    await trash.mutate('restore','session-0');
    assert.deepEqual((await native.search('needle',new AbortController().signal)).items.map(row=>row.sessionId),['session-0','session-21']);
    const cancelled=new AbortController();cancelled.abort();await assert.rejects(native.search('needle',cancelled.signal),error=>error.name==='AbortError');
    dispose();assert.equal((await provider.listSessions()).length,22);
  }finally{rmSync(directory,{recursive:true,force:true});}
});

test('reversible deletion notifies other clients through authenticated SSE and cleans up disconnected streams',async()=>{
  const f=fixture();try{
    let route;registerSessionTrashRoute({effect:fn=>fn(),connection:{requestRejection:r=>r.authorized?undefined:401,fetch:{register:r=>{route=r;}}}},f.trash,fn=>fn());
    const lifetime=new AbortController(), request=new Request('http://localhost/api/harless/session-trash?stream=1',{signal:lifetime.signal});
    assert.equal((await route.fetch(request)).status,401);request.authorized=true;
    const response=await route.fetch(request);assert.match(response.headers.get('content-type'),/event-stream/);
    const reader=response.body.getReader(), read=async()=>new TextDecoder().decode((await reader.read()).value);
    assert.equal(await read(),'data: {"changed":true}\n\n');
    await f.trash.mutate('delete','parent');assert.equal(await read(),'data: {"changed":true}\n\n');
    await f.trash.mutate('restore','parent');assert.equal(await read(),'data: {"changed":true}\n\n');
    lifetime.abort();assert.equal((await reader.read()).done,true);
    await f.trash.mutate('delete','parent'); // no enqueue into the disconnected stream
  }finally{f.close();}
});
