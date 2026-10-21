/** Mirror only the native turn which was already open when its Task closed.
 * Cancellation acknowledgement precedes native tool/turn settlement. The
 * journal stays authoritative; this fence neither revives a Task nor grants
 * another model request, goal round or session any execution authority.
 */
export function createClosingTurnMirror(append:(task:any,event:any)=>void){
 const closing=new Map<string,{task:any;session:any;turn:number;after:number}>();
 const terminalEvents=new Set(['assistant/message','assistant/attempt','tool/result','step/end','turn/end']);
 return {
  arm(task:any,agent:any){
   const session=agent?.session;
   if(!session||session.id!==task.request.session_id)return;
   const events=session.snapshotEvents(),start=events.findLast((e:any)=>e.type==='turn/start');
   if(!start||!Number.isSafeInteger(start.data?.turn)||
    events.some((e:any)=>e.type==='turn/end'&&e.seq>start.seq&&e.data?.turn===start.data.turn))return;
   closing.set(session.id,{task,session,turn:start.data.turn,after:events.at(-1).seq});
  },
  record(session:any,event:any){
   const row=closing.get(session.id);
   if(!row||row.session!==session||!Number.isSafeInteger(event.seq)||event.seq<=row.after)return false;
   if(event.type==='turn/start'){closing.delete(session.id);return false;}
   if(event.data?.turn!==row.turn||!terminalEvents.has(event.type))return false;
   append(row.task,event);row.after=event.seq;
   if(event.type==='turn/end')closing.delete(session.id);
   return true;
  },
  release(task:any){for(const [id,row]of closing)if(row.task===task)closing.delete(id);},
 };
}
