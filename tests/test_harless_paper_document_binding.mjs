/** Free protocol diagnostics only; these fixtures are not training evidence. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,rmSync,realpathSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';

const options={skip:!process.features?.typescript};
const pin='mcp__paper_checks__pin_document',read='mcp__paper_checks__read_pinned_document';
const legacyPin='mcp__paper_checks__pin_paper_sources',legacyRead='mcp__paper_checks__read_pinned_paper_sources';
const edge=(from=pin,to=read)=>({tools:[from,to],transfer_evidence:[
  {from_tool:from,to_tool:to,from_field:'source_id',to_param:'source_id'}]});
const manifest=(artifacts=[edge()])=>({artifacts,version_fields:Object.fromEntries(
  artifacts.flatMap(row=>row.tools).map(name=>[name,'version_sha256'])),contracts:{
    [pin]:{read_only:true,observed_anchor:true,required_params:['name','sha256'],default_params:{}},
    [read]:{read_only:true,required_params:['source_id'],default_params:{page:1}},
  }});
const sha=data=>createHash('sha256').update(data).digest('hex');

function fixture(){
  const root=realpathSync(mkdtempSync(join(tmpdir(),'paper-document-binding-')));
  mkdirSync(join(root,'inputs'));
  const inputs=['study.docx','methods.pdf','notes.txt','data.csv','metadata.json'].map((file,index)=>{
    const data=Buffer.from('diagnostic approved bytes '+index);writeFileSync(join(root,'inputs',file),data);
    return {file,version_sha256:sha(data)};
  });
  const files=Object.fromEntries(inputs.map(row=>[row.file,row.version_sha256]));
  const approve=()=>writeFileSync(join(root,'approved-inputs.json'),JSON.stringify({files}));approve();
  return {root,inputs,files,approve,request:{task_id:'current-task',session_id:'current-session',
    content:[{type:'text',text:'Check the uploaded documents'}]},
    close:()=>rmSync(root,{recursive:true,force:true})};
}

test('generic Paper pin/read binds current approved mixed-format uploads without guessing source handles',options,async()=>{
  const {bindApprovedUploadedReadTask}=await import('../src/adapters/harless_rsi_binding.ts');
  const f=fixture();try{
    const bound=bindApprovedUploadedReadTask(f.root,f.inputs,f.request,manifest(),'paper-proofreading');
    assert.equal(bound.task_id,f.request.task_id);assert.equal(bound.session_id,f.request.session_id);
    assert.deepEqual(bound.bindings,{});assert.deepEqual(bound.source_versions,{[pin]:'@observed',[read]:'@from_anchor'});
    assert.equal(bound.intent,'Check the uploaded documents');
    assert.equal(bound.input_version,sha(JSON.stringify(Object.keys(f.files).sort().map(name=>[name,f.files[name]]))));
    const other={...f.request,session_id:'another-session',task_id:'another-task'};
    const next=bindApprovedUploadedReadTask(f.root,f.inputs,other,manifest(),'paper-proofreading');
    assert.equal(next.session_id,'another-session');assert.equal(next.task_id,'another-task');
  }finally{f.close();}
});

test('generic Paper binding rejects changed bytes, foreign approvals and invalid versions',options,async()=>{
  const {bindApprovedUploadedReadTask:bind}=await import('../src/adapters/harless_rsi_binding.ts');
  const f=fixture();try{
    assert.throws(()=>bind(f.root,[{...f.inputs[0],file:'../study.docx'},...f.inputs.slice(1)],f.request,manifest(),'paper-proofreading'),/source_scope/);
    assert.throws(()=>bind(f.root,[{...f.inputs[0],version_sha256:'not-a-version'},...f.inputs.slice(1)],f.request,manifest(),'paper-proofreading'),/source_scope/);
    assert.throws(()=>bind(f.root,[{...f.inputs[0],version_sha256:'f'.repeat(64)},...f.inputs.slice(1)],f.request,manifest(),'paper-proofreading'),/source_version/);
    f.files[f.inputs[0].file]='f'.repeat(64);f.approve();
    assert.throws(()=>bind(f.root,f.inputs,f.request,manifest(),'paper-proofreading'),/source_version/);
    f.files[f.inputs[0].file]=f.inputs[0].version_sha256;f.files['foreign.txt']='f'.repeat(64);f.approve();
    assert.throws(()=>bind(f.root,f.inputs,f.request,manifest(),'paper-proofreading'),/approval_scope/);
    delete f.files['foreign.txt'];f.approve();writeFileSync(join(f.root,'inputs',f.inputs[0].file),'changed after approval');
    assert.throws(()=>bind(f.root,f.inputs,f.request,manifest(),'paper-proofreading'),/source_version/);
  }finally{f.close();}
});

test('generic Paper binding keeps the new read family separate from legacy edges and rejects unknown or incomplete tools',options,async()=>{
  const {bindApprovedUploadedReadTask:bind}=await import('../src/adapters/harless_rsi_binding.ts');
  const f=fixture();try{
    const check=value=>bind(f.root,f.inputs,f.request,value,'paper-proofreading');
    assert.deepEqual(check(manifest([edge(legacyPin,legacyRead)])).source_versions,
      {[legacyPin]:'@observed',[legacyRead]:'@from_anchor'});
    for(const invalid of [
      manifest([edge(),edge(legacyPin,legacyRead)]),
      manifest([edge(pin,'mcp__paper_checks__export_review_report')]),
      manifest([edge(),edge()]),
      manifest([edge('mcp__paper_checks__pin_paper_citations','mcp__paper_checks__read_pinned_paper_citations')]),
      {...manifest(),version_fields:{[pin]:'version_sha256'}},
      {...manifest(),version_fields:{...manifest().version_fields,mcp__other__read:'version_sha256'}},
      manifest([{...edge(),transfer_evidence:[{...edge().transfer_evidence[0],to_param:'document_id'}]}]),
      {...manifest(),contracts:{}},
      {...manifest(),contracts:{...manifest().contracts,[pin]:{...manifest().contracts[pin],observed_anchor:false}}},
      {...manifest(),contracts:{...manifest().contracts,[read]:{...manifest().contracts[read],default_params:{page:2}}}},
      {...manifest(),contracts:{...manifest().contracts,[read]:{...manifest().contracts[read],read_only:false}}},
    ])assert.throws(()=>check(invalid),/tools_unsupported/);
    assert.throws(()=>bind(f.root,f.inputs,f.request,manifest(),'research-data-analysis'),/tools_unsupported/);
  }finally{f.close();}
});

test('closed Paper first-page guard refuses semantic, write and source-binding extensions',options,async()=>{
  const {closedPaperDocumentFirstPage:closed}=await import('../src/adapters/harless_rsi_binding.ts');
  const base=manifest();base.artifacts[0].motif_id='protocol-motif';
  const row={tool:read,motif_id:'protocol-motif',version_relation:'same_source',code_node_ids:[],
    arguments:{source_id:'source-'+'b'.repeat(32),page:1}};
  assert.equal(closed(row,base),true);
  for(const patch of [
    {tool:'mcp__paper_checks__export_review_report'},
    {motif_id:'another-motif'},
    {arguments:{...row.arguments,page:2}},
    {arguments:{...row.arguments,selection:'model must choose this'}},
    {arguments:{...row.arguments,source_id:'foreign'}},
    {version_relation:'object_lookup'},
    {code_node_ids:['new-code']},
  ])assert.equal(closed({...row,...patch},base),false,JSON.stringify(patch));
  for(const mutate of [
    value=>value.artifacts.push(structuredClone(value.artifacts[0])),
    value=>value.artifacts[0].tools.reverse(),
    value=>value.artifacts[0].transfer_evidence[0].version_relation='lookup_index',
    value=>value.artifacts[0].transfer_evidence[0].from_field='other_id',
    value=>value.artifacts[0].code_nodes=[{kind:'write'}],
    value=>value.artifacts[0].code_dag={nodes:['write']},
    value=>value.contracts[pin].observed_anchor=false,
    value=>value.contracts[pin].read_only=false,
    value=>value.contracts[read].read_only=false,
    value=>value.contracts[read].default_params={page:2},
    value=>value.contracts[read].required_params.push('selection'),
  ]){const changed=structuredClone(base);mutate(changed);assert.equal(closed(row,changed),false);}
});
