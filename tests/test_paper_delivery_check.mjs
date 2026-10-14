import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync, symlinkSync, realpathSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createDeliveryChecker, apply, checkToolName } from '../src/adapters/dsh_paper_delivery_check.ts';
import { snapshotSource, sha256, acceptEvidencePacket, checkReport, validateTriage } from '../src/adapters/paper_triage_validation.ts';
import { Context } from '@deepseek-ai/cordis';
import { ToolRuntime } from '@deepseek-ai/dsh-tools';
import { deliveryResponseClass } from '../scripts/evaluate-paper-delivery-shadow.mjs';

function fixture(mode='enforce') {
  const root=realpathSync(mkdtempSync(join(tmpdir(),'sss-paper-delivery-'))), source=join(root,'source'), work=join(root,'work');
  mkdirSync(source);mkdirSync(work);
  const raw='@article{a,title={Public diagnostic},eprint={2401.02954}}';
  writeFileSync(join(source,'refs.bib'),raw);writeFileSync(join(source,'main.tex'),'\\cite{a}');
  const config={schema_version:1,mode,case_id:'sample',session_id:'s',work,source_root:source,
    source_files:snapshotSource(source),source_version:'a'.repeat(64)};
  const pairs=[{key:'a',arxiv_id:'2401.02954'}];
  const packet={schema_version:1,case_id:'sample',source_id:'source-'+'c'.repeat(32),citation_id:'source-'+'b'.repeat(32),
    version_sha256:config.source_version,scope:'active_manuscript_literal_cite_keys_only',diagnostic:{cited_keys:['a']},
    required_reference_pairs:pairs,references:{source_id:'source-'+'c'.repeat(32),citation_id:'source-'+'b'.repeat(32),
      version_sha256:config.source_version,requested_keys:['a'],required_reference_pairs:pairs,missing_keys:[],duplicate_keys:{},
      records:[{key:'a',bib_file:'refs.bib',raw_bibtex:raw,record_sha256:sha256(raw),bib_file_sha256:sha256(raw)}]}};
  const doc={scope:'cited_arxiv_version_triage',citation_issues:[],references:[{...pairs[0],
    source_urls:['https://arxiv.org/abs/2401.02954'],evidence_status:'已获取',status:'待进一步核验',priority:'P2',
    differences:[],formal_version:'发现线索待核对',next_action:'查正式出版页'}]};
  const audit=[],checker=createDeliveryChecker(config,r=>audit.push(r));
  const bind=(value=packet,result={structuredContent:value})=>checker.observe(
    {name:'mcp__paper_checks__collect_paper_citation_evidence',callId:'collect',arguments:{case_id:'sample'}},result);
  const write=(data=doc)=>writeFileSync(join(work,'triage.json'),JSON.stringify(data));
  const exec={name:'write',callId:'write1',arguments:{file_path:'triage.json'},signal:new AbortController().signal};
  return {root,source,work,config,packet,doc,audit,checker,bind,write,exec};
}
const success={isError:false,value:{path:'triage.json'},content:[{type:'text',text:'written'}]};
const accepted=async()=>({kind:'accept'});

test('flow evidence binds parallel results, invalidates refresh, and artifact recovery respects source and policy',async()=>{
  const f=fixture('shadow');try {
    Object.assign(f.config,{citation_flow:true,require_preprint_metadata:true,read_artifact:true});
    const checker=createDeliveryChecker(f.config,r=>f.audit.push(r));
    const observe=(name,args,value)=>checker.observe({name:'mcp__paper_checks__'+name,arguments:args}, {structuredContent:value});
    observe('read_pinned_paper_citations',{source_id:f.packet.source_id},{...f.packet,case_id:'sample'});
    observe('fetch_pinned_cited_preprint_metadata',{citation_id:f.packet.citation_id},f.packet);
    observe('read_pinned_citation_records',{citation_id:f.packet.citation_id},f.packet.references);
    f.write();assert.equal(checker.check().status,'passed');
    const before=readFileSync(join(f.work,'triage.json'));
    assert.equal(checker.readArtifact().report_sha256,sha256(before));
    await checker.after({...f.exec,name:'edit'},{...success,isError:true},accepted);
    assert.equal(f.audit.at(-1).kind,'paper_recovery_snapshot');
    assert.deepEqual(readFileSync(join(f.work,'triage.json')),before);
    const n=f.audit.length;
    await checker.after({...f.exec,name:'edit'},{...success,isError:true},async()=>({kind:'block'}));
    assert.equal(f.audit.length,n);
    observe('fetch_pinned_cited_preprint_metadata',{citation_id:f.packet.citation_id},null);
    assert.equal(checker.check().status,'needs_repair');
    assert.throws(()=>checker.readArtifact(),/no_current/);
  }finally{rmSync(f.root,{recursive:true,force:true});}
});

