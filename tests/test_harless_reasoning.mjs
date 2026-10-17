/** Deterministic adapter contract diagnostic; this never calls a paid provider. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { resolveAdapterOptions } from '@deepseek-ai/dsh-llm-deepseek';
import { WebDeepSeekAdapter, webReasoningEffort, webReasoningAvailability, webDeepSeekModels } from '../src/adapters/harless_reasoning.ts';

test('Native model discovery offers every supported strength while the installed adapter sends its native wire values',async()=>{
  const requests=[];
  const server=createServer(async(req,res)=>{
    let raw='';for await(const part of req)raw+=part;requests.push(JSON.parse(raw));
    res.writeHead(200,{'Content-Type':'text/event-stream'});
    res.end('data: '+JSON.stringify({id:'diagnostic',object:'chat.completion.chunk',created:1,model:'deepseek-flash',choices:[{index:0,delta:{content:'Diagnostic'},finish_reason:null}]})+'\n\n'+
      'data: '+JSON.stringify({id:'diagnostic',object:'chat.completion.chunk',created:1,model:'deepseek-flash',choices:[{index:0,delta:{},finish_reason:'stop'}],usage:{prompt_tokens:3,completion_tokens:1,total_tokens:4}})+'\n\ndata: [DONE]\n\n');
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  try {
    const options=resolveAdapterOptions({baseURL:`http://127.0.0.1:${server.address().port}`,reasoningEffort:'off'});
    delete options.maxTokens;
    const configured=[{provider:'deepseek-official',model:'deepseek-flash',label:'DeepSeek V4.1 Flash',available:true},
      {provider:'deepseek-official',model:'deepseek-v4-pro',label:'DeepSeek V4 Pro',available:true,reasoning_unavailable:{high:'On 暂不可用：当前任务预算不足。'}}];
    options.models=webDeepSeekModels(options.models,configured);
    const adapter=new WebDeepSeekAdapter({options:()=>options,resolveApiKey:async()=>'local-diagnostic-only',resolveUserId:()=> 'diagnostic',prepareExtensions:async()=>({fields:{},accept:async()=>{}})},configured);
    const catalog=await adapter.listModels('deepseek-official');
    assert.deepEqual(catalog.map(row=>row.id),['deepseek-flash','deepseek-v4-pro']);
    assert.deepEqual(catalog[0].inputModalities,['text','image']);assert.deepEqual(catalog[1].inputModalities,['text']);
    const model=await adapter.resolveModel('deepseek-official','deepseek-flash');
    assert.deepEqual(model.reasoning.efforts.map(row=>[row.id,row.name]),[['off','Off'],['low','Low'],['high','High'],['max','Max']]);
    assert.equal(model.reasoning.defaultEffort,'off');assert.equal(model.defaultMaxTokens,undefined);
    const prepared=await adapter.prepareCall('deepseek-official','deepseek-flash');
    assert.deepEqual(prepared.model.reasoning,model.reasoning);
    for(const effort of ['off','low','high','max']) {
      const chunks=[];
      for await(const chunk of prepared.stream({provider:'deepseek-official',model:'deepseek-flash',reasoningEffort:effort,
        messages:[{id:'diagnostic-user',role:'user',content:[{type:'text',text:'Contract check'}]}]}))chunks.push(chunk);
      assert.ok(chunks.some(chunk=>chunk.type==='text-delta'&&chunk.text==='Diagnostic'));
    }
    assert.equal(requests.length,4);
    assert.deepEqual(requests[0].thinking,{type:'disabled'});assert.ok(!('reasoning_effort' in requests[0]));
    for(const [index,effort] of ['low','high','max'].entries()){
      assert.deepEqual(requests[index+1].thinking,{type:'enabled'});assert.equal(requests[index+1].reasoning_effort,effort);
    }
    const pro=await adapter.prepareCall('deepseek-official','deepseek-v4-pro');
    assert.equal(pro.model.context.contextWindow,options.models.find(row=>row.id==='deepseek-v4-pro').contextWindow);
    assert.equal(pro.model.reasoning.efforts.find(row=>row.id==='high').name,'High（当前预算不可用）');
    for await(const chunk of pro.stream({provider:'deepseek-official',model:'deepseek-v4-pro',reasoningEffort:'off',
      messages:[{id:'pro-user',role:'user',content:[{type:'text',text:'Contract check'}]}]})){}
    assert.equal(requests[4].model,'deepseek-v4-pro');assert.deepEqual(requests[4].thinking,{type:'disabled'});
    for(const request of requests) {assert.equal(request.stream,true);assert.ok(!('max_tokens' in request));}
  }finally{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
});

test('Model availability keeps the configured route and reports unavailable reasoning without fallback',()=>{
  const pro={provider:'deepseek-official',model:'deepseek-v4-pro',label:'Pro',available:true,
    reasoning_unavailable:{high:'On 暂不可用：当前任务预算 $0.23 不足。'}};
  assert.equal(webReasoningAvailability(pro,'off'),'off');
  assert.throws(()=>webReasoningAvailability(pro,'high'),/预算 \$0.23/);
  const native=resolveAdapterOptions({}).models;
  const unavailable=webDeepSeekModels(native,[{...pro,available:false}]);assert.deepEqual(unavailable,[]);
  assert.throws(()=>webDeepSeekModels(native,[{...pro,model:'deepseek-v4-flash'}]),/not supported/);
  assert.throws(()=>webDeepSeekModels(native,[{...pro,model:'invented-model'}]),/not supported/);
  assert.throws(()=>webReasoningAvailability({...pro,supported_reasoning_efforts:['off','high']},'max'),/does not support/);
});

test('Explicit per-model capability intersects installed native modes while an ID-only catalog retains native modes',async()=>{
  const options=resolveAdapterOptions({reasoningEffort:'off'});
  const config={options:()=>options,resolveApiKey:async()=>'unused',resolveUserId:()=>'diagnostic',prepareExtensions:async()=>({fields:{},accept:async()=>{}})};
  const models=[{provider:'deepseek-official',model:'deepseek-flash',label:'Flash',available:true,supported_reasoning_efforts:['off','low','max']},
    {provider:'deepseek-official',model:'deepseek-v4-pro',label:'Pro',available:true}];
  const adapter=new WebDeepSeekAdapter(config,models);
  assert.deepEqual((await adapter.resolveModel('deepseek-official','deepseek-flash')).reasoning.efforts.map(row=>row.id),['off','low','max']);
  assert.deepEqual((await adapter.resolveModel('deepseek-official','deepseek-v4-pro')).reasoning.efforts.map(row=>row.id),['off','low','high','max']);
  const disabledOptions=resolveAdapterOptions({thinking:'disabled',reasoningEffort:'off'});
  const offOnly=new WebDeepSeekAdapter({...config,options:()=>disabledOptions},models);
  assert.deepEqual((await offOnly.resolveModel('deepseek-official','deepseek-flash')).reasoning.efforts.map(row=>row.id),['off']);
});

test('Unsupported provider effort combinations fail without claiming a fake toggle',()=>{
  assert.equal(webReasoningEffort('deepseek-official'),'off');
  for(const effort of ['off','low','high','max'])assert.equal(webReasoningEffort('deepseek-official',effort),effort);
  assert.equal(webReasoningEffort('harless-glm','off'),undefined);
  for(const provider of ['harless-glm','unknown'])assert.throws(()=>webReasoningEffort(provider,'high'),/reasoning/);
  for(const value of ['on','minimal','medium','xhigh','ultra',null,1])assert.throws(()=>webReasoningEffort('deepseek-official',value),/reasoning/);
});
