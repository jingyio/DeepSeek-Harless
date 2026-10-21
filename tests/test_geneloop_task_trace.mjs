import test from 'node:test';
import assert from 'node:assert/strict';
import {createClosingTurnMirror} from '../src/adapters/geneloop_task_trace.ts';

function fixture(){
 const appended=[],task={request:{session_id:'session-own'}},events=[{type:'turn/start',seq:10,data:{turn:2}}];
 const session={id:'session-own',snapshotEvents:()=>events};
 return {task,session,events,appended,mirror:createClosingTurnMirror((task,event)=>appended.push({task,event}))};
}
test('closing trace accepts exact native session and open turn, rejects impersonation, duplicates and future turns',()=>{
 const f=fixture();f.mirror.arm(f.task,{session:f.session});
 const result={type:'tool/result',seq:11,data:{turn:2}};
 assert.equal(f.mirror.record({...f.session},result),false);
 assert.equal(f.mirror.record(f.session,{...result,data:{turn:1}}),false);
 assert.equal(f.mirror.record(f.session,{type:'tool/call',seq:11,data:{turn:2}}),false);
 assert.equal(f.mirror.record(f.session,result),true);
 assert.equal(f.mirror.record(f.session,result),false);
 assert.equal(f.mirror.record(f.session,{type:'turn/start',seq:12,data:{turn:3}}),false);
 assert.equal(f.mirror.record(f.session,{type:'turn/end',seq:13,data:{turn:2}}),false);
 assert.deepEqual(f.appended,[{task:f.task,event:result}]);
});
test('closed turns and foreign tasks cannot create a closing trace; release is exact-task scoped',()=>{
 const f=fixture();f.mirror.arm({request:{session_id:'foreign'}},{session:f.session});
 const end={type:'turn/end',seq:11,data:{turn:2,reason:{kind:'aborted'}}};
 assert.equal(f.mirror.record(f.session,end),false);
 f.mirror.arm(f.task,{session:f.session});f.mirror.release({...f.task});
 assert.equal(f.mirror.record(f.session,end),true);
 assert.equal(f.mirror.record(f.session,{...end,seq:12}),false);
 f.events.push(end);f.mirror.arm(f.task,{session:f.session});
 assert.equal(f.mirror.record(f.session,{...end,seq:12}),false);
 f.events.pop();f.mirror.arm(f.task,{session:f.session});f.mirror.release(f.task);
 assert.equal(f.mirror.record(f.session,end),false);
});
