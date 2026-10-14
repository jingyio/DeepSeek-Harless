/** Frozen full-task comparison; delegates every model turn to the original scene Harness. */
import {createHash,randomUUID} from 'node:crypto';
import {copyFileSync,chmodSync,existsSync,mkdirSync,readFileSync,readdirSync,writeFileSync,realpathSync} from 'node:fs';
import {join,resolve,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {ROOT,HERE,JOBS,runWorkflow,execute,lines,digest} from './agent.ts';
import {taskChecks,stageMetrics} from './run-phase-one.ts';
const read=(p:string)=>JSON.parse(readFileSync(p,'utf8'));
const sha=(p:string)=>createHash('sha256').update(readFileSync(p)).digest('hex');
function save(p:string,v:any){writeFileSync(p,JSON.stringify(v,null,2)+'\n',{mode:0o600});}
async function support(operation:string,values:any){const r=await execute([join(HERE,'agent-support.py')],{operation,...values});if(r.code)throw new Error(r.stderr);return lines(r.stdout).at(-1);}
function snapshot(){
 const files=readdirSync(HERE).filter(n=>/\.(py|ts|mjs|json|md)$/.test(n)&&!['README.md','HANDOFF.md','phase-one-protocol.md'].includes(n)).map(n=>join(HERE,n));
 for(const f of ['scripts/run-scenario.py','scripts/project.mjs','src/adapters/scenario.py','src/adapters/dsh_entry_motif.ts',
  'src/motif_core/entry_read_policy.ts','src/motif_core/inventory_entry_policy.ts','src/motif_core/offline/entry_compiler.py',
  'src/motif_core/online_skill_runtime.mjs','src/adapters/dsh_completion_guard.ts','src/adapters/deepseek_cost_gate.py','package-lock.json'])files.push(join(ROOT,f));
 return Object.fromEntries(files.map(p=>[p.slice(ROOT.length+1),sha(p)]));
}
function privateDirectory(dir:string){if(!realpathSync(dir).startsWith(realpathSync(join(ROOT,'.local'))+sep))throw new Error('private experiment directory required');}
export async function prepare(directory:string,claimPolicy:string,readingPolicy:string){
 directory=resolve(directory);privateDirectory(directory);if(existsSync(join(directory,'comparison-protocol.json')))throw new Error('preserve prior protocol');
 const original=await support('capture',{directory:join(ROOT,'testpdf'),question:'当前实验语料快照'});
 const recipes=[{label:'validation-boundaries',count:3,question:'对科研 PDF Agent，这三篇论文怎样验证工具执行或研究结论？请区分作者实测、适用边界和本项目可测试的复用假设。'},
  {label:'reuse-and-update',count:2,question:'这两篇论文的成本收益来自哪些复用单位，需要哪些验证条件？对科研 PDF 与笔记的增量更新提出有证据边界的方案。'}];
 const cases=[];
 for(const recipe of recipes){const papers=join(directory,'eval-'+recipe.label);mkdirSync(papers,{mode:0o700});
  for(const p of original.task.sources.papers.slice(0,recipe.count)){const target=join(papers,p.filename);copyFileSync(join(original.task.sources.root,p.filename),target);chmodSync(target,0o600);}
  cases.push({...recipe,papers,frame:await support('capture',{directory:papers,question:recipe.question})});
 }
 const arms=['harness','claim-motif','two-motifs'],order=[];
 for(let c=0;c<cases.length;c++)for(let r=0;r<3;r++)for(let a=0;a<3;a++)order.push({case:cases[c].label,round:r+1,arm:arms[(a+r+c)%3]});
 const p={schema_version:1,experiment_id:directory.split(sep).at(-1),created_before_paid_comparison:true,original,cases,order,
  claim_policy:resolve(claimPolicy),claim_policy_digest:read(claimPolicy).policy_digest,
  reading_policy:resolve(readingPolicy),reading_policy_digest:read(readingPolicy).policy_digest,code:snapshot(),
  model:'deepseek-flash',reasoning_effort:'off',compression_enabled:false,tool_presentation:'native',
  budget_usd:10,task_budget_usd:1,model_review:true,repair_rounds:2,repair_scope:'support_audit',
  force_refresh:true,cache_policy:'reuse; source revalidated; warm shared parser cache in every arm',
  quality:'actual source/citation replay, full corpus and fields, gaps; no expert semantic equivalence claim',
  failure_policy:'all expenses retained; stop on missing accounting or workflow failure; no silent paid rerun',
  causal_scope:'entry navigation removed; downstream request differences also include semantic stochasticity and changed context'};
 save(join(directory,'comparison-protocol.json'),p);return p;
}
export async function compare(directory:string,call=false){
 directory=resolve(directory);privateDirectory(directory);const p=read(join(directory,'comparison-protocol.json'));
 if(digest(p.code)!==digest(snapshot())||read(p.claim_policy).policy_digest!==p.claim_policy_digest
  ||read(p.reading_policy).policy_digest!==p.reading_policy_digest)throw new Error('frozen code or policy changed');
 for(const c of p.cases)if(digest(c.frame)!==digest(await support('capture',{directory:c.papers,question:c.question})))throw new Error('source/task changed');
 if(!call){console.log(JSON.stringify({experiment:directory,runs:p.order.length,total_budget_usd:p.budget_usd,model_call_enabled:false,paper_counts:p.cases.map((c:any)=>c.count)}));return;}
 if(existsSync(join(directory,'comparison-progress.json')))throw new Error('prior results must be retained');
 const progress:any={status:'running',rows:[],total_requests:0,total_estimated_usd:0},persist=()=>save(join(directory,'comparison-progress.json'),progress);
 persist();
 try{
  for(const slot of p.order){
   if(digest(p.code)!==digest(snapshot()))throw new Error('code changed during paid experiment');
   const c=p.cases.find((c:any)=>c.label===slot.case),remaining=p.budget_usd-progress.total_estimated_usd;if(remaining<.002)throw new Error('budget exhausted');
   const start=Date.now(),job=await runWorkflow({papers_dir:c.papers,question:c.question,budget_usd:Math.min(p.task_budget_usd,remaining),
    force_refresh:true,call_model:true,model_review:true,repair_rounds:2,repair_scope:'support_audit',
    ...(slot.arm!=='harness'?{claim_entry_policy:p.claim_policy}:{}),...(slot.arm==='two-motifs'?{reading_entry_policy:p.reading_policy}:{})},execute,
    j=>save(join(directory,'active-job.json'),{...slot,job_id:j.id,status:j.status,actual_requests:j.model_requests,estimated_usd:j.accounted_usd}));
   const row:any={...slot,job_id:job.id,status:job.status,error:job.error??null,elapsed_seconds:(Date.now()-start)/1000,
    requests:job.model_requests,estimated_usd:job.accounted_usd,cost_complete:job.cost_complete,stages:stageMetrics(job),
    verified_runtime_batches:job.entry_verified_batches,output_tokens:job.stages.reduce((n:number,s:any)=>n+s.summaries.reduce((n:number,v:any)=>n+(v.outputTokens??0),0),0)};
   progress.rows.push(row);progress.total_requests+=row.requests;progress.total_estimated_usd+=row.estimated_usd;persist();
   if(!job.cost_complete||job.status==='error')throw new Error('failed workflow retained; '+job.error);
   await support('validate',{evidence:join(JOBS,job.id,'evidence.json'),snapshot:join(JOBS,job.id,'source-snapshot.json')});
   row.quality=taskChecks(job,read(join(JOBS,job.id,'evidence.json')));row.quality.numeric_gaps=job.numeric_gap_count;
   persist();console.log(JSON.stringify(row));
  }
  progress.status='completed';
 }catch(error){progress.status='failed';progress.error=String(error);throw error;}
 finally{persist();}
}
async function main(){const args=process.argv.slice(2),v=(f:string)=>{const i=args.indexOf(f);return i<0?undefined:args[i+1];};
 const directory=v('--experiment');if(!directory)throw new Error('--experiment required');
 if(args.includes('--prepare')){if(args.includes('--call-model'))throw new Error('freeze and preview before paid calls');await prepare(directory,v('--claim-policy')!,v('--reading-policy')!);}
 await compare(directory,args.includes('--call-model'));
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url))main().catch(e=>{console.error(String(e));process.exitCode=2;});
