import {appendFileSync,readFileSync,lstatSync,realpathSync} from 'node:fs';
import {resolve} from 'node:path';
import {runArtifactProgram} from '../src/adapters/artifact_motif_runtime.ts';
try{
 const path=process.argv[2];
 if(realpathSync(path)!==resolve(path)||!lstatSync(path).isFile()||lstatSync(path).nlink!==1)throw Error('artifact_job_not_fixed');
 const payload=JSON.parse(readFileSync(path,'utf8'));
 payload.bound=payload.bound.map(b=>({...b,data:Buffer.from(b.data,'base64')}));
 payload.audit=row=>appendFileSync(payload.auditPath,JSON.stringify({...row,at:new Date().toISOString()})+'\n',{mode:0o600});
 console.log(JSON.stringify(runArtifactProgram(payload).receipt));
}catch(error){console.error(String(error.message));process.exitCode=1;}
