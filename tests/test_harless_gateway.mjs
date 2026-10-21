import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import net from 'node:net';
import { once } from 'node:events';
import { spawn } from 'node:child_process';
import { createHash, createHmac } from 'node:crypto';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, realpathSync, rmSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createGateway, createOwnerClaim, createInvites, memberWatcherEnvironment } from '../scripts/harless_gateway.mjs';
import { memberSceneDeployment } from '../scripts/harless_member_scenes.mjs';
import WebSocket, { WebSocketServer } from 'ws';

test('member watcher environment defaults to polling and forwards no unrelated authority', () => {
  assert.deepEqual(memberWatcherEnvironment({}), {CHOKIDAR_USEPOLLING:'1',CHOKIDAR_INTERVAL:'1000'});
  assert.deepEqual(memberWatcherEnvironment({CHOKIDAR_USEPOLLING:'TRUE',CHOKIDAR_INTERVAL:'0250',
    API_KEY:'private-parent-value',NODE_OPTIONS:'--inspect',CHOKIDAR_IGNORED:'**'}),
  {CHOKIDAR_USEPOLLING:'1',CHOKIDAR_INTERVAL:'250'});
  for (const polling of ['0','false','FALSE'])
    assert.deepEqual(memberWatcherEnvironment({CHOKIDAR_USEPOLLING:polling}),
      {CHOKIDAR_USEPOLLING:'0',CHOKIDAR_INTERVAL:'1000'});
  for (const polling of ['', 'yes', '2', 'true\n', true])
    assert.throws(()=>memberWatcherEnvironment({CHOKIDAR_USEPOLLING:polling}),/CHOKIDAR_USEPOLLING/);
  for (const interval of ['', '0', '-1', '1.5', '1e3', '1000ms', '2147483648', '9007199254740993', 1000])
    assert.throws(()=>memberWatcherEnvironment({CHOKIDAR_INTERVAL:interval}),/CHOKIDAR_INTERVAL/);
});

test('member polling receives actual file changes without allocating fs.watch handles', async t => {
  const directory=mkdtempSync(join(tmpdir(),'harless-member-poll-')),file=join(directory,'ownership.json');
  t.after(()=>rmSync(directory,{recursive:true,force:true}));
  writeFileSync(file,'original');
  const source=`
import fs from 'node:fs';
import assert from 'node:assert/strict';
import {once} from 'node:events';
let nativeWatches=0;
fs.watch=()=>{nativeWatches++;throw Object.assign(new Error('diagnostic inotify exhausted'),{code:'ENOSPC'});};
const {watch}=await import('chokidar');
const watcher=watch(process.argv[1],{ignoreInitial:true});
const report=value=>new Promise((resolve,reject)=>process.send(value,error=>error?reject(error):resolve()));
try {
  await once(watcher,'ready',{signal:AbortSignal.timeout(30000)});
  const changed=once(watcher,'change',{signal:AbortSignal.timeout(30000)});
  await report({phase:'ready'});
  await changed;
  assert.equal(nativeWatches,0);
  await report({phase:'changed',nativeWatches});
  console.log('polling-change-without-native-watch');
} finally {await watcher.close();process.disconnect();}
`;
  const child=spawn(process.execPath,['--input-type=module','-e',source,file],{
    cwd:new URL('../',import.meta.url),
    env:{...process.env,...memberWatcherEnvironment({CHOKIDAR_USEPOLLING:'true',CHOKIDAR_INTERVAL:'20'})},
    stdio:['ignore','pipe','pipe','ipc']});
  t.after(()=>{if(child.exitCode===null&&child.signalCode===null)child.kill();});
  let stdout='',stderr='';child.stdout.on('data',chunk=>stdout+=chunk);child.stderr.on('data',chunk=>stderr+=chunk);
  let phase='starting',timer,mutations,timedOut=false,mutationCount=0,observed=false;
  const deadline=ms=>{clearTimeout(timer);timer=setTimeout(()=>{timedOut=true;child.kill();},ms);timer.unref();};
  deadline(30000);
  child.on('message',message=>{
    if(message?.phase==='ready'&&phase==='starting'){
      phase='observing';deadline(30000);
      // ready does not promise that fs.watchFile's first stat sample has
      // finished. Keep making real, distinct versions until a poll sees one.
      const mutate=()=>writeFileSync(file,'changed ownership record '+(++mutationCount)+' '.repeat(mutationCount));
      mutate();mutations=setInterval(mutate,100);
    }else if(message?.phase==='changed'&&phase==='observing'){
      observed=message.nativeWatches===0;phase='closing';clearInterval(mutations);deadline(10000);
    }
  });
  let code,signal;
  try{[code,signal]=await once(child,'close');}
  finally{clearTimeout(timer);clearInterval(mutations);}
  assert.equal(code,0,JSON.stringify({phase,signal,timedOut,mutationCount,stdout,stderr}));
  assert.ok(observed&&mutationCount>0,'child must observe a real changed file with zero native watch allocations');
  assert.match(stdout,/polling-change-without-native-watch/);
});

