import test from 'node:test';
import './test_paper_flow_shadow.mjs';
import assert from 'node:assert/strict';
import { mkdtempSync,writeFileSync,rmSync,readFileSync,realpathSync,symlinkSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { createHash } from 'node:crypto';
import { createNativeInterceptor,nativeArguments } from '../src/adapters/dsh_native_motif.ts';
import { digest } from '../src/motif_core/online_skill_runtime.mjs';
import './test_dsh_parameter_motif.mjs';

test('native read protocol rejects code execution, unsafe options and external operands',()=>{
  const dir=realpathSync(mkdtempSync(join(tmpdir(),'native-safe-')));
  try {
    const make=argv=>({tool:'bash',protocol:'native-read-argv-v1',program:{cwd:'.',stages:[{argv,separator:';'}]}});
    assert.throws(()=>nativeArguments(make(['python3','-c','print(1)']),dir));
    assert.throws(()=>nativeArguments(make(['cat','/etc/passwd']),dir));
    assert.throws(()=>nativeArguments(make(['sort','--compression-program=sh']),dir));
    writeFileSync(join(dir,'known.tex'),'source');
    assert.throws(()=>nativeArguments(make(['cat','known.tex']),dir),/unwitnessed/);
    if (process.platform!=='win32') {
      symlinkSync('/etc/passwd',join(dir,'escape.tex'));
      const escaped=make(['cat','escape.tex']);escaped.dependencies={'escape.tex':'a'.repeat(64)};
      assert.throws(()=>nativeArguments(escaped,dir),/symlink escape/);
    }
  } finally {rmSync(dir,{recursive:true,force:true});}
});

test('native skip requires witnessed prefix, schema, file bytes and real verified result',async()=>{
  const dir=realpathSync(mkdtempSync(join(tmpdir(),'native-flow-')));
  try {
    writeFileSync(join(dir,'submission.zip'),'original');writeFileSync(join(dir,'main.tex'),'source');
    const sha=p=>createHash('sha256').update(readFileSync(p)).digest('hex');
    const params={type:'object',required:['file_path'],properties:{file_path:{type:'string'}}};
    const output=[{type:'text',text:'read source'}];
    const anchor={name:'bash',arguments:{command:'pwd'}};
    const manifest={certification_scope:'same_task_repeated_runs',input_sha256:sha(join(dir,'submission.zip')),
      tool_schema_hashes:{read:digest(params)},motifs:[{motif_id:'learned',
        anchor:[{call:anchor,output_sha256:digest([{type:'text',text:'${WORK}'}])}],
        nodes:[{tool:'read',protocol:'native-file-read-v1',arguments:{file_path:'${WORK}/main.tex'},
          dependencies:{'main.tex':sha(join(dir,'main.tex'))},expected_output_sha256:digest(output)}]}]};
    manifest.manifest_digest=digest(manifest);const audit=[];
    const runtime=createNativeInterceptor({manifest,work:dir,sessionId:'one',audit:r=>audit.push(r)});
    runtime.observe('one',{...anchor,callId:'anchor'},{content:[{type:'text',text:dir}]});
    const chunks=[];for await(const c of await runtime.intercept('one',{tools:[{name:'read',parameters:params}]},()=>{throw Error('must bypass');}))chunks.push(c);
    const c=chunks.find(c=>c.type==='tool-call-delta');
    runtime.observe('one',{name:'read',callId:c.id,arguments:JSON.parse(c.argumentsDelta)},{content:output});
    assert.equal(audit.filter(r=>r.kind==='model_request_skipped_verified').length,1);
    const changed=createNativeInterceptor({manifest,work:dir,sessionId:'two',audit:()=>{}});
    changed.observe('two',{...anchor,callId:'anchor'},{content:[{type:'text',text:dir}]});
    writeFileSync(join(dir,'main.tex'),'changed');let provider=0;
    await changed.intercept('two',{tools:[{name:'read',parameters:params}]},()=>{provider++;return [];});
    assert.equal(provider,1);
  } finally {rmSync(dir,{recursive:true,force:true});}
});

test('native job continuation binds an owned terminal job and verifies fresh output',async()=>{
  const dir=realpathSync(mkdtempSync(join(tmpdir(),'native-jobs-')));
  try {
    writeFileSync(join(dir,'submission.zip'),'original');
    const params={type:'object',properties:{job_id:{type:'string'}}};const bashParams={type:'object'};
    const manifest={certification_scope:'same_task_repeated_runs',input_sha256:createHash('sha256').update('original').digest('hex'),
      tool_schema_hashes:{bash:digest(bashParams),job_output:digest(params)},tool_order:['bash','job_output'],motifs:[],
      job_motifs:[{motif_id:'learned-job',source_tool:'bash',source_field:'jobId',target_tool:'job_output',target_param:'job_id',extra_arguments:{},only_when_terminal:true}]};
    manifest.manifest_digest=digest(manifest);
    const owner={session:{id:'one'}};let status='running';const audit=[];
    const jobs={get:(id,agent)=>{assert.equal(id,'actual');assert.equal(agent,owner);return {id,kind:'bash',status};}};
    const runtime=createNativeInterceptor({manifest,work:dir,sessionId:'one',audit:r=>audit.push(r),jobs});
    const ack=()=>runtime.observe('one',{name:'bash',arguments:{command:'python3 verify.py',run_in_background:true},callId:'start',agent:owner},{value:{kind:'background',jobId:'actual'},content:[{type:'text',text:'started background job actual'}]});
    const request={tools:[{name:'bash',parameters:bashParams},{name:'job_output',parameters:params}]};
    ack();let providers=0;await runtime.intercept('one',request,()=>{providers++;return [];});assert.equal(providers,1);
    status='completed';ack();const chunks=[];
    for await(const c of await runtime.intercept('one',request,()=>{throw Error('must bypass terminal collection');}))chunks.push(c);
    const call=chunks.find(c=>c.type==='tool-call-delta');assert.deepEqual(JSON.parse(call.argumentsDelta),{job_id:'actual'});
    runtime.observe('one',{name:'job_output',callId:call.id,arguments:{job_id:'actual'}},{value:{text:'fresh output',job:{id:'actual',status:'completed'}},content:[{type:'text',text:'fresh output'}]});
    assert.equal(audit.filter(r=>r.kind==='model_request_skipped_verified').length,1);
    const failed=createNativeInterceptor({manifest,work:dir,sessionId:'one',audit:r=>audit.push(r),jobs});
    const start={name:'bash',arguments:{run_in_background:true},agent:owner};
    failed.observe('one',start,{value:{kind:'background',jobId:'actual'},content:[]});
    const attempt=[];for await(const c of await failed.intercept('one',request,()=>[]))attempt.push(c);
    const failedCall=attempt.find(c=>c.type==='tool-call-delta');
    failed.observe('one',{name:'job_output',callId:failedCall.id,arguments:{job_id:'actual'}},{isError:true,content:[]});
    failed.observe('one',start,{value:{kind:'background',jobId:'actual'},content:[]});
    let fallback=0;await failed.intercept('one',request,()=>{fallback++;return [];});assert.equal(fallback,1);
    assert.equal(audit.filter(r=>r.kind==='bypass_result_unverified').length,1);
    // Foreground stdout cannot manufacture ownership or authorize a skip.
    const denied=createNativeInterceptor({manifest,work:dir,sessionId:'one',audit:r=>audit.push(r),jobs:{get:()=>{throw Error('not owned');}}});
    denied.observe('one',{name:'bash',arguments:{command:'echo started background job actual'},agent:owner},{content:[{type:'text',text:'started background job actual'}]});
    await denied.intercept('one',request,()=>{providers++;return [];});assert.equal(providers,2);

    // A model-directed terminal read has already consumed the delta stream.
    const consumed=createNativeInterceptor({manifest,work:dir,sessionId:'one',audit:()=>{},jobs});
    consumed.observe('one',{name:'bash',arguments:{run_in_background:true},agent:owner},{value:{kind:'background',jobId:'actual'},content:[]});
    consumed.observe('one',{name:'job_output',arguments:{job_id:'actual'}},{content:[]});
    await consumed.intercept('one',request,()=>{providers++;return [];});assert.equal(providers,3);
    const reordered=createNativeInterceptor({manifest,work:dir,sessionId:'one',audit:()=>{},jobs});
    reordered.observe('one',start,{value:{kind:'background',jobId:'actual'},content:[]});
    await reordered.intercept('one',{tools:[...request.tools].reverse()},()=>{providers++;return [];});assert.equal(providers,4);

  } finally {rmSync(dir,{recursive:true,force:true});}
});
