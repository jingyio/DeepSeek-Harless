/** State/permission diagnostics; effect evidence comes from real model trials. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {createScriptExecutionFrontier,learnedScriptFragments} from '../src/adapters/script_execution_frontier.ts';
const first={id:'a',inputs:[{suffix:'.txt',format:'text'}],interface:{stdout_labels:['count']}};
const second={...first,id:'b',predecessor:{program_id:'a'},interface:{stdout_labels:['duplicates']}};
function fixture(){
 let valid=true;const events=[];
 const frontier=createScriptExecutionFrontier({library:{programs:[first,second],digest:'test'},goal:'check current document',
  bind:()=>[{path:'/work/current.txt',sha256:'version'}],verify:()=>valid,audit:r=>events.push(r)});
 const prompt=frontier.prompt(),request=JSON.parse(prompt.split('\n').at(-1));
 const command=(status='selected',extra={})=>'geneloop-resolve '+JSON.stringify({request_id:request.request_id,status,...(status==='selected'?{candidate_id:request.candidates[0].id}:{}),...extra});
 return {frontier,events,command,change:()=>{valid=false;}};
}
function acknowledge(f,command){const body=f.frontier.prepare(command);f.frontier.observe({name:'bash',arguments:{command}},{content:[{type:'text',text:JSON.stringify(body.control_receipt)}]});}
test('current semantic choice activates witnessed fragment, then resumes without per-node decisions',()=>{
 const f=fixture();assert.equal(f.frontier.ready(),null);
 acknowledge(f,f.command());assert.equal(f.frontier.ready().program.id,'a');
 f.frontier.finish('a',true);assert.equal(f.frontier.ready().program.id,'b');
 f.frontier.finish('b',true);assert.equal(f.frontier.ready(),null);
 assert.equal(f.events.filter(r=>r.kind==='script_frontier_gap').length,1);
 assert.ok(f.frontier.prompt().includes('已完成'));assert.equal(f.events.filter(r=>r.kind==='script_frontier_completed').length,1);
 assert.throws(()=>f.frontier.prepare(f.command()),/no_current/);
});
for(const status of ['unknown','ambiguous','unneeded'])test(status+' does not authorize any execution',()=>{
 const f=fixture();acknowledge(f,f.command(status));assert.equal(f.frontier.ready(),null);assert.equal(f.frontier.prompt(),'');
});
test('historical frequency, scalar network calls and branching do not create forced routes',()=>{
 const standalone=learnedScriptFragments({programs:[first,{...second,argv_contract:{}}]});
 assert.deepEqual(standalone.map(f=>f.nodes.map(p=>p.id)),[['a']]);
 assert.equal(learnedScriptFragments({programs:[first,second,{...second,id:'c'}]}).length,0);
 assert.equal(learnedScriptFragments({programs:[{...first,predecessor:{program_id:'b'}},second]}).length,0);
});
test('unexpected fields, invented choices and script payloads are rejected',()=>{
 let f=fixture();
 assert.throws(()=>f.frontier.prepare(f.command('selected',{candidate_id:'invented'})),/unapproved/);
 f=fixture();
 assert.throws(()=>f.frontier.prepare(f.command('selected',{code:'print(1)'})),/invalid_semantic/);
 f=fixture();
 assert.throws(()=>f.frontier.prepare(f.command()+' | head'),/JSON/);
});
test('malformed negative resolution withdraws the invitation without authorizing or retrying',()=>{
 const f=fixture();
 assert.throws(()=>f.frontier.prepare(f.command('unneeded')+'; echo "exit=$?"'),/JSON/);
 assert.equal(f.frontier.ready(),null);assert.equal(f.frontier.prompt(),'');
 assert.throws(()=>f.frontier.prepare(f.command()),/no_current/);
 assert.ok(f.events.some(r=>r.reason==='invalid_semantic_resolution_transport'));
 assert.equal(f.events.filter(r=>r.kind==='script_frontier_gap').length,1);
});
test('input changes before acceptance and after one node prevent continued execution',()=>{
 let f=fixture();f.change();assert.throws(()=>f.frontier.prepare(f.command()),/stale/);
 f=fixture();acknowledge(f,f.command());f.frontier.finish('a',true);f.change();assert.equal(f.frontier.ready(),null);
});
test('forged or failed resolution receipt never activates a frame',()=>{
 const f=fixture(),command=f.command(),body=f.frontier.prepare(command);
 f.frontier.observe({name:'bash',arguments:{command}},{content:[{type:'text',text:JSON.stringify({...body.control_receipt,nonce:'forged'})}]});
 assert.equal(f.frontier.ready(),null);assert.ok(f.events.some(r=>r.reason==='resolution_unverified'));
});
test('failed node never runs its successor',()=>{
 const f=fixture();acknowledge(f,f.command());f.frontier.finish('a',false);assert.equal(f.frontier.ready(),null);
});
test('verified current evidence avoids redoing completed work; stale facts do not qualify',()=>{
 const f=fixture();f.frontier.recordEvidence('a',[{path:'/work/current.txt',sha256:'version'}]);
 acknowledge(f,f.command());assert.equal(f.frontier.ready().program.id,'b');
 f.frontier.finish('b',true);f.change();assert.equal(f.frontier.prompt(),'');
});
test('semantic gap is announced once and completion evidence is appended once',()=>{
 const f=fixture();assert.ok(f.frontier.takeNotice().includes('有界语义选择'));assert.equal(f.frontier.takeNotice(),'');
 acknowledge(f,f.command());f.frontier.finish('a',true);f.frontier.finish('b',true);
 assert.ok(f.frontier.takeNotice().includes('已完成'));assert.equal(f.frontier.takeNotice(),'');
});

function batchFixture(){
 const events=[];let valid=true;
 const third={...first,id:'c',interface:{stdout_labels:['encoding']}};
 const frontier=createScriptExecutionFrontier({library:{programs:[first,second,third],digest:'test'},goal:'check current document',
  bind:()=>[{path:'/work/current.txt',sha256:'v'}],verify:()=>valid,audit:r=>events.push(r)});
 const notice=frontier.takeNotice('initial_stable_prefix'),request=JSON.parse(notice.split('\n').at(-1));
 const command=(ids=request.candidates.map(c=>c.id))=>'geneloop-resolve '+JSON.stringify({request_id:request.request_id,status:'selected',candidate_ids:ids});
 return {frontier,events,command,request,change:()=>{valid=false;}};
}
test('one semantic selection authorizes several exact fragments and gives one completion notice',()=>{
 const f=batchFixture();acknowledge(f,f.command());
 for(const id of ['a','b','c']){
  assert.equal(f.frontier.ready().program.id,id);
  assert.equal(f.frontier.takeNotice(),'');
  f.frontier.finish(id,true);
 }
 assert.equal(f.frontier.ready(),null);
 const done=f.frontier.takeNotice();
 assert.ok(done.includes('旧 request_id 已消费'));
 assert.ok(!done.includes('当前有一个有界语义选择'));
 assert.equal(f.frontier.takeNotice(),'');
 assert.equal(f.events.filter(e=>e.kind==='script_frontier_resolution_verified').length,1);
 assert.equal(f.events.find(e=>e.kind==='script_frontier_resolution_verified').operators,3);
});
test('batch rejects duplicates, invented fragments and excess work before starting any node',()=>{
 for(const build of [f=>[f.request.candidates[0].id,f.request.candidates[0].id],_f=>['invented'],f=>Array(9).fill(f.request.candidates[0].id)]){
  const f=batchFixture();assert.throws(()=>f.frontier.prepare(f.command(build(f))));
  assert.equal(f.frontier.ready(),null);
 }
});
test('input changes or failure in the first fragment stop later approved fragments',()=>{
 let f=batchFixture();acknowledge(f,f.command());f.frontier.finish('a',true);f.change();
 assert.equal(f.frontier.ready(),null);
 f=batchFixture();acknowledge(f,f.command());f.frontier.finish('a',false);
 assert.equal(f.frontier.ready(),null);
 assert.equal(f.events.filter(e=>e.kind==='script_frontier_completed').length,0);
});
test('task-specific bindings and random IDs follow the stable catalogue prefix',()=>{
 function notice(path){return createScriptExecutionFrontier({library:{programs:[first,second],digest:'same'},goal:'check document',
  bind:()=>[{path,sha256:'current'}],verify:()=>true,audit:()=>{}}).takeNotice('initial_stable_prefix');}
 const a=notice('/work/a.txt'),b=notice('/work/b.txt');
 assert.equal(a.slice(0,a.indexOf('"bindings":')),b.slice(0,b.indexOf('"bindings":')));
 const request=JSON.parse(a.split('\n').at(-1));
 assert.ok(a.indexOf(request.request_id)>a.indexOf('"bindings":'));
 assert.deepEqual(Object.values(request.bindings),[['/work/a.txt']]);
});

test('compact choices retain full descriptions, share bindings and authorize only their current targets',()=>{
 const events=[],description='Read exact current records; quoted fields may be unsupported.';
 const a={...first,description},b={...first,id:'other',description:'A distinct complete description'};
 const frontier=createScriptExecutionFrontier({library:{programs:[a,b],digest:'library'},goal:'current check',compactContext:true,
  bind:()=>[{path:'/work/current.txt',sha256:'v'}],verify:()=>true,audit:r=>events.push(r)});
 const text=frontier.takeNotice(),gap=JSON.parse(text.split('\n').at(-1));
 assert.deepEqual(gap.bindings,[['/work/current.txt']]);assert.deepEqual(gap.candidates.map(c=>c.id),['c1','c2']);
 assert.ok(text.includes(description));assert.ok(text.includes('最小且足够'));assert.equal(frontier.ready(),null);
 acknowledge({frontier},'geneloop-resolve '+JSON.stringify({request_id:gap.request_id,status:'selected',candidate_ids:['c2']}));
 assert.equal(frontier.ready().program.id,b.id);frontier.finish(b.id,true);
 assert.ok(frontier.takeNotice().includes('局部取证'));
});
test('a compact alias and its full ID cannot select the same fragment twice',()=>{
 const frontier=createScriptExecutionFrontier({library:{programs:[{...first,description:'read'}]},goal:'read',compactContext:true,
  bind:()=>[{path:'/work/current.txt',sha256:'v'}],verify:()=>true,audit:()=>{}});
 const gap=JSON.parse(frontier.prompt().split('\n').at(-1));
 const id=learnedScriptFragments({programs:[first]})[0].id;
 assert.throws(()=>frontier.prepare('geneloop-resolve '+JSON.stringify({request_id:gap.request_id,status:'selected',candidate_ids:['c1',id]})),/duplicate/);
 assert.equal(frontier.ready(),null);
});