test('Scene deployment mounts code read-only and keeps user data and credentials out', t => {
  const root=realpathSync(mkdtempSync(join(tmpdir(),'harless-scene-deploy-')));
  t.after(()=>rmSync(root,{recursive:true,force:true}));
  for(const name of ['src','scripts','scenarios','python/bin'])mkdirSync(join(root,name),{recursive:true});
  const python=join(root,'python/bin/python');writeFileSync(python,'test dependency file');
  writeFileSync(join(root,'python/pyvenv.cfg'),'diagnostic installation marker');
  const scene={id:'new-scene',preset:'sss-task',label:'New Scene',adapter:'workspace',
    allowed_tools:['mcp__workspace__list_files'],environment_references:{},
    mcp_rows:[{name:'@deepseek-ai/dsh-mcp-client',config:{serverName:'workspace',transport:'stdio',command:python,
      cwd:root,args:[join(root,'scenarios/general/server.py'),'__HARLESS_SESSION_WORKSPACE__/inputs']}}]};
  const policy={scenes:[scene],resources:{owner_private:{text:'Never inherit this'}}};
  const deployment={projectRoot:root,pythonExecutable:python,pythonRoots:[join(root,'python')]};
  const result=memberSceneDeployment(policy,deployment);
  assert.equal(result.output,'/app/.local/web');
  assert.deepEqual(result.native_resources,{projectRoot:'/app'});
  assert.deepEqual(result.allowed_tools,scene.allowed_tools);
  assert.equal(result.scenes[0].mcp_rows[0].config.args[0],'/app/scenarios/general/server.py');
  assert.equal(result.scenes[0].mcp_rows[0].config.args[1],'__HARLESS_SESSION_WORKSPACE__/inputs');
  assert.ok(result.mounts.every(row=>row.source!==root && !row.source.includes('/.local/')));
  assert.equal(policy.scenes[0].mcp_rows[0].config.cwd,root);
  assert.equal(result.scenes[0].resources,undefined);
  const certified=memberSceneDeployment({...policy,scenes:[{...scene,certified_code_locks:{
    [join(root,'config/geneloop-capabilities.json')]:'public-capability-digest',
    [join(root,'src/adapters/geneloop_shell.ts')]:'shell-digest'}}]},deployment);
  assert.deepEqual(certified.scenes[0].certified_code_locks,{
    '/app/config/geneloop-capabilities.json':'public-capability-digest',
    '/app/src/adapters/geneloop_shell.ts':'shell-digest'});
  assert.ok(!certified.mounts.some(row=>row.source===join(root,'config')),
    'translate public config locks without mounting private config siblings');
  assert.equal(memberSceneDeployment(policy,undefined),null);
  assert.throws(()=>memberSceneDeployment({...policy,scenes:[{...scene,environment_references:{key:'owner-secret'}}]},deployment),/credentials/);
  const withSecret=structuredClone(scene);withSecret.mcp_rows[0].config.env={API_KEY:'never-deploy'};
  assert.throws(()=>memberSceneDeployment({...policy,scenes:[withSecret]},deployment),/authority/);
  assert.throws(()=>memberSceneDeployment(policy,{...deployment,pythonRoots:[root]}),/installation/);
  const unsafe=structuredClone(scene);unsafe.mcp_rows[0].config.args[0]='/owner/private/tool.py';
  assert.throws(()=>memberSceneDeployment({...policy,scenes:[unsafe]},deployment),/approved scene code/);
  assert.throws(()=>memberSceneDeployment({...policy,scenes:[{...scene,manifest:join(root,'private-manifest.json')}]},deployment),/sanitized/);
  const library=join(root,'library');mkdirSync(library);writeFileSync(join(library,'agent-events.jsonl'),'private raw trace');
  assert.throws(()=>memberSceneDeployment(policy,{...deployment,libraryRoot:library}),/private evidence/);
  const files={id:'files',preset:'sss-scene-files',label:'Files',adapter:'files',
    allowed_tools:['mcp__file_management__read_task'],environment_references:{},
    mcp_rows:[{name:'@deepseek-ai/dsh-mcp-client',config:{serverName:'file_management',transport:'stdio',
      command:python,cwd:root,args:[join(root,'scenarios/file-management/plan_tools.py')],env:{
        FM_WEB_WORKSPACE:'__HARLESS_SESSION_WORKSPACE__',
        FM_TASK_FILE:'__HARLESS_SESSION_WORKSPACE__/file-task.json',
        FM_OUTPUT:'__HARLESS_SESSION_WORKSPACE__/file-results'}}}]};
  const withFiles=memberSceneDeployment({...policy,scenes:[scene,files]},deployment);
  assert.equal(withFiles.scenes[1].mcp_rows[0].config.args[0],'/app/scenarios/file-management/plan_tools.py');
  assert.equal(withFiles.scenes[1].mcp_rows[0].config.env.FM_TASK_FILE,
    '__HARLESS_SESSION_WORKSPACE__/file-task.json');
  assert.deepEqual(withFiles.allowed_tools,[...scene.allowed_tools,...files.allowed_tools]);
  const unsafeFiles=structuredClone(files);
  unsafeFiles.mcp_rows[0].config.env.FM_OUTPUT='/owner/private';
  assert.throws(()=>memberSceneDeployment({...policy,scenes:[unsafeFiles]},deployment),/server-bound task workspace/);
  const dependencyStore=join(root,'dependencies/node_modules'), releaseLink=join(root,'release/node_modules');
  mkdirSync(dependencyStore,{recursive:true});mkdirSync(join(root,'release'));mkdirSync(join(root,'scenarios/research_ppt'));
  symlinkSync(dependencyStore,releaseLink,process.platform==='win32'?'junction':'dir');
  symlinkSync(releaseLink,join(root,'scenarios/research_ppt/node_modules'),process.platform==='win32'?'junction':'dir');
  const linked=memberSceneDeployment(policy,deployment);
  assert.ok(linked.mounts.some(row=>row.source===realpathSync(dependencyStore)&&row.target===releaseLink),
    'the dependency mount must resolve the first release symlink inside the member namespace');
  assert.ok(!linked.mounts.some(row=>row.source===join(root,'release')),'never expose a whole release checkout');
});

test('native member resources use only verified namespace mounts while host resources stay unchanged', t => {
  const root=realpathSync(mkdtempSync(join(tmpdir(),'harless-native-resources-')));
  t.after(()=>rmSync(root,{recursive:true,force:true}));
  for(const name of ['scenarios/ppt_master','python/bin','approved-skill','renderer/program','renderer/share','fonts'])
    mkdirSync(join(root,name),{recursive:true});
  const python=join(root,'python/bin/python');writeFileSync(python,'public diagnostic Python');
  writeFileSync(join(root,'python/pyvenv.cfg'),'diagnostic installation');
  const skillRoot=join(root,'approved-skill'),raw='---\nname: ppt-master\ndescription: Diagnostic public skill.\n---\nPublic diagnostic content.\n';
  writeFileSync(join(skillRoot,'SKILL.md'),raw);
  const files={'SKILL.md':createHash('sha256').update(raw).digest('hex')};
  writeFileSync(join(root,'scenarios/ppt_master/skill-lock.json'),JSON.stringify({schema_version:1,version:'6.6.0',files,
    package_sha256:createHash('sha256').update(JSON.stringify(files)).digest('hex')}));
  const rendererRoot=join(root,'renderer'),fontRoot=join(root,'fonts');
  writeFileSync(join(rendererRoot,'program/soffice.bin'),'diagnostic renderer');
  writeFileSync(join(fontRoot,'NotoSansCJKsc-Regular.otf'),'public diagnostic font');
  writeFileSync(join(fontRoot,'fonts-static.conf'),'public diagnostic configuration');
  const scene={id:'chat',adapter:'workspace',allowed_tools:[],mcp_rows:[{name:'@deepseek-ai/dsh-mcp-client',
    config:{serverName:'workspace',transport:'stdio',command:python,cwd:root,args:[join(root,'scenarios/general/server.py')]}}]};
  const policy={scenes:[scene],command_resources:{projectRoot:'/unmounted/host',pptMasterRoot:'/unvalidated/skill',
    rendererRoot:'/unvalidated/renderer',fontRoot:'/unvalidated/fonts',unapproved:'never-inherit'}};
  const deployment={projectRoot:root,pythonExecutable:python,pythonRoots:[join(root,'python')],pptMasterRoot:skillRoot,rendererRoot,fontRoot};
  const before=structuredClone({policy,deployment}),result=memberSceneDeployment(policy,deployment);
  assert.deepEqual(result.native_resources,{projectRoot:'/app',pptMasterRoot:'/opt/geneloop/ppt-master',rendererRoot,fontRoot});
  assert.ok(result.mounts.some(m=>m.source===skillRoot&&m.target===result.native_resources.pptMasterRoot));
  assert.ok(result.mounts.some(m=>m.source===join(root,'scenarios')&&m.target==='/app/scenarios'));
  for(const field of ['rendererRoot','fontRoot'])assert.ok(result.mounts.some(m=>m.source===deployment[field]&&m.target===result.native_resources[field]));
  assert.deepEqual({policy,deployment},before,'owner configuration and host broker resources must not be rewritten');
  assert.deepEqual(memberSceneDeployment(policy,{...deployment,pptMasterRoot:undefined,rendererRoot:undefined,fontRoot:undefined}).native_resources,
    {projectRoot:'/app'},'an inherited skill path never grants a mount when the validated deployment has no skill');
});

