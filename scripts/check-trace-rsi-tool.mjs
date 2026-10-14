/** Independent source-oracle comparison. This checker never calls a model. */
import {readFileSync} from 'node:fs';
import {validateTraceCandidate,runTraceTool} from '../src/adapters/trace_rsi_program.ts';
import {canonical,digest} from '../src/adapters/paper_rsi_program.ts';
const [candidatePath,casesPath]=process.argv.slice(2);
const candidate=validateTraceCandidate(JSON.parse(readFileSync(candidatePath,'utf8')));
const cases=JSON.parse(readFileSync(casesPath,'utf8'));
const rows=cases.map(row=>{try{
 const actual=runTraceTool(candidate,row.input);
 return {id:row.id,input_sha256:digest(row.input),passed:canonical(actual)===canonical(row.expected),actual,expected:row.expected};
}catch(error){return {id:row.id,input_sha256:digest(row.input),passed:false,error:String(error)};}});
const result={passed:rows.length>0&&rows.every(row=>row.passed),cases:rows};
process.stdout.write(JSON.stringify(result)+'\n');
if(!result.passed)process.exitCode=1;
