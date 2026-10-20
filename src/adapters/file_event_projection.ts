/** Display actual SDK events in the owning native chat, preserving dependencies.
 * Original SDK JSONL stays immutable and remains the sole learning evidence.
 */
export function fileEventProjection(session:any,turn:number){
 const sequences=new Map<number,number>();let step=0,open=false;
 return (event:any)=>{
  if(!['step/start','step/end','assistant/attempt','assistant/message','tool/call','tool/result'].includes(event.type))return;
  if(event.type==='step/start'){if(open)throw Error('overlapping file SDK steps');step++;open=true;}
  if(!open)throw Error('file SDK event outside its recorded step');
  const data={...event.data,turn,step};
  const metadata:any={};
  if(event.surfaceOp!==undefined){
   if(event.surfaceOp!=='append')throw Error('unsupported SDK surface rewrite; preserve original trace');
   metadata.surfaceOp='append';
  }
  if(event.sourceEventSeqs){metadata.sourceEventSeqs=event.sourceEventSeqs.map((seq:number)=>{
   const projected=sequences.get(seq);if(projected===undefined)throw Error('missing SDK event dependency');return projected;
  });}
  const result=session.append(event.type,data,metadata);
  sequences.set(event.seq,result?.seq??session.snapshotEvents().at(-1).seq);
  if(event.type==='step/end')open=false;
 };
}