test('data report fonts require the fixed mounted resource and its matching digest', t => {
  const root=realpathSync(mkdtempSync(join(tmpdir(),'harless-report-font-')));
  t.after(()=>rmSync(root,{recursive:true,force:true}));
  for(const name of ['scenarios','python/bin','fonts'])mkdirSync(join(root,name),{recursive:true});
  const python=join(root,'python/bin/python');writeFileSync(python,'test dependency');
  writeFileSync(join(root,'python/pyvenv.cfg'),'test installation');
  const fontRoot=join(root,'fonts'), font=join(fontRoot,'wqy-microhei.ttc');
  writeFileSync(join(fontRoot,'NotoSansCJKsc-Regular.otf'),'existing public PPT font');
  writeFileSync(join(fontRoot,'WQY-COPYRIGHT.txt'),'public font license');
  writeFileSync(font,'public report font fixture');
  const scene={id:'data',adapter:'data-report',allowed_tools:['mcp__research_report__inspect_study'],
    report_font_sha256:createHash('sha256').update(readFileSync(font)).digest('hex'),
    mcp_rows:[{name:'@deepseek-ai/dsh-mcp-client',config:{serverName:'research_report',transport:'stdio',
      command:python,cwd:root,args:[join(root,'scenarios/data_analysis/report_session.py')],
      env:{HARLESS_REPORT_WORKSPACE:'__HARLESS_SESSION_WORKSPACE__',HARLESS_REPORT_FONT:font}}}]};
  const deployment={projectRoot:root,pythonExecutable:python,pythonRoots:[join(root,'python')],fontRoot};
  const deploy=(value=scene,options=deployment)=>memberSceneDeployment({scenes:[value]},options);
  const result=deploy();
  assert.equal(result.scenes[0].mcp_rows[0].config.env.HARLESS_REPORT_FONT,font);
  assert.ok(result.mounts.some(row=>row.source===fontRoot && row.target===fontRoot));
  assert.throws(()=>deploy(scene,{...deployment,fontRoot:undefined}),/matching fixed public font/);
  const wrongPath=structuredClone(scene);wrongPath.mcp_rows[0].config.env.HARLESS_REPORT_FONT=join(fontRoot,'NotoSansCJKsc-Regular.otf');
  assert.throws(()=>deploy(wrongPath),/matching fixed public font/);
  assert.throws(()=>deploy({...scene,report_font_sha256:undefined}),/matching fixed public font/);
  assert.throws(()=>deploy({...scene,report_font_sha256:'0'.repeat(64)}),/matching fixed public font/);
  const absentEnv=structuredClone(scene);delete absentEnv.mcp_rows[0].config.env.HARLESS_REPORT_FONT;
  assert.throws(()=>deploy(absentEnv),/matching fixed public font/);
  delete absentEnv.report_font_sha256;
  assert.doesNotThrow(()=>deploy(absentEnv),'legacy scenes without a configured report font remain valid');
  writeFileSync(join(fontRoot,'private-data.json'),'private');
  assert.throws(()=>deploy(),/only fixed public font resources/);
  rmSync(join(fontRoot,'private-data.json'));
  rmSync(font);
  assert.throws(()=>deploy(),/matching fixed public font/);
});

test('attachment parsers map only verified public dependencies into member and report environments', t => {
  const root=realpathSync(mkdtempSync(join(tmpdir(),'harless-attachment-deploy-')));
  t.after(()=>rmSync(root,{recursive:true,force:true}));
  for(const name of ['scenarios','python/bin','pdf/bin','pdf/lib/x86_64-linux-gnu','pdf/share',
    'antiword/usr/bin','antiword/usr/share/antiword'])mkdirSync(join(root,name),{recursive:true});
  const python=join(root,'python/bin/python');writeFileSync(python,'test Python');
  writeFileSync(join(root,'python/pyvenv.cfg'),'test installation');
  const pdf=join(root,'pdf'),antiword=join(root,'antiword'),binary=join(antiword,'usr/bin/antiword'),mapping=join(antiword,'usr/share/antiword');
  for(const name of ['pdfinfo','pdftotext'])writeFileSync(join(pdf,'bin',name),'public parser');
  writeFileSync(binary,'public Word parser');writeFileSync(join(mapping,'UTF-8.txt'),'public character mapping');
  writeFileSync(join(antiword,'operator-private.json'),'must not be mounted');
  const scene={id:'data',adapter:'data-report',allowed_tools:['mcp__research_report__inspect_study'],
    pdf_toolchain_root:pdf,antiword_root:antiword,mcp_rows:[{name:'@deepseek-ai/dsh-mcp-client',config:{
      serverName:'research_report',transport:'stdio',command:python,cwd:root,args:[join(root,'scenarios/data_analysis/report_session.py')],
      env:{HARLESS_REPORT_WORKSPACE:'__HARLESS_SESSION_WORKSPACE__',HARLESS_PDF_TOOLCHAIN_ROOT:pdf,HARLESS_ANTIWORD_BIN:binary,ANTIWORDHOME:mapping}}}]};
  const deployment={projectRoot:root,pythonExecutable:python,pythonRoots:[join(root,'python')],pdfToolchainRoot:pdf,antiwordRoot:antiword};
  const deploy=(value=scene,options=deployment)=>memberSceneDeployment({scenes:[value]},options);
  const result=deploy(),env=result.scenes[0].mcp_rows[0].config.env;
  assert.deepEqual(result.attachmentEnvironment,{HARLESS_PDF_TOOLCHAIN_ROOT:'/opt/harless/pdf',
    HARLESS_ANTIWORD_BIN:'/opt/harless/antiword/bin/antiword',ANTIWORDHOME:'/opt/harless/antiword/share/antiword'});
  for(const [key,value] of Object.entries(result.attachmentEnvironment))assert.equal(env[key],value);
  assert.ok(result.mounts.some(row=>row.source===binary&&row.target===env.HARLESS_ANTIWORD_BIN));
  assert.ok(result.mounts.some(row=>row.source===mapping&&row.target===env.ANTIWORDHOME));
  assert.ok(result.mounts.some(row=>row.source===pdf&&row.target===pdf),'old bound PDF presets retain their read-only installation');
  assert.ok(result.mounts.every(row=>row.source!==antiword&&row.source!==root));
  assert.equal(result.scenes[0].pdf_toolchain_root,'/opt/harless/pdf');
  const wrong=structuredClone(scene);wrong.mcp_rows[0].config.env.HARLESS_ANTIWORD_BIN='/owner/private/antiword';
  assert.throws(()=>deploy(wrong),/matching fixed installation/);
  assert.throws(()=>deploy(scene,{...deployment,antiwordRoot:undefined}),/matching fixed installation/);
  assert.throws(()=>deploy(scene,{...deployment,pdfToolchainRoot:undefined}),/matching fixed installation/);
  const missingMetadata=structuredClone(scene);delete missingMetadata.antiword_root;
  assert.throws(()=>deploy(missingMetadata),/matching fixed installation/);
  const link=join(root,'redirected-word');symlinkSync(antiword,link,process.platform==='win32'?'junction':'dir');
  assert.throws(()=>deploy(scene,{...deployment,antiwordRoot:link}),/without redirected paths/);
  const privateMap=join(mapping,'private-dir');mkdirSync(privateMap);
  assert.throws(()=>deploy(),/only fixed public resource files/);
});

