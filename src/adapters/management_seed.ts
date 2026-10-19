/** Admission of read-only product seed attestations; task grants stay native. */
import {readFileSync,lstatSync} from 'node:fs';
import {resolve,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {digest} from '../motif_core/online_skill_runtime.mjs';
const root=resolve(fileURLToPath(new URL('../../',import.meta.url)));
const sha=(p:string)=>createHash('sha256').update(readFileSync(p)).digest('hex');
export function validatePublicManagementSeed(policy:any,cert:any,raw:string,runtime:any){
  if(cert.format!=='sss-management-seed-attestation-v1'||!/^file-v[1-9][0-9]*$/.test(cert.release))throw Error('invalid public seed');
  const release=join(root,'motif-libraries',cert.release);
  if(lstatSync(release).isSymbolicLink())throw Error('seed release symlink refused');
  const manifest=JSON.parse(readFileSync(join(release,'entry.json'),'utf8'));
  if(manifest.format!=='sss-management-seed-release-v1'||manifest.digest!==digest(Object.fromEntries(Object.entries(manifest).filter(([k])=>k!=='digest')))
    ||digest(manifest.runtime_source)!==digest(runtime)||Object.entries(runtime).some(([n,h])=>sha(resolve(root,n))!==h))throw Error('seed source/manifest changed');
  for(const [name,h] of Object.entries(manifest.files)){
    if(!/^(?:policies|certificates)\/[a-f0-9]{64}\.json$/.test(name)||lstatSync(join(release,name)).isSymbolicLink()||sha(join(release,name))!==h)throw Error('seed object changed');
  }
  const entry=manifest.entries.find((e:any)=>e.policy_digest===policy.policy_digest);
  if(!entry||entry.payload_sha256!==raw||digest(JSON.parse(readFileSync(join(release,entry.certificate),'utf8')))!==digest(cert)
    ||cert.policy_digest!==policy.policy_digest||cert.payload_sha256!==raw||cert.quality!=='sss-management-quality-v7'
    ||cert.holdout_used!==false||cert.private_evidence_verified!==true||cert.grants_execution!==false)throw Error('seed publication proof changed');
  const w=cert.witnesses;
  if(!Array.isArray(w)||w.length!==3||w.map((r:any)=>r.role).join(',')!=='native_certification,candidate_certification,candidate_certification'
    ||new Set(w.map((r:any)=>r.task_fingerprint)).size!==3
    ||w.some((r:any)=>!r.accepted||!r.lifecycle_verified||r.repairs||r.deferred||!r.observed_usage_complete||policy.artifact.source_task_fingerprints.includes(r.task_fingerprint)))throw Error('seed independent certification missing');
}
