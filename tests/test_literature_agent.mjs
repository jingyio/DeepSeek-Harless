import test from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { mkdirSync, writeFileSync, readFileSync, rmSync, mkdtempSync } from 'node:fs';
import { join } from 'node:path';
import { request } from 'node:http';
import { costOf, runWorkflow, redeliverJob, recoverJob, JOBS, ROOT, serve } from '../scenarios/literature-notes/agent.ts';
import { checkRetention } from '../scenarios/literature-notes/compare-source-changes.ts';
import { projectEvents, writeDecisionLog } from '../scenarios/literature-notes/decision-log.ts';
import { taskChecks, stageMetrics } from '../scenarios/literature-notes/run-phase-one.ts';
import { repairSelected } from '../scenarios/literature-notes/repair-selected.ts';

test('selected repair rejects empty or duplicate targets and invalid budgets before any source or paid operation', async () => {
  for (const [targets,budget] of [[[],3],[['a','a'],3],[['a'],0],[['a'],Infinity]])
    await assert.rejects(()=>repairSelected('unavailable-parent',targets,budget,true),/invalid selected repair/);
});

test('phase-one checks reject missing new papers and keep scientific quality pending', () => {
  const job={frame:{task:{sources:{papers:[{paper_id:'p'},{paper_id:'new'}]}}}};
  const evidence={draft:{papers:[{paper_id:'p',fields:[]}]},citation_checks:[],gaps:[]};
  assert.throws(()=>taskChecks(job,evidence),/corpus differs/);
  evidence.draft.papers.push({paper_id:'new',fields:[]});
  assert.equal(taskChecks(job,evidence).scientific_truth_certified,false);
  assert.equal(taskChecks(job,evidence).semantic_quality,'independent_source_check_pending');
});

test('phase-one stage metrics preserve failure and retry fees without attributing them to tools', () => {
  const rows=stageMetrics({stages:[{stage:'reading',exit_code:2,complete:true,cost:0.03,summaries:[
    {output_dir:'failed',upstream_requests:2,elapsed_seconds:10},
    {output_dir:'retry',upstream_requests:3,elapsed_seconds:12}]}]});
  assert.deepEqual(rows,[{stage:'reading',exit_code:2,cost_complete:true,requests:5,
    estimated_usd:0.03,harness_seconds:22,native_runs:['failed','retry']}]);
});

test('decision projection links call IDs, retains errors and never invents a reason or skip', () => {
  const event=(type,seq,data)=>({type,seq,time:'2026-10-11T01:00:00.000Z',data});
  const result=(id,isError,text)=>({message:{source:{kind:'tool',callId:id},content:[
    {type:'tool-result',toolCallId:id,isError,content:[{type:'text',text}]}]}});
  const events=[event('assistant/message',1,{usage:{inputTokens:123},message:{source:{kind:'model'},
    content:[{type:'text',text:'I will inspect the evaluation.'},{type:'reasoning',text:'not visible text'}]}}),
    event('tool/call',2,{callId:'a',name:'read_pdf_evidence_plan',arguments:JSON.stringify({windows:[{page:'2',start:0,length:500}]})}),
    event('tool/call',3,{callId:'b',name:'search_pdf_text',arguments:'{"query":"evaluation"}'}),
    event('tool/result',4,result('b',true,'selected windows exceed budget')),
    event('tool/result',5,result('a',false,'{"normalization":{"unique_chars":500}}')),
    event('tool/call',6,{callId:'missing',name:'prepare_pdf',arguments:'{}'})];
  const rows=projectEvents(events,{events_sha256:'original'});
  assert.equal(rows[0].stated_text,'I will inspect the evaluation.');
  assert.deepEqual(rows[0].usage,{inputTokens:123});
  assert.equal(rows[1].result_origin.seq,5);assert.equal(rows[1].normalization.unique_chars,500);
  assert.equal(rows[2].outcome,'error');assert.match(rows[2].error,/exceed/);
  assert.equal(rows[3].outcome,'missing_or_ambiguous_result');
  assert.ok(rows.every(r=>r.rationale_inferred===false));
  assert.ok(rows.slice(1).every(r=>r.model_bypass_inferred===false));
  events[1].time=1000;events[4].time=1123;
  assert.equal(projectEvents(events,{})[1].elapsed_ms,123);
});

