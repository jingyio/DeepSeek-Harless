import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,rmSync,symlinkSync} from 'node:fs';
import {join,resolve,sep} from 'node:path';
import {tmpdir} from 'node:os';
import {comparisonArtifacts,verifiedReportFiles} from '../src/adapters/harless_comparison_artifacts.ts';
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
  const receipt={kind:'delivery',payload:{delivered:true,quality_passed:true,path,sha256:createHash('sha256').update('diagnostic PDF bytes').digest('hex')}};
  writeFileSync(join(output,'records/delivery.json'),JSON.stringify(receipt));
  assert.equal(service.snapshot('delivered-report','motif',0,work,verifiedReportFiles(work)).length,1);
  writeFileSync(path,'modified PDF');assert.equal(verifiedReportFiles(work).size,0);
 }finally{const p=resolve(root);assert.ok(p.startsWith(resolve(tmpdir())+sep)&&p.includes('paired-report-proof-'));rmSync(p,{recursive:true,force:true});}
});
test('Result symlinks cannot expose files outside the Session', {skip:process.platform==='win32'},()=>{
 const root=mkdtempSync(join(tmpdir(),'paired-artifact-'));try{
  const work=join(root,'work');mkdirSync(join(work,'outputs'),{recursive:true});writeFileSync(join(root,'secret.txt'),'never expose');symlinkSync(join(root,'secret.txt'),join(work,'outputs/leak.txt'));
  assert.equal(comparisonArtifacts(root).snapshot('comparison-one','baseline',0,work).length,0);
 }finally{const absolute=resolve(root);assert.ok(absolute.startsWith(resolve(tmpdir())+sep)&&absolute.includes('paired-artifact-'));rmSync(absolute,{recursive:true,force:true});}
});
