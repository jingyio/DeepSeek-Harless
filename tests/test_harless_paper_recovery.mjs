import test from 'node:test';
import assert from 'node:assert/strict';
import {createPaperRecovery,paperExportRequested} from '../src/adapters/harless_paper_recovery.ts';
const execution=name=>({name:'mcp__paper_checks__'+name});
const result=value=>({structuredContent:value});
test('paper export needs an explicit file request and respects text-only requests',()=>{
 for(const text of ['交付可下载的PDF校对报告','generate a PDF report','请导出报告'])assert.equal(paperExportRequested(text),true);
 for(const text of ['你好','校对这一句','不要导出报告，只在聊天回答',"Don't generate a PDF report."])assert.equal(paperExportRequested(text),false);
});
test('paper source read cannot masquerade as a real exported report',()=>{
 const g=createPaperRecovery();assert.equal(g.stop({aborted:false}),null);
 g.observe(execution('read_pinned_document'),result({source_id:'source',status:'visual_input'}));
 assert.match(g.stop({aborted:false}).instruction,/尚无成功/);
 assert.equal(g.stop({aborted:true}),null);
 g.observe(execution('export_review_report'),result({exported:false,reason:'source_versions_mismatch'}));
 assert.ok(g.stop({aborted:false}));
 g.observe(execution('export_review_report'),result({exported:true,artifacts:[]}));
 assert.ok(g.stop({aborted:false}));
 g.observe(execution('export_review_report'),result({exported:true,artifacts:[{name:'outputs/paper-review.pdf',sha256:'a'.repeat(64)}]}));
 assert.equal(g.stop({aborted:false}),null);
});
test('paper permission/version errors and unrelated tools cannot cause automatic export',()=>{
 const g=createPaperRecovery();g.observe({name:'mcp__other__read_pinned_document'},result({source_id:'source'}));
 assert.equal(g.stop({aborted:false}),null);
 g.observe(execution('read_pinned_document'),result({source_id:'source'}));
 g.observe(execution('export_review_report'),{isError:true,content:[{type:'text',text:'source_version_changed'}]});
 assert.equal(g.stop({aborted:false}),null);
});
