import test from 'node:test';
import assert from 'node:assert/strict';
import { AssistantStreamAccumulator, expandAssistantStream } from '@deepseek-ai/dsh-llm';
import { publicText, createPublicTextStream, createPublicStreamProjection, publicSessionEvent,
  publicTaskView, protectPublicSessionOutput } from '../src/adapters/harless_public_output.ts';

const secret = '/home/operator/deployment/source/main.py';
test('product prose hides host paths and old product names without changing model names or URLs', () => {
  const result = publicText('DeepSeek Harness (DSH), @deepseek-ai/dsh-system-prompt, '+secret+' C:\\private\\app.py。DeepSeek-V41-Flash https://example.org/home/docs /data');
  assert.doesNotMatch(result, /Harness|\bDSH\b|@deepseek-ai|operator|private/);
  assert.match(result, /GeneLoop/); assert.match(result, /DeepSeek-V41-Flash/);
  assert.match(result, /https:\/\/example.org\/home\/docs/); assert.match(result, /\/data$/);
});

test('every split of a private path or brand is safe before the next frame arrives', () => {
  for (const token of [secret, 'C:\\private\\app.py', 'DeepSeek Harness', 'DSH', '@deepseek-ai/dsh-system-prompt']) {
    const original = '您好，'+token+'。继续回答';
    for (let offset=1;offset<original.length;offset++) {
      const stream=createPublicTextStream();
      const first=stream.push(original.slice(0,offset));
      assert.doesNotMatch(first, /operator|private|DeepSeek Harness|\bDSH\b|@deepseek-ai/);
      const combined=first+stream.push(original.slice(offset))+stream.push('',true);
      assert.equal(combined,publicText(original),token+' at '+offset);
    }
  }
});

test('ordinary Chinese prose streams immediately and incomplete private suffix is withheld', () => {
  const stream=createPublicTextStream();
  assert.equal(stream.push('正在分析您上传的数据，'),'正在分析您上传的数据，');
  assert.equal(stream.push('目录 /ho'),'目录 ');
  assert.equal(stream.push('me/operator/app'),'');
  assert.equal(stream.push('。完成。'),'〔内部路径已隐藏〕。完成。');
});

test('user source messages and file bytes are not rewritten, detached assistant view is safe', () => {
  const user={type:'user/message',seq:3,time:1,surfaceOp:'append',data:{id:'user-1',role:'user',source:{kind:'user'},content:[{type:'text',text:'Explain DSH '+secret}]}};
  assert.equal(publicSessionEvent(user),user);
  const event={type:'assistant/message',seq:4,time:2,surfaceOp:'append',data:{message:{id:'answer-1',role:'assistant',source:{kind:'model',provider:'deepseek-official',model:'deepseek-flash'},content:[{type:'text',text:'我是 DSH '+secret}]}}};
  const before=JSON.stringify(event), result=publicSessionEvent(event);
  assert.equal(JSON.stringify(event),before);
  assert.equal(result.seq,4); assert.equal(result.surfaceOp,'append');
  assert.doesNotMatch(JSON.stringify(result),/operator|\bDSH\b/);
  assert.equal(result.data.message.source.model,'deepseek-flash');
});

test('system prompt details are not exposed through the message view', () => {
  const result=publicSessionEvent({type:'system/message',seq:0,time:1,surfaceOp:'append',data:{message:{id:'system-1',role:'system',source:{kind:'plugin',plugin:'@deepseek-ai/dsh-system-prompt'},content:[{type:'text',text:'private instructions '+secret}]}}});
  assert.equal(result.data.message.source.plugin,'GeneLoop');
  assert.equal(result.data.message.content[0].text,'已应用本轮会话设置。');
});

test('compact replay keeps chunk positions and flushes delta-only terminal tails', () => {
  const acc=new AssistantStreamAccumulator();
  for (const [i,text] of ['我是 Deep','Seek Harness，位置 /ho','me/operator/app.py','。DSH'].entries()) acc.push({time:i+1,chunk:{type:'text-delta',index:0,text}});
  const source=acc.snapshot(), result=createPublicStreamProjection().compact(source,true);
  const projected=expandAssistantStream(result);
  assert.equal(projected.length,4);
  assert.equal(projected.map(row=>row.chunk.text).join(''),publicText('我是 DeepSeek Harness，位置 /home/operator/app.py。DSH'));
  assert.match(JSON.stringify(source),/operator/);
});

