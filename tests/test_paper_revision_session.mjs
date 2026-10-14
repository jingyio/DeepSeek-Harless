import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdirSync,mkdtempSync,writeFileSync,readFileSync,rmSync} from 'node:fs';
import {resolve,join,sep} from 'node:path';
import {createHash} from 'node:crypto';
const root=resolve(import.meta.dirname,'..');
test('Existing paper audit accepts minimal uploaded references, preserves extra fields, and rejects foreign or stale state',async()=>{
 if(!process.features?.typescript)return;
 const {revisionTools}=await import('../scenarios/paper_proofreading/revision_session.ts');
 mkdirSync(join(root,'.local'),{recursive:true});const directory=mkdtempSync(join(root,'.local','paper-adapter-test-'));
 try{
  const make=name=>{
   const work=join(directory,name,'work');mkdirSync(join(work,'inputs'),{recursive:true});
   const report={title:'Synthetic',references:[{key:'demo',arxiv_id:'1234.56789',note:'preserve me'}]};
   const bytes=Buffer.from(JSON.stringify({report}));writeFileSync(join(work,'inputs','references.json'),bytes);
   writeFileSync(join(work,'approved-inputs.json'),JSON.stringify({files:{'references.json':createHash('sha256').update(bytes).digest('hex')}}));
   return{work,api:revisionTools(work),report};
  };
  const a=make('a'),b=make('b'),before=a.api.call('read_task_state',{});
  assert.throws(()=>b.api.call('triage_revision_audit',{input_id:before.input_id}),/unknown_or_stale/);
  const audit=a.api.call('triage_revision_audit',{input_id:before.input_id});assert.ok(audit.output);
  const exportRow=a.api.call('export_revision_report',{input_id:before.input_id});
  assert.match(readFileSync(join(a.work,'outputs/paper',exportRow.artifact_name),'utf8'),/preserve me/);
  const changed=a.api.call('apply_revision_plan',{report_sha256:before.report_sha256,plan:{set_ids:[{key:'demo',arxiv_id:'9999.99999'}],keep_once_keys:[],remove_keys:[],add_records:[]}});
  assert.notEqual(changed.input_id,before.input_id);
  assert.throws(()=>a.api.call('triage_revision_audit',{input_id:before.input_id}),/unknown_or_stale/);
  assert.equal(a.api.call('read_task_state',{}).report.references[0].note,'preserve me');
  writeFileSync(join(a.work,'inputs/references.json'),'changed');
  assert.throws(()=>a.api.call('read_task_state',{}),/paper_source_changed/);
 }finally{const p=resolve(directory);assert.ok(p.startsWith(join(root,'.local')+sep));rmSync(p,{recursive:true,force:true});}
});