test('delivery opportunity needs a passed check and an entire pure matching response',()=>{
  const call={type:'tool-call',name:'check_paper_triage',arguments:'{}'};
  assert.equal(deliveryResponseClass([call],{status:'passed'}),'closed_tool_continuation');
  assert.equal(deliveryResponseClass([call],{status:'needs_repair'}),'no_valid_check');
  assert.equal(deliveryResponseClass([call],{status:'needs_repair',report_sha256:'a'.repeat(64),source_version:'b'.repeat(64)}),'deterministic_repair_feedback');
  assert.equal(deliveryResponseClass([call,{type:'text',text:'Need a publication judgment'}],{status:'passed'}),'text_or_semantic_review');
  assert.equal(deliveryResponseClass([{...call,arguments:'{"path":"other"}'}],{status:'passed'}),'mixed_or_different_tools');
});

test('one schema checks coverage, duplicate pairs, enums, cited issues and link syntax',()=>{
  const f=fixture();try {
    assert.equal(validateTriage(f.doc,f.packet).status,'passed');
    for(const edit of [d=>d.references.push({...d.references[0]}),d=>d.references=[],
      d=>d.references[0].arxiv_id='other',d=>d.references[0].priority='P9',
      d=>d.references[0].source_urls=['file:///private'],d=>delete d.references[0].formal_version,
      d=>d.citation_issues=[{kind:'missing',keys:['outside'],explanation:'bad'}]]) {
      const d=structuredClone(f.doc);edit(d);assert.equal(validateTriage(d,f.packet).status,'needs_repair');
    }
    const p=structuredClone(f.packet);p.references.missing_keys=['a'];
    assert.match(validateTriage(f.doc,p).errors.join(','),/unreported_source/);
  }finally{rmSync(f.root,{recursive:true,force:true});}
});

test('packet provenance rejects forged raw bytes, source version, scope, pair and case',()=>{
  const f=fixture();try {
    assert.equal(acceptEvidencePacket(f.packet,f.config),true);
    for(const edit of [p=>p.case_id='other',p=>p.version_sha256='b'.repeat(64),
      p=>p.references.records[0].raw_bibtex+='changed',p=>p.required_reference_pairs.push({key:'invented',arxiv_id:'2401.02954'}),
      p=>p.references.records[0].bib_file='../other',p=>p.scope='all_bib']) {
      const p=structuredClone(f.packet);edit(p);assert.equal(acceptEvidencePacket(p,f.config),false);
    }
  }finally{rmSync(f.root,{recursive:true,force:true});}
});

test('automatic write and edit checks reuse the explicit checker without a model request',async()=>{
  const f=fixture();try {
    f.bind();f.write();const out=await f.checker.after(f.exec,success,accepted);
    assert.equal(out.kind,'accept');assert.equal(out.content[0].text,'written');
    const check=JSON.parse(out.content[1].text).runtime_check;
    assert.equal(check.status,'passed');assert.equal(check.semantic_quality,'not_reviewed');
    assert.deepEqual(check,f.checker.check());
    assert.equal(f.audit.at(-1).model_requests_skipped,0);
    f.write({...f.doc,references:[]});
    assert.equal((await f.checker.after({...f.exec,name:'edit'},success,accepted)).kind,'block');
    assert.deepEqual(JSON.parse(readFileSync(join(f.work,'triage.json'),'utf8')).references,[]);
  }finally{rmSync(f.root,{recursive:true,force:true});}
});

test('shadow records a check but preserves the response; off does not automatically check',async()=>{
  for(const mode of ['shadow','off']) {
    const f=fixture(mode);try {
      f.bind();f.write();const d={kind:'accept'};
      assert.equal(await f.checker.after(f.exec,success,async()=>d),d);
      assert.equal(f.audit.filter(r=>r.kind==='paper_delivery_check').length,mode==='shadow'?1:0);
      assert.equal(f.checker.check().status,'passed');
    }finally{rmSync(f.root,{recursive:true,force:true});}
  }
});

test('source additions, changed bytes, invalid JSON, unreadable and symlink reports cannot pass',async()=>{
  for(const mutate of [f=>writeFileSync(join(f.source,'refs.bib'),'changed'),
    f=>writeFileSync(join(f.source,'new.tex'),'new'),f=>writeFileSync(join(f.work,'triage.json'),'{'),
    f=>{rmSync(join(f.work,'triage.json'));symlinkSync(join(f.source,'refs.bib'),join(f.work,'triage.json'));}]) {
    const f=fixture();try {
      f.bind();f.write();mutate(f);assert.equal(f.checker.check().status,'needs_repair');
      assert.equal((await f.checker.after(f.exec,success,accepted)).kind,'block');
    }finally{rmSync(f.root,{recursive:true,force:true});}
  }
});

