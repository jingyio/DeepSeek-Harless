/** Free local transport diagnostics, not model-behavior certification. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {randomUUID} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {resolveAdapterOptions} from '@deepseek-ai/dsh-llm-deepseek';
import {ManagementRoutedAdapter,startManagementGate} from '../src/adapters/management_model_gate.ts';
import {WEB_DEEPSEEK_OUTPUT_CAPACITY} from '../src/adapters/harless_reasoning.ts';

test('Only admitted file tasks use the local gate; other scene serialization stays native',async()=>{
 const rows=[];
 const server=createServer(async(req,res)=>{
  let raw='';for await(const chunk of req)raw+=chunk;rows.push({path:req.url,body:JSON.parse(raw)});
  res.writeHead(200,{'Content-Type':'text/event-stream'});
  res.end('data: '+JSON.stringify({id:'diagnostic',choices:[{index:0,delta:{content:'Diagnostic'},finish_reason:null}]})+'\n\n'+
   'data: '+JSON.stringify({id:'diagnostic',choices:[{index:0,delta:{},finish_reason:'stop'}],usage:{prompt_tokens:3,completion_tokens:1,total_tokens:4}})+'\n\ndata: [DONE]\n\n');
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 try{
  const base=`http://127.0.0.1:${server.address().port}`;
  const options=resolveAdapterOptions({baseURL:base+'/platform',reasoningEffort:'off'});delete options.maxTokens;
  const adapter=new ManagementRoutedAdapter({options:()=>options,resolveApiKey:async()=>'local-diagnostic-only',resolveUserId:()=>'diagnostic',prepareExtensions:async()=>({fields:{},accept:async()=>{}})},[],id=>id==='file-session'?base+'/file-gate':undefined);
  const prepared=await adapter.prepareCall('deepseek-official','deepseek-flash');
  for(const id of ['paper-session','file-session']){
   for await(const chunk of prepared.stream({provider:'deepseek-official',model:'deepseek-flash',sessionId:id,reasoningEffort:'off',messages:[{id:'same-user',role:'user',content:[{type:'text',text:'Contract check'}]}]})){}
  }
  assert.deepEqual(rows.map(r=>r.path),['/platform/chat/completions','/file-gate/chat/completions']);
  assert.deepEqual(rows[0].body,rows[1].body);
  assert.equal(rows[0].body.max_tokens,WEB_DEEPSEEK_OUTPUT_CAPACITY,'file and non-file routes both avoid the provider 8K default');
 }finally{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
});

test('Account-local gate boots with current dependencies and rejects another account before any model call',async()=>{
 const previous=process.env.DEEPSEEK_API_KEY;process.env.DEEPSEEK_API_KEY='local-diagnostic-account-only';
 const root=fileURLToPath(new URL('../',import.meta.url));
 const gate=startManagementGate({python:process.env.SSS_PYTHON??'python3',private_root:join(root,'.local/gate-boot-tests',randomUUID())},'http://127.0.0.1:9/v1',false);
 try{
  const endpoint=await gate.ready;
  const response=await fetch(endpoint+'/chat/completions',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer another-account','X-DeepSeek-Harness-Session-Id':'session-'+randomUUID()},body:JSON.stringify({model:'deepseek-flash',messages:[{role:'user',content:'diagnostic'}],max_tokens:20})});
  assert.equal(response.status,403);
 }finally{gate.close();if(previous===undefined)delete process.env.DEEPSEEK_API_KEY;else process.env.DEEPSEEK_API_KEY=previous;}
});
