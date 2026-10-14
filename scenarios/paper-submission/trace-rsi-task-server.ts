/** Normal private report revision using a frozen trace-derived pure-data tool.
 * This adapter binds data and versions; it contains no report-checking algorithm.
 */
import { constants, closeSync, fstatSync, ftruncateSync, lstatSync, openSync, readFileSync, realpathSync, writeSync } from 'node:fs';
import { basename, isAbsolute, join, resolve } from 'node:path';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';
import { validateJsonSchemaValue } from '@deepseek-ai/dsh-tools';
import { canonical, digest } from '../../src/adapters/paper_rsi_program.ts';
import { runTraceTool, validateTraceFrozen } from '../../src/adapters/trace_rsi_program.ts';
import { readBoundedFile, sha256 } from '../../src/adapters/paper_triage_validation.ts';

const object = (value:any) => value !== null && typeof value === 'object' && !Array.isArray(value);
const hash = (value:any) => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const unsafe = new Set(['__proto__','constructor','prototype']);
function argsOnly(args:any,keys:string[]):void {
  if (!object(args) || Object.keys(args).length !== keys.length || keys.some(key => !Object.hasOwn(args,key)))
    throw Error('invalid_arguments');
}
function bindingsValid(bindings:any):void {
  if (!object(bindings) || !Object.keys(bindings).length || Object.keys(bindings).length > 16) throw Error('bounded_input_bindings_required');
  for (const [name,row] of Object.entries(bindings) as [string,any][]) {
    if (!/^[a-z][a-z0-9_]{0,63}$/.test(name) || unsafe.has(name) || !object(row) ||
        Object.keys(row).some(key => !['file','pointer','fields'].includes(key)) ||
        !['catalog.json','triage.json'].includes(row.file) || typeof row.pointer !== 'string' ||
        (row.pointer !== '' && !row.pointer.startsWith('/')) || row.pointer.length > 4000)
      throw Error('unregistered_input_binding');
    if (Object.hasOwn(row,'fields') && (!Array.isArray(row.fields) || !row.fields.length || row.fields.length > 32 ||
        row.fields.some((key:any) => typeof key !== 'string' || !key || unsafe.has(key)) ||
        new Set(row.fields).size !== row.fields.length)) throw Error('invalid_field_projection');
  }
}

/** Same bounded pointer/fields projection as the offline source protocol. No IO. */
export function projectTraceInputs(catalog:any,report:any,bindings:any):any {
  bindingsValid(bindings);
  const files:any = {'catalog.json':catalog,'triage.json':report};let fuel=20000;
  function select(value:any,tokens:string[],index=0):any {
    if (--fuel < 0) throw Error('projection_operation_limit');
    if (index === tokens.length) return value;
    const key=tokens[index].replace(/~1/g,'/').replace(/~0/g,'~');
    if (unsafe.has(key)) throw Error('unsafe_pointer');
    if (key === '*') {
      if (!Array.isArray(value) || value.length > 2000) throw Error('bounded_array_wildcard_required');
      return value.map(child => select(child,tokens,index+1));
    }
    if (Array.isArray(value)) {
      if (!/^-?[0-9]+$/.test(key) || value.length > 2000) throw Error('invalid_array_pointer');
      const number=Number(key), offset=number < 0 ? value.length+number : number;
      if (!Number.isSafeInteger(offset) || offset < 0 || offset >= value.length) throw Error('missing_pointer_field');
      return select(value[offset],tokens,index+1);
    }
    if (!object(value) || !Object.hasOwn(value,key)) throw Error('missing_pointer_field');
    return select(value[key],tokens,index+1);
  }
  const entries:[string,any][]=[];
  for (const [name,row] of Object.entries(bindings) as [string,any][]) {
    const tokens=row.pointer ? row.pointer.split('/').slice(1) : [];
    if (tokens.length > 48) throw Error('projection_depth_limit');
    let value=select(files[row.file],tokens);
    if (row.fields) {
      if (!Array.isArray(value) || value.length > 2000) throw Error('fields_requires_bounded_array');
      value=value.map(item => {
        if (--fuel < 0) throw Error('projection_operation_limit');
        if (!object(item) || row.fields.some((key:string) => !Object.hasOwn(item,key))) throw Error('missing_projected_field');
        return Object.fromEntries(row.fields.map((key:string) => [key,item[key]]));
      });
    }
    entries.push([name,value]);
  }
  const text=JSON.stringify(Object.fromEntries(entries));
  if (Buffer.byteLength(text)>192000) throw Error('projected_input_too_large');
  return JSON.parse(text);
}

