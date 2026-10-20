import test from 'node:test';
import assert from 'node:assert/strict';
import {createInteractionBridge} from '../src/adapters/geneloop_interactions.ts';
test('native questions preserve pending human choice and exact public parent/lane ownership',async()=>{
 const agent={},owner={session:'parent',task:'active',lane:'motif'};let live=true;
 const bridge=createInteractionBridge(caller=>caller===agent&&live?owner:undefined),abort=new AbortController();
 const request={agent,signal:abort.signal,questions:[{id:'q',question:'Which?',options:[{label:'A'},{label:'B'}]}]};
 const result=bridge.ask(request,()=>{throw Error('not native fallback');}),row=bridge.list('parent')[0];
 assert.equal(row.lane,'motif');assert.deepEqual(bridge.list('foreign'),[]);
 assert.throws(()=>bridge.answer('foreign',row.id,[{id:'q',selected:['A']}]),e=>e.status===404);
 assert.throws(()=>bridge.answer('parent',row.id,[{id:'q',selected:['invented']}]),e=>e.status===400);
 assert.throws(()=>bridge.answer('parent',row.id,[{id:'q',selected:['A','B']}]),e=>e.status===400);
 bridge.answer('parent',row.id,[{id:'q',selected:['B'],custom:'中文补充'}]);
 assert.deepEqual(await result,{answers:[{id:'q',selected:['B'],custom:'中文补充'}]});
 assert.equal(bridge.list('parent').length,0);assert.throws(()=>bridge.answer('parent',row.id,[]));
});
test('cancel, task replacement and foreign callers cannot resolve an old human question',async()=>{
 const agent={};let owner={session:'p',task:'a',lane:'baseline'};
 const bridge=createInteractionBridge(caller=>caller===agent?owner:undefined),abort=new AbortController();
 const promise=bridge.ask({agent,signal:abort.signal,questions:[{id:'q',question:'Input'}]},()=>{});
 const id=bridge.list('p')[0].id;owner={...owner,task:'new'};
 assert.throws(()=>bridge.answer('p',id,[{id:'q',selected:[],custom:'yes'}]),e=>e.status===409);
 abort.abort();await assert.rejects(promise,{name:'AbortError'});assert.deepEqual(bridge.list('p'),[]);
 assert.equal(await bridge.ask({agent:{},questions:[]},async()=>42),42);
});
