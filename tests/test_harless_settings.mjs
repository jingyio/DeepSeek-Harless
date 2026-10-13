import test from 'node:test';
import assert from 'node:assert/strict';
const options={skip:!process.features?.typescript};
test('RSI modes, conflict checks, remembering Execute, and unavailable Execute are coherent',options,async()=>{
 const {initialSelection,changeSelection,sceneCatalog}=await import('../src/adapters/harless_settings.ts');
 const scenes=sceneCatalog([{id:'example',label:'示例',preset:'sss-task',allowed_tools:['mcp__demo__read']}]);
 let state=initialSelection('example','shadow');
 const change=patch=>state=changeSelection(state,patch,scenes,()=>null);
 change({mode:'execute'});change({rsi:false});assert.equal(state.mode,'baseline');change({rsi:true});assert.equal(state.mode,'execute');
 change({mode:'baseline'});assert.equal(state.rsi,false);change({mode:'shadow'});assert.equal(state.rsi,true);
 assert.throws(()=>change({mode:'baseline',rsi:true}),/Baseline/);
 assert.throws(()=>changeSelection(state,{mode:'execute'},scenes,()=> 'no_certified_library'),/no_certified_library/);
 assert.throws(()=>change({scene:'../../private'}),/未登记/);assert.throws(()=>change({manifest:'private'}),/只支持/);
});
test('Scene catalog rejects duplicate identity, arbitrary presets and invalid tool scope',options,async()=>{
 const {sceneCatalog}=await import('../src/adapters/harless_settings.ts');
 const scene={id:'example',label:'示例',preset:'sss-task',allowed_tools:['mcp__demo__read']};
 for(const rows of [[scene,scene],[{...scene,preset:'root'}],[{...scene,allowed_tools:['bash']}],[{...scene,id:'../../'}]])assert.throws(()=>sceneCatalog(rows));
});
