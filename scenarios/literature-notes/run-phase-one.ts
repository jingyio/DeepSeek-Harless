/** Three real tasks through the existing workflow; no second model/agent loop. */
import {createHash, randomUUID} from 'node:crypto';
import {copyFileSync, chmodSync, existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync, renameSync, realpathSync} from 'node:fs';
import {dirname, join, resolve, sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {ROOT, HERE, JOBS, digest, execute, lines, runWorkflow} from './agent.ts';
import {checkRetention} from './compare-source-changes.ts';

const DEFAULT = '这三篇论文的方法、实验证据和限制，对构建高效科研 Agent 有什么启示？';
const UPDATE = '所选论文的方法、实验证据和限制，对构建高效科研 Agent 有什么启示？';
const read = (path: string) => JSON.parse(readFileSync(path, 'utf8'));
const sha = (path: string) => createHash('sha256').update(readFileSync(path)).digest('hex');
function save(path: string, value: any) {
  mkdirSync(dirname(path), {recursive:true,mode:0o700});
  const tmp = path + '.tmp-' + randomUUID();
  writeFileSync(tmp, JSON.stringify(value,null,2)+'\n', {mode:0o600}); renameSync(tmp,path);
}
async function support(operation: string, values: any) {
  const result = await execute([join(HERE,'agent-support.py')], {operation,...values});
  if (result.code) throw new Error('source/task validation failed: '+result.stderr.split('\n').slice(-3).join('\n'));
  return lines(result.stdout).at(-1);
}
async function validate(job: any) {
  return support('validate', {evidence:join(JOBS,job.id,'evidence.json'), snapshot:join(JOBS,job.id,'source-snapshot.json')});
}
export function taskChecks(job: any, evidence: any) {
  const expected = job.frame.task.sources.papers.map((p:any)=>p.paper_id).sort();
  const actual = evidence.draft.papers.map((p:any)=>p.paper_id).sort();
  if (digest(expected)!==digest(actual)) throw new Error('delivery corpus differs from current task');
  return {corpus_count:actual.length, fields:evidence.draft.papers.reduce((n:number,p:any)=>n+p.fields.length,0),
    citations:evidence.citation_checks.length, gaps:evidence.gaps.length,
    source_replay:true, scientific_truth_certified:false, semantic_quality:'independent_source_check_pending'};
}
export function stageMetrics(job: any) {
  return (job.stages??[]).map((s:any)=>({stage:s.stage,exit_code:s.exit_code,cost_complete:s.complete,
    requests:s.summaries.reduce((n:number,r:any)=>n+(r.upstream_requests??0),0),
    estimated_usd:s.cost, harness_seconds:s.summaries.reduce((n:number,r:any)=>n+(r.elapsed_seconds??0),0),
    native_runs:s.summaries.flatMap((r:any)=>r.output_dir?[r.output_dir]:[])}));
}
function codeSnapshot() {
  const paths = readdirSync(HERE).filter(n=>/\.(py|ts|mjs|md|json)$/.test(n)).map(n=>join(HERE,n));
  for (const n of ['scripts/run-scenario.py','scripts/project.mjs','src/adapters/dsh_completion_guard.ts',
    'src/adapters/scenario.py','src/adapters/dsh_scenario_guard.mjs','src/adapters/deepseek_cost_gate.py',
    'src/adapters/harness_runtime.py','package-lock.json']) paths.push(join(ROOT,n));
  return Object.fromEntries(paths.map(p=>[p.slice(ROOT.length+1),sha(p)]));
}
export async function prepare(directory: string, papers: string, budget=12, taskBudget=3) {
  if (!Number.isFinite(budget)||budget<=0||budget>100||!Number.isFinite(taskBudget)||taskBudget<=0||taskBudget>budget) throw new Error('invalid protective budget');
  directory=resolve(directory); mkdirSync(directory,{recursive:true,mode:0o700});
  if (!realpathSync(directory).startsWith(realpathSync(join(ROOT,'.local'))+sep)||existsSync(join(directory,'protocol.json'))) throw new Error('use a new private experiment directory');
  const original = await support('capture',{directory:resolve(papers),question:DEFAULT});
  if (original.task.sources.papers.length!==3) throw new Error('phase one requires the existing three-paper corpus');
  const ordered=[...original.task.sources.papers].sort((a,b)=>a.paper_id.localeCompare(b.paper_id));
  const full=join(directory,'papers-full'), base=join(directory,'papers-base');
  for(const root of [full,base])mkdirSync(root,{mode:0o700});
  for(const [i,p] of ordered.entries())for(const root of i<2?[full,base]:[full]){
    copyFileSync(join(original.task.sources.root,p.filename),join(root,p.filename));chmodSync(join(root,p.filename),0o600);
  }
  const frames={T1:await support('capture',{directory:full,question:DEFAULT}),
    T3_base:await support('capture',{directory:base,question:UPDATE}),
    T3_add:await support('capture',{directory:full,question:UPDATE})};
  const protocol={schema_version:1,experiment_id:directory.split(sep).at(-1),created_at:new Date().toISOString(),
    original,frames,full,base,added_paper_id:ordered[2].paper_id,code:codeSnapshot(),budget_usd:budget,task_budget_usd:taskBudget,
    mode:'baseline',model:'deepseek-flash',reasoning_effort:'off',compression_enabled:false,
    model_review:true,repair_rounds:2,repair_scope:'support_audit',manifest:null,
    task_order:['T1-full','T2-gap-repair','T3-base','T3-add','T3-unchanged'],
    T2_policy:'natural final gap if present; otherwise separately validated one-method removal, marked controlled diagnostic',
    quality:'source replay and explicit gaps; independent scientific support assessed separately',
    no_human_approval:true,no_original_pdf_writes:true,no_learned_motif_claim:true,
    failure_policy:'retain all fees, stop on missing accounting or failed workflow; no silent paid rerun'};
  save(join(directory,'protocol.json'),protocol);
  console.log(JSON.stringify({experiment:directory,model_call_enabled:false,total_budget_usd:budget,task_budget_usd:taskBudget,paper_counts:[3,2,3],question:DEFAULT}));
  return protocol;
}
export async function experiment(directory: string, callModel=false) {
  directory=resolve(directory);
  if(!realpathSync(directory).startsWith(realpathSync(join(ROOT,'.local'))+sep))throw new Error('private directory required');
  const p=read(join(directory,'protocol.json'));
  if(p.schema_version!==1||digest(p.code)!==digest(codeSnapshot()))throw new Error('protocol/code changed; freeze a new experiment or record amendment');
  for(const frame of [p.original,p.frames.T1,p.frames.T3_base,p.frames.T3_add])
    if(digest(frame)!==digest(await support('capture',{directory:frame.task.sources.root,question:frame.task.question})))throw new Error('frozen task or sources changed');
  if(!callModel){console.log(JSON.stringify({experiment:directory,model_call_enabled:false,protocol:p.experiment_id,budget_usd:p.budget_usd}));return;}
  if(existsSync(join(directory,'progress.json')))throw new Error('existing results must not be overwritten or rerun');
  const progress:any={experiment_id:p.experiment_id,status:'running',started_at:new Date().toISOString(),records:[],total_requests:0,total_estimated_usd:0,learned_motif:false,semantic_quality_equivalence:false};
  const persist=()=>save(join(directory,'progress.json'),progress);
  persist();
  async function run(label:string, options:any){
    const remaining=p.budget_usd-progress.total_estimated_usd;
    if(remaining<0.002)throw new Error('experiment budget exhausted');
    const start=Date.now();
    const job=await runWorkflow({call_model:true,model_review:true,repair_rounds:2,force_refresh:true,
      budget_usd:Math.min(p.task_budget_usd,remaining),...options},execute,j=>{
        save(join(directory,'active-job.json'),{label,job_id:j.id,status:j.status,model_requests:j.model_requests,estimated_usd:j.accounted_usd});});
    const row:any={label,job_id:job.id,status:job.status,error:job.error??null,elapsed_seconds:(Date.now()-start)/1000,
      model_requests:job.model_requests,estimated_usd:job.accounted_usd,cost_complete:job.cost_complete,
      stages:stageMetrics(job),verified_skips:job.verified_skips,decision_log:job.decision_log};
    progress.records.push(row);progress.total_requests+=job.model_requests;progress.total_estimated_usd+=job.accounted_usd;persist();
    console.log(JSON.stringify(row));
    if(!job.cost_complete||job.status==='error')throw new Error('task failed: '+label+' / '+job.error);
    await validate(job);
    row.checks=taskChecks(job,read(join(JOBS,job.id,'evidence.json')));persist();
    return job;
  }
  try{
    const first=await run('T1-full',{papers_dir:p.full,question:DEFAULT});
    let parent=first, diagnostic:any=null;
    if(!first.gap_count&&!first.numeric_gap_count){
      const r=await execute([join(HERE,'phase_one_tasks.py')],{parent_job:first.id});
      if(r.code)throw new Error('controlled diagnostic preparation failed: '+r.stderr);
      diagnostic=lines(r.stdout).at(-1);parent=read(join(JOBS,diagnostic.diagnostic_parent_job,'job.json'));
    }
    save(join(directory,'T2-input.json'),{kind:diagnostic?'controlled_missing_data_diagnostic':'natural_final_gaps',parent_job:parent.id,
      originating_job:first.id,diagnostic,prepared_at:new Date().toISOString(),gold_visible_to_model:false});
    const repaired=await run('T2-gap-repair',{papers_dir:p.full,question:DEFAULT,parent_job:parent.id,
      repair_only:true,repair_rounds:1,repair_scope:'unresolved_claims_only'});
    const before=read(join(JOBS,parent.id,'evidence.json')),after=read(join(JOBS,repaired.id,'evidence.json'));
    const target=read(join(JOBS,repaired.id,'repair-input-1/repair-targets.json')).claim_ids;
    const retained=before.draft.papers.flatMap((paper:any)=>paper.fields.map((f:any)=>'claim:'+paper.paper_id+':'+f.name)).filter((id:string)=>!target.includes(id));
    save(join(directory,'T2-checks.json'),{kind:diagnostic?'controlled':'natural',target_claim_ids:target,
      unchanged_fields:checkRetention(before,after,retained),before_gaps:before.gaps.length,after_gaps:after.gaps.length,
      no_original_event_edits:true,semantic_repair_certified:false});
    const seed=await run('T3-base',{papers_dir:p.base,question:UPDATE});
    const update=await run('T3-add',{papers_dir:p.full,question:UPDATE,parent_job:seed.id});
    const added=read(join(JOBS,update.id,'evidence.json'));
    if(!added.draft.papers.some((v:any)=>v.paper_id===p.added_paper_id))throw new Error('new paper absent from update');
    const retainedIds=read(join(JOBS,seed.id,'evidence.json')).draft.papers.flatMap((paper:any)=>paper.fields.map((f:any)=>'claim:'+paper.paper_id+':'+f.name));
    const preserved=checkRetention(read(join(JOBS,seed.id,'evidence.json')),added,retainedIds);
    if(update.status==='cached'||update.incremental?.retained!==preserved||update.incremental?.regenerated!==5)throw new Error('addition must preserve old facts and actually process the new paper');
    save(join(directory,'T3-checks.json'),{added_paper_id:p.added_paper_id,incremental:update.incremental??null,
      prior_claim_ids:retainedIds,prior_fields_exactly_preserved:preserved,
      selection_change_policy:'mechanical source replay preserves per-paper facts; corpus change invalidates synthesis; not semantic conflict detection',
      stale_whole_result_not_reused:update.status!=='cached',semantic_quality_equivalence:false});
    const cached=await run('T3-unchanged',{papers_dir:p.full,question:UPDATE,parent_job:update.id,force_refresh:false});
    if(cached.status!=='cached'||cached.model_requests||cached.accounted_usd)throw new Error('unchanged control failed to reuse');
    if(digest(added.draft)!==digest(read(join(JOBS,cached.id,'evidence.json')).draft))throw new Error('unchanged cache changed the result');
    progress.status='completed';
  }catch(error){progress.status='failed';progress.error=String(error);throw error;}
  finally{progress.finished_at=new Date().toISOString();persist();}
}
async function main(){
  const args=process.argv.slice(2),value=(flag:string)=>{const i=args.indexOf(flag);return i<0?undefined:args[i+1];};
  if(value('--experiment')){await experiment(value('--experiment')!,args.includes('--call-model'));return;}
  if(args.includes('--call-model'))throw new Error('prepare and inspect the frozen experiment first');
  const directory=value('--output')??join(ROOT,'.local/literature-notes','phase-one-20261012-'+randomUUID().slice(0,8));
  await prepare(directory,value('--papers-dir')??join(ROOT,'testpdf'),Number(value('--budget-usd')??12),Number(value('--task-budget-usd')??3));
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url))main().catch(error=>{console.error(String(error));process.exitCode=2;});
