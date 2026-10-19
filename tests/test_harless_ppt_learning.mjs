/** Synthetic event/lifecycle diagnostics; no provider or scientific-quality claims. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {existsSync,mkdirSync,readFileSync,rmSync,writeFileSync} from 'node:fs';
import {createHash,randomUUID} from 'node:crypto';
import {resolve,join} from 'node:path';
import {createPptLearning} from '../src/adapters/harless_ppt_learning.ts';
const python=process.env.SSS_PURE_CODE_PYTHON??process.env.SSS_PYTHON;
const root=resolve(import.meta.dirname,'..'),scope='a'.repeat(64),user='diagnostic-user';
const enabled=Boolean(python&&existsSync(python));
const read=path=>JSON.parse(readFileSync(path,'utf8'));
const storeFor=output=>join(output,'learning','ppt-'+createHash('sha256').update(user+'\0'+scope).digest('hex'));
function add(output,index,paired=false){
 const code=`from pathlib import Path\nfrom tests.test_web_ppt_learning import task,pair,save\nout=Path(${JSON.stringify(output)})\nstore=Path(${JSON.stringify(storeFor(output))})\nstore.mkdir(parents=True,exist_ok=True)\np=store/'request.json'\nif not p.exists():save(p,{'schema_version':1,'output':str(out),'user':'diagnostic-user','scope':'a'*64,'task_ids':[],'automatic_structural_learning':True})\nif not (out/'comparisons.json').exists():save(out/'comparisons.json',{'version':1,'principal':'diagnostic-user','turns':[]})\nowned=(out,store,p)\nn=${index}\nbase=task(owned,n*10,source=n,cost=.003)\nopt=task(owned,n*10+1,source=n,mode='execute',version='round-0001',cost=.001) if ${paired?'True':'False'} else None\npair(owned,n,base,opt,review=False)`;
 execFileSync(python,['-c',code],{cwd:root,env:{...process.env,PYTHONUTF8:'1'},stdio:'pipe'});
}

test('PPT learning worker failure cannot break chat or escape an already removed output',async()=>{
 const output=join(root,'.local/node-ppt-learning',randomUUID());mkdirSync(output,{recursive:true});
 const manager=createPptLearning({output,user,scope,python:process.execPath,taskIds:()=>[]});
 manager.schedule();rmSync(output,{recursive:true,force:true});
 try{await manager.idle();}finally{rmSync(output,{recursive:true,force:true});}
});

test('PPT lifecycle: automatic certification, future-only probation, promotion, restart, veto and integrity guards',{skip:!enabled},async()=>{
 const output=join(root,'.local/node-ppt-learning',randomUUID());mkdirSync(output,{recursive:true});
 try{
  const ids=[],config={output,user,scope,python,taskIds:()=>ids};
  for(let n=1;n<=3;n++){add(output,n);ids.push((n*10).toString(16).padStart(32,'0'));}
  const manager=createPptLearning(config),base={id:'ppt',ppt_execution_strategy:'ppt_master',config_sha256:'original',instructions:'unchanged',allowed_tools:['unchanged']};
  assert.equal(manager.resolve(base),base);
  manager.schedule();manager.schedule();await manager.idle();
  const one=manager.resolve(base);assert.equal(one.learning_version,'round-0001');assert.equal(one.learning_phase,'probation');
  assert.equal(one.runtime_kind,'ppt_master_v2');assert.equal(one.instructions,'unchanged');assert.deepEqual(one.allowed_tools,['unchanged']);
  assert.equal(base.learning_version,undefined);
  assert.equal(createPptLearning({...config,user:'other'}).resolve(base),base);
  assert.equal(createPptLearning({...config,scope:'b'.repeat(64)}).resolve(base),base);
  assert.equal(manager.resolve({...base,id:'paper-proofreading'}).learning_version,undefined);
  for(let n=4;n<=5;n++){add(output,n,true);ids.push(...[n*10,n*10+1].map(i=>i.toString(16).padStart(32,'0')));manager.schedule();await manager.idle();}
  const active=manager.resolve(base);assert.equal(active.learning_phase,'active');
  const status=read(join(storeFor(output),'status.json'));assert.equal(status.quality_cost_promoted,false);assert.equal(status.mechanical_cost_promoted,true);
  assert.equal(createPptLearning(config).resolve(base).learning_phase,'active');
  for(const path of [active.runtime_library,join(storeFor(output),'round-0001/promotion.json'),join(storeFor(output),'round-0001/evaluation.json')]){
   const bytes=readFileSync(path);writeFileSync(path,'{}');assert.equal(manager.resolve(base),base);writeFileSync(path,bytes);
  }
  // Simulate an older worker clearing the temporary suspension after a veto.
  // The persistent generation still prevents stale admission.
  const feedback=join(storeFor(output),'feedback-version.json');
  writeFileSync(feedback,JSON.stringify({version:'concurrent-veto'}));
  assert.equal(manager.resolve(base),base);rmSync(feedback);
  const comparisons=read(join(output,'comparisons.json')),snapshot=comparisons.turns.at(-1);
  assert.throws(()=>manager.review(snapshot,{lane:'motif',output_sha256:'wrong'}),/version_changed/);
  snapshot.lanes.motif.feedback='down';writeFileSync(join(output,'comparisons.json'),JSON.stringify(comparisons));
  manager.negativeFeedback(snapshot);assert.equal(manager.resolve(base),base);await manager.idle();
  assert.equal(read(join(storeFor(output),'selected.json')).phase,'disabled');assert.equal(manager.resolve(base),base);
 }finally{rmSync(output,{recursive:true,force:true});}
});
