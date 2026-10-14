/** Whole-response opportunities for the engineered delivery hook, no API. */
import { readFileSync, writeFileSync, existsSync, readdirSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { classifyResponse } from './evaluate-citation-shadow.mjs';
import { sha256 } from '../src/adapters/paper_triage_validation.ts';
const json=p=>JSON.parse(readFileSync(p,'utf8'));
const lines=p=>readFileSync(p,'utf8').split('\n').filter(s=>s.trim()).map(JSON.parse);

export function deliveryResponseClass(content, check) {
  const repair=check?.status==='needs_repair'&&/^[a-f0-9]{64}$/.test(check.report_sha256??'')&&
    /^[a-f0-9]{64}$/.test(check.source_version??'');
  if(check?.status!=='passed'&&!repair)return 'no_valid_check';
  const kind=classifyResponse(content,[{tool:'check_paper_triage',arguments:{}}]);
  return repair&&kind==='closed_tool_continuation'?'deterministic_repair_feedback':kind;
}

export function evaluateDelivery(run) {
  const config=json(join(run,'manifest.json')),metrics=json(join(run,'metrics.json'));
  if(config.mode!=='shadow'||config.delivery_check_mode!=='shadow'||!config.composite_evidence||
      metrics.status!=='completed'||!metrics.output_coverage_valid||!metrics.source_unchanged||!metrics.delivery_check_passed)
    throw Error('completed source-bound delivery shadow required');
  const auditPath=join(run,'work/.local/paper-delivery-check.jsonl');
  const checks=new Map(lines(auditPath).filter(r=>r.kind==='paper_delivery_check'&&r.mode==='shadow'&&
    r.source_version===config.input_version).map(r=>[r.call_id,r]));
  const events=lines(join(run,'session-events.jsonl')).filter(r=>r.session_id===config.session_id).map(r=>r.event);
  const responses=[];let pending=null;
  for(const event of events) {
    if(event.type==='tool/result') {
      const d=event.data,b=d.message?.content?.[0];
      const check=checks.get(d.message?.source?.callId);
      if(check&&!d.error&&!b?.isError)pending=check;
    }else if(event.type==='assistant/message') {
      responses.push({ordinal:responses.length+1,classification:deliveryResponseClass(event.data.message.content,pending),
        checked_report_sha256:pending?.report_sha256??null});
      pending=null;
    }
  }
  const receiptCount=readdirSync(join(run,'requests')).filter(n=>/^\d+\.json$/.test(n)).length;
  if(receiptCount!==metrics.actual_requests||responses.length!==receiptCount)throw Error('request boundary count mismatch');
  const passes=responses.filter(r=>r.classification==='closed_tool_continuation').length;
  const repairs=responses.filter(r=>r.classification==='deterministic_repair_feedback').length;
  const count=passes+repairs;
  return {kind:'engineered_delivery_hook_shadow',actual_requests:receiptCount,actual_model_requests_skipped:0,
    whole_request_opportunities:count,passed_check_opportunities:passes,repair_feedback_opportunities:repairs,
    whole_request_fraction:count/receiptCount,rows:responses,
    source_hashes:{events:sha256(readFileSync(join(run,'session-events.jsonl'))),audit:sha256(readFileSync(auditPath))},
    quality:'structural_check_only_not_semantic_review',learned_motif:false,execution_authorized_by_analysis:false};
}

if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  const run=resolve(process.argv[2]),root=fileURLToPath(new URL('..',import.meta.url));
  if(!run.startsWith(join(root,'.local')+'/'))throw Error('private run required');
  const path=join(run,'delivery-shadow-evaluation.json');if(existsSync(path))throw Error('preserve existing analysis');
  const result=evaluateDelivery(run);writeFileSync(path,JSON.stringify(result,null,2)+'\n',{mode:0o600});
  process.stdout.write(JSON.stringify(result)+'\n');
}