function serializeReport(report:any):Buffer {
  if (!object(report) || (Object.getPrototypeOf(report)!==Object.prototype && Object.getPrototypeOf(report)!==null))
    throw Error('report_object_required');
  let text:string;
  try {
    text=JSON.stringify(report,(_key,value) => {
      if (value===undefined || typeof value==='function' || typeof value==='symbol' || typeof value==='bigint' ||
          (typeof value==='number' && !Number.isFinite(value))) throw Error('non_json_report');
      return value;
    },2)+'\n';
  } catch { throw Error('json_report_required'); }
  const bytes=Buffer.from(text);
  if (bytes.length>192000) throw Error('report_too_large');
  return bytes;
}

export function createTraceRsiTaskTools(config:any) {
  if (!object(config) || ['library_path','work','catalog_path','session_id'].some(key => typeof config[key]!=='string' || !config[key]) ||
      !hash(config.catalog_sha256) || !hash(config.source_version)) throw Error('invalid_trace_task_config');
  readBoundedFile(join(resolve(config.work),'triage.json'),192000);
  const work=realpathSync(config.work), reportPath=join(work,'triage.json'), catalogPath=resolve(config.catalog_path);
  if (!lstatSync(work).isDirectory() || basename(catalogPath)!=='catalog.json' || reportPath===catalogPath) throw Error('invalid_task_paths');
  const libraryPath=resolve(config.library_path), libraryBytes=readBoundedFile(libraryPath,192000);
  const libraryHash=sha256(libraryBytes), frozen=validateTraceFrozen(JSON.parse(libraryBytes.toString('utf8')));
  const bindings=frozen.provenance?.proposal?.input_bindings;bindingsValid(bindings);
  if (['read_task_state','write_report'].includes(frozen.candidate.name)) throw Error('task_tool_name_collision');
  if (canonical(Object.keys(bindings).sort())!==canonical(Object.keys(frozen.candidate.input_schema.properties??{}).sort()))
    throw Error('schema_binding_fields_mismatch');
  function versionFiles(files:any,label:string):[string,string][] {
    if (!object(files) || !Object.keys(files).length || Object.keys(files).length>256) throw Error('invalid_'+label+'_files');
    return Object.entries(files).map(([path,sha]) => {
      if (!isAbsolute(path) || resolve(path)!==path || !hash(sha) || path===reportPath) throw Error('invalid_'+label+'_file');
      return [path,sha as string];
    });
  }
  const sources=versionFiles(config.source_files,'source'), codes=versionFiles(config.code_files,'code');
  if (config.source_files[catalogPath]!==config.catalog_sha256) throw Error('catalog_not_bound_to_sources');
  let receipt:any=null;
  function guard():void {
    if (sha256(readBoundedFile(libraryPath,192000))!==libraryHash) throw Error('frozen_trace_library_changed');
    for (const [path,sha] of sources) if (sha256(readBoundedFile(path,50000000))!==sha) throw Error('source_version_changed');
    for (const [path,sha] of codes) if (sha256(readBoundedFile(path,2000000))!==sha) throw Error('code_version_changed');
  }
  function projection(catalog:any,report:any):any {
    const input=projectTraceInputs(catalog,report,bindings), errors=validateJsonSchemaValue(frozen.candidate.input_schema,input);
    if (errors.length) throw Error('projected_input_schema_invalid:'+errors.slice(0,8).join(';'));
    return input;
  }
  function snapshot():any {
    guard();
    const reportBytes=readBoundedFile(reportPath,192000), catalogBytes=readBoundedFile(catalogPath,192000);
    if (lstatSync(reportPath).nlink!==1) throw Error('report_must_be_private_copy');
    const report=JSON.parse(reportBytes.toString('utf8')), catalog=JSON.parse(catalogBytes.toString('utf8'));
    if (!object(report)) throw Error('report_object_required');
    const input=projection(catalog,report), base={input_sha256:digest(input),report_sha256:sha256(reportBytes),
      source_version:config.source_version,candidate_sha256:frozen.candidate_sha256,catalog_sha256:sha256(catalogBytes)};
    guard();
    if (sha256(readBoundedFile(reportPath,192000))!==base.report_sha256) throw Error('report_changed_during_read');
    return {report,catalog,input,base};
  }
  function mint(base:any):any {
    receipt={input_id:'trace-input-'+digest({...base,session_id:config.session_id}),...base};
    return {...receipt};
  }
  function read(args:any):any {
    argsOnly(args,[]);const state=snapshot();
    return {report:state.report,input:state.input,...mint(state.base)};
  }
  function write(args:any):any {
    argsOnly(args,['report_sha256','report']);
    const before=snapshot();
    if (args.report_sha256!==before.base.report_sha256) throw Error('stale_report_write');
    const bytes=serializeReport(args.report), report=JSON.parse(bytes.toString('utf8'));
    projection(before.catalog,report);guard();
    // Open without truncation; validate the actual descriptor before any write.
    const fd=openSync(reportPath,constants.O_RDWR | (constants.O_NOFOLLOW??0));
    try {
      const stat=fstatSync(fd);
      if (!stat.isFile() || stat.size>192000 || stat.nlink!==1) throw Error('report_must_be_private_copy');
      if (sha256(readFileSync(fd))!==args.report_sha256) throw Error('stale_report_write');
      receipt=null;
      let offset=0;
      while (offset<bytes.length) {
        const written=writeSync(fd,bytes,offset,bytes.length-offset,offset);
        if (!written) throw Error('report_write_failed');offset+=written;
      }
      ftruncateSync(fd,bytes.length);
    } finally { closeSync(fd); }
    guard();const after=snapshot();
    if (after.base.report_sha256!==sha256(bytes)) throw Error('report_changed_during_write');
    return mint(after.base);
  }
  function check(args:any):any {
    argsOnly(args,['input_id']);
    if (!receipt || args.input_id!==receipt.input_id) throw Error('unregistered_or_stale_input_id');
    const state=snapshot();
    const expected='trace-input-'+digest({...state.base,session_id:config.session_id});
    const {input_id,...registeredBase}=receipt;
    if (receipt.input_id!==expected || canonical(registeredBase)!==canonical(state.base))
      throw Error('stale_input_id');
    const output=runTraceTool(frozen.candidate,state.input);guard();
    if (sha256(readBoundedFile(reportPath,192000))!==state.base.report_sha256) throw Error('report_changed_during_check');
    return {output:JSON.parse(JSON.stringify(output)),...receipt};
  }
  guard();snapshot();
  const empty={type:'object',properties:{},additionalProperties:false};
  const definitions=[
    {name:'read_task_state',description:'只读当前任务报告副本、冻结来源投影与版本句柄，供你判断并修订；不认证文献事实。',inputSchema:empty,annotations:{readOnlyHint:true}},
    {name:'write_report',description:'以 report_sha256 核对当前版本后保存完整报告对象到本任务 triage.json 副本，返回新投影句柄；不修改来源或原件。',
      inputSchema:{type:'object',properties:{report_sha256:{type:'string'},report:{type:'object'}},required:['report_sha256','report'],additionalProperties:false}},
    {name:frozen.candidate.name,description:frozen.candidate.description+' 使用 read_task_state/write_report 颁发的当前 input_id，只检查结构。',
      inputSchema:{type:'object',properties:{input_id:{type:'string'}},required:['input_id'],additionalProperties:false},annotations:{readOnlyHint:true}}
  ];
  function call(name:string,args:any):any {
    if (name==='read_task_state') return read(args);
    if (name==='write_report') return write(args);
    if (name===frozen.candidate.name) return check(args);
    throw Error('unknown_tool');
  }
  return {definitions,call};
}

