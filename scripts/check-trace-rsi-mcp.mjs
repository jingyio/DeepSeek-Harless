/** Free transport diagnostic against the existing frozen-tool MCP stdio server.
 * Usage: node --experimental-strip-types scripts/check-trace-rsi-mcp.mjs FROZEN CASES
 * No model calls or historical shell execution. Hash checks establish integrity,
 * not producer authenticity, scientific quality or cross-paper generality.
 */
import { createHash } from 'node:crypto';
import { lstatSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { validateJsonSchemaValue } from '@deepseek-ai/dsh-tools';
import { canonical, digest } from '../src/adapters/paper_rsi_program.ts';
import { validateTraceFrozen } from '../src/adapters/trace_rsi_program.ts';

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const serverPath = join(root,'scenarios','paper-submission','trace-rsi-server.ts');
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const message = error => String(error instanceof Error ? error.message : error).slice(0,1000);
function readBounded(path,limit) {
  const stat = lstatSync(path);
  if (!stat.isFile() || stat.isSymbolicLink() || stat.size > limit) throw Error('regular_bounded_file_required');
  const bytes = readFileSync(path);
  if (bytes.length > limit) throw Error('file_too_large');
  return bytes;
}

function stdioClient(configPath) {
  const child = spawn(process.execPath,['--experimental-strip-types',serverPath],{
    cwd:root,env:{...process.env,SSS_TRACE_RSI_CONFIG:configPath},stdio:['pipe','pipe','pipe'],shell:false,windowsHide:true});
  const pending = new Map();let nextId=0,buffer='',stderr='',terminalError=null,closed=false,forceTimer;
  let resolveClosed;
  const exit = new Promise(resolve => { resolveClosed=resolve; });
  function fail(error) {
    terminalError ??= error instanceof Error ? error : Error(String(error));
    for (const task of pending.values()) { clearTimeout(task.timer);task.reject(terminalError); }
    pending.clear();
    if (!closed) {
      child.kill('SIGTERM');
      forceTimer ??= setTimeout(() => { if (!closed) child.kill('SIGKILL'); },250);
    }
  }
  const overallTimer = setTimeout(() => fail(Error('mcp_total_timeout')),30000);
  child.stdout.setEncoding('utf8');child.stderr.setEncoding('utf8');
  child.stderr.on('data',chunk => { stderr=(stderr+chunk).slice(-12000); });
  child.stdout.on('data',chunk => {
    buffer += chunk;
    while (buffer.includes('\n')) {
      const index=buffer.indexOf('\n'),line=buffer.slice(0,index);buffer=buffer.slice(index+1);
      // The server JSON-encodes a text block containing up to 192KB of output;
      // its outer JSON-RPC encoding may double escaped bytes.
      if (Buffer.byteLength(line)>512000) { fail(Error('mcp_response_too_large'));return; }
      if (!line.trim()) continue;
      let row;
      try { row=JSON.parse(line); } catch { fail(Error('invalid_mcp_json_response'));return; }
      if (!object(row) || row.jsonrpc !== '2.0') { fail(Error('invalid_mcp_response_envelope'));return; }
      if (row.id === undefined) continue;
      const task=pending.get(row.id);
      if (!task) { fail(Error('unexpected_mcp_response_id'));return; }
      pending.delete(row.id);clearTimeout(task.timer);
      if (row.error) task.reject(Error('mcp_rpc_error:'+message(row.error.message ?? row.error)));
      else if (!Object.hasOwn(row,'result')) task.reject(Error('missing_mcp_result'));
      else task.resolve(row.result);
    }
    if (Buffer.byteLength(buffer)>512000) fail(Error('mcp_response_too_large'));
  });
  child.on('error',error => fail(Error('mcp_process_error:'+message(error))));
  child.stdin.on('error',error => fail(Error('mcp_stdin_error:'+message(error))));
  child.on('close',(code,signal) => {
    closed=true;clearTimeout(overallTimer);clearTimeout(forceTimer);
    if (pending.size) fail(Error('mcp_closed_before_response'));
    resolveClosed({code,signal,error:terminalError ? message(terminalError) : null,
      ...(code !== 0 && stderr ? {stderr:stderr.slice(-1000)} : {})});
  });
  function request(method,params={}) {
    if (terminalError) return Promise.reject(terminalError);
    if (closed) return Promise.reject(Error('mcp_process_closed'));
    const id=++nextId;
    return new Promise((resolve,reject) => {
      const timer=setTimeout(() => fail(Error('mcp_request_timeout:'+method)),5000);
      pending.set(id,{resolve,reject,timer});
      child.stdin.write(JSON.stringify({jsonrpc:'2.0',id,method,params})+'\n',error => {
        if (error) fail(Error('mcp_write_error:'+message(error)));
      });
    });
  }
  async function close() {
    if (!closed) child.stdin.end();
    const closeTimer=setTimeout(() => fail(Error('mcp_shutdown_timeout')),1000);
    try { return await exit; } finally { clearTimeout(closeTimer);clearTimeout(overallTimer);clearTimeout(forceTimer); }
  }
  return {request,close};
}

export async function checkTraceRsiMcp(frozenPath,casesPath) {
  const result={passed:false,name:null,casecount:0,diagnostic:'frozen_mcp_stdio_no_model_calls',
    hash_validation:{frozen_manifest:false,candidate:false,library_stable:false,cases_stable:false},
    schema_validation:{listed_name:false,listed_description:false,listed_input_schema:false,
      all_inputs:false,all_expected_outputs:false,all_actual_outputs:false},cases:[]};
  let temporary=null,client=null;
  try {
    const libraryPath=resolve(frozenPath),casePath=resolve(casesPath);
    const libraryBytes=readBounded(libraryPath,192000),caseBytes=readBounded(casePath,2000000);
    result.frozen_file_sha256=sha256(libraryBytes);result.cases_file_sha256=sha256(caseBytes);
    const frozen=validateTraceFrozen(JSON.parse(libraryBytes.toString('utf8'))),cases=JSON.parse(caseBytes.toString('utf8'));
    result.name=frozen.candidate.name;result.candidate_sha256=frozen.candidate_sha256;result.manifest_digest=frozen.manifest_digest;
    result.hash_validation.frozen_manifest=true;result.hash_validation.candidate=true;
    if (!Array.isArray(cases) || cases.length<1 || cases.length>2000 || cases.some(row =>
      !object(row) || !Object.hasOwn(row,'input') || !Object.hasOwn(row,'expected'))) throw Error('bounded_input_expected_cases_required');
    result.casecount=cases.length;result.cases_sha256=digest(cases);
    temporary=mkdtempSync(join(tmpdir(),'sss-trace-rsi-mcp-'));
    const configPath=join(temporary,'config.json');writeFileSync(configPath,JSON.stringify({library_path:libraryPath}),{mode:0o600});
    client=stdioClient(configPath);
    const initialized=await client.request('initialize',{protocolVersion:'2025-06-18',capabilities:{},
      clientInfo:{name:'sss-trace-rsi-mcp-diagnostic',version:'1.0.0'}});
    if (initialized.protocolVersion !== '2025-06-18' || !object(initialized.capabilities?.tools)) throw Error('unexpected_mcp_initialize_result');
    const listed=await client.request('tools/list');
    if (!Array.isArray(listed.tools) || listed.tools.length !== 1) throw Error('expected_one_dynamic_frozen_tool');
    const definition=listed.tools[0];
    result.schema_validation.listed_name=definition.name === frozen.candidate.name;
    result.schema_validation.listed_description=definition.description === frozen.candidate.description;
    result.schema_validation.listed_input_schema=canonical(definition.inputSchema) === canonical(frozen.candidate.input_schema);
    result.input_schema_sha256=digest(definition.inputSchema);result.output_schema_sha256=digest(frozen.candidate.output_schema);
    if (!result.schema_validation.listed_name || !result.schema_validation.listed_description ||
        !result.schema_validation.listed_input_schema) throw Error('listed_frozen_contract_mismatch');
    for (const [index,row] of cases.entries()) {
      const inputErrors=validateJsonSchemaValue(frozen.candidate.input_schema,row.input);
      const expectedErrors=validateJsonSchemaValue(frozen.candidate.output_schema,row.expected);
      const record={id:row.id ?? index,passed:false,input_sha256:digest(row.input),expected_sha256:digest(row.expected),
        input_schema_valid:inputErrors.length===0,expected_schema_valid:expectedErrors.length===0,
        output_schema_valid:false,candidate_hash_valid:false};
      try {
        const response=await client.request('tools/call',{name:definition.name,arguments:row.input});
        if (response.isError) throw Error('mcp_tool_error:'+message(response.content?.find(block => block.type === 'text')?.text ?? 'unknown'));
        if (!Array.isArray(response.content) || response.content.length !== 1 || response.content[0].type !== 'text')
          throw Error('unexpected_mcp_tool_content');
        const value=JSON.parse(response.content[0].text);
        if (!object(value) || !Object.hasOwn(value,'output')) throw Error('missing_mcp_tool_output');
        const outputErrors=validateJsonSchemaValue(frozen.candidate.output_schema,value.output);
        record.output_schema_valid=outputErrors.length===0;record.candidate_hash_valid=value.candidate_sha256===frozen.candidate_sha256;
        record.output_sha256=digest(value.output);record.output_matches_expected=canonical(value.output)===canonical(row.expected);
        record.passed=record.input_schema_valid && record.expected_schema_valid && record.output_schema_valid &&
          record.candidate_hash_valid && record.output_matches_expected;
        if (outputErrors.length) record.output_schema_errors=outputErrors.slice(0,8);
      } catch (error) { record.error=message(error); }
      if (inputErrors.length) record.input_schema_errors=inputErrors.slice(0,8);
      if (expectedErrors.length) record.expected_schema_errors=expectedErrors.slice(0,8);
      result.cases.push(record);
    }
    result.schema_validation.all_inputs=result.cases.every(row => row.input_schema_valid);
    result.schema_validation.all_expected_outputs=result.cases.every(row => row.expected_schema_valid);
    result.schema_validation.all_actual_outputs=result.cases.every(row => row.output_schema_valid);
    result.hash_validation.library_stable=sha256(readBounded(libraryPath,192000))===result.frozen_file_sha256;
    result.hash_validation.cases_stable=sha256(readBounded(casePath,2000000))===result.cases_file_sha256;
    result.server_exit=await client.close();client=null;
    result.passed=result.cases.every(row => row.passed) && Object.values(result.schema_validation).every(Boolean) &&
      Object.values(result.hash_validation).every(Boolean) && result.server_exit.code===0 && !result.server_exit.error;
  } catch (error) { result.error=message(error); }
  finally {
    if (client) result.server_exit=await client.close();
    if (temporary) rmSync(temporary,{recursive:true,force:true});
  }
  return result;
}

if (process.argv[1] && resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  const args=process.argv.slice(2);
  const result=args.length===2 ? await checkTraceRsiMcp(args[0],args[1]) :
    {passed:false,name:null,casecount:0,error:'usage: check-trace-rsi-mcp.mjs FROZEN_PATH CASES_PATH'};
  process.stdout.write(JSON.stringify(result)+'\n');
  if (!result.passed) process.exitCode=1;
}
