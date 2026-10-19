/** Explicit validation-only draft stop after actual v1 deferral. No effects or fake receipt. */
import {readFileSync,existsSync,writeFileSync} from 'node:fs';
import {resolve,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {isAgentLoopRequest} from '@deepseek-ai/dsh-llm';
import {terminalStream} from '../motif_core/terminal_receipt_policy.ts';
export const name='sss-script-repair-probe';export const inject=['llm'];
const root=resolve(fileURLToPath(new URL('../../',import.meta.url)));
export function repairDraft(probe:any,options:any){
 if(!probe||probe.enabled!==true||existsSync(probe.marker)||!isAgentLoopRequest(options)
  ||options.messages?.some((m:any)=>m.source?.kind==='task-acceptance-repair')||!existsSync(probe.audit_file))return null;
 const rows=readFileSync(probe.audit_file,'utf8').trim().split('\n').filter(Boolean).map(JSON.parse);
 const deferred=rows.find((r:any)=>r.kind==='learned_script_deferred');if(!deferred)return null;
 writeFileSync(probe.marker,JSON.stringify({kind:'controlled_uncompleted_draft',deferred,session_id:options.sessionId,
  source:'explicit validation control; no real model decision or successful receipt',effects_authorized_by_probe:false}),{mode:0o600});
 return terminalStream({status:'uncompleted_controlled_draft',reason:'旧脚本已失效，当前没有实际交付；请原固定程序验收，随后由普通Harness在原任务内修复。'});
}
export function apply(ctx:any){
 const file=process.env.SSS_SCRIPT_REPAIR_PROBE;if(!file)return;
 if(!resolve(file).startsWith(resolve(root,'.local')+sep))throw Error('private repair probe only');
 const probe=JSON.parse(readFileSync(file,'utf8'));
 if([probe.marker,probe.audit_file].some((p:any)=>typeof p!=='string'||!resolve(p).startsWith(resolve(root,'.local')+sep)))throw Error('invalid repair probe paths');
 ctx.on('llm/stream',(options:any,next:()=>any)=>repairDraft(probe,options)??next(),{global:true});
}
