/** One frozen trace-derived tool over MCP stdio. Calls accept only JSON input. */
import { createHash } from 'node:crypto';
import { lstatSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';
import { runTraceTool, validateTraceFrozen } from '../../src/adapters/trace_rsi_program.ts';

function readBounded(path:string,limit:number):Buffer {
  const stat = lstatSync(path);
  if (!stat.isFile() || stat.isSymbolicLink() || stat.size > limit) throw Error('regular_bounded_library_required');
  const bytes = readFileSync(path);
  if (bytes.length > limit) throw Error('library_too_large');
  return bytes;
}
const bytesHash = (bytes:Buffer) => createHash('sha256').update(bytes).digest('hex');
export function createTraceRsiTools(config:any) {
  if (!config || typeof config !== 'object' || Array.isArray(config) || Object.keys(config).length !== 1 ||
      typeof config.library_path !== 'string' || !config.library_path) throw Error('explicit_frozen_trace_library_required');
  const libraryPath = resolve(config.library_path), bytes = readBounded(libraryPath,192000);
  const frozen = validateTraceFrozen(JSON.parse(bytes.toString('utf8'))), initialHash = bytesHash(bytes);
  const definitions = [{name:frozen.candidate.name,description:frozen.candidate.description,
    inputSchema:JSON.parse(JSON.stringify(frozen.candidate.input_schema)),annotations:{readOnlyHint:true}}];
  function call(name:string,args:any) {
    if (name !== frozen.candidate.name) throw Error('unknown_tool');
    if (bytesHash(readBounded(libraryPath,192000)) !== initialHash) throw Error('frozen_trace_library_changed');
    const output = runTraceTool(frozen.candidate,args);
    if (bytesHash(readBounded(libraryPath,192000)) !== initialHash) throw Error('frozen_trace_library_changed');
    return {output,candidate_sha256:frozen.candidate_sha256};
  }
  return {definitions,call};
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const configPath = process.env.SSS_TRACE_RSI_CONFIG;
  if (!configPath) throw Error('explicit_trace_rsi_config_required');
  const tools = createTraceRsiTools(JSON.parse(readBounded(configPath,32000).toString('utf8')));
  const lines = createInterface({input:process.stdin});
  lines.on('line',(line) => {
    let request:any;
    try { request = JSON.parse(line); } catch { return; }
    if (!request || request.id === undefined) return;
    let result:any;
    try {
      switch (request.method) {
        case 'initialize':result = {protocolVersion:request.params.protocolVersion,capabilities:{tools:{}},
          serverInfo:{name:'trace-rsi',version:'1.0.0'}};break;
        case 'ping':result = {};break;
        case 'tools/list':result = {tools:tools.definitions};break;
        case 'tools/call':
          try { result = {content:[{type:'text',text:JSON.stringify(tools.call(request.params.name,request.params.arguments ?? {}))}]}; }
          catch (error) { result = {isError:true,content:[{type:'text',text:String(error)}]}; }
          break;
        default:process.stdout.write(JSON.stringify({jsonrpc:'2.0',id:request.id,error:{code:-32601,message:'Method not found'}})+'\n');return;
      }
      process.stdout.write(JSON.stringify({jsonrpc:'2.0',id:request.id,result})+'\n');
    } catch (error) {
      process.stdout.write(JSON.stringify({jsonrpc:'2.0',id:request.id,error:{code:-32603,message:String(error)}})+'\n');
    }
  });
}