test('private log preserves the native request ledger including failure fees and reports missing history',()=>{
  const run=join(ROOT,'.local/runs',randomUUID()),directory=join(JOBS,randomUUID());
  mkdirSync(run,{recursive:true});mkdirSync(directory,{recursive:true});
  const requests=[{request_id:1,response_status:429,observed_peak_usd:0},
    {request_id:2,response_status:200,observed_peak_usd:0.003,response_usage:{prompt_cache_hit_tokens:123}}];
  writeFileSync(join(run,'agent-events.jsonl'),'');
  writeFileSync(join(run,'cost-ledger.jsonl'),requests.map(r=>JSON.stringify(r)).join('\n'));
  const job={id:'fixture',frame:{question:'fixture'},status:'error',stages:[{stage:'reading',summaries:[{output_dir:run}]}],
    model_requests:2,accounted_usd:0.003,cost_complete:true,workflow_decisions:[{action:'stop_with_error'}]};
  try {
    const info=writeDecisionLog(directory,job),report=JSON.parse(readFileSync(info.path,'utf8'));
    assert.deepEqual(report.runs[0].requests,requests);assert.equal(report.additional_model_requests,0);
    assert.equal(report.synthetic_native_events,false);assert.equal(report.eligible_for_motif_training,false);
    job.stages.push({stage:'repair',summaries:[{output_dir:join(ROOT,'.local/runs','missing')} ]});
    assert.equal(writeDecisionLog(directory,job).complete,false);
  } finally {rmSync(run,{recursive:true});rmSync(directory,{recursive:true});}
});

test('source-change result check rejects changed statements, citations and missing retained fields',()=>{
  const before={draft:{papers:[{paper_id:'p',fields:[{name:'method',statement:'bound fact',citations:[{source_id:'s',quote_id:'q'}]}]}]}};
  assert.equal(checkRetention(before,structuredClone(before),['claim:p:method']),1);
  for(const mutation of ['statement','citation','missing']){
    const after=structuredClone(before);
    if(mutation==='statement')after.draft.papers[0].fields[0].statement='different';
    if(mutation==='citation')after.draft.papers[0].fields[0].citations[0].quote_id='other';
    if(mutation==='missing')after.draft.papers[0].fields=[];
    assert.throws(()=>checkRetention(before,after,['claim:p:method']),/retained field changed/);
  }
});

test('retain known failure expenses while missing accounting stops later calls', async () => {
  assert.deepEqual(costOf({stdout:'{"output_dir":"x","budget_accounted_usd":0.01}\n{"output_dir":"y"}',code:2,stderr:''}),
    {summaries:[{output_dir:'x',budget_accounted_usd:0.01},{output_dir:'y'}],cost:0.01,complete:false});
  const calls=[];
  const exec=async(args,input)=>{calls.push(args);return input
    ? {code:0,stdout:JSON.stringify({unique:randomUUID()}),stderr:''}
    : {code:2,stdout:'{"output_dir":"x","upstream_requests":2,"budget_accounted_usd":0.014}',stderr:'bounded failure'};};
  const job=await runWorkflow({call_model:true},exec);
  try {assert.equal(job.status,'error');assert.equal(job.accounted_usd,0.014);assert.equal(job.model_requests,2);
    assert.equal(calls.length,2);assert.equal(job.cost_complete,true);} finally {rmSync(join(JOBS,job.id),{recursive:true});}
});

test('default preview never enables a paid call',async()=>{
  const calls=[];const exec=async(args,input)=>{calls.push(args);return {code:0,stdout:input?'{"fixture":true}':'{}',stderr:''};};
  const job=await runWorkflow({},exec);
  try {assert.equal(job.options.repair_rounds,2);assert.equal(job.options.repair_scope,'support_audit');assert.equal(job.status,'preview');assert.equal(job.accounted_usd,0);assert.equal(job.model_requests,0);
    assert.equal(calls.flat().includes('--call-model'),false);}finally{rmSync(join(JOBS,job.id),{recursive:true});}
});

test('missing ledger halts automatic review',async()=>{
  let calls=0;const exec=async(args,input)=>{calls++;return {code:0,stdout:input?JSON.stringify({unique:randomUUID()}):'{"pdf_delivery":{}}',stderr:''};};
  const job=await runWorkflow({call_model:true},exec);
  try{assert.equal(job.status,'error');assert.equal(job.cost_complete,false);assert.equal(calls,2);}
  finally{rmSync(join(JOBS,job.id),{recursive:true});}
});

