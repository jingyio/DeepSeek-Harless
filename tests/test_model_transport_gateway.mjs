/** Local HTTP relay only: synthetic accounts and provider, zero paid calls. */
import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {once} from 'node:events';
import {createHash,createHmac} from 'node:crypto';
import {mkdtempSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createGateway,MODEL_REQUEST_MAX_BYTES} from '../scripts/harless_gateway.mjs';

const MiB=1024*1024,session='session-12345678-1234-1234-1234-123456789abc';
const listen=async server=>{server.listen(0,'127.0.0.1');await once(server,'listening');return server.address().port;};
const digest=body=>createHash('sha256').update(body).digest('hex');

async function fixture(t){
  const dir=mkdtempSync(join(tmpdir(),'model-http-envelope-')),received=[];
  t.after(()=>rmSync(dir,{recursive:true,force:true}));
  const upstream=http.createServer(async(req,res)=>{
    let size=0;const hash=createHash('sha256');
    for await(const part of req){size+=part.length;hash.update(part);}
    received.push({path:req.url,bytes:size,sha256:hash.digest('hex')});
    res.writeHead(200,{'content-type':'application/json'});res.end('{}');
  });
  const target=await listen(upstream);
  t.after(()=>{upstream.closeAllConnections();return new Promise(resolve=>upstream.close(resolve));});
  const html=join(dir,'account.html');writeFileSync(html,'<title>diagnostic</title>');
  const config={dataDir:join(dir,'accounts'),membersDir:join(dir,'members'),
    publicOrigin:'https://diagnostic.invalid',accountHtml:html,
    adminToken:'synthetic-control-secret',apiKey:'synthetic-provider-key',
    scopedBudgetPort:1,upstreamControlPort:target,upstreamBrokerPort:target,
    memberPolicy:{control_token:'synthetic-budget-control',budget_usd:null}};
  const gateway=createGateway(config);
  // Isolated fixture identities only; no production login or invitation side effect.
  const alice={id:'diagnostic-alice',role:'member'},bob={id:'diagnostic-bob',role:'member'};
  gateway.db.users.push(alice,bob);
  const port=await listen(gateway.scopedBudget);
  t.after(()=>{gateway.scopedBudget.closeAllConnections();gateway.close();});
  const delegated=(user,purpose)=>createHmac('sha256',config.adminToken).update(purpose+':'+user.id).digest('base64url');
  const headers=(user=alice)=>({'content-type':'application/json',
    authorization:'Bearer '+delegated(user,'model'),'x-deepseek-harness-session-id':session});
  const bind=await fetch(`http://127.0.0.1:${port}/bind`,{method:'POST',
    headers:{'content-type':'application/json','x-sss-control-token':delegated(alice,'control')},
    body:JSON.stringify({session_id:session,budget_session_id:'turn-'+digest(alice.id).slice(0,8)+'a'.repeat(24)})});
  assert.equal(bind.status,200);await bind.text();received.length=0;
  return {port,received,headers,alice,bob,delegated};
}

for(const size of [3*MiB,9*MiB,28*MiB])test(`scoped model relay forwards ${size/MiB} MiB byte-for-byte`,async t=>{
  const f=await fixture(t);
  const body=JSON.stringify({model:'deepseek-flash',max_tokens:393216,messages:[{role:'user',content:[
    {type:'text',text:'Same long context'},
    {type:'image_url',image_url:{url:'data:image/png;base64,'+'A'.repeat(size)}},
  ]}]});
  const rejected=await fetch(`http://127.0.0.1:${f.port}/v1/chat/completions`,
    {method:'POST',headers:f.headers(f.bob),body});
  assert.equal(rejected.status,403);await rejected.text();assert.equal(f.received.length,0);
  const response=await fetch(`http://127.0.0.1:${f.port}/v1/chat/completions`,
    {method:'POST',headers:f.headers(),body});
  assert.equal(response.status,200);await response.text();
  assert.deepEqual(f.received,[{path:'/v1/chat/completions',bytes:Buffer.byteLength(body),sha256:digest(body)}]);
});

