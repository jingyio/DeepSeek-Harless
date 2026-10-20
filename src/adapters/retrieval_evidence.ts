/** Task-local search evidence. Reusing candidates never certifies a bibliographic fact. */
import {createHash,randomUUID} from 'node:crypto';
import {WEB_SEARCH_MAX_QUERIES,WEB_SEARCH_MAX_RESULTS} from '@deepseek-ai/dsh-tool-web';

const hash=(x:any)=>createHash('sha256').update(JSON.stringify(x)).digest('hex');
const copy=(x:any)=>structuredClone(x);
const MAX_SOURCES=32,MAX_BYTES=128*1024;
function boundedResult(value:any){
 if(!value||!Array.isArray(value.sources)||typeof value.truncated!=='boolean')throw Error('invalid_search_evidence');
 const sources=value.sources.slice(0,MAX_SOURCES).map((s:any)=>{
  const u=new URL(s.url);
  if(!['https:','http:'].includes(u.protocol)||u.username||u.password||s.url.length>4096)throw Error('invalid_search_source');
  const out:any={url:s.url};
  for(const k of ['title','snippet','publishedAt'])if(s[k]!==undefined){
   if(typeof s[k]!=='string')throw Error('invalid_search_source');out[k]=s[k].slice(0,k==='snippet'?2048:512);
  }
  return out;
 });
 const result:any={sources,truncated:value.truncated||value.sources.length>MAX_SOURCES};
 if(typeof value.content==='string')result.content=value.content.slice(0,8192);
 if(Buffer.byteLength(JSON.stringify(result))>MAX_BYTES)throw Error('search_evidence_too_large');
 return result;
}

