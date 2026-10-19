/** Actual Harness attachment + wire serialization. Offline transport only. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {Context} from '@deepseek-ai/cordis';
import {LocalAttachmentStore} from '@deepseek-ai/dsh-attachment-local';
import {resolveAdapterOptions} from '@deepseek-ai/dsh-llm-deepseek';
import {createServer} from 'node:http';
import {mkdtempSync,rmSync,readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
// Import during the test, so deployment wiring and the serializer are both checked.
test('Web adapter retains the actual Harness durable image path under its budget provider',async()=>{
 const {WebDeepSeekAdapter,webAttachmentOptions}=await import('../src/adapters/harless_legacy_reasoning.ts');
 const deployment=readFileSync(new URL('../src/adapters/dsh_geneloop_tasks.ts',import.meta.url),'utf8');
 assert.match(deployment,/\.\.\.webAttachmentOptions\(ctx\)/);
 const home=mkdtempSync(join(tmpdir(),'harness-image-wire-')),requests=[];
 const store=new LocalAttachmentStore(new Context(),{dshHome:home});
 const ref=await store.saveImage({data:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEklEQVR4nGMUkdNgYGBgYgADAAROAF4By7ZWAAAAAElFTkSuQmCC','base64'),mediaType:'image/png',name:'diagnostic.png'});
 const server=createServer(async(req,res)=>{
  let raw='';for await(const chunk of req)raw+=chunk;requests.push(JSON.parse(raw));res.writeHead(200,{'Content-Type':'text/event-stream'});
  res.end('data: '+JSON.stringify({id:'offline',object:'chat.completion.chunk',created:1,model:'deepseek-flash',choices:[{index:0,delta:{content:'diagnostic'},finish_reason:'stop'}],usage:{prompt_tokens:10,completion_tokens:1,total_tokens:11}})+'\n\ndata: [DONE]\n\n');
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 try{
  const options=resolveAdapterOptions({baseURL:`http://127.0.0.1:${server.address().port}`,reasoningEffort:'off',maxTokens:100});
  const adapter=new WebDeepSeekAdapter({options:()=>options,resolveApiKey:async()=>'offline-diagnostic',resolveUserId:()=> 'diagnostic',
   ...webAttachmentOptions({get:name=>name==='attachments'?store:undefined}),
   resolveFiles:()=>({ensureUploaded:async()=>{throw Error('offline diagnostic uses inline fallback');}}),
   prepareExtensions:async()=>({fields:{},accept:async()=>{}})});
  const prepared=await adapter.prepareCall('deepseek-official','deepseek-flash');
  for await(const chunk of prepared.stream({provider:'deepseek-official',model:'deepseek-flash',reasoningEffort:'off',
   messages:[{id:'actual-image',role:'user',content:[{type:'text',text:'describe actual pixels'},{type:'image',attachment:ref}]}]})){}
  const images=requests.flatMap(r=>r.messages).flatMap(m=>Array.isArray(m.content)?m.content:[]).filter(p=>p.type==='image_url');
  assert.equal(images.length,1);assert.match(images[0].image_url.url,/^data:image\/png;base64,/);
 }finally{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));rmSync(home,{recursive:true,force:true});}
});