test('scoped vision and Chat use the same envelope capacity',async t=>{
  const f=await fixture(t),body=JSON.stringify({model:'deepseek-flash',pixels:'A'.repeat(9*MiB)});
  const path='/v1/vision/'+session+'/chat/completions';
  const response=await fetch(`http://127.0.0.1:${f.port}${path}`,{method:'POST',headers:f.headers(),body});
  assert.equal(response.status,200);await response.text();
  assert.deepEqual(f.received,[{path,bytes:Buffer.byteLength(body),sha256:digest(body)}]);
});

function rawPost(f,{length,chunks}){
  return new Promise((resolve,reject)=>{
    let responded=false;
    const request=http.request({host:'127.0.0.1',port:f.port,path:'/v1/chat/completions',method:'POST',
      headers:{...f.headers(),...(length===undefined?{}:{'content-length':length})}},response=>{
      responded=true;const parts=[];response.on('data',part=>parts.push(part));
      response.on('end',()=>resolve({status:response.statusCode,body:JSON.parse(Buffer.concat(parts)),headers:response.headers}));
      response.on('error',reject);
    });
    request.on('error',error=>{if(!responded)reject(error);});
    (async()=>{try{
      for(const chunk of chunks??[]){if(!request.write(chunk))await once(request,'drain');}
      request.end();
    }catch(error){if(!responded)reject(error);}})();
  });
}

test('oversized Content-Length returns typed 413 without resetting or forwarding',async t=>{
  const f=await fixture(t);
  const response=await rawPost(f,{length:MODEL_REQUEST_MAX_BYTES+1});
  assert.equal(response.status,413);
  assert.equal(response.body.error.code,'GENELOOP_MODEL_REQUEST_TOO_LARGE');
  assert.equal(response.body.error.type,'invalid_request_error');
  assert.equal(response.body.error.max_bytes,MODEL_REQUEST_MAX_BYTES);
  assert.equal(response.headers.connection,'close');
  assert.equal(f.received.length,0);
});

test('oversized upload already in flight still receives typed 413',async t=>{
  const f=await fixture(t),chunk=Buffer.alloc(MiB,65);
  const chunks=(function*(){for(let n=0;n<MODEL_REQUEST_MAX_BYTES/MiB;n++)yield chunk;yield Buffer.from('A');})();
  const response=await rawPost(f,{length:MODEL_REQUEST_MAX_BYTES+1,chunks});
  assert.equal(response.status,413);
  assert.equal(response.body.error.code,'GENELOOP_MODEL_REQUEST_TOO_LARGE');
  assert.equal(f.received.length,0);
});

test('chunked overflow drains and returns 413; a later valid request still works',async t=>{
  const f=await fixture(t),chunk=Buffer.alloc(MiB,65);
  const chunks=(function*(){for(let n=0;n<MODEL_REQUEST_MAX_BYTES/MiB+1;n++)yield chunk;})();
  const response=await rawPost(f,{chunks});
  assert.equal(response.status,413);
  assert.equal(response.body.error.code,'GENELOOP_MODEL_REQUEST_TOO_LARGE');
  assert.equal(f.received.length,0);
  const valid=await fetch(`http://127.0.0.1:${f.port}/v1/chat/completions`,{
    method:'POST',headers:f.headers(),body:'{}'});
  assert.equal(valid.status,200);await valid.text();assert.equal(f.received.length,1);
});

test('model envelope expansion does not expand the control body allowance',async t=>{
  const f=await fixture(t);
  const response=await fetch(`http://127.0.0.1:${f.port}/bind`,{method:'POST',
    headers:{'content-type':'application/json','x-sss-control-token':f.delegated(f.alice,'control')},
    body:JSON.stringify({padding:'A'.repeat(8193)})});
  assert.equal(response.status,413);
  assert.equal((await response.json()).error.code,'GENELOOP_CONTROL_REQUEST_TOO_LARGE');
  assert.equal(f.received.length,0);
});
