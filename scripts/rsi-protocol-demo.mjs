/** Offline by default. Optional --selection consumes real bounded-Harness choices. */
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';
import {executeRsiOperation,admissionDecision,bytesSha256} from '../src/adapters/rsi_protocol.ts';
import {diagnosticHost,fixtures} from '../examples/rsi-protocol-v1/host.mjs';

const root=fileURLToPath(new URL('../',import.meta.url));
const args=process.argv.slice(2),selectionIndex=args.indexOf('--selection'),outputIndex=args.indexOf('--output');
const selection=selectionIndex<0?null:JSON.parse(readFileSync(args[selectionIndex+1],'utf8'));
const python=process.env.SSS_PYTHON??(process.platform==='win32'?'python':'python3');
const summary={scope:'手工算子与合成数据的 F02 协议诊断；不是自动挖掘/泛化/降本实验',real_model_selection:!!selection,cases:[]};
for(const task of ['A','B']){
 const x=diagnosticHost(task);
 if(selection){
  const choice=selection.choices.find(c=>c.task===task);
  if(!choice||choice.arguments_sha256!==bytesSha256(JSON.stringify(x.args)))throw Error('selection_input_changed');
  if(choice.action!=='group_count')x.host.obligations.clear();
 }
 const execution=await executeRsiOperation(x.request,x.args,()=>x.host,async(operation,input)=>{
  if(operation!=='table.group_count')throw Error('diagnostic_operation_not_allowed');
  // A fixed script, fixed cwd and JSON stdin; no model-authored shell/code.
  const run=spawnSync(python,['examples/rsi-protocol-v1/group_count.py'],{cwd:root,input:JSON.stringify(input),encoding:'utf8',timeout:10000,maxBuffer:100000});
  if(run.status!==0)throw Error('diagnostic_python_failed');
  return JSON.parse(run.stdout);
 });
 const correct=JSON.stringify(execution.result)===JSON.stringify(fixtures.tasks[task].expected);
 summary.cases.push({task,goal:fixtures.tasks[task].goal,decision:execution.decision.payload,
  result:execution.result,correct,events:execution.events});
 if(!correct)process.exitCode=1;
}
for(const [name,change]of [
 ['中途数据版本改变',x=>{x.host.currentEvidence.get('current-table').payload.version='2';}],
 ['权限被撤销',x=>{x.host.grant.revoked=true;}],
 ['任务不需要汇总',x=>{x.host.obligations.clear();}],
 ['没有适用经验',x=>{x.host.operators.clear();}],
]){
 const x=diagnosticHost();change(x);
 const decision=admissionDecision(x.request,x.host);
 summary.cases.push({case:name,decision:decision.payload,dispatched:false});
 if(decision.payload.action==='execute')process.exitCode=1;
}
if(selection){
 const c=selection.choices.find(x=>x.task==='C');
 const x=diagnosticHost();x.host.obligations.clear();
 const decision=admissionDecision(x.request,x.host);
 summary.cases.push({case:'真实模型判断只写邀请，不做汇总',model_action:c?.action??null,decision:decision.payload});
 if(c?.action!=='handoff')process.exitCode=1;
}
if(outputIndex>=0){
 const output=resolve(args[outputIndex+1]);
 if(!output.startsWith(resolve(root,'.local')+'/'))throw Error('diagnostic_output_must_be_private');
 mkdirSync(resolve(output,'..'),{recursive:true,mode:0o700});
 writeFileSync(output,JSON.stringify(summary,null,2)+'\n',{mode:0o600});
}
console.log(JSON.stringify(summary,null,2));