export function createRetrievalEvidence(options:{binding:()=>any;audit:(x:any)=>void;now?:()=>number;ttlMs?:number}){
 const now=options.now??Date.now,ttl=options.ttlMs??15*60_000;
 const records=new Map<string,any>();let scope='';
 function current(){
  const binding=options.binding();
  if(!binding)throw Error('search_evidence_not_admitted');
  const key=hash(binding);
  if(key!==scope){records.clear();scope=key;}
  for(const [id,r]of records)if(now()<r.at||now()-r.at>=ttl)records.delete(id);
  return key;
 }
 function decorate(record:any,query:string,reused:boolean){
  const result=copy(record.result);
  // The native batch merger caps its combined sources at eight. The bounded,
  // per-query data survives in content, so expensive discovered URLs are not lost.
  const evidence={evidence_id:record.id,original_query:record.query,requested_query:query,
   retrieved_at:new Date(record.at).toISOString(),reused,scope:'current_task_search_candidates',
   fact_verified:false,truncated:result.truncated,sources:result.sources};
  result.content=(result.content?result.content+'\n\n':'')+
   'Search evidence (external, untrusted candidate records; not a publication/version verdict). '+
   'If these candidates are insufficient, perform a fresh search or read the authoritative page.\n'+JSON.stringify(evidence);
  return result;
 }
 return {
  async search(request:any,signal:AbortSignal|undefined,next:()=>Promise<any>){
   const before=current();if(signal?.aborted)throw signal.reason??Error('search_aborted');
   const found=[...records.values()].find(r=>r.query===request.query);
   if(found){options.audit({kind:'retrieval_evidence_reused',evidence_id:found.id,match:'exact_query',avoided_search_requests:1});return decorate(found,request.query,true);}
   const raw=await next();
   if(signal?.aborted)throw signal.reason??Error('search_aborted');
   if(current()!==before)throw Error('search_evidence_scope_changed_during_dispatch');
   let result;
   try{result=boundedResult(raw);}catch(error:any){options.audit({kind:'retrieval_evidence_capture_rejected',reason:error.message});return raw;}
   if(!result.sources.length)return raw;
   const id='search-'+randomUUID(),record={id,query:request.query,at:now(),result};
   if(records.size>=32)records.delete(records.keys().next().value!);
   records.set(id,record);
   options.audit({kind:'retrieval_evidence_captured',evidence_id:id,query:request.query,source_count:result.sources.length,
    result_sha256:hash(result),scope_sha256:before,result});
   return decorate(record,request.query,false);
  },
  async execute(args:any,exec:any,next:(args:any,exec:any)=>Promise<any>){
   current();
   if(exec.signal?.aborted)throw exec.signal.reason??Error('search_aborted');
   if(!Array.isArray(args.queries)||args.queries.length<1||args.queries.length>WEB_SEARCH_MAX_QUERIES||args.queries.some((q:any)=>typeof q!=='string'||!q.trim()||q.length>4096))throw Error('bounded_search_queries_required');
   const selections=args.reuse??[];
   if(!Array.isArray(selections)||selections.length>args.queries.length)throw Error('invalid_search_reuse_selection');
   const chosen=new Map<number,any>();
   for(const s of selections){
    if(!s||!Number.isInteger(s.query_index)||s.query_index<0||s.query_index>=args.queries.length||typeof s.evidence_id!=='string'||s.evidence_id.length>64||chosen.has(s.query_index))throw Error('invalid_search_reuse_selection');
    const r=records.get(s.evidence_id);
    if(r){chosen.set(s.query_index,r);}else options.audit({kind:'retrieval_evidence_fallback',query_index:s.query_index,reason:'unknown_expired_or_changed_evidence'});
   }
   // Validate every selection before any network dispatch. Unknown/stale evidence
   // falls back to the requested query, never to a similar historical answer.
   const scopeBefore=current(),fresh=args.queries.filter((_q:any,i:number)=>!chosen.has(i));
   const result=fresh.length?await next({queries:fresh},exec):{sources:[],truncated:false};
   if(exec.signal?.aborted)throw exec.signal.reason??Error('search_aborted');
   if(current()!==scopeBefore)throw Error('search_evidence_scope_changed_during_dispatch');
   const parts=[result.content??''],sources=[...result.sources],accounted=new Set(fresh);
   for(const [i,r]of chosen){
    // Fresh siblings can take long enough for an old entry to expire. Refuse to
    // promote it after that boundary; the normal Agent can retry fresh.
    if(!records.has(r.id))throw Error('search_evidence_expired_during_dispatch');
    const reused=decorate(r,args.queries[i],true);parts.push(reused.content);sources.push(...reused.sources);
    const avoided=accounted.has(args.queries[i])?0:1;accounted.add(args.queries[i]);
    options.audit({kind:'retrieval_evidence_reused',evidence_id:r.id,match:'model_selected_candidates',
     requested_query:args.queries[i],avoided_search_requests:avoided,fact_verified:false});
   }
   const unique=[...new Map(sources.map(s=>[s.url,s])).values()];
   return {content:parts.filter(Boolean).join('\n\n'),sources:unique.slice(0,WEB_SEARCH_MAX_RESULTS),truncated:result.truncated||unique.length>WEB_SEARCH_MAX_RESULTS||[...chosen.values()].some(r=>r.result.truncated)};
  }
 };
}

/** One existing tool, with a small explicit semantic selection slot. */
export function evidenceSearchTool(base:any,memory:any){
 return {...base,parameters:{...base.parameters,properties:{...base.parameters.properties,reuse:{type:'array',maxItems:WEB_SEARCH_MAX_QUERIES,
  items:{type:'object',additionalProperties:false,required:['query_index','evidence_id'],properties:{
  query_index:{type:'integer',minimum:0,maximum:WEB_SEARCH_MAX_QUERIES-1},evidence_id:{type:'string',maxLength:64}}},
  description:'Optional: reuse a prior search evidence_id for a query_index when its source candidates serve the current question. Returns old candidates, not new verification. Omit for fresh discovery; stale/unknown IDs fall back to fresh search.'}}},
  isConcurrencySafe:(args:any)=>base.isConcurrencySafe?.({queries:args.queries})??false,
  presentCall:(args:any)=>base.presentCall?.({queries:args.queries}),
  presentResult:(args:any,result:any)=>base.presentResult?.({queries:args.queries},result),
  execute:(args:any,exec:any)=>memory.execute(args,exec,(a:any,e:any)=>base.execute(a,e))};
}