test('literature uses the mapped PDF environment while package links cannot expose private directories', t => {
  const root=realpathSync(mkdtempSync(join(tmpdir(),'harless-pdf-deploy-')));
  t.after(()=>rmSync(root,{recursive:true,force:true}));
  for(const name of ['scenarios','python/bin','pdf/bin','pdf/lib/x86_64-linux-gnu','pdf/share','private'])mkdirSync(join(root,name),{recursive:true});
  const python=join(root,'python/bin/python');writeFileSync(python,'test Python');writeFileSync(join(root,'python/pyvenv.cfg'),'test installation');
  const pdf=join(root,'pdf');for(const name of ['pdfinfo','pdftotext'])writeFileSync(join(pdf,'bin',name),'public parser');
  const scene={id:'literature',adapter:'literature',allowed_tools:[],pdf_toolchain_root:pdf,mcp_rows:[{name:'@deepseek-ai/dsh-mcp-client',config:{
    serverName:'literature_web',transport:'stdio',command:python,cwd:root,args:[join(root,'scenarios/literature-notes/session_tools.py')],
    env:{SSS_PDF_WEB_TASK:'__HARLESS_SESSION_WORKSPACE__/literature',PATH:join(pdf,'bin')+':/usr/bin:/bin',LD_LIBRARY_PATH:join(pdf,'lib/x86_64-linux-gnu')}}}]};
  const deployment={projectRoot:root,pythonExecutable:python,pythonRoots:[join(root,'python')],pdfToolchainRoot:pdf};
  mkdirSync(join(pdf,'share/public-docs'));
  symlinkSync(join(pdf,'share/public-docs'),join(pdf,'share/package-docs'),process.platform==='win32'?'junction':'dir');
  const env=memberSceneDeployment({scenes:[scene]},deployment).scenes[0].mcp_rows[0].config.env;
  assert.equal(env.PATH,'/opt/harless/pdf/bin:/usr/bin:/bin');assert.equal(env.LD_LIBRARY_PATH,'/opt/harless/pdf/lib/x86_64-linux-gnu');
  symlinkSync(join(root,'private'),join(pdf,'share/redirect'),process.platform==='win32'?'junction':'dir');
  assert.throws(()=>memberSceneDeployment({scenes:[scene]},deployment),/link escapes/);
});

const listen = server => new Promise(resolve => server.listen(0, '127.0.0.1', () => resolve(server.address().port)));
const close = server => new Promise(resolve => server.close(resolve));
const origin = 'https://app.example.test';

test('gateway shutdown closes an idle browser connection and finishes promptly', async t => {
  const dir = mkdtempSync(join(tmpdir(), 'harless-gateway-close-'));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const gateway = createGateway({dataDir:dir,publicOrigin:origin});
  const port = await listen(gateway.server), socket = net.connect(port,'127.0.0.1');
  t.after(() => socket.destroy()); await once(socket,'connect');
  const stopped=once(gateway.server,'close'), disconnected=once(socket,'close');
  gateway.close();gateway.close();
  await Promise.race([Promise.all([stopped,disconnected]),new Promise((_,reject)=>{
    const timer=setTimeout(()=>reject(Error('gateway shutdown remained blocked by browser socket')),1000);timer.unref();
  })]);
});
async function fixture(t, handleUpstream) {
  const dir = mkdtempSync(join(tmpdir(), 'harless-gateway-'));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const seen = [];
  const upstream = http.createServer((req, res) => {
    seen.push({ path: req.url, cookie: req.headers.cookie, host: req.headers.host, origin: req.headers.origin });
    if (req.url.startsWith('/?token=')) {
      res.writeHead(303, { location: '/', 'set-cookie': 'dsh-auth-test=secret-internal; HttpOnly; Path=/' });
      res.end(); return;
    }
    if (handleUpstream?.(req, res)) return;
    res.writeHead(200, { 'content-type': 'application/json', 'set-cookie': 'dsh-auth-test=never-public' });
    res.end(JSON.stringify({ path: req.url }));
  });
  const ownerPort = await listen(upstream);
  t.after(() => close(upstream));
  const tokenFile = join(dir, 'owner-token');
  writeFileSync(tokenFile, 'https://app.example.test/?token=' + 'A'.repeat(43));
  const html = join(dir, 'account.html'); writeFileSync(html, '<!doctype html><title>account</title>');
  const config = { dataDir: join(dir, 'db'), membersDir: join(dir, 'members'),
    publicOrigin: origin, ownerPort, ownerTokenFile: tokenFile, accountHtml: html,
    apiKey: 'test', dummyPasswordHash: 'scrypt-v1$test$' + '0'.repeat(128) };
  let gateway = createGateway(config);
  let port = await listen(gateway.server);
  t.after(() => close(gateway.server));
  const base = () => `http://127.0.0.1:${port}`;
  const request = (path, { method = 'GET', body, cookie, requestOrigin = origin } = {}) => fetch(base() + path, {
    method, redirect: 'manual', headers: {
      ...(cookie ? { cookie } : {}), ...(body ? { 'content-type': 'application/json', origin: requestOrigin } : {}),
    }, body: body ? JSON.stringify(body) : undefined,
  });
  return { dir, seen, config, request, upstream, base, get gateway() { return gateway; },
    async restart() { await close(gateway.server); gateway = createGateway(config); port = await listen(gateway.server); } };
}

