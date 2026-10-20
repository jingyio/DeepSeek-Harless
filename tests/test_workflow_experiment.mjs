import test from 'node:test';import assert from 'node:assert/strict';
import {mkdirSync,writeFileSync,readFileSync,mkdtempSync,rmSync} from 'node:fs';
import {createHash} from 'node:crypto';import {resolve,join} from 'node:path';
import {experimentBoundary} from '../src/adapters/dsh_workflow_experiment.ts';
const root=resolve(import.meta.dirname,'..'),hash=p=>createHash('sha256').update(readFileSync(p)).digest('hex');
function fixture(mode){
 const parent=join(root,'.local/workflow-boundary-tests');mkdirSync(parent,{recursive:true});const out=mkdtempSync(join(parent,'test-'));
 const dataParent=join(root,'testpdf/file-management-experiment/boundary-tests');mkdirSync(dataParent,{recursive:true});const work=mkdtempSync(join(dataParent,'test-'));
 writeFileSync(join(work,'.experiment-copy'),'fixed free test');writeFileSync(join(work,'source.txt'),'old');
 const control={mode,workflow_id:'FM01',target:'source.txt',before_sha256:hash(join(work,'source.txt')),replacement:'new',marker:join(out,'marker.json')};
 return {work,out,control,spec:{workspace:work},close(){rmSync(work,{recursive:true});rmSync(out,{recursive:true});}};
}
test('version injection occurs at actual preview once and stops before another model decision',()=>{
 const f=fixture('version');try{const b=experimentBoundary(f.control,f.spec);b.observe({name:'mcp__file_management__read_task'},{});assert.equal(readFileSync(join(f.work,'source.txt'),'utf8'),'old');
 b.observe({name:'mcp__file_management__preview_actions',callId:'real-preview'},{value:{structuredContent:{status:'validated_copy_plan',actions:[]}}});assert.equal(readFileSync(join(f.work,'source.txt'),'utf8'),'new');assert.throws(()=>b.interrupt(),/FROZEN_WORKFLOW_BOUNDARY_version/);b.interrupt();
 const m=JSON.parse(readFileSync(f.control.marker));assert.equal(m.interrupted,true);assert.equal(m.boundary_call_id,'real-preview');}finally{f.close();}
});
test('changed perturbation preimage and paths outside experimental copies refuse',()=>{
 const f=fixture('version');try{writeFileSync(join(f.work,'source.txt'),'unexpected');const b=experimentBoundary(f.control,f.spec);assert.throws(()=>b.observe({name:'mcp__file_management__preview_actions'},{value:{structuredContent:{status:'validated_copy_plan'}}}),/preimage/);
 assert.throws(()=>experimentBoundary(f.control,{workspace:root}),/boundary/);}finally{f.close();}
});
test('no boundary profile leaves the original provider request unchanged',()=>{
 const f=fixture('none');try{const b=experimentBoundary(f.control,f.spec);b.observe({name:'mcp__file_management__execute_plan'},{isError:true});b.interrupt();}finally{f.close();}
});