test('identical source cache keeps automatic unverified quality and has zero model calls',async()=>{
  mkdirSync(JOBS,{recursive:true});const id=randomUUID(),directory=join(JOBS,id);mkdirSync(directory);
  const frame={unique:randomUUID()};
  writeFileSync(join(directory,'job.json'),JSON.stringify({id,status:'delivered',frame,quality:'automatic_model_reviewed_unverified',
    options:{model_review:true,repair_rounds:1},created_at:new Date().toISOString(),evidence_sha256:'fixture'}));
  for(const file of ['evidence.json','source-snapshot.json','review-cards.json'])writeFileSync(join(directory,file),'{}');
  writeFileSync(join(directory,'research-notes.md'),'Synthetic protocol artifact.');
  let modelCalls=0;const exec=async(args,input)=>{if(!input)modelCalls++;return {code:0,stdout:JSON.stringify(input?.operation==='capture'?frame:{source_replay:true}),stderr:''};};
  let job;
  try{job=await runWorkflow({call_model:true,parent_job:id,repair_rounds:1},exec);assert.equal(job.status,'cached');
    assert.equal(job.quality,'automatic_model_reviewed_unverified');assert.equal(job.human_review_required,false);assert.equal(job.model_requests,0);assert.equal(modelCalls,0);}
  finally{rmSync(directory,{recursive:true});if(job)rmSync(join(JOBS,job.id),{recursive:true});}
});

test('source replay rejection forces a new run and preserves failure expenses',async()=>{
  const id=randomUUID(),directory=join(JOBS,id);mkdirSync(directory,{recursive:true});const frame={unique:randomUUID()};
  writeFileSync(join(directory,'job.json'),JSON.stringify({id,status:'needs_review',frame,options:{model_review:true,repair_rounds:1}}));
  const exec=async(args,input)=>input?.operation==='capture'?{code:0,stdout:JSON.stringify(frame),stderr:''}
    :input?{code:2,stdout:'',stderr:'source changed'}:{code:2,stdout:'{"output_dir":"x","budget_accounted_usd":0.02}',stderr:''};
  let job;try{job=await runWorkflow({call_model:true,parent_job:id,repair_rounds:1},exec);assert.equal(job.cache_rejected,true);
    assert.equal(job.status,'error');assert.equal(job.accounted_usd,0.02);}
  finally{rmSync(directory,{recursive:true});if(job)rmSync(join(JOBS,job.id),{recursive:true});}
});

test('only explicit deterministic zero-work receipt is zero-cost accounting',()=>{
  const zero={scope:'deterministic reuse of previously source-checked artifacts',model_requests:0,budget_accounted_usd:0,
    receipt:{reviewed_field_count:0,retained_field_count:10}};
  assert.equal(costOf({stdout:JSON.stringify(zero)}).complete,true);
  assert.equal(costOf({stdout:'{"model_requests":0,"budget_accounted_usd":0}'}).complete,false);
});

test('local UI rejects foreign Host, origin and missing session; GET has no paid effects',async()=>{
  const server=await serve(0);const port=server.address().port,base='http://127.0.0.1:'+port;
  try{
    const page=await fetch(base);assert.equal(page.status,200);const html=await page.text();
    assert.match(html,/文献工作台/);assert.doesNotMatch(html,/data-approve|synthesis-reviewed|批准当前稿|待人工核对/);assert.match(html,/id="paid" type="checkbox">/);
    const foreignHost = await new Promise((accept,reject)=>{
      const req=request(base,{headers:{Host:'attacker.test'}},res=>{res.resume();accept(res.statusCode);});
      req.on('error',reject);req.end();
    });
    assert.equal(foreignHost,403);
    assert.equal((await fetch(base+'/api/run',{method:'POST',headers:{Origin:base},body:'{}'})).status,403);
    const token=html.match(/const token='([^']+)'/)[1];
    assert.equal((await fetch(base+'/api/run',{method:'POST',headers:{Origin:'https://attacker.test','X-Agent-Session':token},body:'{}'})).status,403);
    assert.equal((await fetch(base+'/api/jobs/not-an-id/notes')).status,404);
  }finally{await new Promise(accept=>server.close(accept));}
});

test('streaming requests cannot both pass the busy guard',async()=>{
  const server=await serve(0),base='http://127.0.0.1:'+server.address().port;
  const empty=mkdtempSync(join(ROOT,'.local/agent-empty-fixture-'));
  try{
    const html=await (await fetch(base)).text(),token=html.match(/const token='([^']+)'/)[1];
    let count=0,firstServerRequest,headersReady;
    const ready=new Promise(accept=>{headersReady=accept;});
    server.on('request',req=>{if(req.url==='/api/run'){count++;if(count===1)firstServerRequest=req;if(count===2)headersReady();}});
    function streaming(){let req;const response=new Promise((accept,reject)=>{
      req=request(base+'/api/run',{method:'POST',headers:{Origin:base,'X-Agent-Session':token}},res=>{
        res.resume();res.on('end',()=>accept(res.statusCode));});req.on('error',reject);
    });req.write(JSON.stringify({papers_dir:empty,call_model:false}).slice(0,-1));return {req,response};}
    const one=streaming(),two=streaming();await ready;
    const firstEnded=new Promise(accept=>firstServerRequest.once('end',()=>setImmediate(accept)));
    one.req.end('}');await firstEnded;two.req.end('}');
    assert.equal(await two.response,409);
    assert.equal(await one.response,400); // empty input rejected before any model or key load
  }finally{rmSync(empty,{recursive:true});await new Promise(accept=>server.close(accept));}
});


