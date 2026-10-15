/** Replay the same Runtime against durable root-session observations, no API. */
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { resolve, join, relative, isAbsolute } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
import { createOnlineInterceptor } from '../src/adapters/dsh_online_motif.mjs';
import { digest, proposeReadyBatch } from '../src/motif_core/online_skill_runtime.mjs';
import { closedCitationBatchRead } from '../src/adapters/dsh_paper_motif.ts';

const json = p => JSON.parse(readFileSync(p, 'utf8'));
const jsonl = p => readFileSync(p, 'utf8').split('\n').filter(s => s.trim()).map(JSON.parse);
const sha = p => createHash('sha256').update(readFileSync(p)).digest('hex');

export function classifyResponse(content, proposals) {
  if (!proposals.length) return 'no_candidate';
  const calls = content.filter(b => b.type === 'tool-call');
  const keys = rows => rows.map(r => digest({ name: r.name ?? r.tool,
    arguments: typeof r.arguments === 'string' ? JSON.parse(r.arguments) : r.arguments })).sort();
  if (JSON.stringify(keys(calls)) !== JSON.stringify(keys(proposals))) return 'mixed_or_different_tools';
  if (content.some(b => (b.type === 'text' && b.text?.trim()) || !['tool-call', 'text'].includes(b.type)))
    return 'text_or_semantic_review';
  return 'closed_tool_continuation';
}

export async function evaluate(run) {
  const config = json(join(run,'manifest.json')), metrics = json(join(run,'metrics.json'));
  if (config.mode !== 'shadow' || metrics.status !== 'completed') throw Error('completed real shadow required');
  const task = json(join(run,'task.json')), manifest = json(join(run,'online-manifest-snapshot.json'));
  const eventPath=join(run,'session-events.jsonl');
  const events=jsonl(eventPath).filter(r => r.session_id===config.session_id).map(r => r.event);
  const receipts=(await import('node:fs')).readdirSync(join(run,'requests')).filter(n => /^\d+\.json$/.test(n)).sort();
  const runtime=createOnlineInterceptor({manifest,task,mode:'shadow',similarity:async()=>[],closedContinuation:closedCitationBatchRead});
  const calls=new Map(), observed=new Set(), responses=[];
  for (const event of events) {
    const data=event.data;
    if (event.type==='assistant/message') {
      const receipt=receipts[responses.length];
      const schemas=receipt?json(join(run,'requests',receipt)).tools:[];
      const tools=new Map(schemas.map(t => [t.function.name,{name:t.function.name,parameters:t.function.parameters}]));
      const proposals=await proposeReadyBatch({manifest,task,history:runtime.state(task.session_id).history,
        availableTools:tools,similarity:async()=>[],minSimilarity:0.8,minMargin:0.1,closedContinuation:closedCitationBatchRead});
      const content=data.message.content;
      responses.push({step:data.step,turn:data.turn,classification:classifyResponse(content,proposals),
        proposed_tools:proposals.map(r=>r.tool),actual_tools:content.filter(b=>b.type==='tool-call').map(b=>b.name)});
    } else if (event.type==='tool/call') {
      calls.set(data.callId,{name:data.name,callId:data.callId,
        arguments:typeof data.arguments==='string'?JSON.parse(data.arguments):data.arguments});
    } else if (event.type==='tool/result' && (!event.surfaceOp || event.surfaceOp==='append' || event.surfaceOp.op==='append')) {
      const id=data.message?.source?.callId;
      if (!id || observed.has(id)) continue;
      const call=calls.get(id), blocks=data.message?.content;
      if (!call || !Array.isArray(blocks) || blocks.length!==1 || blocks[0].type!=='tool-result') continue;
      observed.add(id);
      runtime.observe(task.session_id,call,{content:blocks[0].content,isError:!!data.error || !!blocks[0].isError});
    }
  }
  const replayCandidates=responses.filter(r=>r.classification!=='no_candidate').length;
  const auditPath=join(run,'work/.local/online-motif',createHash('sha256').update(task.session_id).digest('hex')+'.jsonl');
  const live=jsonl(auditPath), liveCandidates=live.filter(r=>r.kind==='shadow_candidate').length;
  let liveOrdinal=0; const liveIndexes=[];
  for(const row of live) {
    if(row.kind==='motif_stream_seen' && row.reason==='session_matched') liveOrdinal++;
    if(row.kind==='shadow_candidate') liveIndexes.push(liveOrdinal);
  }
  const replayIndexes=responses.flatMap((r,i)=>r.classification==='no_candidate'?[]:[i+1]);
  const aligned=liveOrdinal===responses.length && responses.length===metrics.actual_requests &&
    JSON.stringify(liveIndexes)===JSON.stringify(replayIndexes);
  const count=responses.filter(r=>r.classification==='closed_tool_continuation').length;
  return {kind:'real_shadow_offline_replay',actual_requests:metrics.actual_requests,actual_skipped_requests:0,
    live_candidates:liveCandidates,replay_candidates:replayCandidates,replay_count_aligned:aligned,
    live_candidate_request_indexes:liveIndexes,replay_candidate_request_indexes:replayIndexes,
    whole_request_opportunities:aligned?count:null,opportunity_fraction:aligned?count/metrics.actual_requests:null,
    classifications:Object.fromEntries([...new Set(responses.map(r=>r.classification))].map(k=>[k,responses.filter(r=>r.classification===k).length])),
    quality_review:'not_blind_reviewed',execution_authorized_by_replay:false,responses,
    evidence_sha256:{events:sha(eventPath),manifest:sha(join(run,'online-manifest-snapshot.json')),task:sha(join(run,'task.json')),audit:sha(auditPath)}};
}

if (process.argv[1] && import.meta.url===pathToFileURL(resolve(process.argv[1])).href) {
  const root=resolve(import.meta.dirname,'..'), privateRoot=join(root,'.local');
  const run=resolve(process.argv[2]??''), output=resolve(process.argv[3]??'');
  for (const p of [run,output]) {
    const rel=relative(privateRoot,p);
    if (!rel || rel.startsWith('..') || isAbsolute(rel)) throw Error('private input/output required');
  }
  if (existsSync(output)) throw Error('preserve prior evaluation');
  const result=await evaluate(run);writeFileSync(output,JSON.stringify(result,null,2)+'\n',{mode:0o600,flag:'wx'});
  const {responses,evidence_sha256,...summary}=result;console.log(JSON.stringify(summary));
}
