/** Server historical-artifact diagnostic with real MCP packets; no model. */
import { readFileSync, writeFileSync, mkdirSync, existsSync, chmodSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createDeliveryChecker } from '../src/adapters/dsh_paper_delivery_check.ts';
import { snapshotSource, sha256 } from '../src/adapters/paper_triage_validation.ts';

const root=resolve(fileURLToPath(new URL('..',import.meta.url))), privateRoot=join(root,'.local');
const [expArg,runArg,outArg]=process.argv.slice(2);
if(!expArg||!runArg||!outArg)throw Error('Usage: node scripts/check-paper-delivery.mjs PRIVATE_EXPERIMENT HISTORICAL_RUN NEW_PRIVATE_OUTPUT');
const exp=resolve(expArg),run=resolve(runArg),out=resolve(outArg);
for(const p of [exp,run,out])if(!p.startsWith(privateRoot+'/'))throw Error('private paths required');
if(existsSync(out))throw Error('preserve previous diagnostic');
mkdirSync(join(out,'work'),{recursive:true,mode:0o700});
const inputs=JSON.parse(readFileSync(join(exp,'inputs.json'),'utf8'));
const packet=JSON.parse(readFileSync(join(exp,'evidence-packet-manuscript.json'),'utf8'));
const source=join(inputs.manuscript.root,'source'),work=join(out,'work');
const bytes=readFileSync(join(run,'work','triage.json'));writeFileSync(join(work,'triage.json'),bytes,{mode:0o600});
const config={schema_version:1,mode:'enforce',case_id:'manuscript',session_id:'private-historical-delivery',
  work,source_root:source,source_files:snapshotSource(source),source_version:packet.version_sha256};
const audit=[],checker=createDeliveryChecker(config,r=>audit.push(r));
checker.observe({name:'mcp__paper_checks__collect_paper_citation_evidence',callId:'recorded-packet',arguments:{case_id:'manuscript'}},
  {isError:false,value:{structuredContent:packet}});
const checked=checker.check();
const feedback=await checker.after({name:'write',callId:'historical-write',arguments:{file_path:'triage.json'},signal:new AbortController().signal},
  {isError:false,content:[{type:'text',text:'historical artifact copied to diagnostic workspace'}]},async()=>({kind:'accept'}));
const result={kind:'historical_artifact_and_public_hook_diagnostic',real_model_requests:0,api_cost_usd:0,
  input_run_id:run.split('/').at(-1),input_report_sha256:sha256(bytes),packet_sha256:sha256(readFileSync(join(exp,'evidence-packet-manuscript.json'))),
  check:checked,hook_decision:feedback.kind,automatic_checks:audit.filter(r=>r.kind==='paper_delivery_check').length,
  semantic_quality:'not_reviewed',request_savings:'not_measured',learned_motif:false};
writeFileSync(join(out,'verification.json'),JSON.stringify(result,null,2)+'\n',{mode:0o600});
writeFileSync(join(out,'config.json'),JSON.stringify(config,null,2)+'\n',{mode:0o600});
writeFileSync(join(out,'audit.json'),JSON.stringify(audit,null,2)+'\n',{mode:0o600});chmodSync(out,0o700);
process.stdout.write(JSON.stringify(result)+'\n');