for (const gaps of [0, 1]) test('automatic delivery needs no human approval, gaps='+gaps, async()=>{
  const frame={unique:randomUUID()}, operations=[];
  const exec=async(args,input)=>{
    if(input){operations.push(input.operation);return {code:0,stderr:'',stdout:JSON.stringify(
      input.operation==='capture'?frame:{research_quality:input.review_path?'automatic_model_reviewed_unverified':'automatic_source_validated_unverified',
        gap_count:gaps,numeric_gap_count:0,human_review_required:false,delivery_policy:'automatic_v1'})};}
    return {code:0,stderr:'',stdout:JSON.stringify({output_dir:'fixture-run',budget_accounted_usd:0.01,upstream_requests:2})+'\n'+
      JSON.stringify(args[0].endsWith('review-pdf.py')?{claim_review:'fixture-review'}:{pdf_delivery:{status:'completed'}})};
  };
  const job=await runWorkflow({call_model:true,force_refresh:true,repair_rounds:0},exec);
  try{assert.equal(job.status,gaps?'delivered_with_gaps':'delivered');
    assert.equal(job.quality,'automatic_model_reviewed_unverified');assert.equal(job.human_review_required,false);
    assert.equal(job.model_requests,4);assert.equal(job.accounted_usd,0.02);assert.equal(operations.includes('approve'),false);}
  finally{rmSync(join(JOBS,job.id),{recursive:true});}
});

test('legacy policy redelivery validates source and keeps old history',async()=>{
  const id=randomUUID(),directory=join(JOBS,id);mkdirSync(directory,{recursive:true});
  const frame={task_sha256:'task',parser_sha256:'parser',contract_sha256:'contract',workflow_sha256:'old'};
  const old={id,status:'needs_review',quality:'human_review_required',frame,options:{papers_dir:'testpdf',question:'fixture'},accounted_usd:0.02};
  writeFileSync(join(directory,'job.json'),JSON.stringify(old));
  const exec=async(args,input)=>({code:0,stderr:'',stdout:JSON.stringify(input.operation==='capture'?{...frame,workflow_sha256:'new'}:
    {research_quality:'automatic_source_validated_unverified',gap_count:0,numeric_gap_count:0,human_review_required:false})});
  let job;try{job=await redeliverJob(id,exec);assert.equal(job.status,'delivered');assert.equal(job.model_requests,0);
    assert.equal(job.accounted_usd,0);assert.equal(job.frame.workflow_sha256,'new');
    assert.equal(JSON.parse((await import('node:fs')).readFileSync(join(directory,'job.json'))).status,'needs_review');
    await assert.rejects(redeliverJob(id,async()=>({code:0,stderr:'',stdout:JSON.stringify({...frame,parser_sha256:'changed'})})),/需要重新运行/);}
  finally{rmSync(directory,{recursive:true});if(job)rmSync(join(JOBS,job.id),{recursive:true});}
});


test('automatic incremental audit selects changed fields and index metadata cannot overwrite expenses or quality',async()=>{
  const id=randomUUID(),directory=join(JOBS,id),native=join(directory,'native'),frame={unique:randomUUID()};
  mkdirSync(native,{recursive:true});writeFileSync(join(native,'agent-events.jsonl'),'');
  for(const name of ['incremental-evidence.json','input-snapshot.json'])writeFileSync(join(native,name),'{}');
  writeFileSync(join(directory,'automatic-dependencies.json'),'{}');
  writeFileSync(join(directory,'job.json'),JSON.stringify({id,status:'delivered',frame,quality:'automatic_model_reviewed_unverified',options:{model_review:true}}));
  let selected,job;
  const exec=async(args,input)=>{
    if(input){if(input.operation==='capture')return {code:0,stderr:'',stdout:JSON.stringify(frame)};
      if(input.operation==='repair_plan'){selected=input.target_claim_ids;return {code:0,stderr:'',stdout:JSON.stringify({claim_ids:['changed'],input_directory:'fixture'})};}
      if(input.operation==='index_automatic')return {code:0,stderr:'',stdout:JSON.stringify({index_model_requests:0,model_requests:999,accounted_usd:999,research_quality:'wrong'})};
      return {code:0,stderr:'',stdout:JSON.stringify({incremental_claim_ids:['changed'],gap_count:0,numeric_gap_count:0,research_quality:'automatic_model_reviewed_unverified'})};}
    const repair=args[0].endsWith('repair-pdf.py');if(!repair)assert.ok(args[0].endsWith('run-incremental.py'));
    return {code:0,stderr:'',stdout:JSON.stringify({output_dir:native,budget_accounted_usd:0.01,upstream_requests:2})+'\n'+JSON.stringify(repair
      ?{claim_repair:native,receipt:{unresolved_claim_ids:[]}}
      :{incremental_directory:native,receipt:{retained_field_count:10,reviewed_field_count:5}})};
  };
  try{job=await runWorkflow({parent_job:id,call_model:true,force_refresh:true},exec);
    assert.equal(job.status,'delivered',job.error);assert.deepEqual(selected,['changed']);assert.equal(job.model_requests,4);
    assert.equal(job.accounted_usd,0.02);assert.equal(job.quality,'automatic_model_reviewed_unverified');assert.equal(job.verified_skips,0);}
  finally{rmSync(directory,{recursive:true});if(job)rmSync(join(JOBS,job.id),{recursive:true});}
});

