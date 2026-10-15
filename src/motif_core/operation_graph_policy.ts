/** Bounded, witnessed MCP DAG interpreter. No arbitrary code or semantic constants. */
import {validateOperationPolicy as validateV1,createOperationController as createV1} from './operation_graph_policy_v1.ts';
import {digest,observation} from './online_skill_runtime.mjs';
const without=(v:any,k:string)=>Object.fromEntries(Object.entries(v??{}).filter(([n])=>n!==k));
const field=(v:any,p:string):any=>{const [key,...rest]=p.split('.');if(!v||typeof v!=='object')return undefined;
 if(key.endsWith('[]')){const xs=v[key.slice(0,-2)];return Array.isArray(xs)&&xs.length>0&&xs.length<=40?xs.map(x=>rest.length?field(x,rest.join('.')):x):undefined;}
 return rest.length?field(v[key],rest.join('.')):v[key];};
const scalar=(v:any)=>typeof v==='string'&&v.length>0&&v.length<=512&&!/[\x00-\x1f]/.test(v);
const bindable=(v:any,s:any)=>scalar(v)?(s?.type??'string')==='string':Array.isArray(v)&&v.length>0&&v.length<=40&&v.length<=s?.maxItems&&v.length>=(s?.minItems??1)&&v.every(scalar)&&new Set(v).size===v.length&&s?.type==='array'&&s.items?.type==='string'&&s.maxItems>=1&&s.maxItems<=40;
export function validateOperationPolicy(p:any){
 if(p?.format==='sss-operation-graph-v1')return validateV1(p);
 const a=p?.artifact,n=a?.nodes,t=a?.tool_contracts;
 if(p?.schema_version!==1||p.format!=='sss-operation-graph-v2'||p.policy_digest!==digest(without(p,'policy_digest'))
  ||a.certification_contract!=='sss-operation-certification-v2'||a.kind!=='learned_mcp_operation_dag'||!['trace_validated_read_only','trace_validated_effectful'].includes(a.status)
  ||a.certified_digest!==digest(without(a,'certified_digest'))||a.execution_version!==p.execution_version_sha256
  ||a.max_nodes!==8||!Array.isArray(n)||n.length<2||n.length>8||!t
  ||!Array.isArray(a.source_task_fingerprints)||new Set(a.source_task_fingerprints).size!==a.source_task_fingerprints.length
  ||a.source_task_fingerprints.length<2||!a.validation_task_fingerprint||a.source_task_fingerprints.includes(a.validation_task_fingerprint))throw Error('invalid operation DAG evidence');
 n.forEach((node:any,i:number)=>{
  const tc=t[node.tool],c=tc?.contract,required=tc?.schema?.required??[];
  if(!/^mcp__[a-zA-Z0-9_]+$/.test(node.tool)||!tc||tc.schema_sha256!==digest(tc.schema)
   ||c?.format!=='sss-mcp-learning-v1'||!Array.isArray(c.exports)
   ||!['read','stage','authorized_write','semantic'].includes(c.effect)
   ||i===0&&Object.keys(node.bindings).length||i>0&&(c.auto_continue!==true||digest(Object.keys(node.bindings).sort())!==digest([...required].sort())))throw Error('invalid declared operator');
  for(const b of Object.values(node.bindings) as any[]){
   if(!Number.isInteger(b.node)||b.node<0||b.node>=i||typeof b.path!=='string'||!/^\w+(?:\[\])?(?:\.\w+(?:\[\])?)*$/.test(b.path)||b.path.split('[]').length>2
    ||!t[n[b.node].tool].contract.exports.includes(b.path))throw Error('unproved or cyclic parameter binding');
  }
 });
 for(const [name,t] of Object.entries(a.interleaving_contracts??{}) as any){
  if(!/^mcp__[a-zA-Z0-9_]+$/.test(name)||t.schema_sha256!==digest(t.schema)||t.contract?.effect!=='read'
    ||t.contract.safe_interleaving!==true||t.contract.exports.length)throw Error('unapproved interleaving contract');
 }
 return p;
}
export function createOperationController(policy:any,scope:any,audit:(r:any)=>void){
 if(policy?.format==='sss-operation-graph-v1')return createV1(policy,scope,audit);
 validateOperationPolicy(policy);const a=policy.artifact;let cursor=0,pending:any=null,halted=false,done=false,rootId:string|null=null;
 const outputs:any[]=[];
 const fail=(reason:string)=>{halted=true;audit({kind:'operation_motif_deferred',reason,entry_id:policy.policy_digest});};
 const valid=(out:any,index:number)=>{
  const c=a.tool_contracts[a.nodes[index].tool].contract;
  return out&&digest(out._sss_scope)===digest(scope)&&(!c.statuses||c.statuses.includes(out.status))
   &&Object.entries(c.scope_requirements??{}).every(([k,v])=>scope[k]===v)
   &&(c.effect!=='authorized_write'||out._sss_authorized===true);
 };
 const argsAt=(index:number)=>Object.fromEntries(Object.entries(a.nodes[index].bindings).map(([p,b]:any)=>[p,field(outputs[b.node],b.path)]));
 return {get halted(){return halted;},get done(){return done;},get armed(){return rootId!==null;},get pending(){return !!pending;},fail,
  observe(exec:any,result:any){
   if(halted||done)return;const out=observation(result,exec.name);
   if(rootId===null){
    if(exec.name!==a.nodes[0].tool||String(exec.callId).startsWith('sss-'))return;
    if(!valid(out,0)){fail('root_scope_or_authority_changed');return;}
    outputs.push(out);rootId=exec.callId;cursor=1;
    audit({kind:'operation_root_verified',call_id:rootId,entry_id:policy.policy_digest});return;
   }
   const expected=a.nodes[cursor],args=argsAt(cursor);
   const interleaved=a.interleaving_contracts?.[exec.name];
   if(exec.name!==expected.tool&&interleaved?.contract.safe_interleaving===true&&interleaved.contract.effect==='read'
     &&out&&digest(out._sss_scope)===digest(scope)
     &&(!interleaved.contract.statuses||interleaved.contract.statuses.includes(out.status))
     &&Object.entries(interleaved.contract.scope_requirements??{}).every(([k,v])=>scope[k]===v)){
    audit({kind:'operation_read_interleaving_observed',call_id:exec.callId,model_request_bypassed:false});return;
   }
   if(exec.name!==expected.tool||digest(exec.arguments)!==digest(args)||!valid(out,cursor)
    ||pending&&exec.callId!==pending.callId){fail('changed_or_failed_operation_result');return;}
   if(pending){audit({kind:'operation_model_request_bypassed_verified',entry_id:policy.policy_digest,node:cursor,call_id:exec.callId});pending=null;}
   else audit({kind:'operation_native_step_adopted',entry_id:policy.policy_digest,node:cursor,model_request_bypassed:false});
   outputs.push(out);cursor++;
   if(cursor===a.nodes.length){done=true;audit({kind:'operation_graph_complete',entry_id:policy.policy_digest,root_call_id:rootId,nodes:cursor});}
  },
  propose(tools:any[],newId:()=>string,modelCalls:Set<string>){
   if(!rootId||halted||done||pending)return [];
   if(!modelCalls.has(rootId)){fail('root_requires_actual_model_decision');return [];}
   if(scope.execution_version!==policy.execution_version_sha256){fail('operation_execution_version_changed');return [];}
   for(const [name,t] of Object.entries({...a.tool_contracts,...a.interleaving_contracts}) as any){
    const actual=tools.find((v:any)=>v.name===name);
    if(!actual||digest(actual.parameters)!==t.schema_sha256){fail('operation_schema_changed');return [];}
   }
   const args=argsAt(cursor);
   if(!Object.entries(a.tool_contracts[a.nodes[cursor].tool].contract.scope_requirements??{}).every(([k,v])=>scope[k]===v)){
    fail('operation_outside_current_intent_grant');return [];
   }
   if(Object.entries(args).some(([k,v])=>!bindable(v,a.tool_contracts[a.nodes[cursor].tool].schema.properties?.[k]))){fail('missing_or_non_scalar_verified_binding');return [];}
   pending={callId:'sss-operation-'+newId(),proposal:{tool:a.nodes[cursor].tool,arguments:args}};
   audit({kind:'operation_bypass_attempt',entry_id:policy.policy_digest,node:cursor,call_id:pending.callId});return [pending];
  }
 };
}
