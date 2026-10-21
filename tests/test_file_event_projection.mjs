import test from 'node:test';
import assert from 'node:assert/strict';
import {Session,interruptedTurnClosers} from '@deepseek-ai/dsh-session';
import {createAssistantMessage,createUserMessage,createToolResultMessage} from '@deepseek-ai/dsh-llm';
import {compactCheckpointSource} from '@deepseek-ai/dsh-compaction';
const options={skip:!process.features?.typescript};
test('file SDK display preserves native step, surface and call dependencies after parent history',options,async()=>{
 const {fileEventProjection}=await import('../src/adapters/file_event_projection.ts');
 const sdk=new Session('file-sdk'),parent=new Session('native-parent');
 parent.append('turn/start',{turn:1});parent.append('turn/end',{turn:1,reason:{kind:'completed'}});
 parent.append('turn/start',{turn:2});parent.append('user/message',createUserMessage({content:[{type:'text',text:'/file 盘点'}],source:{kind:'user',rpcId:'request'}}),{surfaceOp:'append'});
 sdk.append('turn/start',{turn:1});sdk.append('step/start',{turn:1,step:1});
 sdk.append('assistant/message',{turn:1,step:1,stream:[],message:createAssistantMessage({source:{provider:'deepseek-official',model:'deepseek-flash'},content:[{type:'tool-call',id:'call-1',name:'mcp__file_management__read_task',arguments:'{}'}]})},{surfaceOp:'append'});
 const call=sdk.append('tool/call',{turn:1,step:1,callId:'call-1',name:'mcp__file_management__read_task',arguments:'{}'});
 sdk.append('tool/result',{turn:1,step:1,message:{id:'result-1',role:'user',source:{kind:'tool',callId:'call-1'},content:[{type:'tool-result',toolCallId:'call-1',isError:false,content:[{type:'text',text:'{"diagnostic":true}'}]}]}},{surfaceOp:'append',sourceEventSeqs:[call.seq]});
 sdk.append('step/end',{turn:1,step:1});sdk.append('turn/end',{turn:1,reason:{kind:'completed'}});
 const original=JSON.stringify(sdk.snapshotEvents()),project=fileEventProjection(parent,2);
 for(const event of sdk.snapshotEvents())project(event);
 parent.append('turn/end',{turn:2,reason:{kind:'completed'}});
 const events=parent.snapshotEvents(),result=events.find(e=>e.type==='tool/result'),projectedCall=events.find(e=>e.type==='tool/call');
 assert.deepEqual(result.sourceEventSeqs,[projectedCall.seq]);assert.equal(result.surfaceOp,'append');
 assert.equal(result.data.turn,2);assert.equal(result.data.step,projectedCall.data.step);
 assert.deepEqual(new Session('restored-parent',events).snapshotEvents().slice(0,events.length),events);
 assert.deepEqual(interruptedTurnClosers(events),[]);assert.equal(JSON.stringify(sdk.snapshotEvents()),original);
});

function fixture(){
 const sdk=new Session('file-sdk'),parent=new Session('parent');
 parent.append('turn/start',{turn:1});parent.append('user/message',createUserMessage({content:[{type:'text',text:'用户原始要求'}],source:{kind:'user'}}),{surfaceOp:'append'});
 sdk.append('turn/start',{turn:1});
 return {sdk,parent};
}
function checkpoint(sdk,nodes,id='compact-file'){
 const range={start:nodes[0],end:nodes.at(-1)},start=sdk.append('compaction/start',{compactionId:id,trigger:'pressure',turn:1});
 const summary=sdk.append('compaction/summary',{compactionId:id,summary:'保留原始文件 SHA 与待完成操作。',shadowedSeqs:nodes,shadowedRange:range,
  shadowedTokenCount:123,provider:'deepseek-official',model:'deepseek-flash',usage:{inputTokens:30,outputTokens:12}});
 sdk.append('user/message',createUserMessage({content:[{type:'text',text:summary.data.summary}],source:compactCheckpointSource(id)}),
  {surfaceOp:{op:'replace',startSeq:range.start,endSeq:range.end},sourceEventSeqs:[start.seq,summary.seq,...nodes]});
 sdk.append('compaction/end',{compactionId:id,trigger:'pressure',turn:1});
}
function assistant(sdk,text){
 sdk.append('step/start',{turn:1,step:1});
 const event=sdk.append('assistant/message',{turn:1,step:1,stream:[],message:createAssistantMessage({content:[{type:'text',text}],source:{provider:'deepseek-official',model:'deepseek-flash'}})},{surfaceOp:'append'});
 sdk.append('step/end',{turn:1,step:1});return event;
}

