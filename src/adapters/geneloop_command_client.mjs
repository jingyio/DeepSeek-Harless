/** Stream a native Bash child through the account's private socket. No host credentials. */
import {request} from 'node:http';
const payload=Buffer.from(process.argv[3]??'','base64url');
let receivedExit=false;
const req=request({socketPath:process.argv[2],path:'/run',method:'POST',headers:{'Content-Type':'application/json','Content-Length':payload.length}},res=>{
 if(res.statusCode!==200){res.resume();process.stderr.write('Isolated command admission failed\n');process.exitCode=1;return;}
 let pending='';
 res.setEncoding('utf8');
 res.on('data',chunk=>{
  pending+=chunk;
  let end;
  while((end=pending.indexOf('\n'))>=0){
   const row=JSON.parse(pending.slice(0,end));pending=pending.slice(end+1);
   if(row.stdout)process.stdout.write(Buffer.from(row.stdout,'base64'));
   if(row.stderr)process.stderr.write(Buffer.from(row.stderr,'base64'));
   if(Number.isInteger(row.exit)){receivedExit=true;process.exitCode=row.exit;}
  }
 });
 res.on('end',()=>{if(!receivedExit)process.exitCode=1;});
 res.on('error',()=>{process.exitCode=1;});
});
req.on('error',()=>{process.stderr.write('Isolated command service unavailable\n');process.exitCode=1;});
for(const signal of ['SIGTERM','SIGINT'])process.on(signal,()=>{req.destroy();process.exit(130);});
req.end(payload);
