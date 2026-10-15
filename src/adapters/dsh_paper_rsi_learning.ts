/** Opt-in, isolated learning profile. Candidate programs are data, never evaluated JS. */
import { appendFileSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { validateCandidate,runReportCheck,digest,canonical } from './paper_rsi_program.ts';
export const name='sss-paper-rsi-learning';
export const inject=['tools','agents'];
export function apply(ctx:any){
  const config=JSON.parse(readFileSync(process.env.SSS_PAPER_RSI_LEARNING!,'utf8'));
  let current:any=null;
  const audit=(row:any)=>appendFileSync(join(config.work,'learning.jsonl'),JSON.stringify(row)+'\n',{mode:0o600});
  // Register before agent/created: this Harness rejects restrictions naming unknown tools.
  ctx.tools.register({name:'rsi_trial',description:'运行当前模型生成的纯数据报告检查程序，不访问文件或网络；必须先安装候选。',
    parameters:{type:'object',properties:{input:{type:'object'}},required:['input'],additionalProperties:false},
    output:{schema:{type:'object'},render:(_:any,v:any)=>[{type:'text',text:JSON.stringify(v)}]},
    async execute(args:any){
      if(!current)throw Error('install_candidate_first');
      const result=runReportCheck(current,args.input);
      audit({kind:'trial',candidate_sha256:digest(current),input_sha256:digest(args.input),output:result});return result;
    }});
  const service={install(candidate:any){
    validateCandidate(candidate);current=JSON.parse(JSON.stringify(candidate));
    const sha=digest(current),path=join(config.work,sha+'.candidate.json');
    if(!existsSync(path))writeFileSync(path,JSON.stringify(current,null,2),{mode:0o600,flag:'wx'});
    writeFileSync(join(config.work,'current-candidate.json'),JSON.stringify(current,null,2),{mode:0o600});
    audit({kind:'candidate_installed',candidate_sha256:sha});return {candidate_sha256:sha,tool:'rsi_trial'};
  }};
  ctx.provide('sssPaperRsi',service);
  ctx.tools.register({name:'rsi_test',description:'对当前候选执行开发样例，返回逐项期望和实际值；失败应更新 Cordis 包。此工具不展示独立验收样例。',
    parameters:{type:'object',properties:{},additionalProperties:false},
    output:{schema:{type:'object'},render:(_:any,v:any)=>[{type:'text',text:JSON.stringify(v)}]},
    async execute(args:any){
      if(!current||Object.keys(args).length)throw Error('install_candidate_first');
      const rows=config.training.map((f:any)=>{try{const actual=runReportCheck(current,f.input);return {id:f.id,passed:canonical(actual)===canonical(f.expected),actual,expected:f.expected};}catch(e){return {id:f.id,passed:false,error:String(e)};}});
      const result={candidate_sha256:digest(current),passed:rows.every((r:any)=>r.passed),cases:rows};audit({kind:'development_test',...result});return result;
    }});
  ctx.on('agent/created',({agent}:any)=>{
    if(agent.session.id!==config.session_id)return;
    agent.ctx.tools.restrict({allow:['cordis_inspect_list','cordis_inspect_query','cordis_inspect_self','cordis_define','cordis_run','cordis_stop','cordis_undefine','rsi_test','rsi_trial']});
  });
}