test('disconnecting an HTTP event stream releases its backend subscription without ending sibling streams', { timeout: 5000 }, async t => {
  const active = new Map(), stopped = [];
  let f;
  t.after(() => { for (const response of active.values()) response.destroy(); f?.gateway.close(); });
  f = await fixture(t, (req, res) => {
    if (!req.url.startsWith('/api/harless/events/')) return false;
    active.set(req.url, res);
    res.once('close', () => { active.delete(req.url); stopped.push(req.url); });
    res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-store' });
    res.write('event: ready\ndata: {}\n\n');
    return true;
  });
  const code = createOwnerClaim(f.gateway);
  const claimed = await f.request('/api/account/claim', { method: 'POST', body: {
    claimCode: code, username: 'owner', displayName: 'Owner', password: 'long-enough-test-password',
  } });
  assert.equal(claimed.status, 200);
  const cookie = claimed.headers.get('set-cookie').split(';')[0];
  const openStream = path => new Promise((resolve, reject) => {
    const request = http.get(f.base() + path, { headers: { cookie }, agent: false }, response => {
      response.once('error', () => {}); // Expected on deliberate downstream cancellation.
      response.once('data', chunk => resolve({ request, response, first: chunk.toString() }));
    });
    request.once('error', reject);
  });
  const [left, right] = await Promise.all([openStream('/api/harless/events/left'), openStream('/api/harless/events/right')]);
  assert.match(left.first, /event: ready/); assert.match(right.first, /event: ready/);
  assert.equal(active.size, 2, 'GET body completion must not cancel a live event stream');
  const leftClosed = once(active.get('/api/harless/events/left'), 'close', { signal: AbortSignal.timeout(2000) });
  left.response.destroy(); left.request.destroy(); await leftClosed;
  assert.deepEqual(stopped, ['/api/harless/events/left']);
  assert.equal(active.size, 1);
  const nextChunk = once(right.response, 'data', { signal: AbortSignal.timeout(2000) });
  active.get('/api/harless/events/right').write('event: progress\ndata: {"step":2}\n\n');
  assert.match((await nextChunk)[0].toString(), /"step":2/);
  const json = await f.request('/api/harless/tasks', { cookie });
  assert.equal(json.status, 200); assert.deepEqual(await json.json(), { path: '/api/harless/tasks' });
  const rightClosed = once(active.get('/api/harless/events/right'), 'close', { signal: AbortSignal.timeout(2000) });
  right.response.destroy(); right.request.destroy(); await rightClosed;
  assert.equal(active.size, 0);
});

test('browser disconnect before response headers cancels the pending upstream HTTP request', { timeout: 5000 }, async t => {
  let received;
  const arrived = new Promise(resolve => { received = resolve; });
  let f, backend, downstream;
  t.after(() => { downstream?.destroy(); backend?.res.destroy(); f?.gateway.close(); });
  f = await fixture(t, (req, res) => {
    if (req.url !== '/api/harless/slow-stream') return false;
    received({ req, res }); return true;
  });
  const code = createOwnerClaim(f.gateway);
  const claimed = await f.request('/api/account/claim', { method: 'POST', body: {
    claimCode: code, username: 'owner', displayName: 'Owner', password: 'long-enough-test-password',
  } });
  const cookie = claimed.headers.get('set-cookie').split(';')[0];
  downstream = http.get(f.base() + '/api/harless/slow-stream', { headers: { cookie }, agent: false });
  downstream.on('error', () => {});
  backend = await arrived;
  const closed = once(backend.res, 'close', { signal: AbortSignal.timeout(2000) });
  downstream.destroy(); await closed;
  assert.equal(backend.res.destroyed, true);
});

test('gateway shutdown closes both sides of an upgraded browser connection',async t=>{
 const f=await fixture(t);let backendSocket;
 f.upstream.on('upgrade',(_req,socket)=>{backendSocket=socket;socket.resume();socket.once('end',()=>socket.end());socket.write('HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n\r\n');});
 const code=createOwnerClaim(f.gateway);
 const response=await f.request('/api/account/claim',{method:'POST',body:{claimCode:code,username:'owner',displayName:'Owner',password:'long-enough-test-password'}});
 assert.equal(response.status,200);const cookie=response.headers.get('set-cookie').split(';')[0];
 const socket=net.connect(new URL(f.base()).port,'127.0.0.1');
 try {
  await once(socket,'connect',{signal:AbortSignal.timeout(2000)});
  socket.write('GET /api/$stream HTTP/1.1\r\nHost: localhost\r\nConnection: Upgrade\r\nUpgrade: websocket\r\nCookie: '+cookie+'\r\n\r\n');
  const [reply]=await once(socket,'data',{signal:AbortSignal.timeout(2000)});assert.match(reply.toString(),/101 Switching/);assert.ok(backendSocket);
  const stopped=once(f.gateway.server,'close'),downstream=once(socket,'close'),upstream=once(backendSocket,'close');
  f.gateway.close();
  await Promise.race([Promise.all([stopped,downstream,upstream]),new Promise((_,reject)=>{const timer=setTimeout(()=>reject(Error('upgraded connection prevented gateway shutdown')),1000);timer.unref();})]);
 } finally {socket.destroy();backendSocket?.destroy();f.gateway.close();}
});

test('native RPC errors hide server diagnostics while success and downloads retain exact bytes', async t => {
  const secret='/home/operator/deployment/private.py',success=Buffer.from(JSON.stringify({type:'server-response',rpcId:'r1',result:{ok:true,value:{text:secret,data:'AAECAw=='}}},null,2));
  const f=await fixture(t,(req,res)=>{
    if(req.url==='/api/session/failure'){
      const bytes=Buffer.from(JSON.stringify({type:'server-response',rpcId:'r2',result:{ok:false,error:{code:'gateway/internal',message:secret,details:{stack:secret}}}}));
      res.writeHead(200,{'content-type':'application/json','content-length':bytes.length,'etag':'private-etag','set-cookie':'backend=private'});res.end(bytes);return true;
    }
    if(req.url==='/api/session/compressed'){
      assert.equal(req.headers['accept-encoding'],'identity');
      res.writeHead(200,{'content-type':'application/json','content-encoding':'gzip'});res.end(success);return true;
    }
    if(['/api/session/page','/api/session/modelCatalog','/api/session/download'].includes(req.url)){
      res.writeHead(200,{'content-type':'application/json',...(req.url.endsWith('download')?{'content-disposition':'attachment; filename="user.json"'}:{})});res.end(success);return true;
    }
  });
  const claim=createOwnerClaim(f.gateway),account=await f.request('/api/account/claim',{method:'POST',body:{claimCode:claim,username:'owner',displayName:'Owner',password:'long-password-123'}});
  assert.equal(account.status,200);const cookie=account.headers.get('set-cookie').split(';')[0];
  const failed=await f.request('/api/session/failure',{method:'POST',cookie,body:{type:'client-request'}}),raw=Buffer.from(await failed.arrayBuffer());
  assert.equal(failed.status,200);assert.equal(failed.headers.get('etag'),null);assert.equal(failed.headers.get('set-cookie'),null);
  assert.equal(Number(failed.headers.get('content-length')),raw.length);assert.ok(!raw.includes(Buffer.from(secret)));
  assert.equal(JSON.parse(raw).result.error.code,'gateway/internal');assert.equal(f.seen.at(-1).cookie,'dsh-auth-test=secret-internal');
  for(const path of ['/api/session/page','/api/session/modelCatalog','/api/session/download']){
    const response=await f.request(path,{method:'POST',cookie,body:{type:'client-request'}});
    assert.deepEqual(Buffer.from(await response.arrayBuffer()),success);
  }
  const compressed=await f.request('/api/session/compressed',{method:'POST',cookie,body:{type:'client-request'}});
  assert.equal(compressed.status,502);assert.equal(compressed.headers.get('content-encoding'),null);
  assert.ok(!(await compressed.text()).includes(secret));
});

