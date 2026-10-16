import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {paperPdfDelivered,paperReferenceReportRequired} from '../src/adapters/harless_paper_delivery.ts';

test('general proofreading stays compatible; reference output is task/source/hash bound', () => {
  const work=mkdtempSync(join(tmpdir(),'paper-delivery-'));
  const write=(name,value)=>{ const path=join(work,name);mkdirSync(join(path,'..'),{recursive:true});writeFileSync(path,typeof value==='string'?value:JSON.stringify(value)); };
  const hash=value=>createHash('sha256').update(value).digest('hex');
  const task={workspace:work,scene:{id:'paper-proofreading'},scene_options:{allow_output:true},request:{task_id:'current'}};
  try {
    write('paper-output-grant.json',{task_id:'current',allow_output:true,audit_sha256:null});
    write('approved-inputs.json',{files:{'paper.txt':'a'.repeat(64)}});
    write('outputs/paper-audits/previous/draft.json',{});
    assert.equal(paperReferenceReportRequired(task),false,'ordinary reports keep main export recovery');
    assert.equal(paperPdfDelivered(task),true,'old reference tasks do not impose reference output on ordinary proofreading');
    write('outputs/paper-audits/current/draft.json',{});
    assert.equal(paperReferenceReportRequired(task),true,'only this task reference draft selects the reference path');
    assert.equal(paperPdfDelivered(task),false,'a started reference draft cannot silently finish without a report');
    const pdf='diagnostic PDF bytes',md='reviewed source words';
    write('outputs/documents/report/paper-review.pdf',pdf);write('outputs/documents/report/paper-review.md',md);
    const receipt={task_id:'previous',kind:'source_bound_review',category:'paper-review',layout_passed:true,
      source_versions:{'paper.txt':'a'.repeat(64)},files:['paper-review.pdf','paper-review.md'].map((name,i)=>({name:'outputs/documents/report/'+name,sha256:hash(i?md:pdf)}))};
    write('outputs/documents/report/delivery.json',receipt);
    assert.equal(paperPdfDelivered(task),false,'a previous task report is not current delivery');
    receipt.task_id='current';write('outputs/documents/report/delivery.json',receipt);
    assert.equal(paperPdfDelivered(task),true,'main generic exporter can deliver a source-bound reference review');
    write('outputs/documents/report/paper-review.pdf','tampered');
    assert.equal(paperPdfDelivered(task),false,'changed output bytes are rejected');
    write('outputs/documents/report/paper-review.pdf',pdf);
    receipt.source_versions['paper.txt']='b'.repeat(64);write('outputs/documents/report/delivery.json',receipt);
    assert.equal(paperPdfDelivered(task),false,'another source version is rejected');
    write('outputs/current-export/reference-check-report.pdf',pdf);
    const legacy={artifact_file:'outputs/current-export/reference-check-report.pdf',output_sha256:hash(pdf),content_coverage:{all_fields_present:false}};
    write('outputs/current-export/export-receipt.json',legacy);
    assert.equal(paperPdfDelivered(task),false,'failed content coverage is rejected');
    legacy.content_coverage.all_fields_present=true;write('outputs/current-export/export-receipt.json',legacy);
    assert.equal(paperPdfDelivered(task),true,'the reviewed historical renderer remains supported');
    assert.equal(paperReferenceReportRequired(task),true,'a reference PDF must not trigger a second generic export');
    task.scene_options.allow_output=false;
    assert.equal(paperPdfDelivered(task),true,'output-disabled tasks retain ordinary completion');
  } finally {rmSync(work,{recursive:true,force:true});}
});
