/** Historical replay of exact write/edit operations, never evaluates programs. */
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createDeliveryChecker } from '../src/adapters/dsh_paper_delivery_check.ts';
import { sha256 } from '../src/adapters/paper_triage_validation.ts';
import { deliveryResponseClass } from './evaluate-paper-delivery-shadow.mjs';
const json=p=>JSON.parse(readFileSync(p,'utf8'));
const [runArg,outArg]=process.argv.slice(2);
const root=fileURLToPath(new URL('..',import.meta.url)),run=resolve(runArg??''),out=resolve(outArg??'');
if(!run.startsWith(join(root,'.local')+'/')||!out.startsWith(join(root,'.local')+'/'))throw Error('private run/output required');
const manifest=json(join(run,'manifest.json')),metrics=json(join(run,'metrics.json'));
if(manifest.delivery_check_mode!=='off'||!manifest.composite_evidence||metrics.status!=='completed'||
   !metrics.source_unchanged||!metrics.delivery_check_passed)throw Error('completed normal composite baseline required');
if(existsSync(out))throw Error('preserve previous replay');
const work=join(out,'work');mkdirSync(work,{recursive:true,mode:0o700});
const saved=json(join(run,'delivery-check-config.json')),config={...saved,work,mode:'shadow'};
const audit=[],checker=createDeliveryChecker(config,r=>audit.push(r));
const events=readFileSync(join(run,'session-events.jsonl'),'utf8').split('\n').filter(s=>s.trim()).map(JSON.parse)
  .filter(r=>r.session_id===manifest.session_id).map(r=>r.event);
const calls=new Map(),responses=[];let pending=null;
for(const event of events) {
  const d=event.data;
  if(event.type==='tool/call') {
    calls.set(d.callId,{name:d.name,callId:d.callId,arguments:typeof d.arguments==='string'?JSON.parse(d.arguments):d.arguments});
  } else if(event.type==='tool/result') {
    const id=d.message?.source?.callId,exec=calls.get(id),block=d.message?.content?.[0];
    if(!exec||block?.type!=='tool-result')continue;
    const result={isError:!!d.error||!!block.isError,value:{content:block.content},content:block.content};
    checker.observe(exec,result);
    if(!['write','edit'].includes(exec.name)||result.isError)continue;
    if(resolve(saved.work,exec.arguments.file_path)!==join(saved.work,'triage.json'))throw Error('out-of-scope historical write');
    const path=join(work,'triage.json');
    if(exec.name==='write')writeFileSync(path,exec.arguments.content,{mode:0o600});
    else {
      const text=readFileSync(path,'utf8'),old=exec.arguments.old_string,replacement=exec.arguments.new_string;
      if(typeof old!=='string'||!old||typeof replacement!=='string')throw Error('unsupported edit shape');
      const n=text.split(old).length-1;
      if(n!==1&&!exec.arguments.replace_all)throw Error('ambiguous or absent historical edit');
      writeFileSync(path,exec.arguments.replace_all?text.split(old).join(replacement):text.replace(old,()=>replacement),{mode:0o600});
    }
    await checker.after({...exec,arguments:{...exec.arguments,file_path:'triage.json'},signal:new AbortController().signal},
      result,async()=>({kind:'accept'}));
    pending=audit.at(-1);
  } else if(event.type==='assistant/message') {
    responses.push({ordinal:responses.length+1,classification:deliveryResponseClass(d.message.content,pending),
      check_status:pending?.status??null,checked_report_sha256:pending?.report_sha256??null});pending=null;
  }
}
const original=sha256(readFileSync(join(run,'work','triage.json'))),replayed=sha256(readFileSync(join(work,'triage.json')));
if(original!==replayed||responses.length!==metrics.actual_requests)throw Error('replay artifact or request boundary differs');
const passed=responses.filter(r=>r.classification==='closed_tool_continuation').length;
const repair=responses.filter(r=>r.classification==='deterministic_repair_feedback').length;
const result={kind:'historical_delivery_hook_replay',actual_historical_requests:metrics.actual_requests,
  new_model_requests:0,actual_requests_skipped:0,api_cost_usd:0,final_artifact_sha256_matches:true,
  automatic_checks:audit.filter(r=>r.kind==='paper_delivery_check').length,passed_check_opportunities:passed,
  repair_feedback_opportunities:repair,whole_request_opportunities:passed+repair,
  whole_request_fraction:(passed+repair)/metrics.actual_requests,rows:responses,
  qualification:'historical_replay_not_prospective_shadow_or_savings',semantic_quality:'not_reviewed',learned_motif:false,
  run_manifest_sha256:sha256(readFileSync(join(run,'manifest.json')))};
writeFileSync(join(out,'verification.json'),JSON.stringify(result,null,2)+'\n',{mode:0o600});
writeFileSync(join(out,'audit.json'),JSON.stringify(audit,null,2)+'\n',{mode:0o600});
process.stdout.write(JSON.stringify(result)+'\n');