test('native mux projects extra public events with authenticated headers, fragments, heartbeat and binary forwarding', {timeout:10000}, async t => {
  const f=await fixture(t),wss=new WebSocketServer({noServer:true});let backend,handshake;
  f.upstream.on('upgrade',(req,socket,head)=>{handshake=req.headers;wss.handleUpgrade(req,socket,head,ws=>{backend=ws;wss.emit('connection',ws,req);});});
  t.after(()=>{for(const ws of wss.clients)ws.terminate();wss.close();f.gateway.close();});
  const claim=createOwnerClaim(f.gateway),account=await f.request('/api/account/claim',{method:'POST',body:{claimCode:claim,username:'owner',displayName:'Owner',password:'long-password-123'}});
  assert.equal(account.status,200);const cookie=account.headers.get('set-cookie').split(';')[0];
  const opened=once(wss,'connection');
  const client=new WebSocket(f.base().replace(/^http/,'ws')+'/api/remote.mux',{headers:{cookie,origin}});
  client.on('error',()=>{});t.after(()=>client.terminate());
  await Promise.all([once(client,'open'),opened]);
  assert.equal(handshake.cookie,'dsh-auth-test=secret-internal');
  assert.equal(handshake.origin,'http://127.0.0.1:'+f.config.ownerPort);assert.notEqual(handshake.cookie,cookie);
  const request=JSON.stringify({type:'open',streamId:'events',endpoint:'$events',payload:{args:{}}});
  let got=once(backend,'message');client.send(request);assert.equal((await got)[0].toString(),request);
  const ready=JSON.stringify({type:'item',streamId:'events',value:{type:'ready',clientId:'live',host:{home:'/home/operator/中文'}}});
  const readyBytes=Buffer.from(ready),cut=readyBytes.indexOf(Buffer.from('中文'))+1;
  let incoming=once(client,'message');backend.send(readyBytes.subarray(0,cut),{binary:false,fin:false});backend.send(readyBytes.subarray(cut),{binary:false,fin:true});
  assert.equal(JSON.parse((await incoming)[0]).value.host.home,'');
  for(const value of [
    {type:'item',streamId:'events',value:{type:'emit',event:'api-session/added',args:[{sessionId:'one',cwd:'/home/operator/work',running:false,blank:true,updatedAt:1}]}},
    {type:'item',streamId:'events',value:{type:'emit',event:'api-session/error',args:['one','Error /home/operator/stack']}},
    {type:'error',streamId:'other',error:{code:'gateway/internal',message:'/home/operator',details:{path:'/app/private'}}},
  ]){
    incoming=once(client,'message');backend.send(JSON.stringify(value));const data=(await incoming)[0];assert.ok(!data.toString().includes('/home/'));assert.ok(!data.toString().includes('/app/'));
  }
  const untouched=JSON.stringify({type:'item',streamId:'follow',value:{type:'event',event:{seq:1,data:{userText:'/home/user/upload.txt'}}}});
  incoming=once(client,'message');backend.send(untouched);assert.equal((await incoming)[0].toString(),untouched);
  const binary=Buffer.from([0,128,255,1]);got=once(backend,'message');client.send(binary);let [bytes,isBinary]=await got;assert.deepEqual(bytes,binary);assert.equal(isBinary,true);
  incoming=once(client,'message');backend.send(binary);[bytes,isBinary]=await incoming;assert.deepEqual(bytes,binary);assert.equal(isBinary,true);
  const pong=once(backend,'pong');backend.ping('browser-heartbeat');assert.equal((await pong)[0].toString(),'browser-heartbeat');
  // A burst shares one carrier; a slow send callback may pause reads but cannot
  // reorder/deduplicate dense follow indices or block sibling cancellation.
  const burst=Array.from({length:64},(_,index)=>JSON.stringify({type:'item',streamId:index%2?'right':'left',value:{index,text:'增量'.repeat(500)}}));
  const received=[];
  const complete=new Promise(resolve=>{
    const collect=data=>{received.push(data.toString());if(received.length===burst.length){client.off('message',collect);resolve();}};
    client.on('message',collect);
  });
  for(const frame of burst)backend.send(frame);
  const cancel=JSON.stringify({type:'cancel',streamId:'left'});
  got=once(backend,'message');client.send(cancel);
  assert.equal((await got)[0].toString(),cancel);await complete;assert.deepEqual(received,burst);
  const stopped=once(backend,'close');client.close(1000);await stopped;
});

test('native mux browser cancellation releases a pending upstream handshake', {timeout:5000}, async t => {
  const f=await fixture(t);let backend;
  const arrived=new Promise(resolve=>f.upstream.on('upgrade',(_req,socket)=>{backend=socket;socket.on('error',()=>{});socket.once('end',()=>socket.end());socket.resume();resolve();}));
  t.after(()=>{backend?.destroy();f.gateway.close();});
  const claim=createOwnerClaim(f.gateway),account=await f.request('/api/account/claim',{method:'POST',body:{claimCode:claim,username:'owner',displayName:'Owner',password:'long-password-123'}});
  const cookie=account.headers.get('set-cookie').split(';')[0];
  const client=new WebSocket(f.base().replace(/^http/,'ws')+'/api/remote.mux',{headers:{cookie,origin}});
  client.on('error',()=>{});t.after(()=>client.terminate());await arrived;
  const closed=once(backend,'close',{signal:AbortSignal.timeout(2000)});
  client.terminate();await closed;assert.equal(backend.destroyed,true);
});

test('native mux rejects anonymous or foreign-origin connections and shutdown cancels both sockets', {timeout:10000}, async t => {
  const f=await fixture(t),wss=new WebSocketServer({noServer:true});let upgrades=0;
  f.upstream.on('upgrade',(req,socket,head)=>{upgrades++;wss.handleUpgrade(req,socket,head,ws=>wss.emit('connection',ws));});
  t.after(()=>{for(const ws of wss.clients)ws.terminate();wss.close();f.gateway.close();});
  const claim=createOwnerClaim(f.gateway),account=await f.request('/api/account/claim',{method:'POST',body:{claimCode:claim,username:'owner',displayName:'Owner',password:'long-password-123'}});
  assert.equal(account.status,200);const cookie=account.headers.get('set-cookie').split(';')[0],url=f.base().replace(/^http/,'ws')+'/api/remote.mux';
  for(const [headers,status] of [[{origin},401],[{cookie,origin:'https://foreign.example'},403]]){
    const ws=new WebSocket(url,{headers});ws.on('error',()=>{});
    const response=await new Promise(resolve=>ws.once('unexpected-response',(_request,response)=>{response.resume();resolve(response.statusCode);ws.terminate();}));
    assert.equal(response,status);
  }
  assert.equal(upgrades,0);
  const opened=once(wss,'connection'),client=new WebSocket(url,{headers:{cookie,origin}});client.on('error',()=>{});
  await once(client,'open');const [backend]=await opened;
  const closed=Promise.all([once(client,'close'),once(backend,'close'),once(f.gateway.server,'close')]);
  f.gateway.close();await closed;
});

