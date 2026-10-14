/** No host code evaluation: submit RSI AST, test development cases, retain it. */
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {join} from 'node:path';
import {createInterface} from 'node:readline';
import {digest,canonical} from '../../src/adapters/paper_rsi_program.ts';
import {runTraceTool} from '../../src/adapters/trace_rsi_program.ts';
import {readBoundedFile,sha256} from '../../src/adapters/paper_triage_validation.ts';
const config=JSON.parse(readFileSync(process.env.SSS_PATCH_RSI_GENERATION!,'utf8'));
function submit(args:any):any {
  if(!args||canonical(Object.keys(args))!==canonical(['program'])||!Array.isArray(args.program))throw Error('program_array_required');
  for(const [path,hash]of Object.entries(config.learning_files))if(sha256(readBoundedFile(path,2000000))!==hash)throw Error('learning_fixture_or_code_changed');
  const contract=JSON.parse(readBoundedFile(config.contract_path,192000).toString('utf8'));
  const cases=JSON.parse(readBoundedFile(config.development_path,2000000).toString('utf8'));
  const candidate={schema_version:1,...contract,program:args.program},id=digest(candidate),checks=[];
  for(const row of cases){
    try{const actual=runTraceTool(candidate,row.input);checks.push({id:row.id,passed:canonical(actual)===canonical(row.expected)});}
    catch(error){checks.push({id:row.id,passed:false,error:String(error).slice(0,250)});}
  }
  const directory=join(config.work,'candidates');mkdirSync(directory,{recursive:true,mode:0o700});
  try{writeFileSync(join(directory,id+'.json'),JSON.stringify(candidate,null,2)+'\n',{mode:0o600,flag:'wx'});}catch(error:any){if(error.code!=='EEXIST')throw error;}
  const passed=checks.every(r=>r.passed);
  if(passed)writeFileSync(join(config.work,'passed-candidate.json'),JSON.stringify(candidate,null,2)+'\n',{mode:0o600});
  return {candidate_sha256:id,passed,development_cases:checks.length,checks};
}
const definition={name:'submit_generated_program',description:'保存你生成的纯JSON AST并在公开开发样例上验证；没有宿主代码/文件执行，不读取留出样例。失败时可根据错误修正后再提交。',
 inputSchema:{type:'object',properties:{program:{type:'array',items:{},maxItems:2000}},required:['program'],additionalProperties:false}};
const lines=createInterface({input:process.stdin});
lines.on('line',line=>{
 let request:any;try{request=JSON.parse(line);}catch{return;}if(request.id===undefined)return;
 try{
  let result:any;
  if(request.method==='initialize')result={protocolVersion:request.params.protocolVersion,capabilities:{tools:{}},serverInfo:{name:'paper_patch_learning',version:'1.0.0'}};
  else if(request.method==='tools/list')result={tools:[definition]};else if(request.method==='ping')result={};
  else if(request.method==='tools/call'){
   try{if(request.params.name!==definition.name)throw Error('unknown_learning_tool');result={content:[{type:'text',text:JSON.stringify(submit(request.params.arguments))}]};}
   catch(error){result={isError:true,content:[{type:'text',text:String(error)}]};}
  }else throw Error('unknown_method');
  process.stdout.write(JSON.stringify({jsonrpc:'2.0',id:request.id,result})+'\n');
 }catch(error){process.stdout.write(JSON.stringify({jsonrpc:'2.0',id:request.id,error:{code:-32603,message:String(error)}})+'\n');}
});
