/** Protocol diagnostics only; real learning acceptance uses separate API tasks. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,rmSync,realpathSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';
import {resolveScriptLearningSettings} from '../src/adapters/script_learning_store.ts';

function fixture(t){
 const store=realpathSync(mkdtempSync(join(tmpdir(),'script-learning-')));
 t.after(()=>rmSync(store,{recursive:true,force:true}));
 function publish(round,value){
  mkdirSync(join(store,round));const body={version:1,programs:[value]};
  writeFileSync(join(store,round,'library.json'),JSON.stringify({...body,digest:digest(body)}));
  const pointer={user:'owner',file:round+'/library.json',digest:digest(body),triggered_by_task:value};
  writeFileSync(join(store,'latest.json'),JSON.stringify(pointer));return pointer;
 }
 return {store,publish};
}
test('cold start falls back; later tasks load a new immutable generation',t=>{
 const {store,publish}=fixture(t),config={learningStore:store,mode:'execute'};
 assert.equal(resolveScriptLearningSettings(config,'owner').snapshot.status,'cold_start');
 const a=publish('round-aaa','task-a'),running=resolveScriptLearningSettings(config,'owner');
 publish('round-bbb','task-b');const next=resolveScriptLearningSettings(config,'owner');
 assert.equal(running.snapshot.script.digest,a.digest);
 assert.equal(running.snapshot.triggered_by_task,'task-a');
 assert.notEqual(running.settings.library,next.settings.library);
 assert.equal(next.snapshot.triggered_by_task,'task-b');
 assert.equal(config.library,undefined);
});
test('foreign owner, pointer digest changes and path escapes fail closed',t=>{
 const {store,publish}=fixture(t);const pointer=publish('round-aaa','task-a'),config={learningStore:store};
 assert.throws(()=>resolveScriptLearningSettings(config,'other'),/foreign/);
 writeFileSync(join(store,'latest.json'),JSON.stringify({...pointer,digest:'0'.repeat(64)}));
 assert.throws(()=>resolveScriptLearningSettings(config,'owner'),/digest_mismatch/);
 writeFileSync(join(store,'latest.json'),JSON.stringify({...pointer,file:'../library.json'}));
 assert.throws(()=>resolveScriptLearningSettings(config,'owner'),/invalid_learning_pointer/);
});
test('negative-only generation is frozen and can never acquire automatic blocking authority',t=>{
 const {store}=fixture(t);mkdirSync(join(store,'round-aaa'));
 const body={rules:[{retry_policy:'prompt_only'}]},value={...body,digest:digest(body)};
 writeFileSync(join(store,'round-aaa/negative-library.json'),JSON.stringify(value));
 const pointer={user:'owner',negative_file:'round-aaa/negative-library.json',negative_digest:value.digest};
 writeFileSync(join(store,'latest.json'),JSON.stringify(pointer));
 const selected=resolveScriptLearningSettings({learningStore:store,negativeMode:'enforce'},'owner');
 assert.equal(selected.settings.negativeMode,'prompt');
 assert.equal(selected.snapshot.script,null);assert.equal(selected.snapshot.negative.digest,value.digest);
 const strong={rules:[{retry_policy:'warn_then_current_constraint'}]};
 writeFileSync(join(store,'round-aaa/negative-library.json'),JSON.stringify({...strong,digest:digest(strong)}));
 writeFileSync(join(store,'latest.json'),JSON.stringify({...pointer,negative_digest:digest(strong)}));
 assert.throws(()=>resolveScriptLearningSettings({learningStore:store},'owner'),/authority_denied/);
});
test('mixed generations and empty publication cannot silently fall through',t=>{
 const {store,publish}=fixture(t),pointer=publish('round-aaa','a');
 mkdirSync(join(store,'round-bbb'));const body={rules:[]};
 writeFileSync(join(store,'round-bbb/negative-library.json'),JSON.stringify({...body,digest:digest(body)}));
 writeFileSync(join(store,'latest.json'),JSON.stringify({...pointer,negative_file:'round-bbb/negative-library.json',negative_digest:digest(body)}));
 assert.throws(()=>resolveScriptLearningSettings({learningStore:store},'owner'),/mixed_learning_generations/);
 writeFileSync(join(store,'latest.json'),JSON.stringify({user:'owner'}));
 assert.throws(()=>resolveScriptLearningSettings({learningStore:store},'owner'),/empty_learning_pointer/);
});
