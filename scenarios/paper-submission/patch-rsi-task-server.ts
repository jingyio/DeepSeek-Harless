/** Opt-in compact write interface; original report-write MCP stays unchanged. */
import {appendFileSync,constants,closeSync,openSync,writeFileSync,fstatSync,lstatSync,renameSync,rmSync} from 'node:fs';
import {randomUUID} from 'node:crypto';
import {join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createInterface} from 'node:readline';
import {createTraceRsiTaskTools} from './trace-rsi-task-server.ts';
import {applyGeneratedRevision,renderRevisionMarkdown,validateRevisionPlan} from '../../src/adapters/report_patch_protocol.ts';
import {canonical} from '../../src/adapters/paper_rsi_program.ts';
import {readBoundedFile,sha256} from '../../src/adapters/paper_triage_validation.ts';
import {validateTraceFrozen} from '../../src/adapters/trace_rsi_program.ts';
import {revisionExportOutput} from '../../src/adapters/revision_export_receipt.ts';

export function createPatchRsiTaskTools(config:any) {
  const original=createTraceRsiTaskTools(config);
  const patchPath=resolve(config.patch_library_path),bytes=readBoundedFile(patchPath,192000),hash=sha256(bytes);
  const frozen=validateTraceFrozen(JSON.parse(bytes.toString('utf8')));
  if(config.code_files[patchPath]!==hash||config.patch_library_sha256!==hash)throw Error('patch_library_not_version_bound');
  function patch(args:any):any {
    if(!args||canonical(Object.keys(args).sort())!==canonical(['plan','report_sha256']))throw Error('invalid_patch_arguments');
    validateRevisionPlan(args.plan);
    if(sha256(readBoundedFile(patchPath,192000))!==hash)throw Error('patch_library_changed');
    const state=original.call('read_task_state',{});
    if(state.report_sha256!==args.report_sha256)throw Error('stale_report_write');
    const result=applyGeneratedRevision(state.report,args.plan,frozen);
    if(sha256(readBoundedFile(patchPath,192000))!==hash)throw Error('patch_library_changed');
    const receipt=original.call('write_report',{report_sha256:args.report_sha256,report:result.report});
    appendFileSync(join(config.work,'patch-audit.jsonl'),JSON.stringify({receipt,plan:args.plan,
      plan_sha256:result.plan_sha256,program_sha256:result.program_sha256,patch_output:result.patch_output})+'\n',{mode:0o600});
    return receipt;
  }
  function exportReport(args:any):any {
    if(!args||canonical(Object.keys(args))!==canonical(['input_id']))throw Error('invalid_export_arguments');
    const state=original.call('read_task_state',{});
    if(args.input_id!==state.input_id)throw Error('stale_export_input_id');
    const checked=original.call(config.check_name,{input_id:state.input_id});
    const markdown=renderRevisionMarkdown(state.input.before_report,state.report,checked.output);
    const path=join(config.work,'revision-report.md');
    try {
      const stat=lstatSync(path);
      if(!stat.isFile()||stat.isSymbolicLink()||stat.nlink!==1)throw Error('export_must_be_private_regular_file');
    } catch(error:any) {if(error.code!=='ENOENT')throw error;}
    const temp=join(config.work,'.revision-report-'+randomUUID()+'.tmp');
    let created=false;
    try {
      const fd=openSync(temp,constants.O_WRONLY|constants.O_CREAT|constants.O_EXCL,0o600);created=true;
      try {
        const stat=fstatSync(fd);if(!stat.isFile()||stat.nlink!==1)throw Error('export_must_be_private_regular_file');
        writeFileSync(fd,markdown);
      }finally{closeSync(fd);}
      const after=original.call('read_task_state',{});
      if(after.report_sha256!==state.report_sha256)throw Error('report_changed_during_export');
      // Rename replaces a destination link itself; it never writes its target,
      // including platforms without O_NOFOLLOW and a link introduced mid-write.
      renameSync(temp,path);
    }finally{if(created)rmSync(temp,{force:true});}
    const {report,input,...receipt}=state;
    return {...receipt,artifact_name:'revision-report.md',artifact_sha256:sha256(Buffer.from(markdown)),
      scope:'structural_revision_not_full_bibliography_verification',output:revisionExportOutput(checked.output,config.export_result_protocol)};
  }
  const planSchema={type:'object',properties:{
    set_ids:{type:'array',items:{type:'object',properties:{key:{type:'string'},arxiv_id:{type:'string'}},required:['key','arxiv_id'],additionalProperties:false}},
    keep_once_keys:{type:'array',items:{type:'string'}},remove_keys:{type:'array',items:{type:'string'}},
    add_records:{type:'array',items:{type:'object',properties:{key:{type:'string'},arxiv_id:{type:'string'},status:{type:'string',enum:['待进一步核验']}},required:['key','arxiv_id','status'],additionalProperties:false}}
  },required:['set_ids','keep_once_keys','remove_keys','add_records'],additionalProperties:false};
  const definitions=original.definitions.filter(t=>t.name!=='write_report');
  if(config.read_context_protocol==='revision_view_v1'){
    if(config.write_protocol==='full_report')throw Error('full_write_requires_full_state');
    definitions[0]={...definitions[0],description:'读取当前结构修订最小视图：当前key/标识、来源目录配对和RSI生成审计结果。完整来源/科研字段保存在报告副本，由局部写入工具原样保留；不进行真实性或正式版本核验。'};
  }
  const compact={name:'apply_revision_plan',description:'RSI生成程序把局部计划转换为修订操作，保留未变字段并保存本任务报告；有冲突的重复版本拒绝。按当前report_sha256核验版本。',
    inputSchema:{type:'object',properties:{report_sha256:{type:'string'},plan:planSchema},required:['report_sha256','plan'],additionalProperties:false}} as any;
  definitions.splice(1,0,config.write_protocol==='full_report'?original.definitions.find(t=>t.name==='write_report')!:compact);
  definitions.push({name:'export_revision_report',description:'按当前input_id生成完整结构修订Markdown，包含当前检查、全部报告字段/来源和修订前快照；不进行真实性核验。',
    inputSchema:{type:'object',properties:{input_id:{type:'string'}},required:['input_id'],additionalProperties:false}} as any);
  if(config.export_result_protocol==='revision_receipt_v2')definitions[definitions.length-1].description+=' 成功仅返回当前完整检查摘要哈希和结构通过标记，完整检查在产物中；失败仍返回全部问题，不得视为通过。';
  return {definitions,call(name:string,args:any){
    if(name==='read_task_state'&&config.read_context_protocol==='revision_view_v1'){
      const state=original.call(name,args),checked=original.call(config.check_name,{input_id:state.input_id});
      const {report,input,...receipt}=state;
      return {...receipt,view:{current_rows:input.triage_references,
        source_records:input.catalog_cited_records,query_items:input.catalog_query_items,
        audit:checked.output,scope:'structural_revision_only; full_fields_remain_in_private_report'}};
    }
    if(name==='apply_revision_plan'){
      if(config.write_protocol==='full_report')throw Error('compact_write_not_enabled_in_full_report_condition');
      return patch(args);
    }
    if(name==='export_revision_report')return exportReport(args);
    if(name==='write_report'&&config.write_protocol!=='full_report')throw Error('full_report_write_not_enabled_in_compact_condition');
    return original.call(name,args);
  }};
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  const config=JSON.parse(readBoundedFile(process.env.SSS_TRACE_RSI_TASK_CONFIG!,64000).toString('utf8'));
  const tools=createPatchRsiTaskTools(config),lines=createInterface({input:process.stdin});
  lines.on('line',line=>{
    let request:any;try{request=JSON.parse(line);}catch{return;}if(request?.id===undefined)return;
    try{
      let result:any;
      if(request.method==='initialize')result={protocolVersion:request.params.protocolVersion,capabilities:{tools:{}},serverInfo:{name:'paper_trace_rsi',version:'2.0.0'}};
      else if(request.method==='tools/list')result={tools:tools.definitions};
      else if(request.method==='ping')result={};
      else if(request.method==='tools/call'){
        try{result={content:[{type:'text',text:JSON.stringify(tools.call(request.params.name,request.params.arguments??{}))}]};}
        catch(error){result={isError:true,content:[{type:'text',text:String(error)}]};}
      }else throw Error('unknown_method');
      process.stdout.write(JSON.stringify({jsonrpc:'2.0',id:request.id,result})+'\n');
    }catch(error){process.stdout.write(JSON.stringify({jsonrpc:'2.0',id:request.id,error:{code:-32603,message:String(error)}})+'\n');}
  });
}
