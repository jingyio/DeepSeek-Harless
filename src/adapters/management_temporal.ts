/** Admission barrier only: the model still chooses all semantic tool arguments. */
import {digest,observation} from '../motif_core/online_skill_runtime.mjs';
export function createTemporalBarrier(task:any,scope:any,audit:(v:any)=>void){
 const contract=task?.quality?.goal?.temporal,rows:any[]=[],handles=new Map<string,string>(),files=new Map<string,string>(),documents=new Map<string,string>();
 let yielded=false,released=false;
 const match=(s:any,r:any)=>{
  if(r.name!=='mcp__file_management__'+s.tool)return false;
  if(s.tool==='read_file'&&(r.out.status!=='readable'||r.out.truncated!==false||r.out.metadata?.preview_only))return false;
  if(s.tool==='document_coverage'&&r.out.complete!==true)return false;
  return !s.path||r.path==='workspace/'+s.path;
 };
 return {
  observe(exec:any,result:any){
   const out=observation(result,exec.name);if(!out||digest(out._sss_scope??null)!==digest(scope)||result?.isError||result?.value?.isError)return;
   if(exec.name==='mcp__file_management__list_files')for(const f of out.files??[])files.set(f.file_id,f.root_id+'/'+f.path);
   if(exec.name==='mcp__file_management__pin_file'&&files.has(exec.arguments?.file_id))handles.set(out.source_id,files.get(exec.arguments.file_id)!);
   if(exec.name==='mcp__file_management__pin_files')for(let i=0;i<(out.file_ids??[]).length;i++)if(files.has(out.file_ids[i]))handles.set(out.source_ids[i],files.get(out.file_ids[i])!);
   const path=out.path??handles.get(exec.arguments?.source_id)??documents.get(out.document_id);
   if(out.document_id&&path)documents.set(out.document_id,path);
   rows.push({name:exec.name,id:exec.callId,out,path});
  },
  ready(messages:any[],tool?:string){
   if(!contract||contract.state==='not_requested')return true;
   const ids=new Set<string>();for(const m of messages)if(m.role==='assistant'&&m.source?.kind==='model')for(const c of m.content??[])if(c.type==='tool-call')ids.add(c.id);
   const short=tool?.replace('mcp__file_management__','');
   // Keep independent phases independent. Pending preparation requirements do
   // not prevent already-authorized document loops from progressing.
   const predicates=(contract.predicates??[]).filter((p:any)=>{
    if(!tool)return true;
    const preparation=p.events.some((s:any)=>s.tool==='prepare_tool_call');
    return preparation?['prepare_tool_call','execute_tool_call','inspect_tool_result'].includes(short??'')
      :!['prepare_tool_call','execute_tool_call','inspect_tool_result','discover_tools','describe_tool'].includes(short??'');
   });
   const required=tool&&contract.predicates?predicates.flatMap((p:any)=>p.relation==='same_batch'?p.events:p.events.slice(0,1)):contract.release_after;
   const ok=contract.state==='frozen'&&contract.format==='sss-management-temporal-v2'&&required.every((s:any)=>rows.filter(r=>ids.has(r.id)&&match(s,r)).length>=(s.min_count??1));
   if(!ok&&!yielded){yielded=true;audit({kind:'operation_temporal_yield',reason:contract.state==='frozen'?'await_actual_temporal_prerequisites':'unsupported_temporal_goal',model_request_bypassed:false});}
   if(ok&&!released){released=true;audit({kind:'operation_temporal_released',prerequisites:contract.release_after,model_request_bypassed:false});}
   return ok;
  }
 };
}
