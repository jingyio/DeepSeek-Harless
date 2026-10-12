import test from 'node:test';
import assert from 'node:assert/strict';
import {guardAllows} from '../src/adapters/dsh_trace_rsi_effect_guard.ts';
test('output conditions distinguish complete state, field loss, missing and wrong types',()=>{
 const c=[{feature:'matched:true',equals:true},{feature:'changed:empty',equals:true}];
 assert.equal(guardAllows(c,{matched:true,changed:[]}),true);
 for(const o of [{matched:false,changed:[]},{matched:true,changed:['lost']},{matched:true},{matched:'true',changed:[]}])assert.equal(guardAllows(c,o),false);
});
test('condition evaluation cannot execute getters or accept unsafe and duplicate fields',()=>{
 let accessed=0;const o={};Object.defineProperty(o,'x',{get(){accessed++;return true;}});
 assert.equal(guardAllows([{feature:'x:true',equals:true}],o),false);assert.equal(accessed,0);
 assert.equal(guardAllows([{feature:'__proto__:true',equals:true}],{}),false);
 assert.equal(guardAllows([{feature:'x:true',equals:true},{feature:'x:true',equals:true}],{x:true}),false);
 assert.equal(guardAllows([],{x:true}),false);
});
