/** Integration regression: auto publication can contain an empty positive lib. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {optionalScriptRuntime,continueScriptRequest} from '../src/adapters/script_motif_web.ts';
import {markAgentLoopRequest} from '@deepseek-ai/dsh-llm';
async function collect(stream){const result=[];for await(const item of stream)result.push(item);return result;}
test('negative-only and empty positive publication need no embedding endpoint',async()=>{
 for(const library of [null,{programs:[]}]){
  const audit=[],runtime=optionalScriptRuntime({mode:'shadow'},library,{},r=>audit.push(r));
  const negative={prompt:'current verified failure'};runtime.negative=negative;
  let calls=0;assert.equal(await runtime.intercept('session',{},()=>++calls),1);
  assert.equal(runtime.negative,negative);assert.deepEqual(audit,[]);
 }
});
test('positive initialization failure falls back locally and preserves native continuation',async()=>{
 const audit=[],runtime=optionalScriptRuntime({mode:'shadow'},{programs:[{}]},{},r=>audit.push(r));
 let calls=0;assert.equal(await runtime.intercept('session',{},()=>++calls),1);
 assert.equal(audit[0].kind,'script_component_fallback');assert.equal(audit[0].component,'positive_matcher');
});
test('a configured matcher without execution frontier remains available to the existing cache catalog',()=>{
 const runtime=optionalScriptRuntime({mode:'cache',similarity:async()=>[]},{programs:[{}]},{},()=>{});
 assert.equal(runtime.positiveUnavailable,undefined);assert.equal(runtime.frontier,null);runtime.dispose();
});
test('native compaction and other auxiliary requests bypass matching without mutating evidence',async()=>{
 for(const request of [{sessionId:'same',purpose:'compaction'},{sessionId:'same',purpose:'title'}]){
  let sent=0;const next=async function*(){sent++;yield 'native';};
  const stream=continueScriptRequest(request,next,()=>{throw Error('auxiliary request touched Motif state');});
  assert.deepEqual(await collect(stream),['native']);assert.equal(sent,1);
 }
});
test('the exact DSH-marked agent request retains evidence updates and checked native continuation',async()=>{
 const request={sessionId:'owner'};markAgentLoopRequest(request);
 const order=[],runtime={negative:{update:r=>{assert.equal(r,request);order.push('negative');},beforeRequest:()=>order.push('warning')},
  reuse:{update:()=>order.push('reuse'),ready:()=>null},intercept:async(_id,r,next)=>{assert.equal(r,request);order.push('match');return next();}};
 const next=async function*(){order.push('native');yield 'result';};
 const stream=continueScriptRequest(request,next,id=>{assert.equal(id,'owner');return runtime;});
 assert.deepEqual(await collect(stream),['result']);assert.deepEqual(order,['negative','reuse','match','warning','native']);
});
