/** Fresh HTTP evidence is lifted outside the network-disabled script sandbox. */
import {mkdtempSync,rmSync} from 'node:fs';
import {join,resolve,relative} from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {scriptArgv} from '../src/adapters/script_motif_shell.ts';
import {scriptCommand} from '../src/adapters/script_motif_runtime.ts';
const root=fileURLToPath(new URL('../',import.meta.url));

export function runCertifiedScript(job){
 const {workspace,program,paths=[],versions=[],nonce,argv=[]}=job;
 const scratch=join(workspace,'code'),temp=mkdtempSync(join(scratch,'.motif-http-'));
 const layout={work:workspace,scratch,inputs:join(workspace,'inputs'),outputs:join(workspace,'outputs/code'),temp:join(workspace,'command-tmp')};
 const http={},evidence=[];const start=Date.now();
 try{
  for(let round=0;round<=12;round++){
   if(Date.now()-start>90000)throw Error('network_script_deadline');
   const command=scriptCommand(program,paths,versions,nonce,{argv,http});
   const commandArgv=scriptArgv(layout,command,'/work',true,{network:'none',ephemeralTemp:true});
   const run=spawnSync(commandArgv[0],commandArgv.slice(1),{encoding:'utf8',timeout:30000,maxBuffer:256000});
   if(run.error||run.status!==0)throw Error('script_sandbox_failed: '+(run.stderr??'').slice(-1000));
   const receipt=JSON.parse(run.stdout);
   if(receipt.kind==='script_motif_receipt')return {...receipt,network_evidence:evidence,elapsed_ms:Date.now()-start};
   if(receipt.kind!=='script_http_demand'||program.network_policy!=='fixed_metadata_get_v1'||round===12)throw Error('invalid_http_demand');
   const file=join(temp,round+'.bin');
   const fetch=spawnSync(process.env.SSS_PYTHON??'python3',[join(root,'scripts/fetch-script-evidence.py'),receipt.url,file],
    {encoding:'utf8',timeout:25000,maxBuffer:4000,env:{PATH:process.env.PATH,PYTHONUTF8:'1',PYTHONDONTWRITEBYTECODE:'1'}});
   if(fetch.error||fetch.status!==0)throw Error('metadata_evidence_fetch_failed: '+(fetch.stderr??'').slice(-500));
   const row=JSON.parse(fetch.stdout);evidence.push(row);
   http[receipt.url]={file:'/work/'+relative(scratch,file),sha256:row.sha256};
  }
 }finally{rmSync(temp,{recursive:true,force:true});}
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 try{const payload=JSON.parse(Buffer.from(process.argv[2],'base64').toString('utf8'));
  console.log(JSON.stringify(payload.control_receipt??(payload.jobs?{kind:'script_cache_batch_receipt',receipts:payload.jobs.map(runCertifiedScript),semantic_quality_accepted:false}:runCertifiedScript(payload))));}
 catch(error){console.error(error.message);process.exitCode=1;}
}
