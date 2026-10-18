import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,rmSync,realpathSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';

test('PPTX template pins cannot enter the historical PDF conversion edges, including mixed input',
 {skip:!process.features?.typescript},async()=>{
 const {bindUploadedSourceTask}=await import('../src/adapters/harless_rsi_binding.ts');
 const root=realpathSync(mkdtempSync(join(tmpdir(),'ppt-version-scope-')));mkdirSync(join(root,'inputs'));
 try{
  const inputs=[['paper.pdf','%PDF-1.7 test'],['template.pptx','PK test'],['fake.pdf','not a PDF']].map(([file,bytes])=>{
   writeFileSync(join(root,'inputs',file),bytes);return {file,version_sha256:createHash('sha256').update(bytes).digest('hex')};
  });
  writeFileSync(join(root,'approved-inputs.json'),JSON.stringify({files:Object.fromEntries(inputs.map(x=>[x.file,x.version_sha256]))}));
  const pin='mcp__ppt_master__pin_source',convert='mcp__ppt_master__convert_source',read='mcp__ppt_master__read_converted_source';
  const manifest={contracts:{[pin]:{observed_anchor:true},[convert]:{},[read]:{}},version_fields:{[pin]:'version_sha256',[convert]:'version_sha256',[read]:'version_sha256'}};
  for(const selected of [inputs,[inputs[1]]]){
   const bound=bindUploadedSourceTask(root,selected,{task_id:'task',session_id:'session',content:[{type:'text',text:'Reuse this template'}]},manifest);
   assert.equal(bound.source_versions[pin],'@observed');
   assert.deepEqual(bound.source_versions[convert],selected.length===1?[]:[inputs[0].version_sha256]);
   assert.deepEqual(bound.source_versions[read],bound.source_versions[convert]);
  }
 }finally{rmSync(root,{recursive:true,force:true});}
});
test('PPT source continuation allows only the selected PDF first page, never authoring or another page',
 {skip:!process.features?.typescript},async()=>{
 const {closedPptSourceFirstPage:closed}=await import('../src/adapters/harless_rsi_binding.ts');
 const pin='mcp__ppt_master__pin_source',read='mcp__ppt_master__read_source_page';
 const manifest={contracts:{[pin]:{read_only:true,observed_anchor:true,required_params:['name','sha256'],default_params:{}},
  [read]:{read_only:true,required_params:['source_id'],default_params:{page:1}}},artifacts:[{motif_id:'diagnostic',tools:[pin,read],
  transfer_evidence:[{from_tool:pin,to_tool:read,from_field:'source_id',to_param:'source_id'}]}]};
 const row={tool:read,motif_id:'diagnostic',version_relation:'same_source',code_node_ids:[],arguments:{source_id:'source-'+'a'.repeat(32),page:1}};
 assert.equal(closed(row,manifest),true);
 for(const patch of [{tool:'bash'},{arguments:{...row.arguments,page:2}},{arguments:{...row.arguments,command:'write'}},
   {version_relation:'object_lookup'},{code_node_ids:['script']}])assert.equal(closed({...row,...patch},manifest),false);
 const unsafe=structuredClone(manifest);unsafe.contracts[read].read_only=false;assert.equal(closed(row,unsafe),false);
});

test('conversion edges only accept exact source/derivative bindings and read-only contracts',
 {skip:!process.features?.typescript},async()=>{
 const {closedPptConvertedSource:closed}=await import('../src/adapters/harless_rsi_binding.ts');
 const chain=['mcp__ppt_master__pin_source','mcp__ppt_master__convert_source','mcp__ppt_master__read_converted_source'];
 for(let i=0;i<2;i++){
  const [from,to]=chain.slice(i,i+2),field=i?'converted_id':'source_id',prefix=i?'result':'source';
  const manifest={contracts:{[from]:{read_only:true,observed_anchor:i===0},[to]:{read_only:true,required_params:[field],default_params:{}}},
   artifacts:[{motif_id:'witnessed-edge',tools:[from,to],transfer_evidence:[{from_tool:from,to_tool:to,from_field:field,to_param:field}]}]};
  const row={tool:to,motif_id:'witnessed-edge',version_relation:'same_source',code_node_ids:[],arguments:{[field]:prefix+'-'+'b'.repeat(32)}};
  assert.equal(closed(row,manifest),true);
  for(const patch of [{tool:'bash'},{arguments:{...row.arguments,page:2}},
    {arguments:{[field]:'/etc/passwd'}},{version_relation:'object_lookup'},{code_node_ids:['unsafe']}])assert.equal(closed({...row,...patch},manifest),false);
  const changed=structuredClone(manifest);changed.artifacts[0].transfer_evidence[0].from_field='other';assert.equal(closed(row,changed),false);
  changed.artifacts[0].transfer_evidence[0].from_field=field;changed.contracts[to].read_only=false;assert.equal(closed(row,changed),false);
 }
});
