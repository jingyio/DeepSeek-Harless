import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,rmSync,realpathSync} from 'node:fs';
import {join,resolve,sep} from 'node:path';
import {tmpdir} from 'node:os';
import {bindReportAnswer,hasReportPlaceholders,REPORT_ANSWER_BINDING} from '../src/adapters/harless_report_answer.ts';
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
function fixture(){
 const root=mkdtempSync(join(tmpdir(),'report-answer-')),workspace=join(root,'work'),directory=join(workspace,'outputs/report/records');mkdirSync(directory,{recursive:true});
 const eventsPath=join(root,'task-events.jsonl'),events=[];
 const context={workspace,eventsPath,startedAt:new Date(1000).toISOString(),finishedAt:new Date(2000).toISOString()};
 function add({number=1,time=1500,estimate=1.34,passed=true,tool='mcp__research_report__build_evidence',isError=false}={}){
  const id='rra-evidence-'+String(number).padStart(32,'0'),path=join(directory,id+'.json');
  const values={estimate:{value:estimate,display:String(estimate)},ci_low:{value:1.27,display:'1.27'},ci_high:{value:1.42,display:'1.42'},p_value:{value:2.3e-12,display:'2.3e-12'},n:{value:12,display:'12'},outcome_unit:{value:'原始结局单位（未提供单位）',display:'原始结局单位（未提供单位）'}};
  const catalog=Object.fromEntries(Object.entries(values).map(([name,value])=>[name,{...value,token:'{{'+name+'}}',source:'verified_analysis.checked_metrics'}]));
  const record={id,kind:'evidence',workspace_id:'fixture-work',source_version:'source-a',payload:{passed,plan_id:'plan-a',verified_id:'rra-verified_analysis-'+'a'.repeat(32),available_placeholders:catalog}};
  writeFileSync(path,JSON.stringify(record));
  const receipt={ok:true,evidence_id:id,source_version:record.source_version,results:values,_provenance:{workspace_id:record.workspace_id,study_sha256:record.source_version,plan_id:record.payload.plan_id,record_path:realpathSync(path),record_sha256:sha(readFileSync(path))}};
  const callId='call-'+number;
  events.push({type:'tool/call',time,data:{name:tool,callId}},{type:'tool/result',time:time+1,data:{message:{content:[{type:'tool-result',toolCallId:callId,isError,content:[{type:'text',text:JSON.stringify(receipt)}]}]}}});
  writeFileSync(eventsPath,events.map(e=>JSON.stringify(e)).join('\n'));return{path,receipt,events};
 }
 return{root,context,add,close(){const path=resolve(root);assert.ok(path.startsWith(resolve(tmpdir())+sep)&&path.includes('report-answer-'));rmSync(path,{recursive:true,force:true});}};
}
test('Chat statistics bind only verified task values while original text and code examples remain unchanged',()=>{
 const f=fixture();try{
  f.add();const answer='斜率 {{estimate}}；CI [{{ci_low}}, {{ci_high}}]，p={{p_value}}，n={{n}}，单位 {{outcome_unit}}。\n`{{estimate}}` 是工具参数。\n```json\n{"value":"{{estimate}}"}\n```';
  const result=bindReportAnswer({...f.context,answer});
  assert.match(result.answer_display,/斜率 1\.34；CI \[1\.27, 1\.42\]，p=2\.3e-12，n=12/);
  assert.match(result.answer_display,/单位 原始结局单位（未提供单位）/);
  assert.match(result.answer_display,/`\{\{estimate\}\}` 是工具参数/);
  assert.ok(result.answer_display.includes('"value":"{{estimate}}"'));
  assert.equal(result.answer_binding.version,REPORT_ANSWER_BINDING);assert.equal(result.answer_binding.status,'bound');
  assert.equal(result.answer_binding.source_answer_sha256,sha(answer));assert.ok(answer.includes('斜率 {{estimate}}'));
  assert.equal(hasReportPlaceholders('`{{estimate}}`\n```\n{{n}}\n```'),false);
  assert.deepEqual(bindReportAnswer({...f.context,answer:'普通回复，没有模板值。'}),{});
 }finally{f.close();}
});
test('Missing, failed, other-tool and past/future receipts never supply statistical values',()=>{
 for(const settings of [{time:500},{time:2500},{passed:false},{isError:true},{tool:'mcp__untrusted__echo'}]){
  const f=fixture();try{
   f.add(settings);const value=bindReportAnswer({...f.context,answer:'estimate={{estimate}}'});
   assert.equal(value.answer_display,'estimate=【未绑定：estimate】');assert.equal(value.answer_binding.reason,'no_verified_task_evidence');
  }finally{f.close();}
 }
});
test('Changed evidence bytes, another account workspace and forged source metadata fail closed',()=>{
 const f=fixture(),other=fixture();try{
  const row=f.add();
  const foreign=bindReportAnswer({...f.context,workspace:other.context.workspace,answer:'{{estimate}}'});
  assert.equal(foreign.answer_binding.status,'unresolved');
  const record=JSON.parse(readFileSync(row.path,'utf8'));record.payload.available_placeholders.estimate.display='999';writeFileSync(row.path,JSON.stringify(record));
  assert.equal(bindReportAnswer({...f.context,answer:'{{estimate}}'}).answer_binding.status,'unresolved');
  f.add({number:2});const event=f.add({number:3}).events.at(-1);const receipt=JSON.parse(event.data.message.content[0].content[0].text);
  receipt._provenance.study_sha256='foreign-source';event.data.message.content[0].content[0].text=JSON.stringify(receipt);
  writeFileSync(f.context.eventsPath,JSON.stringify({type:'tool/call',time:1500,data:{name:'mcp__research_report__build_evidence',callId:'call-3'}})+'\n'+JSON.stringify(event));
  assert.equal(bindReportAnswer({...f.context,answer:'{{estimate}}'}).answer_binding.status,'unresolved');
 }finally{f.close();other.close();}
});
test('Multiple evidence plans stay ambiguous and unknown units are never guessed',()=>{
 const f=fixture();try{
  f.add();const one=bindReportAnswer({...f.context,answer:'{{estimate}} / {{invented_unit}}'});
  assert.equal(one.answer_display,'1.34 / 【未绑定：invented\\_unit】');assert.deepEqual(one.answer_binding.unresolved_tokens,['invented_unit']);
  f.add({number:2,estimate:9.99});const two=bindReportAnswer({...f.context,answer:'{{estimate}}'});
  assert.equal(two.answer_binding.reason,'ambiguous_task_evidence');assert.equal(two.answer_display,'【未绑定：estimate】');
 }finally{f.close();}
});
