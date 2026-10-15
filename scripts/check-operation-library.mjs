/** Validate public original learned policies without private evidence or a model. */
import {readFileSync,readdirSync} from 'node:fs';
import {resolve,dirname,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {validateOperationPolicy} from '../src/motif_core/operation_graph_policy.ts';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..'),bundle=join(root,'examples/motif-library/file-management-operation-v2');
const read=p=>JSON.parse(readFileSync(p,'utf8')),sha=p=>createHash('sha256').update(readFileSync(p)).digest('hex');
const need=(v,s)=>{if(!v)throw Error(s);};const cat=read(join(bundle,'catalog.json')),lock=read(join(bundle,'files.lock.json'));
need(cat.format==='sss-public-operation-library-v2'&&cat.default_activation===false&&cat.includes_private_runtime_admission_proofs===false,'invalid publication boundary');
for(const [name,h] of Object.entries(lock.sha256)){need(!name.includes('..')&&!name.startsWith('/')&&sha(join(bundle,name))===h,'changed policy bytes');}
const result=[];
for(const e of cat.entries){
 const p=validateOperationPolicy(read(join(bundle,e.path)));need(sha(join(bundle,e.path))===e.sha256&&p.policy_digest===e.policy_digest,'changed original policy');
 need(e.original_status==='certified_motif_v2'&&e.holdout_used===false&&e.quality_and_permission_required===true,'unverified source status');
 need(e.reviews.length===3&&new Set(e.reviews.map(r=>r.task_fingerprint)).size===3&&e.reviews.every(r=>!p.artifact.source_task_fingerprints.includes(r.task_fingerprint)),'overlapping decisions');
 need(e.reviews.filter(r=>r.role==='candidate_certification').length===2&&e.reviews.filter(r=>r.role==='candidate_certification').every(r=>r.completion_count>=1),'missing actual guarded executions');
 const incompatible=Object.entries(e.runtime_source).filter(([name,h])=>{try{return sha(join(root,name))!==h;}catch{return true;}}).map(([name])=>name);
 if(process.argv.includes('--require-runtime'))need(!incompatible.length,'current execution source differs from original certification');
 result.push({entry:e.entry_id,nodes:p.artifact.nodes.length,matching_runtime:!incompatible.length,incompatible});
}
need(result.length===4,'incomplete public library');console.log(JSON.stringify({passed:true,policies:result,automatic_activation:false,cloud_requests:0},null,2));
