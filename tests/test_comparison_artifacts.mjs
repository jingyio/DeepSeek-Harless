import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,readFileSync,writeFileSync,rmSync,symlinkSync} from 'node:fs';
import {join,resolve,sep} from 'node:path';
import {tmpdir} from 'node:os';
import {comparisonArtifacts,verifiedReportFiles,captureComparisonDeliveries} from '../src/adapters/harless_comparison_artifacts.ts';
import {createHash} from 'node:crypto';
test('Only derived results are copied; prior results survive edits and mutated copies fail closed',()=>{
 const root=mkdtempSync(join(tmpdir(),'paired-artifact-'));try {
  const work=join(root,'work');for(const name of ['outputs','inputs','literature'])mkdirSync(join(work,name),{recursive:true});
  writeFileSync(join(work,'outputs/deck.pptx'),'first result');writeFileSync(join(work,'inputs/private.pdf'),'source');writeFileSync(join(work,'outputs/config.json'),'not a deliverable');
  writeFileSync(join(work,'literature/task.json'),'private question');writeFileSync(join(work,'literature/research-notes.md'),'notes');
  const service=comparisonArtifacts(root),rows=service.snapshot('comparison-one','baseline',0,work);
  assert.equal(rows.length,1);assert.equal(rows[0].name,'outputs/deck.pptx');
  writeFileSync(join(work,'outputs/deck.pptx'),'edited after first turn');assert.equal(service.read('comparison-one','baseline',rows[0]).toString(),'first result');
  assert.deepEqual(service.snapshot('comparison-one','baseline',0,work),rows);
  assert.throws(()=>service.read('comparison-one','motif',rows[0]));
  writeFileSync(join(root,'comparison-artifacts/comparison-one/baseline/0',rows[0].id),'changed file');assert.throws(()=>service.read('comparison-one','baseline',rows[0]),/version_changed/);
  writeFileSync(join(work,'literature/delivery-receipt.json'),'{}');const next=service.snapshot('comparison-two','motif',0,work);assert.equal(next.length,2);
 }finally {const absolute=resolve(root);assert.ok(absolute.startsWith(resolve(tmpdir())+sep)&&absolute.includes('paired-artifact-'));rmSync(absolute,{recursive:true,force:true});}
});

test('Unverified layout PDFs are withheld; delivery grants require matching PDF bytes',()=>{
 const root=mkdtempSync(join(tmpdir(),'paired-report-proof-'));try{
  const work=join(root,'work'),output=join(work,'outputs/report'),path=join(output,'report.pdf');
  mkdirSync(join(output,'records'),{recursive:true});writeFileSync(path,'diagnostic PDF bytes');
  const service=comparisonArtifacts(root);
  assert.equal(service.snapshot('failed-draft','motif',0,work,verifiedReportFiles(work)).length,0);
  const eventsPath=join(root,'task-events.jsonl');
  const context={turn:'budget-final-summary',lane:'motif',attempt:0,workspace:work,adapter:'data-report',status:'budget_exhausted',
    eventsPath,startedAt:new Date(1000).toISOString(),finishedAt:new Date(2000).toISOString()};
  assert.equal(captureComparisonDeliveries(service,context).length,0);
  const receipt={kind:'delivery',payload:{delivered:true,quality_passed:true,path,sha256:createHash('sha256').update('diagnostic PDF bytes').digest('hex')}};
  writeFileSync(join(output,'records/delivery.json'),JSON.stringify(receipt));
  assert.equal(service.snapshot('delivered-report','motif',0,work,verifiedReportFiles(work)).length,1);
  const events=time=>[
    {type:'tool/call',time,data:{callId:'delivery-call',name:'mcp__research_report__deliver_report'}},
    {type:'tool/result',time:time+1,data:{message:{content:[{type:'tool-result',toolCallId:'delivery-call',isError:false,
      content:[{type:'text',text:JSON.stringify({ok:true,...receipt.payload})}]}]}}},
  ].map(e=>JSON.stringify(e)).join('\n');
  writeFileSync(eventsPath,events(100)+'\n'+events(3000));
  assert.equal(captureComparisonDeliveries(service,context).length,0,'prior or later turns cannot grant the failed turn a file');
  writeFileSync(eventsPath,events(1500));
  assert.equal(captureComparisonDeliveries(service,context).length,1);
  assert.equal(service.snapshot('old-empty-index','motif',0,work,new Set()).length,0);
  assert.equal(captureComparisonDeliveries(service,{...context,turn:'old-empty-index',status:'completed'}).length,0,'ordinary calls do not rewrite an immutable index');
  writeFileSync(eventsPath,events(3000));
  assert.equal(captureComparisonDeliveries(service,{...context,turn:'old-empty-index',status:'completed',recoverMissing:true}).length,0,'later turn deliveries cannot repair an older completed turn');
  writeFileSync(eventsPath,events(1500));
  const recovered=captureComparisonDeliveries(service,{...context,turn:'old-empty-index',status:'completed',recoverMissing:true});
  assert.equal(recovered.length,1,'task-bound evidence repairs an old empty download index');
  assert.equal(service.read('old-empty-index','motif',recovered[0]).toString(),'diagnostic PDF bytes');
  assert.equal(captureComparisonDeliveries(service,{...context,turn:'still-running',status:'running'}).length,0);
  assert.equal(captureComparisonDeliveries(service,{...context,turn:'unverified-scene',adapter:'ppt'}).length,0);
  writeFileSync(path,'modified PDF');assert.equal(verifiedReportFiles(work).size,0);
  assert.equal(captureComparisonDeliveries(service,{...context,turn:'changed-delivery'}).length,0);
 }finally{const p=resolve(root);assert.ok(p.startsWith(resolve(tmpdir())+sep)&&p.includes('paired-report-proof-'));rmSync(p,{recursive:true,force:true});}
});
test('Result symlinks cannot expose files outside the Session', {skip:process.platform==='win32'},()=>{
 const root=mkdtempSync(join(tmpdir(),'paired-artifact-'));try{
  const work=join(root,'work');mkdirSync(join(work,'outputs'),{recursive:true});writeFileSync(join(root,'secret.txt'),'never expose');symlinkSync(join(root,'secret.txt'),join(work,'outputs/leak.txt'));
  assert.equal(comparisonArtifacts(root).snapshot('comparison-one','baseline',0,work).length,0);
 }finally{const absolute=resolve(root);assert.ok(absolute.startsWith(resolve(tmpdir())+sep)&&absolute.includes('paired-artifact-'));rmSync(absolute,{recursive:true,force:true});}
});

