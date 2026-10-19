/** Offline replay bridge to the existing authoritative TS controllers; no model/provider. */
import fs from 'node:fs';
import readline from 'node:readline';
import {createCollectionController} from '../src/motif_core/collection_read_policy.ts';
import {createPlanController} from '../src/motif_core/authorized_plan_policy.ts';
const [kind,policyPath,taskPath,schemaPath]=process.argv.slice(2);
if(!['collection','plan'].includes(kind))throw Error('unsupported fixed controller');
const policy=JSON.parse(fs.readFileSync(policyPath,'utf8')),task=JSON.parse(fs.readFileSync(taskPath,'utf8'));
const schemas=JSON.parse(fs.readFileSync(schemaPath,'utf8')).map(r=>({name:'mcp__file_management__'+r.name,parameters:r.inputSchema??r.input_schema}));
const log=[];let id=0;
const controller=(kind==='collection'?createCollectionController:createPlanController)(policy,task,r=>log.push(r));
for await (const line of readline.createInterface({input:process.stdin,crlfDelay:Infinity})){
 const request=JSON.parse(line);
 if(request.operation==='observe')controller.observe(request.exec,request.result);
 else if(request.operation!=='propose')throw Error('unsupported replay operation');
 const tools=request.changedSchema?schemas.map(r=>({...r,parameters:{...r.parameters,changed:true}})):schemas;
 const proposals=controller.propose(tools,()=>String(++id));
 process.stdout.write(JSON.stringify({proposals,halted:controller.halted,done:controller.done,pending:controller.pending,log})+'\n');
}
