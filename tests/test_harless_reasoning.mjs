/** Deterministic adapter contract diagnostic; this never calls a paid provider. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { resolveAdapterOptions } from '@deepseek-ai/dsh-llm-deepseek';
import { WebDeepSeekAdapter, webReasoningEffort } from '../src/adapters/harless_reasoning.ts';

test('Native model discovery offers Off/On while the installed adapter sends the supported wire values',async()=>{
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
    const adapter=new WebDeepSeekAdapter({options:()=>options,resolveApiKey:async()=>'local-diagnostic-only',resolveUserId:()=> 'diagnostic',prepareExtensions:async()=>({fields:{},accept:async()=>{}})});
    const model=await adapter.resolveModel('deepseek-official','deepseek-flash');
    assert.deepEqual(model.reasoning.efforts.map(row=>[row.id,row.name]),[['off','Off'],['high','On']]);
    assert.equal(model.reasoning.defaultEffort,'off');assert.equal(model.defaultMaxTokens,undefined);
    const prepared=await adapter.prepareCall('deepseek-official','deepseek-flash');
    assert.deepEqual(prepared.model.reasoning,model.reasoning);
    for(const effort of ['off','high']) {
      const chunks=[];
      for await(const chunk of prepared.stream({provider:'deepseek-official',model:'deepseek-flash',reasoningEffort:effort,
        messages:[{id:'diagnostic-user',role:'user',content:[{type:'text',text:'Contract check'}]}]}))chunks.push(chunk);
      assert.ok(chunks.some(chunk=>chunk.type==='text-delta'&&chunk.text==='Diagnostic'));
    }
    assert.equal(requests.length,2);
    assert.deepEqual(requests[0].thinking,{type:'disabled'});assert.ok(!('reasoning_effort' in requests[0]));
    assert.deepEqual(requests[1].thinking,{type:'enabled'});assert.equal(requests[1].reasoning_effort,'high');
    for(const request of requests) {assert.equal(request.stream,true);assert.ok(!('max_tokens' in request));}
  }finally{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
});

test('Unsupported provider effort combinations fail without claiming a fake toggle',()=>{
  assert.equal(webReasoningEffort('deepseek-official'),'off');
  assert.equal(webReasoningEffort('deepseek-official','high'),'high');
  assert.equal(webReasoningEffort('harless-glm','off'),undefined);
  for(const provider of ['harless-glm','unknown'])assert.throws(()=>webReasoningEffort(provider,'high'),/reasoning/);
  for(const value of ['on','low','max',null,1])assert.throws(()=>webReasoningEffort('deepseek-official',value),/reasoning/);
});
