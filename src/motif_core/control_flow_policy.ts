/** Finite witnessed branches and loops. Only declared observations select edges. */
import {digest,observation} from './online_skill_runtime.mjs';
const without=(v:any,k:string)=>Object.fromEntries(Object.entries(v??{}).filter(([n])=>n!==k));
const scalar=(v:any)=>typeof v==='string'&&v.length>0&&v.length<=512&&!/[\x00-\x1f]/.test(v);
const field=(v:any,p:string):any=>p.split('.').reduce((x,k)=>x?.[k],v);
function control(out:any,c:any){return Object.fromEntries(Object.entries(c.control_fields??{}).map(([path,domain]:any)=>{
 let value=out;for(const key of path.split('.')){if(!value||typeof value!=='object'||!Object.hasOwn(value,key))throw Error('missing_control_field');value=value[key];}
 if(domain==='nullable_handle'&&(value===null||scalar(value)))return [path,value===null?'null':'present'];
 if(domain==='boolean'&&typeof value==='boolean'||Array.isArray(domain)&&domain.some(x=>typeof x===typeof value&&x===value))return [path,value];
 throw Error('unknown_control_value');
}));}
const validValue=(v:any,s:any)=>scalar(v)?(s?.type??'string')==='string':Array.isArray(v)&&s?.type==='array'&&s.items?.type==='string'&&v.length>0&&v.length<=40&&v.length<=(s.maxItems??0)&&v.length>=(s.minItems??1)&&v.every(scalar)&&new Set(v).size===v.length;
export function controlFlowRootApplies(p:any,out:any){try{const g=control(out,p.artifact.tool_contracts[p.artifact.root].contract);return p.artifact.edges.some(e=>e.from===p.artifact.root&&digest(e.guard)===digest(g));}catch{return false;}}
export function validateControlFlow(p:any){
 const a=p?.artifact,edges=a?.edges,t=a?.tool_contracts,n=a?.nodes,training=a?.source_task_fingerprints;
 if(p?.schema_version!==1||p.format!=='sss-operation-flow-v3'||p.policy_digest!==digest(without(p,'policy_digest'))
  ||a?.kind!=='learned_mcp_control_flow'||a.certification_contract!=='sss-operation-certification-v3'
  ||a.certified_digest!==digest(without(a,'certified_digest'))||a.execution_version!==p.execution_version_sha256
  ||!['trace_validated_read_only','trace_validated_effectful'].includes(a.status)||a.max_steps!==64
  ||!Array.isArray(n)||n.length<2||n.length>16||n[0].tool!==a.root||new Set(n.map(v=>v.tool)).size!==n.length
  ||!Array.isArray(edges)||edges.length<3||edges.length>64||!t||!Array.isArray(training)||training.length<2
  ||new Set(training).size!==training.length||!a.validation_task_fingerprint||training.includes(a.validation_task_fingerprint))throw Error('invalid control-flow evidence');
 const cases=new Set<string>();
 for(const node of n){const tc=t[node.tool];if(!/^mcp__\w+$/.test(node.tool)||!tc||tc.schema_sha256!==digest(tc.schema)||tc.contract?.format!=='sss-mcp-learning-v1'
  ||!['read','stage','authorized_write','semantic'].includes(tc.contract.effect)||!Array.isArray(tc.contract.exports))throw Error('invalid flow operator');}
 for(const e of edges){const source=t[e.from],target=t[e.to],key=digest({from:e.from,guard:e.guard});
  if(!source||cases.has(key)||!e.guard||!e.bindings||digest(Object.keys(e.guard).sort())!==digest(Object.keys(source.contract.control_fields??{}).sort()))throw Error('ambiguous flow branch');
  cases.add(key);
  for(const [path,value] of Object.entries(e.guard)){const d=source.contract.control_fields[path];if(d==='nullable_handle'?!['null','present'].includes(value as string):d==='boolean'?typeof value!=='boolean':!Array.isArray(d)||!d.includes(value))throw Error('undeclared branch condition');}
  const witnesses=a.branch_evidence?.[key];if(!Array.isArray(witnesses)||new Set(witnesses).size<2||witnesses.some(v=>!training.includes(v)))throw Error('branch lacks independent native proof');
  if(e.to===null){if(source.contract.exports.length||Object.keys(e.bindings).length)throw Error('unproved terminal');continue;}
  if(!target||target.contract.auto_continue!==true||target.contract.effect==='semantic'||digest(Object.keys(e.bindings).sort())!==digest([...(target.schema.required??[])].sort())||!Object.keys(e.bindings).length)throw Error('unapproved flow continuation');
  for(const path of Object.values(e.bindings) as string[])if(typeof path!=='string'||!/^\w+(?:\.\w+)*$/.test(path)||!source.contract.exports.includes(path))throw Error('unproved flow parameter');
 }
 if(!edges.some(e=>e.to===null))throw Error('flow requires witnessed exit');
 for(const [name,tc] of Object.entries(a.interleaving_contracts??{}) as any){if(!/^mcp__\w+$/.test(name)||tc.schema_sha256!==digest(tc.schema)||tc.contract?.effect!=='read'||!(tc.contract.flow_interleaving||tc.contract.safe_interleaving))throw Error('invalid flow interleaving');}
 return p;
}
export function createControlFlow(policy:any,scope:any,audit:(r:any)=>void){
 validateControlFlow(policy);const a=policy.artifact;let current:any=null,rootId:string|null=null,pending:any=null,halted=false,done=false,count=0;
 const seen=new Set<string>(),visited:string[]=[],callIds:string[]=[];
 const fail=(reason:string)=>{halted=true;audit({kind:'operation_motif_deferred',reason,entry_id:policy.policy_digest});};
 const valid=(out:any,name:string)=>{const c=(a.tool_contracts[name]??a.interleaving_contracts?.[name])?.contract;return c&&out&&digest(out._sss_scope??null)===digest(scope)
  &&(!c.statuses||c.statuses.includes(out.status))&&Object.entries(c.scope_requirements??{}).every(([k,v])=>scope[k]===v)
  &&(c.effect!=='authorized_write'||out._sss_authorized===true);};
 const edgeAt=()=>{try{const g=control(current.out,a.tool_contracts[current.name].contract);const xs=a.edges.filter(e=>e.from===current.name&&digest(e.guard)===digest(g));
  if(xs.length!==1){fail('unseen_or_ambiguous_branch');return null;}return xs[0];}catch{fail('malformed_branch_observation');return null;}};
 const argsAt=(e:any)=>Object.fromEntries(Object.entries(e.bindings).map(([key,path]:any)=>[key,field(current.out,path)]));
 const finish=()=>{const e=edgeAt();if(e?.to===null){visited.push(digest(e));done=true;audit({kind:'operation_graph_complete',entry_id:policy.policy_digest,root_call_id:rootId,nodes:count,control_edges:visited,control_call_ids:callIds,control_flow:true});}};
 return {get halted(){return halted;},get done(){return done;},get armed(){return rootId!==null;},get pending(){return !!pending;},fail,
  get nextTool(){return current&&!halted&&!done?edgeAt()?.to:null;},
  willConsume(exec:any){if(!rootId||halted||done)return false;const e=edgeAt();return !!e&&e.to===exec.name&&digest(exec.arguments)===digest(argsAt(e));},
  observe(exec:any,result:any){
   if(halted||done)return;const out=observation(result,exec.name);
   if(rootId===null){if(exec.name!==a.root||String(exec.callId).startsWith('sss-'))return;if(!valid(out,exec.name)){fail('root_scope_or_authority_changed');return;}
    rootId=exec.callId;current={name:exec.name,out};count=1;callIds.push(exec.callId);seen.add(digest({tool:exec.name,args:exec.arguments}));audit({kind:'operation_root_verified',call_id:rootId,entry_id:policy.policy_digest});finish();return;}
   const e=edgeAt();if(!e||e.to===null)return;
   const args=argsAt(e);
   if(exec.name!==e.to||digest(exec.arguments)!==digest(args)){
    const tc=a.interleaving_contracts?.[exec.name];
    if(tc?.contract.effect==='read'&&(tc.contract.flow_interleaving||tc.contract.safe_interleaving)&&valid(out,exec.name)){
     audit({kind:'operation_read_interleaving_observed',entry_id:policy.policy_digest,call_id:exec.callId,model_request_bypassed:false});return;
    }
    fail('changed_or_failed_flow_result');return;
   }
   if(!valid(out,exec.name)||pending&&pending.callId!==exec.callId){fail('changed_or_failed_flow_result');return;}
   const signature=digest({tool:exec.name,args});if(seen.has(signature)||count>=a.max_steps){fail('loop_no_progress_or_step_limit');return;}
   seen.add(signature);count++;visited.push(digest(e));callIds.push(exec.callId);
   audit({kind:pending?'operation_model_request_bypassed_verified':'operation_native_step_adopted',entry_id:policy.policy_digest,call_id:exec.callId,node:count-1,control_edge:digest(e),model_request_bypassed:!!pending});
   pending=null;current={name:exec.name,out};finish();
  },
  propose(tools:any[],newId:()=>string,modelCalls:Set<string>){
   if(!rootId||halted||done||pending)return [];
   if(!modelCalls.has(rootId)||scope.execution_version!==policy.execution_version_sha256){fail('flow_root_or_version_changed');return [];}
   for(const [name,t] of Object.entries({...a.tool_contracts,...a.interleaving_contracts}) as any){const actual=tools.find(v=>v.name===name);if(!actual||digest(actual.parameters)!==t.schema_sha256){fail('flow_schema_changed');return [];}}
   const e=edgeAt();if(!e||e.to===null)return [];
   const tc=a.tool_contracts[e.to],args=Object.fromEntries(Object.entries(e.bindings).map(([key,path]:any)=>[key,field(current.out,path)]));
   if(Object.entries(tc.contract.scope_requirements??{}).some(([k,v])=>scope[k]!==v)||Object.entries(args).some(([key,v])=>!validValue(v,tc.schema.properties?.[key]))){fail('flow_parameter_or_permission_changed');return [];}
   if(count>=a.max_steps||seen.has(digest({tool:e.to,args}))){fail('loop_no_progress_or_step_limit');return [];}
   pending={callId:'sss-flow-'+newId(),proposal:{tool:e.to,arguments:args}};
   audit({kind:'operation_bypass_attempt',entry_id:policy.policy_digest,node:count,call_id:pending.callId,control_edge:digest(e)});return [pending];
  }
 };
}
