import test from 'node:test';
import assert from 'node:assert/strict';
import {createProbeFrontier} from '../src/adapters/probe_frontier.ts';
const contract={failure:{ok:false,checks:['x']},success_fields:['ok'],axes:[{path:['items']},{path:['items','*','parts']}],max_probes:24};
test('nested learned axes narrow only observed failures',()=>{
 const r=createProbeFrontier(contract,{items:[{parts:['a','bad']},{parts:['c','d']}]});
 let a,n=0;while(a=r.next()){n++;r.observe(a.items.some(i=>i.parts.includes('bad'))?contract.failure:{ok:true});}
 assert.equal(n,3);assert.deepEqual(r.report().witness,{items:[{parts:['bad']}]});
});
test('both passing halves do not establish a cause; different error and budget stop',()=>{
 const a=createProbeFrontier(contract,{items:[1,2]});a.next();a.observe({ok:true});a.next();a.observe({ok:true});assert.equal(a.next(),null);assert.deepEqual(a.report().witness,{items:[1,2]});assert.ok(a.report().history.some(x=>x.outcome.includes('interaction')));
 const b=createProbeFrontier(contract,{items:[1,2]});b.next();b.observe({ok:false,checks:['different']});assert.equal(b.next(),null);assert.match(b.report().reason,/different_failure/);
 const c=createProbeFrontier({...contract,max_probes:1},{items:[1,2,3,4]});c.next();c.observe(contract.failure);assert.equal(c.next(),null);assert.equal(c.report().reason,'probe_limit');
});
