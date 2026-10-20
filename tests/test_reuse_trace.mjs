import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,rmSync,realpathSync,symlinkSync,readdirSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {createReuseTrace} from '../src/adapters/reuse_trace.ts';
test('native boundaries preserve before/after bytes without following links or rewriting sources',t=>{
 const root=realpathSync(mkdtempSync(join(tmpdir(),'reuse-boundary-')));t.after(()=>rmSync(root,{recursive:true,force:true}));
 const work=join(root,'work'),output=join(root,'task');mkdirSync(join(work,'code'),{recursive:true});mkdirSync(join(work,'inputs'));mkdirSync(output);
 const path=join(work,'code/data.json');writeFileSync(path,'[1]');writeFileSync(join(root,'private.json'),'secret');symlinkSync(join(root,'private.json'),join(work,'code/link.json'));
 const tracker=createReuseTrace(work,output),execution={callId:'call',name:'bash',arguments:{command:'observed command'}};
 tracker.before(execution);writeFileSync(path,'[2]');tracker.after(execution,{isError:false,content:[]});
 const record=JSON.parse(readFileSync(join(output,'reuse-boundaries.jsonl'),'utf8'));
 assert.notEqual(record.before.files['code/data.json'].sha256,record.after.files['code/data.json'].sha256);
 assert.deepEqual(Object.keys(record.before.files),['code/data.json']);assert.equal(record.before.scope,'bounded_text_files_not_all_files');
 assert.equal(readFileSync(join(output,'reuse-evidence',record.before.files['code/data.json'].sha256),'utf8'),'[1]');
 assert.equal(readFileSync(path,'utf8'),'[2]');assert.equal(readdirSync(join(output,'reuse-evidence')).length,2);
});