test('owner claim, login, profile, password, logout and persistence', async t => {
  const f = await fixture(t);
  const claim = createOwnerClaim(f.gateway);
  const initial = await f.request('/');
  assert.equal(initial.status, 303); assert.equal(initial.headers.get('location'), '/login');
  const badOrigin = await f.request('/api/account/claim', { method: 'POST', requestOrigin: 'https://evil.test',
    body: { claimCode: claim, username: 'owner', displayName: 'Owner', password: 'StrongPass123!' } });
  assert.equal(badOrigin.status, 403);
  const claimed = await f.request('/api/account/claim', { method: 'POST',
    body: { claimCode: claim, username: 'owner', displayName: 'Owner', password: 'StrongPass123!' } });
  assert.equal(claimed.status, 200);
  const firstCookie = claimed.headers.get('set-cookie').split(';')[0];
  assert.equal((await claimed.json()).user.role, 'owner');
  const invalidInvite = await f.request('/api/account/invites', { method: 'POST', cookie: firstCookie,
    body: { currentPassword: 'incorrect-pass', count: 1 } });
  assert.equal(invalidInvite.status, 403);
  const generated = await f.request('/api/account/invites', { method: 'POST', cookie: firstCookie,
    body: { currentPassword: 'StrongPass123!', count: 1 } });
  assert.equal(generated.status, 200);
  const inviteCode = (await generated.json()).codes[0];
  assert.ok(inviteCode.length >= 20);
  assert.ok(!readFileSync(join(f.config.dataDir, 'accounts.json'), 'utf8').includes(inviteCode));
  assert.equal((await f.request('/api/account/me', { cookie: firstCookie }).then(r => r.json())).user.username, 'owner');
  assert.equal((await f.request('/?token=' + 'A'.repeat(43), { cookie: firstCookie })).status, 400);
  const root = await f.request('/api/harless/tasks', { cookie: firstCookie });
  assert.equal(root.status, 200); assert.equal(root.headers.get('set-cookie'), null);
  assert.equal(f.seen.at(-1).cookie, 'dsh-auth-test=secret-internal');
  assert.equal(f.seen.at(-1).host, `127.0.0.1:${f.config.ownerPort}`);
  writeFileSync(join(f.dir, 'owner-token'), 'https://app.example.test/?token=' + 'B'.repeat(43));
  assert.equal((await f.request('/api/harless/tasks', { cookie: firstCookie })).status, 200);
  assert.ok(f.seen.some(row => row.path === '/?token=' + 'B'.repeat(43)));
  const profile = await f.request('/api/account/profile', { method: 'POST', cookie: firstCookie,
    body: { username: 'owner2', displayName: '研究负责人' } });
  assert.equal(profile.status, 200); assert.equal((await profile.json()).user.displayName, '研究负责人');
  const wrong = await f.request('/api/account/password', { method: 'POST', cookie: firstCookie,
    body: { currentPassword: 'wrong-password', newPassword: 'LongerPass123!' } });
  assert.equal(wrong.status, 403);
  const changed = await f.request('/api/account/password', { method: 'POST', cookie: firstCookie,
    body: { currentPassword: 'StrongPass123!', newPassword: 'LongerPass123!' } });
  assert.equal(changed.status, 200);
  assert.equal((await f.request('/api/account/me', { cookie: firstCookie }).then(r => r.json())).user, null);
  await f.restart();
  const login = await f.request('/api/account/login', { method: 'POST',
    body: { username: 'owner2', password: 'LongerPass123!' } });
  assert.equal(login.status, 200);
  const secondCookie = login.headers.get('set-cookie').split(';')[0];
  assert.equal((await f.request('/api/account/logout', { method: 'POST', cookie: secondCookie, body: {} })).status, 200);
  assert.equal((await f.request('/api/account/me', { cookie: secondCookie }).then(r => r.json())).user, null);
  assert.equal((await f.request('/api/account/claim', { method: 'POST',
    body: { claimCode: claim, username: 'again', displayName: 'Again', password: 'StrongPass123!' } })).status, 400);
});

test('invite registration is single-use and account metadata is independent', async t => {
  const f = await fixture(t);
  const [invite] = createInvites(f.gateway, 1);
  const registered = await f.request('/api/account/register', { method: 'POST',
    body: { inviteCode: invite, username: 'alice', displayName: 'Alice', password: 'AlicePass123!' } });
  assert.equal(registered.status, 200);
  const cookie = registered.headers.get('set-cookie').split(';')[0];
  const user = (await registered.json()).user;
  assert.equal(user.role, 'member'); assert.notEqual(user.id, 'owner');
  const memberInvite = await f.request('/api/account/invites', { method: 'POST', cookie,
    body: { currentPassword: 'AlicePass123!', count: 1 } });
  assert.equal(memberInvite.status, 403);
  const duplicate = await f.request('/api/account/register', { method: 'POST',
    body: { inviteCode: invite, username: 'bob', displayName: 'Bob', password: 'BobStrong123!' } });
  assert.equal(duplicate.status, 400);
  const me = await f.request('/api/account/me', { cookie });
  assert.equal((await me.json()).user.username, 'alice');
  const db = JSON.parse(readFileSync(join(f.config.dataDir, 'accounts.json'), 'utf8'));
  assert.ok(!JSON.stringify(db).includes('AlicePass123!'));
  assert.ok(!JSON.stringify(db).includes(invite));
  assert.ok(db.users[0].passwordHash.startsWith('scrypt-v1$'));
});

test('batch invitations stay valid after years and restarts, consume only one code, and keep raw codes out of storage', async t => {
  const f = await fixture(t);
  const codes = createInvites(f.gateway, 20);
  assert.equal(new Set(codes).size, 20);
  for (const row of f.gateway.db.invites) row.createdAt = '2000-01-01T00:00:00.000Z';
  f.gateway.save(); await f.restart();
  const register = (code, username) => f.request('/api/account/register', { method: 'POST',
    body: { inviteCode: code, username, displayName: username, password: 'LongTestPassword123!' } });
  const registered = await register(' \n' + codes[0] + '\n ', 'old_invite');
  assert.equal(registered.status, 200, 'creation time and whitespace do not expire an unused code');
  const duplicate = await register(codes[0], 'another_user');
  assert.equal(duplicate.status, 400);
  assert.match((await duplicate.json()).error, /已使用/);
  await f.restart();
  assert.equal((await register(codes[19], 'last_invite')).status, 200);
  const saved = readFileSync(join(f.config.dataDir, 'accounts.json'), 'utf8');
  for (const code of codes) assert.ok(!saved.includes(code));
  assert.equal(JSON.parse(saved).invites.filter(row => !row.usedBy).length, 18);
});