test('native todo and request recovery preserve order, dependencies and incomplete status',options,async()=>{
 const {fileEventProjection}=await import('../src/adapters/file_event_projection.ts');const {sdk,parent}=fixture();
 sdk.append('step/start',{turn:1,step:1});
 sdk.append('todo/write',{todos:[{content:'核实文件版本',status:'in_progress'},{content:'交付结果',status:'pending'}]});
 sdk.append('assistant/attempt',{turn:1,step:1,stream:[],error:{code:'RATE_LIMIT'}});
 sdk.append('llm/retry',{turn:1,step:1,retryId:'r',retry:1,delayMs:1000,failure:{code:'RATE_LIMIT'}});
 sdk.append('llm/retry-started',{turn:1,step:1,retryId:'r',retry:1});sdk.append('step/end',{turn:1,step:1});
 const original=JSON.stringify(sdk.snapshotEvents()),project=fileEventProjection(parent,1);
 sdk.snapshotEvents().forEach(project);
 assert.deepEqual(parent.snapshotEvents().filter(e=>e.type==='todo/write').at(-1).data.todos,
  [{content:'核实文件版本',status:'in_progress'},{content:'交付结果',status:'pending'}]);
 assert.equal(parent.snapshotEvents().filter(e=>e.type==='llm/retry').length,1);
 assert.equal(parent.snapshotEvents().find(e=>e.type==='llm/retry-started').data.turn,1);
 assert.equal(JSON.stringify(sdk.snapshotEvents()),original);
});

test('SDK compaction never replaces the different parent user prompt or unmapped contract',options,async()=>{
 const {fileEventProjection}=await import('../src/adapters/file_event_projection.ts');const {sdk,parent}=fixture();
 const user=sdk.append('user/message',createUserMessage({content:[{type:'text',text:'generated SDK task contract and private references'}],source:{kind:'user'}}),{surfaceOp:'append'});
 const reply=assistant(sdk,'读取文件完成');checkpoint(sdk,[user.seq,reply.seq]);
 const project=fileEventProjection(parent,1);sdk.snapshotEvents().forEach(project);
 assert.deepEqual(parent.surface.nodes.map(seq=>parent.deriveEventMessage(parent.eventAt(seq))).map(m=>m.content[0].text),['用户原始要求','读取文件完成']);
 const observation=parent.snapshotEvents().find(e=>e.type==='geneloop/file-compaction');assert.equal(observation.data.projectedSurface,false);
 assert.equal(parent.snapshotEvents().filter(e=>e.type==='compaction/start').length,1);
 assert.equal(parent.snapshotEvents().filter(e=>e.type==='compaction/end').length,1);
 assert.equal(parent.snapshotEvents().filter(e=>e.type==='compaction/summary').length,0);
 assert.deepEqual(new Session('restore',parent.snapshotEvents()).surface.nodes,parent.surface.nodes);
});

test('only an exactly mapped contiguous history span receives the native checkpoint',options,async()=>{
 const {fileEventProjection}=await import('../src/adapters/file_event_projection.ts');
 for(const interfering of [false,true]){
  const {sdk,parent}=fixture(),project=fileEventProjection(parent,1);
  const first=assistant(sdk,'已确认原件 SHA256 abc'),firstEvents=sdk.snapshotEvents();firstEvents.forEach(project);
  if(interfering)parent.append('user/message',createUserMessage({content:[{type:'text',text:'不能被 SDK 摘要覆盖的新要求'}],source:{kind:'user'}}),{surfaceOp:'append'});
  const second=assistant(sdk,'待提交审批');sdk.snapshotEvents().slice(firstEvents.length).forEach(project);
  const count=sdk.snapshotEvents().length;checkpoint(sdk,[first.seq,second.seq]);sdk.snapshotEvents().slice(count).forEach(project);
  assert.equal(parent.snapshotEvents().find(e=>e.type==='geneloop/file-compaction').data.projectedSurface,!interfering);
  const replacements=parent.snapshotEvents().filter(e=>e.surfaceOp?.op==='replace');assert.equal(replacements.length,interfering?0:1);
  if(!interfering){const summary=parent.snapshotEvents().find(e=>e.type==='compaction/summary');
   assert.deepEqual(summary.data.shadowedSeqs,[...replacements[0].sourceEventSeqs.slice(2)]);
   assert.equal(parent.surface.nodes.length,2);assert.equal(parent.deriveEventMessage(parent.eventAt(parent.surface.nodes[0])).content[0].text,'用户原始要求');}
  assert.deepEqual(new Session('restored',parent.snapshotEvents()).surface.nodes,parent.surface.nodes);
 }
});
