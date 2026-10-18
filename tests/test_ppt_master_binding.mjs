import test from 'node:test';
import assert from 'node:assert/strict';
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
