/** Prospective source-change experiment; all semantic turns use the existing Harness workflow. */
import { createHash, randomUUID } from 'node:crypto';
import { copyFileSync, chmodSync, existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync, renameSync, realpathSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { ROOT, HERE, JOBS, digest, execute, lines, loadJob, runWorkflow } from './agent.ts';

const QUESTION = '这些论文的方法、实验证据和限制，对构建高效科研 Agent 有什么启示？';
function read(path: string) { return JSON.parse(readFileSync(path, 'utf8')); }
function sha(path: string) { return createHash('sha256').update(readFileSync(path)).digest('hex'); }
function save(path: string, value: any) {
  mkdirSync(dirname(path), {recursive:true,mode:0o700});
  const temp=path+'.tmp-'+randomUUID();
  writeFileSync(temp,JSON.stringify(value,null,2)+'\n',{mode:0o600});renameSync(temp,path);
}
function pdfs(path: string) {
  return readdirSync(path).filter(n=>n.toLowerCase().endsWith('.pdf')).sort().map(filename=>({filename,sha256:sha(join(path,filename))}));
}
function copyPdfs(from: string,to: string) {
  mkdirSync(to,{recursive:true,mode:0o700});
  for(const {filename} of pdfs(from)){copyFileSync(join(from,filename),join(to,filename));chmodSync(join(to,filename),0o600);}
}
export function fields(evidence: any): Map<string, any> {
  const entries: [string, any][]=[];
  for(const paper of evidence.draft.papers)for(const f of paper.fields)entries.push(['claim:'+paper.paper_id+':'+f.name,f]);
  if(new Set(entries.map(e=>e[0])).size!==entries.length)throw new Error('duplicate claim');
  return new Map(entries);
}
export function checkRetention(before: any, after: any, retained: string[]) {
  const a=fields(before),b=fields(after);
  for(const cid of retained)if(!a.has(cid)||!b.has(cid)||digest(a.get(cid))!==digest(b.get(cid)))throw new Error('retained field changed: '+cid);
  return retained.length;
}

async function validate(job: any) {
  const result=await execute([join(HERE,'agent-support.py')],{operation:'validate',
    evidence:join(JOBS,job.id,'evidence.json'),snapshot:join(JOBS,job.id,'source-snapshot.json')});
  if(result.code)throw new Error('source replay failed: '+job.id);
  return lines(result.stdout).at(-1);
}

async function review(job: any,parent?: any) {
  const evidence=read(join(JOBS,job.id,'evidence.json'));
  await validate(job);
  const current=job.frame.task.sources.papers.map((p:any)=>p.paper_id).sort();
  if(digest(current)!==digest(evidence.draft.papers.map((p:any)=>p.paper_id).sort()))throw new Error('output source selection mismatch');
  const result:any={job:job.id,status:job.status,model_requests:job.model_requests,accounted_usd:job.accounted_usd,
    quality:job.quality,gaps:job.gap_count,numeric_gaps:job.numeric_gap_count,verified_motif_skips:job.verified_skips,
    source_replay_passed:true,semantic_quality_equivalence:false,
    repair_warning:job.repair_warning??null,synthesis_full_table_read:!!job.synthesis_result,
    fields:[...fields(evidence)].map(([id,f])=>({id,status:f.status,statement:f.statement,
      quotes:evidence.citation_checks.filter((c:any)=>'claim:'+c.paper_id+':'+c.field===id)
        .map((c:any)=>({page:c.page,quote:c.quote,version_sha256:c.version_sha256}))}))};
  if(parent){
    const previous=read(join(JOBS,parent.id,'evidence.json'));
    const retained=evidence.incremental_audit?.retained_claim_ids;
    // A synthesis/repair publication retains the incremental audit in the underlying reading artifact.
    const reading=read(join(JOBS,job.id,'review-input','evidence.json'));
    const ids=retained??reading.incremental_audit.retained_claim_ids;
    result.retained_exact=checkRetention(previous,evidence,ids);
    result.regenerated=reading.incremental_audit.reviewed_field_count;
    result.removed_papers=parent.frame.task.sources.papers.map((p:any)=>p.paper_id).filter((pid:string)=>!current.includes(pid));
    const oldQuotes=previous.citation_checks.filter((c:any)=>{
      const p=job.frame.task.sources.papers.find((p:any)=>p.paper_id===c.paper_id);
      const old=parent.frame.task.sources.papers.find((p:any)=>p.paper_id===c.paper_id);
      return !p||p.pdf_sha256!==old.pdf_sha256;
    }).map((c:any)=>c.source_id);
    if(evidence.citation_checks.some((c:any)=>oldQuotes.includes(c.source_id)))throw new Error('stale source handle published');
    result.stale_source_handles_rejected=true;
  }
  return result;
}

export async function experiment(directory: string, callModel: boolean) {
  directory=resolve(directory);
  if(!realpathSync(directory).startsWith(realpathSync(join(ROOT,'.local'))+'/'))throw new Error('experiment must remain private');
  const plan=read(join(directory,'experiment-plan.json'));
  if(plan.schema_version!==1||plan.question!==QUESTION)throw new Error('unknown experiment protocol');
  for(const v of plan.versions)if(digest(pdfs(v.directory))!==digest(v.pdfs))throw new Error('frozen corpus changed');
  const protocol=read(join(directory,'protocol-frame.json'));
  const frame=await execute([join(HERE,'agent-support.py')],{operation:'capture',directory:plan.versions[0].directory,question:plan.question});
  if(frame.code||digest(lines(frame.stdout).at(-1))!==digest(protocol))throw new Error('code or protocol changed; register amendment before paid execution');
  if(!callModel){console.log(JSON.stringify({experiment:directory,model_call_enabled:false,plan},null,2));return;}
  if(existsSync(join(directory,'progress.json')))throw new Error('existing experiment: preserve results, do not silently rerun');
  const progress:any={experiment:directory,started_at:new Date().toISOString(),records:[],status:'running',
    semantic_quality_equivalence:false,learned_motif:false};
  const record=(value:any)=>{progress.records.push(value);save(join(directory,'progress.json'),progress);console.log(JSON.stringify(value));};
  async function run(label:string,root:string,parent?:any){
    const start=Date.now();
    const job=await runWorkflow({papers_dir:root,question:plan.question,call_model:true,force_refresh:true,
      model_review:true,repair_rounds:1,budget_usd:100,...(parent?{parent_job:parent.id}:{})},execute,j=>{
        save(join(directory,'active-job.json'),{label,job_id:j.id,status:j.status,model_requests:j.model_requests,accounted_usd:j.accounted_usd});});
    const row:any={label,job_id:job.id,status:job.status,elapsed_seconds:(Date.now()-start)/1000,
      model_requests:job.model_requests,accounted_usd:job.accounted_usd,cost_complete:job.cost_complete,error:job.error??null};
    // Save failure/expense before any result validation can throw.
    record(row);
    if(!job.cost_complete||job.status==='error')throw new Error('workflow failed: '+label+' / '+job.error);
    row.review=await review(job,parent);save(join(directory,'progress.json'),progress);
    return job;
  }
  try{
    let parent=await run('seed',plan.versions[0].directory);
    for(let i=1;i<plan.versions.length;i++){
      const version=plan.versions[i],order=i%2?['full','incremental']:['incremental','full'];
      const pair:any={};
      for(const arm of order)pair[arm]=await run(version.name+'-'+arm,version.directory,arm==='incremental'?parent:undefined);
      save(join(directory,version.name+'-comparison.json'),{full:pair.full.id,incremental:pair.incremental.id,
        same_task_sha256:pair.full.frame.task_sha256===pair.incremental.frame.task_sha256,
        semantic_quality_equivalence:false,reason:'source replay and zero gaps do not establish claim entailment or completeness'});
      parent=pair.incremental;
    }
    const start=Date.now();
    const cached=await runWorkflow({papers_dir:parent.options.papers_dir,question:plan.question,parent_job:parent.id,call_model:true},execute);
    record({label:'unchanged-cache',job_id:cached.id,status:cached.status,elapsed_seconds:(Date.now()-start)/1000,
      model_requests:cached.model_requests,accounted_usd:cached.accounted_usd,cost_complete:cached.cost_complete});
    if(cached.status!=='cached'||cached.model_requests||cached.accounted_usd)throw new Error('unchanged cache not reused');
    await validate(cached);
    progress.status='completed';
  }catch(error){progress.status='failed';progress.error=String(error);throw error;}
  finally{progress.finished_at=new Date().toISOString();progress.total_requests=progress.records.reduce((n:number,r:any)=>n+r.model_requests,0);
    progress.total_accounted_usd=progress.records.reduce((n:number,r:any)=>n+r.accounted_usd,0);save(join(directory,'progress.json'),progress);}
}

async function main(){
  const args=process.argv.slice(2),value=(f:string)=>{const i=args.indexOf(f);return i<0?undefined:args[i+1];};
  if(value('--experiment')){await experiment(value('--experiment')!,args.includes('--call-model'));return;}
  if(args.includes('--call-model'))throw new Error('first prepare and inspect the frozen protocol without model calls');
  const addition=value('--addition'),replacement=value('--replacement');
  if(!addition||!replacement)throw new Error('prepare requires --addition <real PDF> --replacement <real PDF>');
  const directory=join(ROOT,'.local/literature-notes','source-change-20261011-'+randomUUID().slice(0,8));
  const roots=['00-base','01-add','02-replace','03-remove'].map(n=>join(directory,n));
  copyPdfs(join(ROOT,'testpdf'),roots[0]);copyPdfs(roots[0],roots[1]);
  copyFileSync(addition,join(roots[1],'added-research-paper.pdf'));chmodSync(join(roots[1],'added-research-paper.pdf'),0o600);
  copyPdfs(roots[1],roots[2]);copyFileSync(replacement,join(roots[2],'added-research-paper.pdf'));chmodSync(join(roots[2],'added-research-paper.pdf'),0o600);
  mkdirSync(roots[3],{recursive:true,mode:0o700});
  for(const p of pdfs(roots[2]).filter(p=>p.filename!=='added-research-paper.pdf')){
    copyFileSync(join(roots[2],p.filename),join(roots[3],p.filename));chmodSync(join(roots[3],p.filename),0o600);}
  const plan={schema_version:1,created_at:new Date().toISOString(),question:QUESTION,
    versions:roots.map((directory,i)=>({name:['base','add','replace','remove'][i],directory,pdfs:pdfs(directory)})),
    operations:'add real paper, replace same filename with a different real paper, remove that entry; not an author revision or counterevidence benchmark',
    model:'deepseek-flash',reasoning_effort:'off',model_review:true,repair_rounds:1,manifest:null,
    arms:'ordinary Harness full refresh vs ordinary automatic dependency cache; no learned Motif claim',
    order:['seed','add-full','add-incremental','replace-incremental','replace-full','remove-full','remove-incremental','unchanged-cache'],
    failure_policy:'stop on missing ledger/workflow error; no extra paid retry; preserve gaps and all costs',
    quality:'source replay, unchanged fields exact, changed source handles fresh, removed entries absent; semantic equivalence assessed separately',
    pricing:'existing proxy estimate, supplier bill unverified; report seed and all repairs/synthesis/failures separately',
    source_originals:{testpdf:pdfs(join(ROOT,'testpdf')),addition:sha(addition),replacement:sha(replacement)},
    runner_sha256:sha(fileURLToPath(import.meta.url))};
  save(join(directory,'experiment-plan.json'),plan);
  const frame=await execute([join(HERE,'agent-support.py')],{operation:'capture',directory:roots[0],question:QUESTION});
  if(frame.code)throw new Error('protocol capture failed');save(join(directory,'protocol-frame.json'),lines(frame.stdout).at(-1));
  console.log(JSON.stringify({experiment:directory,model_call_enabled:false,version_paper_counts:plan.versions.map(v=>v.pdfs.length)}));
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url))main().catch(e=>{console.error(String(e));process.exitCode=2;});