test('stream tool arguments wait for the complete safe JSON block; provider replay state stays private', () => {
  const view=createPublicStreamProjection();
  const delta=view.chunk({type:'tool-call-delta',index:1,id:'call-1',name:'read_file',argumentsDelta:'{"path":"/home/operator/'});
  assert.equal(delta.argumentsDelta,''); assert.equal(delta.id,'call-1');
  const block=view.chunk({type:'block-end',index:1,block:{type:'tool-call',id:'call-1',name:'read_file',arguments:{path:secret}}});
  assert.doesNotMatch(JSON.stringify(block),/operator/);
  assert.equal(block.block.arguments.path,'〔内部路径已隐藏〕');
  const end=view.chunk({type:'finish',reason:'stop',replayState:{private:secret}});
  assert.equal(Object.hasOwn(end,'replayState'),false);
});

test('comparison projection preserves rating identity and artifact receipts', () => {
  const source={snapshot_revision:7,lanes:{baseline:{status:'running',answer:'您好 /ho',output_sha256:'123',artifacts:[{id:'file-1',name:'report.pdf',sha256:'abc'}]},motif:{status:'completed',answer:'我是 DSH '+secret}}};
  const result=publicTaskView(source);
  assert.equal(result.lanes.baseline.answer,'您好 ');
  assert.equal(result.lanes.baseline.output_sha256,'123');
  assert.equal(result.lanes.baseline.artifacts,source.lanes.baseline.artifacts);
  assert.match(source.lanes.motif.answer,/DSH/); assert.doesNotMatch(result.lanes.motif.answer,/operator|DSH/);
});

test('controller public projection preserves cursor and dense live frame identities; cold inspect untouched', async () => {
  const log={type:'event',event:{type:'assistant/message',seq:1,time:1,surfaceOp:'append',data:{message:{id:'m1',role:'assistant',source:{kind:'model',provider:'p',model:'m'},content:[{type:'text',text:secret}]}}}};
  const frames=[{type:'snapshot',header:{id:'s1',cwd:secret},cursor:1,records:[log],hasMore:false},
    {type:'assistant-stream',frame:{type:'start',attemptId:'a',revision:1}},
    ...['位置 /ho','me/operator/app.py','。'].map((text,index)=>({type:'assistant-stream',frame:{type:'chunk',attemptId:'a',revision:index+2,index,time:index,chunk:{type:'text-delta',index:0,text}}}))];
  const controller={async page(){return {records:[log],hasMore:false}},async *follow(){yield* frames},async inspect(){return log}};
  const original=controller.follow,dispose=protectPublicSessionOutput(controller);
  const result=[];for await(const frame of controller.follow({})) result.push(frame);
  assert.equal(result.length,frames.length); assert.equal(result[0].cursor,1);
  assert.doesNotMatch(JSON.stringify(result),/operator/); assert.equal(result[0].header.cwd,undefined);
  for(let i=1;i<result.length;i++) {assert.equal(result[i].frame.revision,frames[i].frame.revision);assert.equal(result[i].frame.index,frames[i].frame.index);}
  assert.equal(await controller.inspect(),log); assert.match(JSON.stringify(log),/operator/);
  dispose();assert.equal(controller.follow,original);
});

test('reconnect compact baseline and subsequent delta share the same private tail buffer', async () => {
  const acc=new AssistantStreamAccumulator();acc.push({time:1,chunk:{type:'text-delta',index:0,text:'位置 /ho'}});
  const controller={async *follow(){yield {type:'snapshot',header:{id:'s'},cursor:0,records:[],assistantStream:{revision:2,activeAttempt:{attemptId:'a',nextIndex:1,stream:acc.snapshot()}}};
    yield {type:'assistant-stream',frame:{type:'chunk',attemptId:'a',revision:3,index:1,time:2,chunk:{type:'text-delta',index:0,text:'me/operator/app.py。'}}};}};
  protectPublicSessionOutput(controller); const result=[];for await(const frame of controller.follow({}))result.push(frame);
  const initial=expandAssistantStream(result[0].assistantStream.activeAttempt.stream).map(row=>row.chunk.text).join('');
  assert.equal(initial+result[1].frame.chunk.text,'位置 〔内部路径已隐藏〕。');
  assert.equal(result[0].assistantStream.activeAttempt.nextIndex,1);
});