test('source removal rechecks global synthesis even when no field requires repair',async()=>{
  const id=randomUUID(),directory=join(JOBS,id),native=join(directory,'native'),frame={unique:randomUUID()};
  mkdirSync(native,{recursive:true});writeFileSync(join(native,'agent-events.jsonl'),'');
  for(const name of ['incremental-evidence.json','input-snapshot.json'])writeFileSync(join(native,name),'{}');
  writeFileSync(join(directory,'automatic-dependencies.json'),'{}');
  writeFileSync(join(directory,'job.json'),JSON.stringify({id,status:'delivered',frame,options:{model_review:true}}));
  let syntheses=0,job;
  const exec=async(args,input)=>{
    if(input){
      const data=input.operation==='capture'?frame:input.operation==='repair_plan'?{claim_ids:[]}:
        input.operation==='synthesis_plan'?{claim_ids:[],input_directory:'synthesis-fixture',input_sha256:'frozen'}:
        {incremental_claim_ids:[],incremental_synthesis_requires_review:true,claim_count:10,gap_count:0,numeric_gap_count:0};
      return {code:0,stderr:'',stdout:JSON.stringify(data)};
    }
    const repair=args[0].endsWith('repair-pdf.py');if(repair){syntheses++;assert.ok(args.includes('synthesis-fixture'));}
    return {code:0,stderr:'',stdout:JSON.stringify({output_dir:native,budget_accounted_usd:0.01,upstream_requests:2})+'\n'+JSON.stringify(repair
      ?{claim_repair:native,receipt:{unresolved_claim_ids:[]}}
      :{incremental_directory:native,receipt:{retained_field_count:10,reviewed_field_count:0}})};
  };
  try{job=await runWorkflow({parent_job:id,call_model:true,force_refresh:true},exec);
    assert.equal(job.status,'delivered',job.error);assert.equal(syntheses,1);
    assert.equal(job.model_requests,4);assert.equal(job.accounted_usd,0.02);assert.equal(job.synthesis_result.retained_field_count,10);}
  finally{rmSync(directory,{recursive:true});if(job)rmSync(join(JOBS,job.id),{recursive:true});}
});

for (const noWork of [false,true]) test('resume targets only gaps and no-work needs no model, empty='+noWork,async()=>{
  const id=randomUUID(),directory=join(JOBS,id),frame={task_sha256:'t',parser_sha256:'p',contract_sha256:'c',unique:randomUUID()};
  mkdirSync(directory,{recursive:true});
  writeFileSync(join(directory,'job.json'),JSON.stringify({id,status:'delivered_with_gaps',frame,options:{model_review:true},source_run:'original'}));
  let calls=0,planned;
  const exec=async(args,input)=>{
    if(input){if(input.operation==='capture')return {code:0,stderr:'',stdout:JSON.stringify(frame)};
      if(input.operation==='repair_plan'){planned=input;return {code:0,stderr:'',stdout:JSON.stringify({claim_ids:noWork?[]:['gap'],input_directory:'fixture',scope:input.scope})};}
      return {code:0,stderr:'',stdout:JSON.stringify({gap_count:0,numeric_gap_count:0,research_quality:'automatic_model_reviewed_unverified'})};}
    calls++;assert.ok(args[0].endsWith('repair-pdf.py'));
    return {code:0,stderr:'',stdout:'{"output_dir":"fixture","budget_accounted_usd":0.01,"upstream_requests":2}\n'+JSON.stringify({claim_repair:'fixture',receipt:{unresolved_claim_ids:[]}})};
  };
  let job;
  try{job=await runWorkflow({parent_job:id,repair_only:true,call_model:true},exec);
    assert.equal(job.status,'delivered');assert.equal(planned.scope,'unresolved_claims_only');assert.equal(planned.parent_job,directory);
    assert.equal(calls,noWork?0:1);assert.equal(job.model_requests,noWork?0:2);assert.equal(job.verified_skips,0);}
  finally{rmSync(directory,{recursive:true});if(job)rmSync(join(JOBS,job.id),{recursive:true});}
});