test('two invited users register and remain authenticated concurrently', async t => {
  const f = await fixture(t);
  const [aliceCode, bobCode] = createInvites(f.gateway, 2);
  const [alice, bob] = await Promise.all([
    f.request('/api/account/register', { method: 'POST', body: {
      inviteCode: aliceCode, username: 'alice', displayName: 'Alice', password: 'AlicePass123!' } }),
    f.request('/api/account/register', { method: 'POST', body: {
      inviteCode: bobCode, username: 'bob', displayName: 'Bob', password: 'BobStrong123!' } }),
  ]);
  assert.equal(alice.status, 200); assert.equal(bob.status, 200);
  const aliceCookie = alice.headers.get('set-cookie').split(';')[0];
  const bobCookie = bob.headers.get('set-cookie').split(';')[0];
  assert.notEqual(aliceCookie, bobCookie);
  const [aliceMe, bobMe] = await Promise.all([
    f.request('/api/account/me', { cookie: aliceCookie }).then(r => r.json()),
    f.request('/api/account/me', { cookie: bobCookie }).then(r => r.json()),
  ]);
  assert.equal(aliceMe.user.username, 'alice'); assert.equal(bobMe.user.username, 'bob');
  assert.notEqual(aliceMe.user.id, bobMe.user.id);
  await f.restart();
  assert.equal((await f.request('/api/account/me', { cookie: aliceCookie }).then(r => r.json())).user.username, 'alice');
  assert.equal((await f.request('/api/account/me', { cookie: bobCookie }).then(r => r.json())).user.username, 'bob');
});

test('stale member plugin paths fail during gateway startup', async t => {
  const f = await fixture(t);
  assert.throws(() => createGateway({ ...f.config, sourceDir: join(f.dir, 'new-checkout', 'src'),
    memberPatch: [{ insert: [{ name: 'file:///old-checkout/src/adapters/dsh_web_tasks.ts' }] }] }),
  /Plugin is outside source directory/);
});

test('scoped budget rejects cross-account control and model traffic', async t => {
  const dir = mkdtempSync(join(tmpdir(), 'harless-scoped-'));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const upstream = [];
  const mock = http.createServer(async (req, res) => {
    const chunks = []; for await (const chunk of req) chunks.push(chunk);
    upstream.push({ path: req.url, authorization: req.headers.authorization,
      control: req.headers['x-sss-control-token'], body: Buffer.concat(chunks).toString() });
    res.writeHead(200, { 'content-type': 'application/json' }); res.end('{}');
  });
  const upstreamPort = await listen(mock); t.after(() => close(mock));
  const html = join(dir, 'account.html'); writeFileSync(html, '<title>test</title>');
  const config = { dataDir: join(dir, 'accounts'), membersDir: join(dir, 'members'),
    publicOrigin: origin, accountHtml: html, adminToken: 'test-admin-secret', apiKey: 'real-model-key',
    scopedBudgetPort: 1, upstreamControlPort: upstreamPort, upstreamBrokerPort: upstreamPort,
    memberPolicy: { control_token: 'real-control-secret', budget_usd: .5 } };
  const gateway = createGateway(config);
  const port = await listen(gateway.server), scopePort = await listen(gateway.scopedBudget);
  t.after(() => close(gateway.server)); t.after(() => close(gateway.scopedBudget));
  const [codeA, codeB] = createInvites(gateway, 2);
  async function register(code, username) {
    const response = await fetch(`http://127.0.0.1:${port}/api/account/register`, {
      method: 'POST', headers: { origin, 'content-type': 'application/json' },
      body: JSON.stringify({ inviteCode: code, username, displayName: username, password: 'LongTestPassword123!' }),
    });
    assert.equal(response.status, 200); return (await response.json()).user;
  }
  const alice = await register(codeA, 'alice'), bob = await register(codeB, 'bob');
  const prefix = user => createHash('sha256').update(user.id).digest('hex').slice(0, 8);
  const delegated = (user, kind) => createHmac('sha256', config.adminToken)
    .update(kind + ':' + user.id).digest('base64url');
  const task = prefix(alice) + 'a'.repeat(24), budget = 'turn-' + task;
  const session = 'session-12345678-1234-1234-1234-123456789abc';
  const scoped = (path, body, token, model = false) => fetch(`http://127.0.0.1:${scopePort}${path}`, {
    method: 'POST', headers: { 'content-type': 'application/json',
      ...(model ? { authorization: `Bearer ${token}`, 'x-deepseek-harness-session-id': session }
        : { 'x-sss-control-token': token }) }, body: JSON.stringify(body),
  });
  assert.equal((await scoped('/tasks/register', { task_id: task, session_id: budget, budget_usd: .5 },
    delegated(bob, 'control'))).status, 403);
  assert.equal((await scoped('/tasks/register', { task_id: task, session_id: budget, budget_usd: .5 },
    delegated(alice, 'control'))).status, 200);
  assert.equal((await scoped('/tasks/register', { task_id: task, session_id: budget, budget_usd: null },
    delegated(alice, 'control'))).status, 403);
  config.memberPolicy.budget_usd = null;
  for (const budget_usd of [null, 0, 200]) {
    assert.equal((await scoped('/tasks/register', { task_id: task, session_id: budget, budget_usd },
      delegated(alice, 'control'))).status, 200);
    assert.equal(JSON.parse(upstream.at(-1).body).budget_usd, budget_usd);
  }
  for (const budget_usd of [-1, '0', true, {}]) {
    assert.equal((await scoped('/tasks/register', { task_id: task, session_id: budget, budget_usd },
      delegated(alice, 'control'))).status, 403);
  }
  assert.equal((await scoped('/tasks/register', { task_id: task, session_id: budget, budget_usd: null },
    delegated(bob, 'control'))).status, 403);
  assert.equal((await scoped('/v1/chat/completions', { model: 'test' }, delegated(alice, 'model'), true)).status, 403);
  assert.equal((await scoped('/bind', { session_id: session, budget_session_id: budget },
    delegated(bob, 'control'))).status, 403);
  assert.equal((await scoped('/bind', { session_id: session, budget_session_id: budget },
    delegated(alice, 'control'))).status, 200);
  assert.equal((await scoped('/v1/chat/completions', { model: 'test' }, delegated(bob, 'model'), true)).status, 403);
  assert.equal((await scoped('/v1/chat/completions', { model: 'test' }, delegated(alice, 'model'), true)).status, 200);
  assert.equal(upstream.at(-1).authorization, 'Bearer real-model-key');
  const visionPath='/v1/vision/'+session+'/chat/completions';
  assert.equal((await scoped(visionPath,{model:'deepseek-flash'},delegated(bob,'model'),true)).status,403);
  assert.equal((await scoped(visionPath,{model:'deepseek-flash'},delegated(alice,'model'),true)).status,200);
  assert.equal(upstream.at(-1).path,visionPath);
  assert.equal(upstream.at(-1).authorization,'Bearer real-model-key');
  assert.equal((await scoped('/v1/vision/session-99999999-9999-4999-8999-999999999999/chat/completions',{},delegated(alice,'model'),true)).status,403);
  assert.equal((await fetch(`http://127.0.0.1:${scopePort}/tasks/stats?session_id=${budget}`, {
    headers: { 'x-sss-control-token': delegated(bob, 'control') },
  })).status, 403);
  assert.equal((await scoped('/unbind', { session_id: session, budget_session_id: budget },
    delegated(alice, 'control'))).status, 200);
  assert.equal((await scoped('/v1/chat/completions', { model: 'test' }, delegated(alice, 'model'), true)).status, 403);
  assert.equal((await scoped(visionPath,{model:'deepseek-flash'},delegated(alice,'model'),true)).status,403);
});
