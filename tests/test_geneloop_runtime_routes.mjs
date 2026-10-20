/** Actual native Gateway over authenticated loopback HTTP and WebSocket.
 * No model provider or user data is involved.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {Context,Service} from '@deepseek-ai/cordis';
import {AgentRegistry} from '@deepseek-ai/dsh-agent';
import {AgentLoop} from '@deepseek-ai/dsh-agent-loop';
import {SessionStore} from '@deepseek-ai/dsh-session';
import {SessionProjectionRegistry} from '@deepseek-ai/dsh-session-projection';
import {SystemPrompt} from '@deepseek-ai/dsh-system-prompt';
import {ToolRuntime} from '@deepseek-ai/dsh-tools';
import {LlmRuntime} from '@deepseek-ai/dsh-llm';
import {GoalService} from '@deepseek-ai/dsh-goal';
import {TypertRegistry} from '@deepseek-ai/dsh-typert-registry';
import {TypertGatewayService} from '@deepseek-ai/dsh-api-gateway';
import {Remote,TypertRemoteService} from '@deepseek-ai/dsh-typert-protocol';
import {WebServer} from '@deepseek-ai/dsh-host-webserver';
import {apply as nativeConnection} from '@deepseek-ai/dsh-client-connection';
import WebSocket from 'ws';
import {protectGoalRpc,registerIndependentFileMode,independentFileMode,guardNativeModeCommand} from '../src/adapters/geneloop_runtime_routes.ts';

// Standard Remote decorator initialization, without requiring a transpiler.
const initializers=[];
class DiagnosticStream extends TypertRemoteService{
 constructor(ctx){super(ctx,'diagnostic');for(const initialize of initializers)initialize.call(this);}
 async *follow(value){yield {echo:value};}
}
Remote({mode:'stream'})(DiagnosticStream.prototype.follow,{kind:'method',name:'follow',static:false,private:false,addInitializer(fn){initializers.push(fn);}});
const ref=goal=>({id:goal.id,revision:goal.revision});
async function fixture(){
 const ctx=new Context();new SessionStore(ctx);new AgentRegistry(ctx);new SessionProjectionRegistry(ctx);
 new SystemPrompt(ctx,{});new ToolRuntime(ctx,{});new LlmRuntime(ctx);new TypertRegistry(ctx);
 const loop=new AgentLoop(ctx,{agents:[]}),agent=await loop.create('session-'+randomUUID(),{provider:'deepseek-official',model:'deepseek-flash'});
 new GoalService(ctx);new DiagnosticStream(ctx);
 const server=new WebServer(ctx,{host:'127.0.0.1',port:0});await server[Service.init]();
 ctx.provide('credentials',{async modifyRecord(_key,change){return change(undefined);}});await nativeConnection(ctx);
 const gateway=new TypertGatewayService(ctx,{websocketHeartbeatIntervalMs:2000});await new Promise(resolve=>setImmediate(resolve));
 const restore=protectGoalRpc(ctx),origin='http://127.0.0.1:'+server.port;
 server.register({kind:'exact',path:'/',handler:(req,res)=>{if(ctx.connection.authorizeIndex(req,res)){res.writeHead(200);res.end('diagnostic');}}});
 const exchange=await fetch(ctx.connection.authenticatedUrl(origin),{redirect:'manual'}),cookie=exchange.headers.get('set-cookie').split(';',1)[0];
 const http=async(method,args)=>{
  const response=await fetch(origin+'/api/'+method,{method:'POST',headers:{cookie,'Content-Type':'application/json'},
   body:JSON.stringify({type:'client-request',rpcId:randomUUID(),method,payload:{args}})});
  assert.equal(response.status,200);return (await response.json()).result;
 };
 const sockets=[];
 const websocket=async()=>{
  const ws=new WebSocket(origin.replace('http:','ws:')+'/api/remote.mux',{headers:{cookie,Origin:origin}});sockets.push(ws);
  const queue=[],waiting=[];ws.on('message',raw=>{const value=JSON.parse(raw.toString());const waiter=waiting.shift();if(waiter)waiter(value);else queue.push(value);});
  await new Promise((resolve,reject)=>{ws.once('open',resolve);ws.once('error',reject);});
  return {ws,next:()=>queue.length?Promise.resolve(queue.shift()):new Promise(resolve=>waiting.push(resolve)),
   open(endpoint,args){const id=randomUUID();ws.send(JSON.stringify({type:'open',streamId:id,endpoint,payload:{args}}));return id;}};
 };
 return {ctx,agent,gateway,http,websocket,restore,async close(){restore();for(const ws of sockets)ws.terminate();await ctx.fiber.dispose();}};
}

test('actual native Gateway denies every public goal mutation, allows get, and preserves internal native lifecycle', {timeout:5000},async()=>{
 const f=await fixture();try{
  const goal=f.ctx.goals.create(f.agent,{objective:'Synthetic explicitly chosen objective',maxGoalRounds:2});
  const get=()=>f.gateway.invoke({namespace:'goals',method:'get',args:{agentId:f.agent.id}});
  assert.equal((await get()).id,goal.id);
  for(const method of ['create','edit','pause','resume','complete','block','clear','unknown']){
   await assert.rejects(f.gateway.invoke({namespace:'goals',method,args:{}}),e=>e.code==='gateway/forbidden');
   await assert.rejects(f.gateway.stream({namespace:'goals',method,args:{}}),e=>e.code==='gateway/forbidden');
  }
  assert.deepEqual(f.ctx.goals.get(f.agent),goal,'public denial leaves native state untouched');
  const paused=f.ctx.goals.pause(f.agent,ref(goal)),resumed=f.ctx.goals.resume(f.agent,ref(paused));
  const edited=f.ctx.goals.edit(f.agent,ref(resumed),{maxGoalRounds:3});
  assert.equal(edited.maxGoalRounds,3);assert.equal((await get()).activation,'armed');
  const complete=f.ctx.goals.complete(f.agent,ref(edited));assert.equal((await get()).phase,'complete');
  f.ctx.goals.clear(f.agent,ref(complete));assert.equal(await get(),undefined);
 }finally{await f.close();}
});

test('authenticated native HTTP and WebSocket carriers both pass through the same public mode boundary', {timeout:5000},async()=>{
 const f=await fixture();try{
  const goal=f.ctx.goals.create(f.agent,{objective:'Transport boundary objective',maxGoalRounds:1});
  const read=await f.http('goals/get',{agentId:f.agent.id});assert.equal(read.ok,true);assert.equal(read.value.id,goal.id);
  for(const method of ['create','resume','edit','clear']){
   const result=await f.http('goals/'+method,{});assert.equal(result.ok,false);assert.equal(result.error.code,'gateway/forbidden');
  }
  const socket=await f.websocket();
  for(const method of ['resume','edit','clear']){
   const id=socket.open('goals/'+method,{}),result=await socket.next();
   assert.equal(result.streamId,id);assert.equal(result.type,'error');assert.equal(result.error.code,'gateway/forbidden');
  }
  const id=socket.open('diagnostic/follow',{value:'allowed-native-stream'}),item=await socket.next(),end=await socket.next();
  assert.deepEqual(item,{type:'item',streamId:id,value:{echo:'allowed-native-stream'}});assert.deepEqual(end,{type:'end',streamId:id});
  assert.deepEqual(f.ctx.goals.get(f.agent),goal);
 }finally{await f.close();}
});

test('File mode guard shares the original native controller identity and never leaks to another host',async()=>{
 const ctx=new Context(),other=new Context();new Service(ctx,'sessionController');new Service(other,'sessionController');
 try{
  const alias=ctx.extend(),remove=registerIndependentFileMode(ctx,id=>id==='file-one');let dispatched=0;
  const handler=guardNativeModeCommand(alias,()=>{dispatched++;return {kind:'success'};});
  const invocation=id=>({agent:{session:{id}}});
  assert.equal(handler(invocation('file-one')).kind,'error');assert.equal(dispatched,0);
  assert.equal(handler(invocation('chat')).kind,'success');assert.equal(dispatched,1);
  assert.equal(independentFileMode(other,'file-one'),false);
  const replacement=registerIndependentFileMode(alias,id=>id==='file-two');remove();
  assert.equal(independentFileMode(ctx,'file-two'),true,'old disposer cannot erase a newer route');
  replacement();assert.equal(independentFileMode(alias,'file-two'),false);
 }finally{await ctx.fiber.dispose();await other.fiber.dispose();}
});