if (process.argv[1] && resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  const configPath=process.env.SSS_TRACE_RSI_TASK_CONFIG;
  if (!configPath) throw Error('explicit_trace_task_config_required');
  const tools=createTraceRsiTaskTools(JSON.parse(readBoundedFile(configPath,64000).toString('utf8')));
  const lines=createInterface({input:process.stdin});
  lines.on('line',line => {
    let request:any;try { request=JSON.parse(line); } catch { return; }
    if (!request || request.id===undefined) return;
    let result:any;
    try {
      switch(request.method) {
        case 'initialize':result={protocolVersion:request.params.protocolVersion,capabilities:{tools:{}},serverInfo:{name:'paper_trace_rsi',version:'1.0.0'}};break;
        case 'ping':result={};break;
        case 'tools/list':result={tools:tools.definitions};break;
        case 'tools/call':
          try { result={content:[{type:'text',text:JSON.stringify(tools.call(request.params.name,request.params.arguments??{}))}]}; }
          catch(error) { result={isError:true,content:[{type:'text',text:String(error)}]}; }break;
        default:process.stdout.write(JSON.stringify({jsonrpc:'2.0',id:request.id,error:{code:-32601,message:'Method not found'}})+'\n');return;
      }
      process.stdout.write(JSON.stringify({jsonrpc:'2.0',id:request.id,result})+'\n');
    } catch(error) { process.stdout.write(JSON.stringify({jsonrpc:'2.0',id:request.id,error:{code:-32603,message:String(error)}})+'\n'); }
  });
}