test('cold history passes the native session address when resolving old human admission content', async () => {
  const event={type:'user/message',seq:8,time:1,surfaceOp:'append',data:{id:'old-user',role:'user',
    source:{kind:'user',rpcId:'old-comparison-request'},content:[{type:'text',text:'请核对教学资料。'}],
    harless_comparison:{id:'old-comparison'}}};
  const record={type:'event',event}, requested=[];
  const controller={async page(){return {records:[record],hasMore:false}}};
  const restore=protectPublicSessionOutput(controller,(id,received)=>{
    assert.equal(id,'old-session');requested.push(id);assert.equal(received,event);
    return undefined; // The old comparison has no ordinary task admission.
  });
  const result=await controller.page({address:{kind:'session',sessionId:'old-session'},throughSeq:8});
  assert.deepEqual(requested,['old-session']);assert.equal(result.records[0].event,event);
  assert.equal(result.hasMore,false);restore();
});

test('native subagent history resolves the child identity for pages and live frames', async () => {
  const event={type:'user/message',seq:0,time:1,surfaceOp:'append',data:{id:'user',role:'user',
    source:{kind:'user',rpcId:'request'},content:[{type:'text',text:'hello'}]}};
  const record={type:'event',event}, requested=[];
  const controller={async page(){return {records:[record],hasMore:false}},async *follow(){
    yield {type:'snapshot',header:{id:'child'},cursor:0,records:[record]};yield {type:'event',event};
  }};
  protectPublicSessionOutput(controller,id=>{requested.push(id);return undefined;});
  const request={address:{kind:'subagent',parentSessionId:'parent',childSessionId:'child',mode:'background'},throughSeq:0};
  await controller.page(request);for await(const _ of controller.follow(request)){}
  assert.deepEqual(requested,['child','child','child']);
});

test('absent or malformed history addresses never resolve admission records with an undefined identity', async () => {
  const event={type:'user/message',seq:0,time:1,surfaceOp:'append',data:{id:'user',role:'user',
    source:{kind:'user',rpcId:'old-request'},content:[{type:'text',text:'untouched'}]}};
  const record={type:'event',event};let lookedUp=0;
  const controller={async page(){return {records:[record],hasMore:false}},async *follow(){
    yield {type:'snapshot',header:{id:'server-header-is-not-request-authority'},cursor:0,records:[record]};
    yield {type:'event',event};
  }};
  protectPublicSessionOutput(controller,()=>{lookedUp++;throw Error('Admission lookup requires a request identity');});
  for(const request of [undefined,{}, {address:{}}, {address:{kind:'other',sessionId:'ignored'}},
    {address:{kind:'session'}}, {address:{kind:'session',sessionId:42}}, {address:{kind:'subagent',parentSessionId:'parent'}}]){
    assert.equal((await controller.page(request)).records[0].event,event);
    for await(const frame of controller.follow(request))if(frame.type==='event')assert.equal(frame.event,event);
  }
  assert.equal(lookedUp,0);
});

test('history presentation preserves authoritative page and follow permission failures', async () => {
  const denied=Object.assign(Error('forbidden'),{code:'gateway/forbidden'});let lookedUp=0;
  const controller={async page(){throw denied;},async *follow(){throw denied;}};
  protectPublicSessionOutput(controller,()=>{lookedUp++;});
  const request={address:{kind:'session',sessionId:'foreign'},throughSeq:0};
  await assert.rejects(controller.page(request),error=>error===denied);
  await assert.rejects(async()=>{for await(const _ of controller.follow(request)){}},error=>error===denied);
  assert.equal(lookedUp,0);
});