test('A delivered report includes only its hash-checked figure chain and repairs old draft-filled indexes',()=>{
 const root=mkdtempSync(join(tmpdir(),'paired-report-chain-'));try{
  const work=join(root,'work'),directory=join(work,'outputs/report/records');mkdirSync(directory,{recursive:true});
  const makeFile=(name,text)=>{const path=join(work,'outputs/report',name);mkdirSync(join(path,'..'),{recursive:true});writeFileSync(path,text);return{path,sha256:createHash('sha256').update(text).digest('hex')};};
  const pdf=makeFile('artifacts/draft/report/version/research_report.pdf','verified report');
  const figure=makeFile('artifacts/evidence/figures/figure_01.png','verified figure');
  const draft=makeFile('artifacts/draft/failed.pdf','failed unverified layout');
  const plan='plan-one',meta={workspace_id:'this-workspace',source_version:'source-v1'};
  let index=0;
  const record=(kind,payload)=>{const id='rra-'+kind+'-'+(++index).toString(16).padStart(32,'0');writeFileSync(join(directory,id+'.json'),JSON.stringify({id,kind,...meta,payload:{plan_id:plan,...payload}}));return id;};
  const bundle=record('figure_bundle',{analysis_id:'analysis',evidence_id:'evidence',figures:[{paths:{png:figure.path},sha256:{png:figure.sha256}}]});
  const packet=record('evidence_packet',{quality_passed:true,analysis_id:'analysis',evidence_id:'evidence',figure_bundle_id:bundle});
  const reportDraft=record('report_draft',{packet_id:packet});
  const report=record('report',{quality_passed:true,...pdf,draft_id:reportDraft});
  record('delivery',{delivered:true,quality_passed:true,...pdf,report_id:report});
  assert.deepEqual([...verifiedReportFiles(work)].sort(),[pdf.path,figure.path].sort());
  assert.equal(verifiedReportFiles(work,new Map()).size,0,'no report tool event means no report or figures for historical recovery');
  const proof=new Map([[pdf.path,pdf.sha256]]);
  assert.equal(verifiedReportFiles(work,proof).size,2);
  const service=comparisonArtifacts(root),old=service.snapshot('old-unfiltered','motif',0,work);
  assert.equal(old.length,3);
  const filtered=service.snapshot('old-unfiltered','motif',0,work,verifiedReportFiles(work,proof),true);
  assert.equal(filtered.length,2);assert.ok(filtered.every(row=>row.verification==='data-report-delivery-v1'));
  assert.ok(filtered.every(row=>!row.name.endsWith('failed.pdf')));
  assert.ok(filtered.every(row=>old.find(prior=>prior.id===row.id)),'old immutable file identities survive verification');
  writeFileSync(figure.path,'modified chart');
  assert.deepEqual([...verifiedReportFiles(work,proof)],[pdf.path]);
  const foreign=join(root,'private.png');writeFileSync(foreign,'verified figure');
  const row=JSON.parse(readFileSync(join(directory,bundle+'.json'),'utf8'));
  row.payload.figures[0].paths.png=foreign;writeFileSync(join(directory,bundle+'.json'),JSON.stringify(row));
  assert.deepEqual([...verifiedReportFiles(work,proof)],[pdf.path],'a referenced chart outside this Session is never published');
 }finally{const path=resolve(root);assert.ok(path.startsWith(resolve(tmpdir())+sep)&&path.includes('paired-report-chain-'));rmSync(path,{recursive:true,force:true});}
});
