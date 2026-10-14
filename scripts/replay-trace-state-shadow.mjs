/** Historical real-trace replay into an isolated report copy. No model or MCP. */
import {mkdtempSync,readFileSync,writeFileSync,rmSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {canonical} from '../src/adapters/paper_rsi_program.ts';
import {sha256} from '../src/adapters/paper_triage_validation.ts';
import {createStateShadowInterceptor} from '../src/adapters/dsh_trace_rsi_state_shadow.ts';

const run=resolve(process.argv[2]),libraryPath=resolve(process.argv[3]);
const config=JSON.parse(readFileSync(join(run,'config.json'),'utf8'));
const library=JSON.parse(readFileSync(libraryPath,'utf8'));
const events=readFileSync(join(run,'events.jsonl'),'utf8').trim().split('\n').map(JSON.parse)
  .filter(row=>(row.sessionId??row.session_id)===config.session_id).map(row=>row.event);
const decode=block=>{try{return JSON.parse(block.content.filter(c=>c.type==='text').map(c=>c.text).join(''));}catch{return null;}};
const first=events.filter(e=>e.type==='tool/result').flatMap(e=>e.data.message.content).map(decode).find(v=>v?.report);
if(!first)throw Error('initial_report_snapshot_required');
const work=mkdtempSync(join(resolve('.local'),'trace-state-replay-'));
function reportBytes(report,expected){
  const variants=[JSON.stringify(report,null,2)+'\n',JSON.stringify(report)+'\n',JSON.stringify(report)];
  const match=variants.find(s=>sha256(s)===expected);
  if(!match)throw Error('cannot_reconstruct_exact_historical_report_bytes');
  return match;
}
try {
  writeFileSync(join(work,'triage.json'),reportBytes(first.report,first.report_sha256),{mode:0o600});
  const replayConfig={...config,work,code_files:library.derived_library.code_files_sha256,shadow_library:libraryPath};
  const audit=[],interceptor=createStateShadowInterceptor({library,config:replayConfig,audit:r=>audit.push(r)});
  const calls=new Map(),results=new Map(),messages=[];
  for(const e of events){
    if(e.type==='assistant/message'){
      await interceptor.intercept(config.session_id,{tools:library.derived_library.tools},()=>null);
      messages.push(e.data.message.content);
    }else if(e.type==='tool/call')calls.set(e.data.callId,e.data);
    else if(e.type==='tool/result')for(const block of e.data.message.content){
      if(block.type!=='tool-result')continue;
      const exec=calls.get(block.toolCallId);if(!exec)throw Error('unpaired_historical_result');
      const value=decode(block),args=typeof exec.arguments==='string'?JSON.parse(exec.arguments):exec.arguments;
      const report=value?.report??(exec.name.endsWith('__write_report')?args.report:null);
      if(!block.isError&&report)writeFileSync(join(work,'triage.json'),reportBytes(report,value.report_sha256),{mode:0o600});
      if(!block.isError)results.set(block.toolCallId,value);
      interceptor.observe(config.session_id,{...exec,signal:null}, {isError:Boolean(block.isError||e.data.error),value:{content:block.content}});
    }
  }
  const boundaries=audit.filter(r=>['prediction','deferred'].includes(r.kind));
  if(boundaries.length!==messages.length)throw Error('replay_boundary_mismatch');
  const outcomes=boundaries.map((row,index)=>{
    const blocks=messages[index],toolCalls=blocks.filter(b=>b.type==='tool-call');
    const actual=toolCalls.map(b=>({tool:b.name,arguments:typeof b.arguments==='string'?JSON.parse(b.arguments):b.arguments}));
    const matches=row.prediction&&canonical(actual)===canonical(row.prediction.expected_tools)&&toolCalls.length===1&&
      canonical(results.get(toolCalls[0].id))===canonical(row.prediction.expected_result)&&
      audit.some(a=>a.kind==='shadow_result'&&a.request_ordinal===row.request_ordinal&&a.verified);
    return {request_ordinal:row.request_ordinal,kind:row.kind,reason:row.reason??null,state_features:row.state_features,
      prediction_present:Boolean(row.prediction),matched:Boolean(matches)};
  });
  const record={kind:'historical_replay_diagnostic',run_id:run.split('/').at(-1),
    events_sha256:sha256(readFileSync(join(run,'events.jsonl'))),state_library_sha256:sha256(readFileSync(libraryPath)),
    requests:messages.length,predictions:outcomes.filter(o=>o.prediction_present).length,
    matched:outcomes.filter(o=>o.matched).length,
    state_deferred:outcomes.filter(o=>o.reason==='learned_state_guard').length,
    actual_model_skips:0,new_model_requests:0,semantic_quality:'not_reviewed',outcomes};
  console.log(JSON.stringify(record));
}finally{rmSync(work,{recursive:true,force:true});}
