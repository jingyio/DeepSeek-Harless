import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,readFileSync,mkdirSync,rmSync,realpathSync,symlinkSync,existsSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {spawnSync} from 'node:child_process';
import {request} from 'node:http';
const ts={skip:!process.features?.typescript};
test('common tools augment explicit scene capabilities without weakening certified MCP contracts',ts,async()=>{
 const {COMMON_TOOLS,sceneCertifiedTools,commonToolDenial}=await import('../src/adapters/geneloop_capabilities.ts');
 const {sceneCatalog}=await import('../src/adapters/harless_settings.ts');
 const scene={id:'new-scene',label:'Chat',preset:'sss-task',common_tools:[...COMMON_TOOLS],allowed_tools:['mcp__workspace__read_file',...COMMON_TOOLS]};
 assert.equal(sceneCatalog([scene]).length,1);
 const certified={name:'mcp__workspace__read_file',parameters:{type:'object'}};
 assert.deepEqual(sceneCertifiedTools(scene,[certified,...COMMON_TOOLS.map(name=>({name}))]),[certified]);
 for(const patch of [{common_tools:['bash']},{allowed_tools:[...scene.allowed_tools,'arbitrary_eval']},{common_tools:[...COMMON_TOOLS,'arbitrary_eval']}])
   assert.throws(()=>sceneCatalog([{...scene,...patch}]));
 assert.throws(()=>sceneCertifiedTools({common_tools:['mcp__workspace__read_file']},[certified]));
 assert.ok(commonToolDenial({name:'bash',arguments:{sandbox_permissions:'danger-full-access'}}));
 assert.equal(commonToolDenial({name:'bash',arguments:{command:'python3 script.py'}}),undefined);
});

