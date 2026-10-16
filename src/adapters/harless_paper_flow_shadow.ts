/** Current-Task observer for migrated historical paper flows. No tool execution. */
import {digest, observation} from '../motif_core/online_skill_runtime.mjs';

const P='mcp__paper_checks__';
const params:Record<string,string>={
  [P+'pin_paper_citations']:'case_id',
  [P+'read_pinned_paper_citations']:'source_id',
  [P+'read_pinned_citation_records']:'citation_id',
  [P+'fetch_pinned_cited_preprint_metadata']:'citation_id',
  [P+'fetch_pinned_formal_reference_metadata']:'citation_id',
  [P+'recover_pinned_formal_reference_queries']:'citation_id',
};
const reportIds=new Set(['paper-flow-1254fc79a35f','paper-flow-e4d6cba4afc9','paper-flow-f813f5b15671']);
const same=(a:any,b:any)=>digest(a)===digest(b);

export function validatePaperFlowBridge(bridge:any, schemas:any[]) {
  const {manifest_digest,...body}=bridge??{};
  if(bridge?.schema_version!==1||bridge.kind!=='paper_flow_current_shadow'||
     bridge.execution_policy!=='shadow_only'||bridge.scene!=='paper-proofreading'||
     manifest_digest!==digest(body)||!Array.isArray(bridge.candidates)||bridge.candidates.length!==6||
     !Array.isArray(bridge.report_migrations)||bridge.report_migrations.length!==3||
     !/^[a-f0-9]{64}$/.test(bridge.old_library_sha256??'')||
     !/^[a-f0-9]{64}$/.test(bridge.current_tool_schemas_sha256??''))
    throw TypeError('invalid paper flow bridge');
  const offered=new Map(schemas.map(row=>[row.name,row.parameters]));
  if(Object.keys(params).some(tool=>!offered.has(tool)||
     digest(offered.get(tool))!==bridge.tool_schema_hashes?.[tool]))
    throw TypeError('paper flow tool schema changed');
  const ids=new Set<string>();
  for(const row of bridge.candidates){
    const g=row.graph, n=g?.nodes?.[0], param=params[n?.tool];
    if(!g||!n||!param||!Array.isArray(g.anchor)||g.nodes.length!==1||
       g.anchor.some((tool:string)=>!params[tool])||g.artifact!==undefined||
       !['success','task_start'].includes(g.anchor_result)||
       row.motif_id!=='paper-flow-'+digest(g).slice(0,12)||ids.has(row.motif_id)||
       !Number.isSafeInteger(row.training_session_count)||row.training_session_count<1||
       !Number.isSafeInteger(row.witness_count)||row.witness_count<row.training_session_count||
       !same(Object.keys(n.bindings??{}),[param]))throw TypeError('unwitnessed paper flow');
    const binding=n.bindings[param];
    if(binding?.task_field!==undefined){
      if(n.tool!==P+'pin_paper_citations'||g.anchor.length||g.anchor_result!=='task_start'||
         binding.task_field!=='case_id')throw TypeError('invalid paper task binding');
    }else if(!Array.isArray(binding?.source_fields)||!binding.source_fields.length||
             binding.source_fields.some((field:any)=>!g.anchor.includes(field.tool)||field.field!==param))
      throw TypeError('invalid paper source binding');
    ids.add(row.motif_id);
  }
  if(bridge.report_migrations.some((row:any)=>!reportIds.has(row.legacy_motif_id)||
       row.execution_policy!=='model_owned_report_write')||
     new Set(bridge.report_migrations.map((row:any)=>row.legacy_motif_id)).size!==3)
    throw TypeError('invalid paper report migration');
}

export function createPaperFlowShadowObserver(bridge:any, task:any, schemas:any[], audit:(row:any)=>void) {
  validatePaperFlowBridge(bridge,schemas);
  if(typeof task.session_id!=='string'||!task.session_id||typeof task.task_id!=='string'||
     !task.source_versions?.[P+'pin_paper_citations'])throw TypeError('paper flow task is not bound');
  let recent:any[]=[],started=false;
  function observe(sessionId:string,exec:any,result:any){
    if(sessionId!==task.session_id)return;
    const output=observation(result,exec.name);
    recent.push({name:exec.name,ok:result?.isError!==true&&output!==null,
                 arguments:exec.arguments,output});
    if(recent.length>32)recent=recent.slice(-32);
  }
  function beforeModel(sessionId:string, schemasNow:any[]) {
    if(sessionId!==task.session_id)return;
    const batch=recent;recent=[];
    const offered=new Map(schemasNow.map(row=>[row.name,row.parameters]));
    if(Object.keys(params).some(tool=>digest(offered.get(tool))!==bridge.tool_schema_hashes[tool])){
      audit({kind:'paper_flow_deferred',reason:'current_tool_schema_changed'});started=true;return;
    }
    const names=batch.map(row=>row.name).sort();
    for(const row of bridge.candidates){
      const g=row.graph;
      if(!same(names,g.anchor)||new Set(names).size!==names.length)continue;
      if(g.anchor_result==='task_start'?(started||batch.length):
         batch.some(item=>!item.ok||!item.output||typeof item.output.version_sha256!=='string'))continue;
      const node=g.nodes[0], args:any={};let valid=true;
      for(const [param,binding] of Object.entries(node.bindings) as any[]){
        if(binding.task_field)args[param]='current';
        else{
          const values=binding.source_fields.map((field:any)=>
            batch.find(item=>item.name===field.tool)?.output?.[field.field]);
          if(!values.length||values.some((value:any)=>typeof value!=='string'||
               !/^[A-Za-z0-9_-]{8,160}$/.test(value)||value!==values[0]))valid=false;
          else args[param]=values[0];
        }
      }
      if(!valid)continue;
      const versions=new Set(batch.map(item=>item.output?.version_sha256));
      if(batch.length&&versions.size!==1)continue;
      audit({kind:'shadow_candidate',candidate_class:'legacy_paper_flow',
        motif_id:row.motif_id,expected_tools:[node.tool],
        expected_arguments_sha256:digest(args),execution:false});
    }
    const stage=batch.find(item=>item.name===P+'stage_current_audit'&&item.ok&&item.output?.staged===true);
    if(stage?.output?.draft_sha256&&stage.output.reference_count>0&&
       stage.output.citation_check_count>=6)
      audit({kind:'paper_report_shadow_candidate',target_tool:P+'finalize_current_audit',
        argument_sha256:digest({expected_draft_sha256:stage.output.draft_sha256}),
        legacy_motif_ids:['paper-flow-1254fc79a35f','paper-flow-e4d6cba4afc9'],execution:false});
    const invalid=batch.find(item=>item.name===P+'finalize_current_audit'&&
      item.ok&&item.output?.finalized===false);
    if(invalid)audit({kind:'paper_report_model_handoff',
      legacy_motif_id:'paper-flow-f813f5b15671',reason:invalid.output.validation_error,
      execution:false});
    started=true;
  }
  return {observe,beforeModel};
}
