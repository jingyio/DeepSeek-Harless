import test from 'node:test';
import assert from 'node:assert/strict';
test('provider length recovery keeps native tool continuation, stops on final/error/cancel', {skip:!process.features?.typescript}, async()=>{
 const {createPptMasterRecovery}=await import('../src/adapters/ppt_master_recovery.ts');
 const r=createPptMasterRecovery();r.begin();r.observe({type:'finish',reason:{kind:'tool-calls'}});assert.equal(r.stop(false),null);
 r.begin();r.observe({type:'finish',reason:{kind:'max-tokens'}});assert.equal(r.stop(false).truncated,true);assert.equal(r.stop(false),null);
 r.begin();r.observe({type:'finish',reason:{kind:'tool-calls'}});assert.equal(r.stop(false).continuation,2);
 for(const kind of ['stop','error','aborted']){r.begin();r.observe({type:'finish',reason:{kind}});assert.equal(r.stop(false),null);}
 r.begin();r.observe({type:'finish',reason:{kind:'max-tokens'}});assert.equal(r.stop(true),null);
});