test('Private account command transport computes without nested namespaces and rejects foreign Sessions',
 {skip:!process.features?.typescript||process.platform!=='linux'||!existsSync('/usr/bin/bwrap')},async()=>{
 const {startCommandBroker}=await import('../src/adapters/geneloop_command_broker.ts');
 const {commandLayout}=await import('../src/adapters/geneloop_shell.ts');
 const root=realpathSync(mkdtempSync(join(tmpdir(),'geneloop-command-broker-')));
 const session='session-11111111-1111-4111-8111-111111111111';commandLayout(root,session);
 const broker=await startCommandBroker({output:root,python:'/usr/bin/python3',node:process.execPath});
 const call=payload=>new Promise((resolve,reject)=>{const req=request({socketPath:broker.socketPath,path:'/run',method:'POST'},res=>{
  let body='';res.on('data',part=>body+=part);res.on('end',()=>resolve({status:res.statusCode,body}));});req.on('error',reject);req.end(JSON.stringify(payload));});
 try{
  const payload={session,command:'python3 -c "print(sum([3,5,8,13]))"',cwd:'/work',readOnly:false};
  const result=await call(payload);assert.equal(result.status,200);
  const rows=result.body.trim().split('\n').map(line=>JSON.parse(line));
  assert.equal(rows.at(-1).exit,0);assert.equal(rows.filter(r=>r.stdout).map(r=>Buffer.from(r.stdout,'base64').toString()).join('').trim(),'29');
  assert.equal((await call({...payload,session:'session-22222222-2222-4222-8222-222222222222'})).status,400);
  assert.equal((await call({...payload,cwd:'/work/../../etc'})).status,400);
  assert.equal((await call({...payload,env:{DEEPSEEK_API_KEY:'untrusted'}})).status,400);
  assert.equal((await call({...payload,network:'host'})).status,400);
  const isolated=await call({...payload,network:'none',command:'python3 -c "import socket; assert all(name==\'lo\' for _,name in socket.if_nameindex()); print(\'isolated\')"'});
  assert.equal(isolated.status,200);
  assert.equal(JSON.parse(isolated.body.trim().split('\n').at(-1)).exit,0);
 }finally{broker.close();rmSync(root,{recursive:true,force:true});}
});
test('native search discovers without an Agent, but dispatch requires an owning Session and accounted endpoint',ts,async()=>{
 const directory=mkdtempSync(join(tmpdir(),'geneloop-search-'));
 const oldPolicy=process.env.SSS_WEB_POLICY,oldKey=process.env.DEEPSEEK_API_KEY,oldFetch=globalThis.fetch;
 try{
  process.env.SSS_WEB_POLICY=join(directory,'policy.json');process.env.DEEPSEEK_API_KEY='test-not-a-secret';
  writeFileSync(process.env.SSS_WEB_POLICY,JSON.stringify({endpoint:'http://127.0.0.1:12345/v1'}));
  const {apply}=await import('../src/adapters/geneloop_web_search.ts');let provider,agent,call;
  apply({web:{registerSearchProvider:p=>provider=p},agents:{currentInitiator:()=>agent}});
  assert.equal(provider.available(),true);
  await assert.rejects(provider.search({query:'test'}),/owning Agent/);
  agent={session:{id:'session-11111111-1111-4111-8111-111111111111',requestHeader:()=>({config:{model:'deepseek-v4-pro'}}),append(){}}};
  globalThis.fetch=async(url,options)=>{call={url,options};return new Response(JSON.stringify({content:[{type:'web_search_tool_result',content:[{type:'web_search_result',url:'https://docs.python.org/3/',title:'Python'}]}]}),{status:200});};
  const result=await provider.search({query:'Python official documentation'});
  assert.equal(result.sources[0].url,'https://docs.python.org/3/');
  assert.equal(call.url,'http://127.0.0.1:12345/v1/search/'+agent.session.id+'/messages');
  assert.equal(JSON.parse(call.options.body).model,'deepseek-v4-pro');
  assert.equal(new Headers(call.options.headers).get('authorization'),'Bearer test-not-a-secret');
  writeFileSync(process.env.SSS_WEB_POLICY,JSON.stringify({endpoint:'http://127.0.0.1:12345/v1',budget_broker_endpoint:'http://127.0.0.1:12346'}));
  apply({web:{registerSearchProvider:p=>provider=p},agents:{currentInitiator:()=>agent}});
  await provider.search({query:'owner persistent turn'});
  assert.equal(call.url,'http://127.0.0.1:12346/v1/search/'+agent.session.id+'/messages');
  const cancel=new AbortController();cancel.abort();await assert.rejects(provider.search({query:'cancel'},cancel.signal),/aborted/);
 }finally{globalThis.fetch=oldFetch;for(const [key,value]of[['SSS_WEB_POLICY',oldPolicy],['DEEPSEEK_API_KEY',oldKey]])value===undefined?delete process.env[key]:process.env[key]=value;rmSync(directory,{recursive:true,force:true});}
});
test('Linux commands compute, isolate credentials and sessions, protect inputs, and honor read-only policy',
 {skip:!process.features?.typescript||process.platform!=='linux'||!existsSync('/usr/bin/bwrap')},async()=>{
 const {commandLayout,commandArgv}=await import('../src/adapters/geneloop_shell.ts');
 const root=realpathSync(mkdtempSync(join(tmpdir(),'geneloop-shell-')));
 try{
  const layout=commandLayout(root,'session-11111111-1111-4111-8111-111111111111');
  const foreign=join(root,'foreign-secret');writeFileSync(foreign,'private');writeFileSync(join(layout.inputs,'input.txt'),'original');
  const run=(command,readOnly=false)=>{const [bin,...args]=commandArgv(layout,command,'/work','/usr/bin/python3',process.execPath,readOnly);return spawnSync(bin,args,{env:{...process.env,DEEPSEEK_API_KEY:'must-not-leak'},encoding:'utf8',timeout:15000});};
  const result=run(`python3 -c 'import json,os; assert not os.getenv("DEEPSEEK_API_KEY"); assert not os.path.exists("${foreign}"); print(sum([3,5,8,13])); open("outputs/result.txt","w").write("29")'`);
  assert.equal(result.status,0,result.stderr);assert.equal(result.stdout.trim(),'29');assert.equal(readFileSync(join(layout.outputs,'result.txt'),'utf8'),'29');
  assert.notEqual(run('printf changed > inputs/input.txt').status,0);assert.equal(readFileSync(join(layout.inputs,'input.txt'),'utf8'),'original');
  assert.notEqual(run('touch outputs/forbidden',true).status,0);
  assert.equal(run('printf report > /tmp/checker-report.txt').status,0);
  assert.equal(run('cat /tmp/checker-report.txt').stdout,'report');
  const other=commandLayout(root,'session-22222222-2222-4222-8222-222222222222');
  const [otherBin,...otherArgs]=commandArgv(other,'test ! -e /tmp/checker-report.txt','/work','/usr/bin/python3',process.execPath);
  assert.equal(spawnSync(otherBin,otherArgs,{encoding:'utf8',timeout:15000}).status,0);
  assert.throws(()=>commandLayout(root,'../../other'));
  rmSync(layout.scratch,{recursive:true});symlinkSync(root,layout.scratch);assert.throws(()=>commandLayout(root,'session-11111111-1111-4111-8111-111111111111'),/fixed directory/);
 }finally{rmSync(root,{recursive:true,force:true});}
});
