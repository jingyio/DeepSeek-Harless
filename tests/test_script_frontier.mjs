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
 assert.equal(learnedScriptFragments({programs:[first,{...second,argv_contract:{}}]}).length,0);
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
