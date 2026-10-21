/** Integration regression: auto publication can contain an empty positive lib. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {optionalScriptRuntime} from '../src/adapters/script_motif_web.ts';
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
