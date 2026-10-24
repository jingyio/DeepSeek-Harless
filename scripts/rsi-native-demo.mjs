/** Real native loop only behind the existing local cumulative budget gate. */
import {writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {runNativeDiagnostic} from '../examples/rsi-protocol-v1/native_harness.mjs';

const args=process.argv.slice(2),value=name=>args[args.indexOf(name)+1];
const endpoint=new URL(process.env.DEEPSEEK_BASE_URL??'https://invalid');
if(process.env.SSS_BUDGET_GATE_ACTIVE!=='1'||process.env.SSS_BUDGET_CAP_USD!=='null'||
 !process.env.SSS_BUDGET_LEDGER||endpoint.protocol!=='http:'||!['localhost','127.0.0.1','[::1]'].includes(endpoint.hostname))throw Error('explicit_cumulative_budget_gate_required');
const root=fileURLToPath(new URL('../',import.meta.url)),output=resolve(value('--output'));
if(!output.startsWith(resolve(root,'.local')+'/'))throw Error('private_native_output_required');
const result=await runNativeDiagnostic({task:value('--task'),baseURL:endpoint.href,resolveApiKey:async()=>process.env.DEEPSEEK_API_KEY});
writeFileSync(output,JSON.stringify(result,null,2)+'\n',{mode:0o600});
console.log(JSON.stringify({task:result.task,model_requests:result.model_requests,native_python_dispatches:result.native_python_dispatches,correct:result.correct,errors:result.errors}));
if(!result.correct||result.errors.length)process.exitCode=1;
