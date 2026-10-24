/** Native tool lifecycle diagnostic over a local HTTP fixture; not model evidence. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {runNativeDiagnostic} from '../examples/rsi-protocol-v1/native_harness.mjs';

const frame=(delta,finish_reason=null)=>'data: '+JSON.stringify({id:'f02-local',object:'chat.completion.chunk',created:1,
 model:'deepseek-flash',choices:[{index:0,delta,finish_reason}]})+'\n\n';
async function localFixture(task){
 const requests=[];
 const server=createServer(async(req,res)=>{
  let raw='';for await(const part of req)raw+=part;
  requests.push(JSON.parse(raw));
  res.writeHead(200,{'Content-Type':'text/event-stream'});
  if(task==='C'||requests.length>1)res.end(frame({content:'Diagnostic result recorded.'})+frame({},'stop')+'data: [DONE]\n\n');
  else res.end(frame({tool_calls:[{index:0,id:'f02-call',type:'function',function:{name:'group_count',arguments:'{}'}}]})+frame({},'tool_calls')+'data: [DONE]\n\n');
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 try{return {result:await runNativeDiagnostic({task,baseURL:`http://127.0.0.1:${server.address().port}`,resolveApiKey:async()=>'synthetic-test-only'}),requests};}
 finally{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
}

test('native Harness exposes one bounded tool and records actual tool lifecycle + protocol receipts',async()=>{
 const {result,requests}=await localFixture('B');
 assert.equal(result.correct,true);assert.deepEqual(result.errors,[]);
 assert.equal(result.native_python_dispatches,1);assert.equal(result.model_requests,2);
 assert.equal(result.events.filter(x=>x.type==='tool/result').length,1);
 assert.equal(result.executions[0].events[0].payload.call_id,result.events.find(x=>x.type==='tool/result').data.message.source.callId);
 assert.deepEqual(result.executions[0].events.map(x=>x.payload.phase),['started','succeeded']);
 assert.ok(requests.every(x=>x.tools.length===1&&x.tools[0].function.name==='group_count'));
});

test('native no-operation task has no Python dispatch',async()=>{
 const {result}=await localFixture('C');
 assert.equal(result.correct,true);assert.deepEqual(result.errors,[]);
 assert.equal(result.model_requests,1);assert.equal(result.native_python_dispatches,0);
});
