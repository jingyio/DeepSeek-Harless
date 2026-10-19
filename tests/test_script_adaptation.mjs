import test from 'node:test';import assert from 'node:assert/strict';
import {mkdtempSync,rmSync,writeFileSync,existsSync,mkdirSync} from 'node:fs';import {join} from 'node:path';
import {hashRepresentatives,eligibleBackupSources,validateScript,runtimeFiles,createScriptController} from '../src/adapters/dsh_learned_script_v2.ts';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';
test('version 2 derives actual full-path min/max independently of returned group order',()=>{
 const groups=[{files:[{path:'b/same.txt'},{path:'a/same.txt'}]},{files:[{path:'x/file'}]}];
 assert.deepEqual(hashRepresentatives(groups,'min').map(r=>r.path),['a/same.txt','x/file']);
 assert.deepEqual(hashRepresentatives(groups,'max').map(r=>r.path),['b/same.txt','x/file']);
});
test('metadata filter skips only zero-byte text and preserves empty markdown',()=>{
 const rows=[{path:'zero.TXT',extension:'.txt',bytes:0},{path:'empty.md',extension:'.md',bytes:0},{path:'space.txt',extension:'.txt',bytes:2}];
 assert.deepEqual(eligibleBackupSources(rows).map(r=>r.path),['empty.md','space.txt']);
});
function program(){
 const spec={objective:'copy',report_contract:{kind:'task_result'},initial_snapshot:{}};
 const s={format:'sss-learned-copy-script-v2',schema_version:2,execution_version_sha256:'a'.repeat(64),guard_cases:[{objective_sha256:digest('copy'),context_text_sha256:null,destination_prefixes:['backup-set/']}],
  steps:[{op:'copy_map',source:'nonempty_txt_sources',strip_prefix:'source/',destination_slot:0}],training:[1,2].map(n=>({role:'explore',events_sha256:'b'.repeat(64),task_fingerprint:digest(n)})),
  runtime_source:Object.fromEntries(runtimeFiles.map(n=>[n,'c'.repeat(64)])),tool_schema_sha256:Object.fromEntries(['read_task','list_files','pin_file','read_file','hash_files','preview_actions','execute_plan','submit_report'].map(n=>['mcp__file_management__'+n,digest({})]))};
 s.script_digest=digest(s);return {s,spec};
}
test('missing schema defers without throwing; invalid instructions and validation-source training rejected',()=>{
 const {s,spec}=program();validateScript(s);const c=createScriptController(s,{spec,input_sha256:digest(spec),prompt_sha256:'d'.repeat(64)},()=>{});
 assert.equal(c.propose([{name:'mcp__file_management__read_task'}]),null);assert.equal(c.halted,true);
 for(const change of [v=>v.steps[0].destination_slot=9,v=>v.training[0].role='certify',v=>delete v.runtime_source[runtimeFiles[0]]]){
  const v=structuredClone(s);delete v.script_digest;change(v);v.script_digest=digest(v);assert.throws(()=>validateScript(v));
 }
});