test('failed refresh invalidates earlier evidence, other paths and failed downstream policies stay untouched',async()=>{
  const f=fixture();try {
    f.bind();f.write();assert.equal(f.checker.check().status,'passed');
    f.bind(null,{isError:true});assert.equal(f.checker.check().status,'needs_repair');
    const denied={kind:'block',feedback:[{type:'text',text:'permission denied'}]};
    assert.equal(await f.checker.after(f.exec,success,async()=>denied),denied);
    const d={kind:'accept'};
    assert.equal(await f.checker.after(f.exec,{...success,isError:true},async()=>d),d);
    assert.equal(await f.checker.after({...f.exec,arguments:{file_path:'other.json'}},success,async()=>d),d);
  }finally{rmSync(f.root,{recursive:true,force:true});}
});

test('plugin attaches only to its session and explicit checker uses only its registered artifact',async()=>{
  const f=fixture(), prior=process.env.SSS_PAPER_CHECK_CONFIG, cwd=process.cwd();
  try {
    const p=join(f.root,'config.json');writeFileSync(p,JSON.stringify(f.config));
    process.env.SSS_PAPER_CHECK_CONFIG=p;process.chdir(f.work);
    let created;const scoped=new Map();let definition;
    apply({on(_event,callback){created=callback;}});
    created({agent:{session:{id:'other'}}});
    created({agent:{session:{id:'s'},ctx:{tools:{register(d){definition=d;}},on(n,cb){scoped.set(n,cb);}}}});
    assert.equal(definition.name,checkToolName);
    scoped.get('tools/result')({name:'mcp__paper_checks__collect_paper_citation_evidence',arguments:{case_id:'sample'}},
      {isError:false,value:{structuredContent:f.packet}});
    f.write();assert.equal((await definition.execute({})).status,'passed');
    await assert.rejects(definition.execute({path:'../source/main.tex'}),/registered artifact/);
  }finally{
    process.chdir(cwd);if(prior===undefined)delete process.env.SSS_PAPER_CHECK_CONFIG;else process.env.SSS_PAPER_CHECK_CONFIG=prior;
    rmSync(f.root,{recursive:true,force:true});
  }
});

test('real Harness tool registry commits automatic feedback and blocks invalid artifact without undoing writes',async()=>{
  const f=fixture();const disposers=[];
  try {
    const ctx=new Context();ctx.systemPrompt={tools(){}};
    const tools=new ToolRuntime(ctx);
    disposers.push(ctx.on('tools/result',f.checker.observe),ctx.on('tools/post-execute',f.checker.after));
    disposers.push(tools.register({name:'mcp__paper_checks__collect_paper_citation_evidence',description:'recorded diagnostic evidence',
      parameters:{type:'object',properties:{case_id:{type:'string'}},required:['case_id']},
      output:{schema:{type:'object'},render:()=>[]},async execute(){return {structuredContent:f.packet};}}));
    disposers.push(tools.register({name:'write',description:'private diagnostic file write',
      parameters:{type:'object',properties:{file_path:{type:'string'},content:{type:'string'}},required:['file_path','content']},
      output:{schema:{type:'object'},render:()=>[{type:'text',text:'written'}]},
      async execute(args){assert.equal(args.file_path,'triage.json');writeFileSync(join(f.work,'triage.json'),args.content);return {path:'triage.json'};}}));
    const exec=(name,args,id)=>tools.execute({name,arguments:args,callId:id,signal:new AbortController().signal});
    assert.equal((await exec('mcp__paper_checks__collect_paper_citation_evidence',{case_id:'sample'},'collect')).isError,false);
    const good=await exec('write',{file_path:'triage.json',content:JSON.stringify(f.doc)},'good');
    assert.equal(good.isError,false);assert.equal(JSON.parse(good.content.at(-1).text).runtime_check.status,'passed');
    const bad=await exec('write',{file_path:'triage.json',content:'{'},'bad');
    assert.equal(bad.isError,true);assert.equal(JSON.parse(bad.content[0].text).runtime_check.errors[0],'invalid_json');
    assert.equal(readFileSync(join(f.work,'triage.json'),'utf8'),'{');
  }finally{for(const d of disposers.reverse())d();rmSync(f.root,{recursive:true,force:true});}
});
