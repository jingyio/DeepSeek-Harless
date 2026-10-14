/** Frozen learned report tool over MCP stdio. All file access is in this adapter. */
import { readFileSync,writeFileSync,lstatSync,realpathSync } from 'node:fs';
import { join,resolve } from 'node:path';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';
import { validateFrozen,runReportCheck } from '../../src/adapters/paper_rsi_program.ts';
import { sourceUnchanged,readBoundedFile,sha256 } from '../../src/adapters/paper_triage_validation.ts';

export function createRsiTools(config:any){
  const work=realpathSync(config.work),path=join(work,'triage.json');
  const lib=validateFrozen(JSON.parse(readBoundedFile(config.library_path,128000).toString('utf8')));
  const initialLibHash=sha256(readFileSync(config.library_path));
  function guard(){
    if(!sourceUnchanged(config)||sha256(readFileSync(config.library_path))!==initialLibHash)throw Error('source_or_tool_version_changed');
  }
  function read(){guard();const bytes=readBoundedFile(path,192000);const report=JSON.parse(bytes.toString('utf8'));
    guard();return {report,report_sha256:sha256(bytes),source_version:config.source_version,
      expected_pairs:config.expected_pairs,candidate_sha256:lib.candidate_sha256,semantic_quality:'not_reviewed'};}
  function check(){const current=read();const output=runReportCheck(lib.candidate,{report:current.report,
    expected_pairs:config.expected_pairs,current_source_version:current.source_version,expected_source_version:config.source_version});
    guard();return {output,report_sha256:current.report_sha256,source_version:current.source_version,
      candidate_sha256:lib.candidate_sha256,semantic_quality:'not_reviewed'};}
  function write(args:any){
    guard();const before=read();if(args.previous_sha256!==before.report_sha256)throw Error('stale_report_write');
    if(args.report===null||typeof args.report!=='object'||Array.isArray(args.report))throw Error('report_object_required');
    const text=JSON.stringify(args.report,null,2)+'\n';if(Buffer.byteLength(text)>192000)throw Error('report_too_large');
    if(lstatSync(path).isSymbolicLink())throw Error('report_symlink');
    writeFileSync(path,text,{mode:0o600});guard();return {report_sha256:sha256(text),source_version:config.source_version,candidate_sha256:lib.candidate_sha256};
  }
  const empty={type:'object',properties:{},additionalProperties:false};
  const definitions=[
    {name:'read_report',description:'读取本任务论文报告副本和源码计算的 expected_pairs、版本及摘要。缺失文献判断保持待核验；不读取原稿。',inputSchema:empty},
    {name:'write_report',description:'保存本任务报告副本的修订。传完整报告与上次读取的摘要防止覆盖新版本。只写 triage.json，不验证科研内容。',inputSchema:{type:'object',properties:{report:{type:'object'},previous_sha256:{type:'string'}},required:['report','previous_sha256'],additionalProperties:false}},
    {name:'check_report_structure',description:lib.candidate.description+' 只读检查当前副本，无参数。程序由 DeepSeek 生成并通过独立结构验收；不认证文献真实性。',inputSchema:empty,annotations:{readOnlyHint:true}}
  ];
  function call(name:string,args:any){
    if(name==='write_report'){if(Object.keys(args).sort().join(',')!=='previous_sha256,report')throw Error('invalid_args');return write(args);}
    if(Object.keys(args).length)throw Error('no_arguments');
    if(name==='read_report')return read();if(name==='check_report_structure')return check();throw Error('unknown_tool');
  }
  return {definitions,call};
}

if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const config=JSON.parse(readFileSync(process.env.SSS_PAPER_RSI_CONFIG!,'utf8')),tools=createRsiTools(config);
  const lines=createInterface({input:process.stdin});
  lines.on('line',(line)=>{
    let request:any;try{request=JSON.parse(line);}catch{return;}
    if(request.id===undefined)return;
    let result:any;
    try{
      switch(request.method){
        case 'initialize':result={protocolVersion:request.params.protocolVersion,capabilities:{tools:{}},serverInfo:{name:'paper-rsi',version:'1.0.0'}};break;
        case 'ping':result={};break;
        case 'tools/list':result={tools:tools.definitions};break;
        case 'tools/call':try{result={content:[{type:'text',text:JSON.stringify(tools.call(request.params.name,request.params.arguments??{}))}]};}
          catch(e){result={isError:true,content:[{type:'text',text:String(e)}]};}break;
        default:process.stdout.write(JSON.stringify({jsonrpc:'2.0',id:request.id,error:{code:-32601,message:'Method not found'}})+'\n');return;
      }
      process.stdout.write(JSON.stringify({jsonrpc:'2.0',id:request.id,result})+'\n');
    }catch(e){process.stdout.write(JSON.stringify({jsonrpc:'2.0',id:request.id,error:{code:-32603,message:String(e)}})+'\n');}
  });
}
