/** Independent public-schema and stream-boundary regression review; no model. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { AssistantStreamAccumulator, expandAssistantStream } from '@deepseek-ai/dsh-llm';
import { publicText, createPublicTextStream, publicSessionEvent, protectPublicSessionOutput,
  publicTaskView } from '../src/adapters/harless_public_output.ts';

test('local file links never expose server paths in full text or across any split',()=>{
  for(const token of ['file:///home/operator/source/main.py','file:///C:/private/source/main.py',
    'file://localhost/home/operator/source/main.py','/app/src/adapters/runtime.ts',
    'cwd:/home/operator/source/main.py','src:/app/src/adapters/runtime.ts']){
    const input='文件 ['+token+']('+token+')。继续';
    assert.doesNotMatch(publicText(input),/operator|private|adapters/);
    for(let offset=1;offset<input.length;offset++){
      const stream=createPublicTextStream();
      const first=stream.push(input.slice(0,offset));
      assert.doesNotMatch(first,/operator|private|adapters/,'early leak at '+offset);
      assert.equal(first+stream.push(input.slice(offset))+stream.push('',true),publicText(input),token+' at '+offset);
    }
  }
});

test('all accepted historical brand spellings agree between incremental and durable text',()=>{
  for(const token of ['DeepSeek-Harness','DeepSeek_Harness','DeepSeek  Harness','DeepSeek\tHarless']){
    const input='我是 '+token+'。继续';
    for(let offset=1;offset<input.length;offset++){
      const stream=createPublicTextStream();
      assert.equal(stream.push(input.slice(0,offset))+stream.push(input.slice(offset))+stream.push('',true),publicText(input),token+' at '+offset);
    }
  }
});

test('safe public URLs keep their left-boundary context when the provider splits a token',()=>{
  for(const input of ['参考 https://example.org/home/docs。','下载 https://example.org/app/a.pdf。',
    '论文 https://example.org/Users/researcher/paper.pdf。']){
    assert.equal(publicText(input),input);
    for(let offset=1;offset<input.length;offset++){
      const stream=createPublicTextStream();
      assert.equal(stream.push(input.slice(0,offset))+stream.push(input.slice(offset))+stream.push('',true),input,'split at '+offset);
    }
  }
});

test('native tool results and tool-call events retain their event identity and original journal',()=>{
  const original={type:'tool/result',seq:3,time:12,surfaceOp:'append',data:{turn:0,step:1,message:{
    id:'tool-result-1',role:'user',source:{kind:'tool',callId:'call-1'},
    content:[{type:'text',text:'read failed at /home/operator/source/main.py'}]},
    error:{code:'ENOENT',message:'Cannot open /home/operator/source/main.py'}}};
  const before=JSON.stringify(original),shown=publicSessionEvent(original);
  assert.equal(JSON.stringify(original),before);
  assert.equal(shown.data.message.source.callId,'call-1');
  assert.equal(shown.data.message.role,'user');
  assert.equal(shown.seq,3);assert.equal(shown.surfaceOp,'append');
  assert.doesNotMatch(JSON.stringify(shown),/operator/);
  const call={type:'tool/call',seq:2,time:11,data:{turn:0,step:1,callId:'call-1',name:'read_file',arguments:JSON.stringify({path:'/home/operator/source/main.py'})}};
  const safe=publicSessionEvent(call);
  assert.equal(safe.data.callId,'call-1');assert.equal(safe.data.name,'read_file');
  assert.equal(JSON.parse(safe.data.arguments).path,'〔内部路径已隐藏〕');
});

test('native control jobs are projected while queue inputs and model selections remain exact',async()=>{
  const queue={sessionId:'s',content:[{type:'text',text:'解释 DSH 和 /home/my-own/file.txt'}]};
  const projections={s:{asOfSeq:2,values:{modelSelection:{next:{provider:'deepseek-official',model:'deepseek-flash',reasoningEffort:'high'}}}}};
  const baseline={type:'baseline',value:{queues:{s:[queue]},jobs:{s:{error:'failed /home/operator/app'}},projections}};
  const controller={async *control(){yield baseline;yield {type:'jobs',jobs:{s:{error:'DSH /home/operator/app'}}};}};
  const dispose=protectPublicSessionOutput(controller),frames=[];
  try{for await(const frame of controller.control())frames.push(frame);}finally{dispose();}
  assert.equal(frames[0].value.queues,baseline.value.queues);
  assert.equal(frames[0].value.projections,baseline.value.projections);
  assert.doesNotMatch(JSON.stringify(frames.map(frame=>frame.value?.jobs??frame.jobs)),/operator|DSH/);
  assert.match(baseline.value.jobs.s.error,/operator/);
});

test('reconnect preserves original compact event count, dense index and download receipts',async()=>{
  const acc=new AssistantStreamAccumulator();
  acc.push({time:1,chunk:{type:'text-delta',index:0,text:'源码 file:///ho'}});
  const snapshot={type:'snapshot',header:{id:'s',version:1,cwd:'/home/operator'},cursor:4,hasMore:false,records:[],
    assistantStream:{revision:3,activeAttempt:{attemptId:'a',nextIndex:1,stream:acc.snapshot()}}};
  const delta={type:'assistant-stream',frame:{type:'chunk',attemptId:'a',revision:4,index:1,time:2,chunk:{type:'text-delta',index:0,text:'me/operator/source.py。'}}};
  const controller={async *follow(){yield snapshot;yield delta;}};
  const dispose=protectPublicSessionOutput(controller),frames=[];
  try{for await(const frame of controller.follow({sessionId:'s'}))frames.push(frame);}finally{dispose();}
  const initial=expandAssistantStream(frames[0].assistantStream.activeAttempt.stream);
  assert.equal(initial.length,1);assert.equal(frames[0].assistantStream.activeAttempt.nextIndex,1);
  assert.equal(frames[1].frame.index,1);assert.equal(frames[1].frame.revision,4);
  assert.equal(initial[0].chunk.text+frames[1].frame.chunk.text,publicText('源码 file:///home/operator/source.py。'));
  const task={status:'completed',answer:'GeneLoop /home/operator/result',rating:{score:5,task_id:'task-1'},
    artifacts:[{id:'artifact-1',name:'my-file.pdf',sha256:'abcd',receiptId:'receipt-1',download:'/tasks/t/artifacts/a'}]};
  const visible=publicTaskView(task);
  assert.equal(visible.rating,task.rating);assert.equal(visible.artifacts,task.artifacts);
});

test('paired step messages and paged trace apply the same private tail boundary as the main answer',()=>{
  const original={status:'running',messages:[{id:'assistant-1',status:'streaming',text:'正在读取 /ho'}],
    trace:[{id:'trace-1',status:'running',kind:'assistant',text:'目录:/home/operator/work'}]};
  const live=publicTaskView(original);
  assert.equal(live.messages[0].text,'正在读取 ');assert.equal(live.trace[0].text,'目录:');
  assert.match(original.trace[0].text,/operator/);
  const page=publicTaskView({items:[{id:'trace-2',kind:'assistant',status:'completed',text:'file:///home/operator/work',cursor:2}]});
  assert.doesNotMatch(JSON.stringify(page),/operator/);assert.equal(page.items[0].cursor,2);
});
