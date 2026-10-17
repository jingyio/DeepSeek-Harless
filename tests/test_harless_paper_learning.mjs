/** Real offline compiler with synthetic diagnostic events; no provider calls. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {existsSync,mkdirSync,readFileSync,rmSync,writeFileSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {randomUUID} from 'node:crypto';
import {createPaperLearning} from '../src/adapters/harless_paper_learning.ts';
const python=process.env.SSS_PURE_CODE_PYTHON??process.env.SSS_PYTHON;
const root=resolve(import.meta.dirname,'..');
const enabled=Boolean(python&&existsSync(python));
const scope='a'.repeat(64),user='diagnostic-user';
function add(output,index){
 const code=`import json,hashlib\nfrom pathlib import Path\nfrom tests.test_web_paper_learning import task,save\nout=Path(${JSON.stringify(output)})\nstore=out/'learning'/hashlib.sha256(('diagnostic-user'+'\\0'+'a'*64).encode()).hexdigest()\nstore.mkdir(parents=True,exist_ok=True)\np=store/'request.json'\nif not p.exists():save(p,{'schema_version':1,'output':str(out),'user':'diagnostic-user','scope':'a'*64,'task_ids':[]})\ntask((out,store,p),${index})`;
 execFileSync(python,['-c',code],{cwd:root,env:{...process.env,PYTHONUTF8:'1'},stdio:'pipe'});
}

test('a removed output directory cannot turn a background worker failure into an uncaught exception',async()=>{
 const output=join(root,'.local/node-paper-learning',randomUUID());mkdirSync(output,{recursive:true});
 // Node deliberately rejects the Python worker; only the close/error lifecycle is under test.
 const manager=createPaperLearning({output,user,scope,python:process.execPath,taskIds:()=>[]});
 manager.schedule();rmSync(output,{recursive:true,force:true});
 try{await manager.idle();}finally{rmSync(output,{recursive:true,force:true});}
});

test('automatic offline learning uses existing tasks, advances only new tasks and isolates users/scopes',{skip:!enabled},async()=>{
 const output=join(root,'.local/node-paper-learning',randomUUID());mkdirSync(output,{recursive:true});
 try{
  for(let index=1;index<=3;index++)add(output,index);
  const ids=[1,2,3].map(i=>i.toString(16).padStart(32,'0'));
  const config={output,user,scope,python,taskIds:()=>ids};
  const manager=createPaperLearning(config),base={id:'paper-proofreading',config_sha256:'before',allowed_tools:['original'],instructions:'unchanged'};
  assert.equal(manager.resolve(base),base);
  manager.schedule();manager.schedule();await manager.idle();
  const one=manager.resolve(base);assert.equal(one.learning_version,'round-0001');assert.equal(one.runtime_kind,'paper_document_read_v1');
  assert.deepEqual(one.allowed_tools,['original']);assert.equal(one.instructions,'unchanged');assert.equal(base.learning_version,undefined);
  assert.equal(createPaperLearning({...config,user:'another-user'}).resolve(base),base);
  assert.equal(createPaperLearning({...config,scope:'b'.repeat(64)}).resolve(base),base);
  const foreign=createPaperLearning({...config,user:'another-user'});foreign.schedule();await foreign.idle();assert.equal(foreign.resolve(base),base);
  add(output,4);ids.push('4'.padStart(32,'0'));manager.schedule();await manager.idle();
  const two=manager.resolve(base);assert.equal(two.learning_version,'round-0002');assert.equal(one.learning_version,'round-0001');
  assert.notEqual(one.certification_path,two.certification_path);
  const restarted=createPaperLearning(config);assert.equal(restarted.resolve(base).learning_version,'round-0002');
  restarted.schedule();await restarted.idle();assert.equal(restarted.resolve(base).learning_version,'round-0002');
  const original=readFileSync(two.runtime_library);writeFileSync(two.runtime_library,'{}');assert.equal(manager.resolve(base),base);
  writeFileSync(two.runtime_library,original);assert.equal(manager.resolve(base).learning_version,'round-0002');
 }finally{rmSync(output,{recursive:true,force:true});}
});
