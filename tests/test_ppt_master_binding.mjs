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