for (const staysUnresolved of [false,true]) test('bounded repair reviews all then only unresolved claims, unresolved='+staysUnresolved,async()=>{
  const frame={unique:randomUUID()},calls=[];let repairCalls=0;
  const exec=async(args,input)=>{
    if(input){calls.push(input.operation);if(input.operation==='capture')return {code:0,stderr:'',stdout:JSON.stringify(frame)};
      if(input.operation==='repair_plan')return {code:0,stderr:'',stdout:JSON.stringify({input_directory:'fixture',input_sha256:'fixture',
        claim_ids:input.round_number===1?['a','b']:['a'],scope:input.round_number===1?'all_claim_audit':'unresolved_claims_only'})};
      return {code:0,stderr:'',stdout:JSON.stringify({research_quality:'automatic_model_reviewed_unverified',gap_count:staysUnresolved?1:0,numeric_gap_count:0})};}
    if(args[0].endsWith('repair-pdf.py')){repairCalls++;return {code:0,stderr:'',stdout:'{"output_dir":"fixture","budget_accounted_usd":0.01,"upstream_requests":2}\n'+
      JSON.stringify({claim_repair:'fixture',receipt:{unresolved_claim_ids:staysUnresolved?['a']:[],changed_claim_count:1}})};}
    return {code:0,stderr:'',stdout:'{"output_dir":"fixture","budget_accounted_usd":0.01,"upstream_requests":2}\n'+JSON.stringify(
      args[0].endsWith('review-pdf.py')?{claim_review:'fixture'}:{pdf_delivery:{status:'completed'}})};
  };
  const job=await runWorkflow({call_model:true,force_refresh:true,repair_rounds:2},exec);
  try{assert.equal(job.status,staysUnresolved?'delivered_with_gaps':'delivered');
    assert.equal(repairCalls,staysUnresolved?3:1);assert.equal(job.repair_stop_reason,staysUnresolved?'round_limit_reached':'no_unresolved_claims');
    assert.equal(job.model_requests,staysUnresolved?8:4);assert.equal(job.human_review_required,false);
    if(staysUnresolved)assert.equal(job.repair_rounds[1].target_count,1);}
  finally{rmSync(join(JOBS,job.id),{recursive:true});}
});

test('repair failure retains actual expense and stops later rounds',async()=>{
  const frame={unique:randomUUID()};let repairs=0;
  const exec=async(args,input)=>{if(input)return {code:0,stderr:'',stdout:JSON.stringify(input.operation==='capture'?frame:
    input.operation==='repair_plan'?{claim_ids:['a'],input_directory:'fixture'}:{gap_count:0,numeric_gap_count:0})};
    if(args[0].endsWith('repair-pdf.py')){repairs++;return {code:2,stderr:'failed',stdout:'{"output_dir":"failed","budget_accounted_usd":0.03,"upstream_requests":3}'};}
    return {code:0,stderr:'',stdout:'{"output_dir":"fixture","budget_accounted_usd":0.01,"upstream_requests":2}\n'+
      JSON.stringify(args[0].endsWith('review-pdf.py')?{claim_review:'fixture'}:{pdf_delivery:{}})};};
  const job=await runWorkflow({call_model:true,force_refresh:true,repair_rounds:2},exec);
  try{assert.equal(job.status,'delivered_with_gaps');assert.equal(job.repair_stop_reason,'stage_failed');assert.match(job.repair_warning,/上一份/);assert.equal(job.repair_rounds[0].status,'failed');assert.equal(repairs,1);assert.equal(job.accounted_usd,0.04);assert.equal(job.model_requests,5);}
  finally{rmSync(join(JOBS,job.id),{recursive:true});}
});


test('default claim audit replaces duplicate whole-draft review',async()=>{
  const frame={unique:randomUUID()},paid=[];
  const exec=async(args,input)=>{if(input)return {code:0,stderr:'',stdout:JSON.stringify(input.operation==='capture'?frame:
    input.operation==='repair_plan'?{claim_ids:['a'],input_directory:'fixture'}:{gap_count:0,numeric_gap_count:0})};
    paid.push(args[0]);return {code:0,stderr:'',stdout:'{"output_dir":"fixture","budget_accounted_usd":0.01,"upstream_requests":1}\n'+
    JSON.stringify(args[0].endsWith('repair-pdf.py')?{claim_repair:'fixture',receipt:{unresolved_claim_ids:[]}}:{pdf_delivery:{}})};};
  const job=await runWorkflow({call_model:true,force_refresh:true},exec);
  try{assert.equal(job.status,'delivered');assert.equal(paid.length,2);
    assert.equal(paid.some(p=>p.endsWith('review-pdf.py')),false);}
  finally{rmSync(join(JOBS,job.id),{recursive:true});}
});

