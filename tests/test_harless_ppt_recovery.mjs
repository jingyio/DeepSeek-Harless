import test from 'node:test';
import assert from 'node:assert/strict';
import {createPptRecovery} from '../src/adapters/harless_ppt_recovery.ts';
const exec=name=>({name:'mcp__ppt__'+name});
const result=value=>({content:[{type:'text',text:JSON.stringify(value)}]});
const fail=code=>({...result({ok:false,code}),isError:true});

test('unsupported statistics are removed in the same task and remaining budget',()=>{
 const g=createPptRecovery();g.observe(exec('render_deck'),{isError:true,structuredContent:{error:'unsupported_statistics'}});
 const continuation=g.stop({aborted:false,expectedSlides:3});
 assert.equal(continuation.error.code,'unsupported_statistics');
 assert.match(continuation.instruction,/剩余任务预算/);
 g.observe(exec('deliver_deck'),result({delivered:true}));assert.equal(g.stop({aborted:false}),null);
});
test('wrong page count continues same task through actual successful delivery',()=>{
 const g=createPptRecovery();g.observe(exec('render_deck'),fail('slide_count_mismatch'));
 const first=g.stop({aborted:false,expectedSlides:3});assert.equal(first.error.code,'slide_count_mismatch');
 assert.match(first.instruction,/总页数.*3/);assert.match(first.instruction,/剩余任务预算/);
 g.observe(exec('render_deck'),result({deck_id:'new-corrected-deck'}));
 assert.ok(g.stop({aborted:false,expectedSlides:3}),'render alone cannot masquerade as delivery');
 g.observe(exec('inspect_deck'),result({passed:true}));g.observe(exec('validate_deck'),result({passed:true}));
 assert.ok(g.stop({aborted:false,expectedSlides:3}));
 g.observe(exec('deliver_deck'),result({delivered:true}));assert.equal(g.stop({aborted:false,expectedSlides:3}),null);
});
test('greetings and unsupported/fatal errors do not fabricate a recovery task',()=>{
 const g=createPptRecovery();g.observe(exec('list_inputs'),result({inputs:[]}));assert.equal(g.stop({aborted:false}),null);
 for(const code of ['output_permission_denied','job_version_changed','path_scope_rejected','pending_recovery_exhausted']){
  const guard=createPptRecovery();guard.observe(exec('render_delivery'),fail(code));
  assert.equal(guard.stop({aborted:false,expectedSlides:3}),null);
 }
});
test('cancel and isolated tasks never receive continuation; no new request-count cap',()=>{
 const a=createPptRecovery(),b=createPptRecovery();a.observe(exec('render_deck'),fail('invalid_plan'));
 assert.equal(a.stop({aborted:true}),null);assert.equal(b.stop({aborted:false}),null);
 for(let i=1;i<=25;i++)assert.equal(a.stop({aborted:false,expectedSlides:3}).continuation,i);
 assert.equal(a.state().delivered,false);
});
test('structured MCP errors and combined delivery use the same repair/receipt protocol',()=>{
 const g=createPptRecovery();g.observe(exec('render_delivery'),{isError:true,structuredContent:{ok:false,code:'text_box_overflow'}});
 assert.equal(g.stop({aborted:false}).error.code,'text_box_overflow');
 g.observe(exec('render_delivery'),{structuredContent:{delivered:true}});assert.equal(g.stop({aborted:false}),null);
});
test('real renderer errors inside adapter reports remain repairable; version refusals do not',()=>{
 const g=createPptRecovery();g.observe(exec('render_deck'),{isError:true,structuredContent:{ok:false,code:'backend_tool_failed',
  backend_report:{content:[{type:'text',text:JSON.stringify({report:{code:'text_overflow',page:2}})}]}}});
 assert.equal(g.stop({aborted:false}).error.code,'text_overflow');
 g.observe(exec('validate_deck'),result({passed:false}));assert.equal(g.stop({aborted:false}).error.code,'validation_failed');
 g.observe(exec('render_deck'),fail('source_version_changed'));assert.equal(g.stop({aborted:false}),null);
});
test('native Harness argument validation continues before MCP dispatch',()=>{
 const g=createPptRecovery();g.observe(exec('render_deck'),{isError:true,error:{info:{code:'INVALID_ARGS'}},content:[{type:'text',text:'Error: invalid arguments: slides'}]});
 assert.equal(g.stop({aborted:false,expectedSlides:3}).error.code,'invalid_arguments');
});
test('actual MCP Error prefix and atomic delivery receipt avoid false stops and repeated delivery',()=>{
 const g=createPptRecovery();g.observe(exec('render_deck'),{isError:true,content:[{type:'text',text:'Error: '+JSON.stringify({ok:false,code:'slide_count_mismatch'})}]});
 assert.equal(g.stop({aborted:false,expectedSlides:3}).error.code,'slide_count_mismatch');
 g.observe(exec('render_delivery'),{isError:true,content:[{type:'text',text:'Error: '+JSON.stringify({ok:false,code:'backend_tool_failed',backend_report:{error:'invalid_plan'}})}]});
 assert.equal(g.stop({aborted:false}).error.code,'invalid_plan');
 g.observe(exec('deliver_deck'),result({deck_id:'verified-deck',validation_id:'verified-validation',file_sha256:'a'.repeat(64),input_version:'b'.repeat(64),artifacts:[{kind:'pdf',sha256:'c'.repeat(64)}]}));
 assert.equal(g.stop({aborted:false}),null);
});
