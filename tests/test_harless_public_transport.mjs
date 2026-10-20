import test from 'node:test';
import assert from 'node:assert/strict';
import { createRemoteProjection, isNativeRpcResponse, publicRpcBytes, publicTransportError } from '../scripts/harless_public_transport.mjs';

test('only native RPC failure envelopes are projected; successful user/file bytes stay exact', () => {
  const text = '/home/operator/private file.txt 和 DeepSeek DSH 用户文档';
  const success = Buffer.from(JSON.stringify({type:'server-response',rpcId:'rpc1',result:{ok:true,value:{content:text,data:'AAECAw=='}}},null,2));
  assert.equal(publicRpcBytes(success),success);
  const failure={type:'server-response',rpcId:'rpc2',result:{ok:false,error:{code:'gateway/internal',message:text,details:{stack:text}}}};
  const projected=JSON.parse(publicRpcBytes(Buffer.from(JSON.stringify(failure))));
  assert.equal(projected.rpcId,'rpc2');assert.equal(projected.result.error.code,'gateway/internal');
  assert.deepEqual(projected.result.error.details,{});assert.ok(!JSON.stringify(projected).includes('/home/'));
  assert.equal(failure.result.error.message,text);
  assert.equal(publicTransportError({code:'/home/operator'}).code,'gateway/internal');
  const req={method:'POST',url:'/api/session/page'},response={headers:{'content-type':'application/json; charset=utf-8'}};
  assert.equal(isNativeRpcResponse(req,response),true);
  for(const changed of [{method:'GET'},{url:'/api/harless/comparisons'},{url:'/api/sss/tasks'}])
    assert.equal(isNativeRpcResponse({...req,...changed},response),false);
  assert.equal(isNativeRpcResponse(req,{headers:{...response.headers,'content-disposition':'attachment; filename="result.json"'}}),false);
  assert.equal(isNativeRpcResponse(req,{headers:{'content-type':'text/event-stream'}}),false);
});

test('event projection conceals home, added cwd and errors without touching other streams or requests', () => {
  const p=createRemoteProjection(), encode=v=>Buffer.from(JSON.stringify(v)), project=v=>JSON.parse(p.project(encode(v),false));
  const open=encode({type:'open',streamId:'events1',endpoint:'$events',payload:{args:{}}});
  p.observe(open,false);
  const ready={type:'item',streamId:'events1',value:{type:'ready',clientId:'browser1',host:{home:'/home/operator'}}};
  assert.equal(project(ready).value.host.home,'');assert.equal(ready.value.host.home,'/home/operator');
  const added={type:'item',streamId:'events1',value:{type:'emit',event:'api-session/added',args:[{sessionId:'one',cwd:'/home/operator/work',blank:true,updatedAt:1,running:false,projections:{asOfSeq:2,values:{safe:true}}}]}};
  const addedPublic=project(added);assert.equal(addedPublic.value.args[0].cwd,undefined);
  assert.deepEqual(addedPublic.value.args[0].projections,added.value.args[0].projections);
  const failed={type:'item',streamId:'events1',value:{type:'emit',event:'api-session/error',args:['one','failed: /home/operator/tool.py\nprivate stack']}};
  assert.equal(project(failed).value.args[0],'one');assert.ok(!JSON.stringify(project(failed)).includes('private'));
  const notification=encode({type:'item',streamId:'follow',value:{type:'event',event:{seq:3,data:{text:'/home/user/file.pdf'}}}});
  assert.equal(p.project(notification,false),notification);
  const waterfall=encode({type:'item',streamId:'events1',value:{type:'waterfall',event:'approval/request',eventId:'approval1',request:{path:'/home/user/file'},agentId:'one'}});
  assert.equal(p.project(waterfall,false),waterfall,'approval identity/request must not be rewritten');
  const binary=Buffer.from([0,128,255]);assert.equal(p.project(binary,true),binary);p.observe(binary,true);
  const error=project({type:'error',streamId:'follow',error:{code:'gateway/internal',message:'/home/operator',details:{where:'/app/private'}}});
  assert.deepEqual(error.error.details,{});assert.ok(!JSON.stringify(error).includes('/home/'));
  project({type:'end',streamId:'events1'});
  assert.equal(project(ready).value.host.home,'/home/operator','retired ID is no longer an event stream');
});

test('model selection failures retain actionable safe codes without returning private diagnostics',()=>{
  for(const code of ['model_budget_unavailable','model_not_allowed']){
    const error=publicTransportError({code,message:'/home/private/runtime: provider secret failure',details:{token:'secret'}});
    assert.equal(error.code,code);assert.deepEqual(error.details,{});
    assert.doesNotMatch(JSON.stringify(error),/private|secret/);
    assert.match(error.message,code==='model_budget_unavailable'?/Off/:/模型/);
  }
});

test('prompt admission failures preserve actionable codes without exposing internal paths',()=>{
 for(const code of ['session_busy','comparison_busy','task_busy','request_id_conflict']){
  const error=publicTransportError({code,message:'/home/private/request',details:{secret:'token'}});
  assert.equal(error.code,code);assert.deepEqual(error.details,{});
  assert.doesNotMatch(JSON.stringify(error),/private|secret|token/);
  assert.notEqual(error.message,'请求未能完成，请稍后重试。');
 }
});
