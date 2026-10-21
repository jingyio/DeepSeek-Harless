/** Display actual SDK events in the owning native chat, preserving dependencies.
 * Original SDK JSONL stays immutable and remains the sole learning evidence.
 */
import {isCompactCheckpointSource} from '@deepseek-ai/dsh-compaction';

export function fileEventProjection(session:any,turn:number){
 const sequences=new Map<number,number>();let step=0,open=false;
 const summaries=new Map<string,any>(),compactions=new Set<string>();
 const append=(event:any,data:any,metadata:any={})=>{
  const result=session.append(event.type,data,metadata);
  sequences.set(event.seq,result?.seq??session.snapshotEvents().at(-1).seq);
 };
 const sources=(event:any)=>event.sourceEventSeqs?.map((seq:number)=>{
  const mapped=sequences.get(seq);if(mapped===undefined)throw Error('missing SDK event dependency');return mapped;
 });
 return (event:any)=>{
  if(event.type==='compaction/start'){
   compactions.add(event.data.compactionId);append(event,{...event.data,turn});return;
  }
  if(event.type==='compaction/summary'){
   summaries.set(event.data.compactionId,event);return;
  }
  if(event.type==='user/message'&&isCompactCheckpointSource(event.data?.source)){
   const summary=summaries.get(event.data.source.compactionId),range=event.surfaceOp;
   if(!summary||!compactions.has(event.data.source.compactionId)||range?.op!=='replace')return;
   const original=summary.data.shadowedSeqs,mapped=Array.isArray(original)?original.map((seq:number)=>sequences.get(seq)):[];
   const nodes=session.surface.nodes,start=nodes.indexOf(mapped[0]),end=nodes.indexOf(mapped.at(-1));
   const span=start<0||end<start?[]:nodes.slice(start,end+1);
   // The SDK's initial user message is its generated contract, while the parent
   // contains the user's actual prompt. Never pretend those are interchangeable.
   // Only an exactly mapped, contiguous parent surface may receive a checkpoint.
   const equivalent=mapped.length>0&&mapped.every((seq:any)=>Number.isInteger(seq))&&
    range.startSeq===original[0]&&range.endSeq===original.at(-1)&&
    summary.data.shadowedRange?.start===range.startSeq&&summary.data.shadowedRange?.end===range.endSeq&&
    span.length===mapped.length&&span.every((seq:number,i:number)=>seq===mapped[i])&&
    event.sourceEventSeqs?.every((seq:number)=>seq===summary.seq||sequences.has(seq));
   session.append('geneloop/file-compaction',{phase:'summary',compactionId:event.data.source.compactionId,
    summary:summary.data.summary,sourceShadowedRange:summary.data.shadowedRange,sourceShadowedSeqs:original,
    shadowedTokenCount:summary.data.shadowedTokenCount,...(summary.data.usage?{usage:summary.data.usage}:{}),
    projectedSurface:equivalent,turn});
   if(equivalent){
    append(summary,{...summary.data,shadowedRange:{start:mapped[0],end:mapped.at(-1)},shadowedSeqs:mapped});
    append(event,event.data,{surfaceOp:{op:'replace',startSeq:mapped[0],endSeq:mapped.at(-1)},sourceEventSeqs:sources(event)});
   }
   return;
  }
  if(event.type==='compaction/end'){
   if(compactions.delete(event.data.compactionId)){append(event,{...event.data,turn});summaries.delete(event.data.compactionId);}return;
  }
  if(!['step/start','step/end','assistant/attempt','assistant/message','tool/call','tool/result','todo/write','llm/retry','llm/retry-started'].includes(event.type))return;
  if(event.type==='step/start'){if(open)throw Error('overlapping file SDK steps');step++;open=true;}
  if(!open)throw Error('file SDK event outside its recorded step');
  const data={...event.data,turn,step};
  const metadata:any={};
  if(event.surfaceOp!==undefined){
   if(event.surfaceOp!=='append')throw Error('unsupported SDK surface rewrite; preserve original trace');
   metadata.surfaceOp='append';
  }
  if(event.sourceEventSeqs)metadata.sourceEventSeqs=sources(event);
  append(event,data,metadata);
  if(event.type==='step/end')open=false;
 };
}
