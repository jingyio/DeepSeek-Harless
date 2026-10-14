import test from 'node:test';
import assert from 'node:assert/strict';
import {revisionPatchInput,applyGeneratedRevision,renderRevisionMarkdown,validateRevisionPlan} from '../src/adapters/report_patch_protocol.ts';
import {digest} from '../src/adapters/paper_rsi_program.ts';

const empty=()=>({set_ids:[],keep_once_keys:[],remove_keys:[],add_records:[]});
const report=()=>({scope:'diagnostic',references:[{key:'a',arxiv_id:'old',source_urls:['one','two']},
 {key:'a',arxiv_id:'old',source_urls:['one','two']},{key:'b',arxiv_id:'b-id',source_urls:['three']}]});
function literalTool(output){
 const s={type:'string'},arr=items=>({type:'array',items,maxItems:2000}),obj=properties=>({type:'object',properties,required:Object.keys(properties),additionalProperties:false});
 const candidate={schema_version:1,name:'diagnostic_patch',description:'固定操作仅用于权限/原子性诊断，非RSI验收程序',
 input_schema:obj({rows:arr(obj({key:s,path:s,id_path:s})),rows_reverse:arr(obj({key:s,path:s,id_path:s})),plan:obj({set_ids:arr(obj({key:s,arxiv_id:s})),keep_once_keys:arr(s),remove_keys:arr(s),add_records:arr(obj({key:s,arxiv_id:s,status:s}))})}),
 output_schema:obj({replacements:arr(obj({path:s,value:s})),removals:arr(s),additions:arr(obj({key:s,arxiv_id:s,status:s}))}),program:['lit',output]};
 const provenance={trace_bundle_sha256:'a'.repeat(64),source_witnesses:[{run_id:'synthetic',session_id:'s',call_id:'c',events_sha256:'b'.repeat(64)}]};
 const certification={status:'passed',kind:'source_replay',heldout_cases:2};
 const body={schema_version:1,kind:'model_generated_trace_tool',candidate,candidate_sha256:digest(candidate),provenance,provenance_sha256:digest(provenance),certification,certification_sha256:digest(certification)};
 return {...body,manifest_digest:digest(body)};
}
test('rows use current array paths and removals address reverse original order',()=>{
 const p={...empty(),keep_once_keys:['a']},input=revisionPatchInput(report(),p);
 assert.deepEqual(input.rows.map(r=>r.path),['/references/0','/references/1','/references/2']);
 assert.deepEqual(input.rows_reverse.map(r=>r.path),['/references/2','/references/1','/references/0']);
});
test('generated operations preserve untouched strings, arrays and top-level fields',()=>{
 const before=report(),p={...empty(),set_ids:[{key:'a',arxiv_id:'new'}],keep_once_keys:['a'],add_records:[{key:'c',arxiv_id:'c-id',status:'待进一步核验'}]};
 const t=literalTool({replacements:[{path:'/references/0/arxiv_id',value:'new'},{path:'/references/1/arxiv_id',value:'new'}],removals:['/references/1'],additions:p.add_records});
 const after=applyGeneratedRevision(before,p,t).report;
 assert.deepEqual(after,{scope:'diagnostic',references:[{...before.references[0],arxiv_id:'new'},before.references[2],p.add_records[0]]});
 assert.deepEqual(before,report());
});
test('protected paths, invented values, missing requested effects and wrong removal order fail without changing input',()=>{
 const p={...empty(),set_ids:[{key:'a',arxiv_id:'new'}],keep_once_keys:['a']},before=report();
 for(const out of [
  {replacements:[{path:'/references/0/source_urls',value:'new'}],removals:[],additions:[]},
  {replacements:[{path:'/references/0/arxiv_id',value:'invented'}],removals:[],additions:[]},
  {replacements:[],removals:[],additions:[]},
  {replacements:[],removals:['/references/0'],additions:[]},
  {replacements:[],removals:[],additions:[{key:'x',arxiv_id:'fake',status:'待进一步核验'}]}
 ])assert.throws(()=>applyGeneratedRevision(before,p,literalTool(out)));
 assert.deepEqual(before,report());
 const all={...empty(),remove_keys:['a','b']};
 assert.throws(()=>applyGeneratedRevision(before,all,literalTool({replacements:[],removals:['/references/0','/references/2'],additions:[]})),/wrong_order/);
});
test('unknown keys and conflicting old versions require a new semantic decision',()=>{
 assert.throws(()=>revisionPatchInput(report(),{...empty(),remove_keys:['missing']}),/unknown_plan_key/);
 const r=report();r.references[1].source_urls.reverse();
 assert.throws(()=>revisionPatchInput(r,{...empty(),keep_once_keys:['a']}),/semantic_resolution/);
});
test('plans cannot add judgments, duplicate instructions or side-effect fields',()=>{
 for(const p of [{...empty(),set_ids:[{key:'a',arxiv_id:'x'},{key:'a',arxiv_id:'y'}]},
  {...empty(),set_ids:[{key:'a',arxiv_id:'x'}],remove_keys:['a']},
  {...empty(),add_records:[{key:'c',arxiv_id:'c',status:'已确认'}]},
  {...empty(),path:'/private/original'},
  {...empty(),add_records:[{key:'c',arxiv_id:'c',status:'待进一步核验',source_urls:['invented']}]}
 ])assert.throws(()=>validateRevisionPlan(p));
});
test('rendering contains both complete reports, current failed checks and explicit scope',()=>{
 const b=report(),a={...report(),extra:'完整保留'},s=renderRevisionMarkdown(b,a,{existing_fields_preserved:false});
 assert.ok(s.includes(JSON.stringify(b,null,2)));assert.ok(s.includes(JSON.stringify(a,null,2)));
 assert.ok(s.includes('"existing_fields_preserved": false'));assert.ok(s.includes('未核验文献真实性'));
});
