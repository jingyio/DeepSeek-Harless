import test from 'node:test';
import assert from 'node:assert/strict';
import {runInNewContext} from 'node:vm';
import {lowerRevisionProgram} from '../src/adapters/revision_rsi_macros.ts';
import {runProgram} from '../src/adapters/paper_rsi_program.ts';

test('generic field projection retains unknown keys, arrays and missing/null distinctions',()=> {
  const p=lowerRevisionProgram(['pairs_without',['var','input'],['lit',['ignored']]]);
  assert.deepEqual(runProgram(p,{z:[2,1],unknown:null,a:{q:1},ignored:'x'}),[['a',{q:1}],['unknown',null],['z',[2,1]]]);
  assert.notDeepEqual(runProgram(p,{unknown:null}),runProgram(p,{}));
  assert.notDeepEqual(runProgram(p,{z:[1,2]}),runProgram(p,{z:[2,1]}));
});

test('macro lowering avoids capturing model variables and supports native Cordis realms',()=> {
  const expr=['let','_rsi_m0',['lit','keep'],['object',{result:['pairs_without',['var','input'],['lit',[]]],kept:['var','_rsi_m0']}]];
  const lowered=lowerRevisionProgram(runInNewContext(JSON.stringify(expr)));
  assert.deepEqual(runProgram(lowered,{field:2}),{result:[['field',2]],kept:'keep'});
  assert.equal(JSON.stringify(lowered).includes('pairs_without'),false);
});

test('macros reject executable/accessor data and retain interpreter safety bounds',()=> {
  assert.throws(()=>lowerRevisionProgram({body:[]}),/expression_array/);
  assert.throws(()=>lowerRevisionProgram(['pairs_without',['var','input']]),/arity/);
  const p=['lit',{}];Object.defineProperty(p[1],'probe',{enumerable:true,get(){throw Error('executed');}});
  assert.throws(()=>lowerRevisionProgram(p),/data_property/);
  assert.throws(()=>runProgram(lowerRevisionProgram(['pairs_without',['var','input'],['lit',[]]]),null),/plain_object/);
  assert.throws(()=>lowerRevisionProgram(['eval',['lit','source']]),/invalid_program_node/);
});
