import {fileURLToPath} from 'node:url';
import {writeFileSync,mkdtempSync} from 'node:fs';
import {join} from 'node:path';
import GeneLoopShell from './geneloop_shell.ts';
import {artifactInvocation} from './artifact_motif_runtime.ts';
import {resolveExecutionAgent} from './geneloop_delegation.ts';
export default class ArtifactMotifShell extends GeneLoopShell {
 resolve(request:any):any{
  const agent=resolveExecutionAgent(this.ctx),job=agent&&artifactInvocation(agent.session.id,request.command,request.workdir);
  const spec=super.resolve(request);
  if(job)spec.artifactJob=job;
  return spec;
 }
 run(spec:any){
  if(!spec.artifactJob)return super.run(spec);
  // Use the native executor lifecycle for cancellation and stdout delivery.
  // The child is a trusted interpreter of a private versioned library, not shell text.
  const job=spec.artifactJob;
  const {audit,...serializable}=job;
  const payload={...serializable,bound:job.bound.map((b:any)=>({...b,data:b.data.toString('base64')}))};
  const path=join(mkdtempSync(join(job.workspace,'command-tmp','artifact-job-')),'job.json');
  writeFileSync(path,JSON.stringify(payload),{mode:0o600,flag:'wx'});
  const argv=[process.execPath,fileURLToPath(new URL('../../scripts/run-artifact-motif.mjs',import.meta.url)),path];
  return this.runArgv(spec,argv);
 }
 start(spec:any){if(spec.artifactJob)throw Error('artifact_background_execution_requires_foreground_receipt');return super.start(spec);}
}