test('offline proposal recovery keeps native provenance and historical expense separate',async()=>{
  const id=randomUUID(),directory=join(JOBS,id);mkdirSync(directory,{recursive:true});
  const frame={task_sha256:'task',parser_sha256:'parser',contract_sha256:'contract'};
  const old={id,status:'delivered_with_gaps',cost_complete:true,repair_stop_reason:'stage_failed',active_repair_round:1,
    frame,options:{papers_dir:'testpdf',question:'fixture'},model_requests:4,accounted_usd:0.009,
    stages:[{stage:'repair-1',summaries:[{output_dir:'native-fixture'}]}]};
  writeFileSync(join(directory,'job.json'),JSON.stringify(old));
  const exec=async(args,input)=>input?{code:0,stderr:'',stdout:JSON.stringify(input.operation==='capture'?frame:
    {gap_count:1,numeric_gap_count:0,research_quality:'automatic_model_reviewed_unverified'})}:
    {code:0,stderr:'',stdout:JSON.stringify({claim_repair:'fixture',receipt_origin:'validated_model_final_json_recovery',
      model_call_enabled:false,model_requests:0,budget_accounted_usd:0,receipt:{unresolved_claim_ids:['a']}})};
  let job;try{job=await recoverJob(id,exec);assert.equal(job.status,'delivered_with_gaps');assert.equal(job.accounted_usd,0);
    assert.equal(job.inherited_expense_usd,0.009);assert.equal(job.inherited_model_requests,4);assert.equal(job.verified_skips,0);
    await assert.rejects(recoverJob(id,async()=>({code:0,stderr:'',stdout:JSON.stringify({...frame,task_sha256:'drift'})})),/拒绝回收/);}
  finally{rmSync(directory,{recursive:true});if(job)rmSync(join(JOBS,job.id),{recursive:true});}
});

test('learned entries apply only to initial reading and first support audit; gaps and synthesis remain native',async()=>{
 const dir=mkdtempSync(join(ROOT,'.local/entry-agent-test-')),policy=join(dir,'policy.json');writeFileSync(policy,'{}');
 const seen=[],frame={unique:randomUUID()};let round=0;
 const exec=async(args,input)=>{
  if(input){if(input.operation==='capture')return {code:0,stderr:'',stdout:JSON.stringify(frame)};
   if(input.operation==='repair_plan')return {code:0,stderr:'',stdout:JSON.stringify({input_directory:'fixture',input_sha256:'fixture',claim_ids:['a'],
    scope:input.round_number===1?'claim_support_audit':'unresolved_claims_only'})};
   if(input.operation==='synthesis_plan')return {code:0,stderr:'',stdout:JSON.stringify({input_directory:'synthesis',claim_ids:[]})};
   return {code:0,stderr:'',stdout:JSON.stringify({gap_count:0,numeric_gap_count:0,claim_count:1})};}
  seen.push(args);if(args[0].endsWith('repair-pdf.py'))round++;
  return {code:0,stderr:'',stdout:JSON.stringify({output_dir:'fixture',budget_accounted_usd:.01,upstream_requests:2,
   entry_model_requests_bypassed_verified:args.includes('--entry-policy')?1:0})+'\n'+JSON.stringify(args[0].endsWith('repair-pdf.py')
   ?{claim_repair:'fixture',receipt:{unresolved_claim_ids:round===1?['a']:[],changed_claim_count:1}}
   :{pdf_delivery:{status:'preview'}})};
 };
 let job;
 try{job=await runWorkflow({call_model:true,force_refresh:true,reading_entry_policy:policy,claim_entry_policy:policy},exec);
  assert.equal(job.status,'delivered',job.error);assert.equal(seen.length,4);
  assert.ok(seen[0].includes('--entry-policy'));assert.ok(seen[1].includes('--entry-policy'));
  assert.ok(!seen[2].includes('--entry-policy'));assert.ok(!seen[3].includes('--entry-policy'));
  assert.equal(job.entry_verified_batches,2);assert.equal(job.model_requests,8);assert.equal(job.verified_skips,0);
 }finally{rmSync(dir,{recursive:true});if(job)rmSync(join(JOBS,job.id),{recursive:true});}
});

