/** Selected support review and synthesis through existing Harness stages. */
import {randomUUID} from 'node:crypto';
import {mkdirSync,writeFileSync,readFileSync,renameSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {HERE,JOBS,digest,execute,lines,loadJob,costOf} from './agent.ts';
import {writeDecisionLog} from './decision-log.ts';
import {checkRetention} from './compare-source-changes.ts';

async function support(operation:string,values:any){
  const r=await execute([join(HERE,'agent-support.py')],{operation,...values});
  if(r.code)throw new Error('selected repair source validation failed: '+r.stderr);
  return lines(r.stdout).at(-1);
}
export async function repairSelected(parentId:string,claimIds:string[],budget=3,callModel=false,sourceFeedback?:string){
  if(!Array.isArray(claimIds)||!claimIds.length||new Set(claimIds).size!==claimIds.length
    ||claimIds.some(v=>typeof v!=='string')||!Number.isFinite(budget)||budget<=0||budget>100)throw new Error('invalid selected repair targets or budget');
  const parent=loadJob(parentId),id=randomUUID(),directory=join(JOBS,id);
  if(!['delivered','delivered_with_gaps','cached'].includes(parent.status))throw new Error('complete parent required');
  const frame=await support('capture',{directory:parent.options.papers_dir,question:parent.options.question});
  for(const key of ['task_sha256','parser_sha256','contract_sha256'])
    if(frame[key]!==parent.frame[key])throw new Error('parent sources or tool contract changed');
  mkdirSync(directory,{mode:0o700});
  const job:any={schema_version:1,id,created_at:new Date().toISOString(),options:parent.options,frame,parent_job:parentId,
    status:'preparing',source_run:parent.source_run,stages:[],accounted_usd:0,model_requests:0,cost_complete:true,
    verified_skips:0,human_review_required:false,user_pdf_writes:false,selected_claim_ids:claimIds,
    workflow_decisions:[],scope:'selected independent support issues; inherited costs remain in parent',budget_cap_usd:budget,
    workflow_change:{parent_sha256:parent.frame.workflow_sha256,current_sha256:frame.workflow_sha256,
      changed:parent.frame.workflow_sha256!==frame.workflow_sha256}};
  const persist=()=>{const tmp=join(directory,'job.json.tmp');writeFileSync(tmp,JSON.stringify(job,null,2)+'\n',{mode:0o600});renameSync(tmp,join(directory,'job.json'));};
  persist();
  try{
    Object.assign(job,await support('package',{job:directory,evidence_path:join(JOBS,parentId,'evidence.json'),
      snapshot_path:join(JOBS,parentId,'source-snapshot.json')}));
    const initial=JSON.parse(readFileSync(join(directory,'evidence.json'),'utf8'));
    const plan=await support('repair_plan',{job:directory,round_number:1,scope:'support_audit',target_claim_ids:claimIds});
    if(sourceFeedback){
      // Existing Python entry validates private location, candidate digest and target set before model calls.
      const preview=await execute([join(HERE,'repair-pdf.py'),'--run',plan.input_directory,'--source-feedback',sourceFeedback]);
      if(preview.code)throw new Error('source feedback preflight failed: '+preview.stderr);
      writeFileSync(join(directory,'source-feedback-preview.txt'),preview.stdout,{mode:0o600});
    }
    if(!callModel){job.status='preview';job.plan=plan;persist();return job;}
    async function stage(name:string,input:string){
      const remaining=budget-job.accounted_usd;if(remaining<0.002)throw new Error('selected repair budget exhausted');
      job.status=name==='synthesis'?'reviewing':'repairing';persist();
      const r=await execute([join(HERE,'repair-pdf.py'),'--run',input,'--budget-usd',String(remaining),'--call-model',
        ...(sourceFeedback&&name==='selected-support'?['--source-feedback',sourceFeedback]:[])]);
      for(const k of ['stdout','stderr'] as const)writeFileSync(join(directory,name+'-'+k+'.txt'),r[k],{mode:0o600});
      const usage=costOf(r);job.stages.push({stage:name,exit_code:r.code,...usage});
      job.accounted_usd+=usage.cost;job.model_requests+=usage.summaries.reduce((n:number,v:any)=>n+(v.upstream_requests??0),0);job.cost_complete&&=usage.complete;persist();
      const out=lines(r.stdout).find(v=>v.claim_repair);
      if(!usage.complete||job.accounted_usd>budget+1e-10||r.code||!out?.receipt)throw new Error('selected repair did not deliver; all costs retained');
      Object.assign(job,await support('package',{job:directory,evidence_path:join(out.claim_repair,'revised-evidence.json'),
        snapshot_path:join(directory,'source-snapshot.json'),review_path:join(out.claim_repair,'claim-review.json')}));
      job[name+'_receipt']=out.receipt;persist();
    }
    await stage('selected-support',plan.input_directory);
    const synthesis=await support('synthesis_plan',{job:directory});await stage('synthesis',synthesis.input_directory);
    const final=JSON.parse(readFileSync(join(directory,'evidence.json'),'utf8'));
    const retained=initial.draft.papers.flatMap((p:any)=>p.fields.map((f:any)=>'claim:'+p.paper_id+':'+f.name)).filter((cid:string)=>!claimIds.includes(cid));
    job.retained_fields=checkRetention(initial,final,retained);
    if(digest(frame)!==digest(await support('capture',{directory:parent.options.papers_dir,question:parent.options.question})))throw new Error('sources changed during correction');
    Object.assign(job,await support('index_automatic',{job:directory}));
    job.status=job.gap_count||job.numeric_gap_count?'delivered_with_gaps':'delivered';job.quality=job.research_quality;
  }catch(error){job.status='error';job.error=String(error);}
  finally{job.finished_at=new Date().toISOString();job.decision_log=writeDecisionLog(directory,job);persist();}
  return job;
}
async function main(){
  const args=process.argv.slice(2),value=(f:string)=>{const i=args.indexOf(f);return i<0?undefined:args[i+1];};
  const job=await repairSelected(value('--job')!,JSON.parse(value('--claim-ids')??'[]'),Number(value('--budget-usd')??3),args.includes('--call-model'),value('--source-feedback'));
  console.log(JSON.stringify(job,null,2));if(job.status==='error')process.exitCode=2;
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url))main().catch(e=>{console.error(String(e));process.exitCode=2;});