test('incremental entry policy reaches only the changed-field reading stage',async()=>{
 const id=randomUUID(),directory=join(JOBS,id),native=join(directory,'native'),frame={unique:randomUUID()};
 mkdirSync(native,{recursive:true});
 for(const name of ['incremental-evidence.json','input-snapshot.json','agent-events.jsonl'])writeFileSync(join(native,name),'{}');
 const policy=join(directory,'policy.json');writeFileSync(policy,'{}');writeFileSync(join(directory,'automatic-dependencies.json'),'{}');
 writeFileSync(join(directory,'job.json'),JSON.stringify({id,status:'delivered',frame,quality:'automatic_model_reviewed_unverified',options:{model_review:true}}));
 const seen=[];let job;
 const exec=async(args,input)=>{
  if(input){if(input.operation==='capture')return {code:0,stderr:'',stdout:JSON.stringify(frame)};
   if(input.operation==='repair_plan')return {code:0,stderr:'',stdout:JSON.stringify({claim_ids:['changed'],input_directory:'fixture',scope:'claim_support_audit'})};
   return {code:0,stderr:'',stdout:JSON.stringify({incremental_claim_ids:['changed'],gap_count:0,numeric_gap_count:0})};}
  seen.push(args);const repair=args[0].endsWith('repair-pdf.py');
  return {code:0,stderr:'',stdout:JSON.stringify({output_dir:native,budget_accounted_usd:.01,upstream_requests:2,entry_model_requests_bypassed_verified:repair?0:2})+'\n'+JSON.stringify(repair
   ?{claim_repair:native,receipt:{unresolved_claim_ids:[]}}:{incremental_directory:native,receipt:{retained_field_count:10,reviewed_field_count:5}})};
 };
 try{job=await runWorkflow({parent_job:id,call_model:true,force_refresh:true,incremental_entry_policy:policy},exec);
  assert.equal(job.status,'delivered',job.error);assert.ok(seen[0].includes(policy));assert.ok(!seen[1].includes('--entry-policy'));
  assert.equal(job.entry_verified_batches,2);assert.equal(job.model_requests,4);
 }finally{rmSync(directory,{recursive:true});if(job)rmSync(join(JOBS,job.id),{recursive:true});}
});

test('terminal policy reaches only first support audit and keeps upstream accounting separate',async()=>{
 const dir=mkdtempSync(join(ROOT,'.local/terminal-agent-test-')),policy=join(dir,'policy.json');writeFileSync(policy,'{}');
 const seen=[],frame={unique:randomUUID()};let round=0,job;
 const exec=async(args,input)=>{
  if(input){if(input.operation==='capture')return {code:0,stderr:'',stdout:JSON.stringify(frame)};
   if(input.operation==='repair_plan')return {code:0,stderr:'',stdout:JSON.stringify({input_directory:'fixture',input_sha256:'fixture',claim_ids:['a'],
    scope:input.round_number===1?'claim_support_audit':'unresolved_claims_only'})};
   if(input.operation==='synthesis_plan')return {code:0,stderr:'',stdout:JSON.stringify({input_directory:'synthesis',claim_ids:[]})};
   return {code:0,stderr:'',stdout:JSON.stringify({gap_count:0,numeric_gap_count:0,claim_count:1})};}
  seen.push(args);if(args[0].endsWith('repair-pdf.py'))round++;
  return {code:0,stderr:'',stdout:JSON.stringify({output_dir:'fixture',budget_accounted_usd:.01,upstream_requests:2,
   terminal_model_requests_bypassed_verified:args.includes('--terminal-policy')?1:0})+'\n'+JSON.stringify(args[0].endsWith('repair-pdf.py')
   ?{claim_repair:'fixture',receipt:{unresolved_claim_ids:round===1?['a']:[],changed_claim_count:1}}:{pdf_delivery:{status:'preview'}})};
 };
 try{job=await runWorkflow({call_model:true,force_refresh:true,claim_terminal_policy:policy},exec);
  assert.equal(job.status,'delivered',job.error);assert.equal(seen.length,4);
  assert.ok(!seen[0].includes('--terminal-policy'));assert.ok(seen[1].includes('--terminal-policy'));
  assert.ok(!seen[2].includes('--terminal-policy'));assert.ok(!seen[3].includes('--terminal-policy'));
  assert.equal(job.terminal_verified_batches,1);assert.equal(job.entry_verified_batches,0);assert.equal(job.model_requests,8);
  await assert.rejects(()=>runWorkflow({claim_terminal_policy:policy,reading_entry_policy:policy},exec),/组合尚未认证/);
 }finally{rmSync(dir,{recursive:true});if(job)rmSync(join(JOBS,job.id),{recursive:true});}
});
