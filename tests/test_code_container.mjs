/** Optional actual Docker/upstream execution checks, never call a paid model. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,rmSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {runContainer} from '../src/adapters/dsh_code_container.ts';
const options={skip:process.env.SSS_TEST_CONTAINER!=='1'};
const image='node@sha256:9f6d5975c7dca860947d3915877f85607946403fc55349f39b4bc3688448bb6e';

test('Actual upstream TypeScript backend preserves nested callback results and parallel completion',options,async()=>{
  const calls=[];
  const result=await runContainer({program:'const r=await Promise.all([tools.read({n:1}),tools.read({n:2})]); return r.map(x=>x.n);',
    bindings:[{global:'tools',functions:{read:async arg=>{calls.push(arg.n);return arg;}}}]},image);
  assert.deepEqual(result.value,[1,2]);assert.equal(result.error,undefined);assert.deepEqual(calls,[1,2]);
});

test('Host private files/environment are not mounted, network is disabled, and program cannot write the mounted runtime',options,async()=>{
  const directory=mkdtempSync(join(tmpdir(),'sss-private-probe-')),secret=join(directory,'key.txt');writeFileSync(secret,'fixture-never-exported');
  const previous=process.env.DEEPSEEK_API_KEY;process.env.DEEPSEEK_API_KEY='fixture-host-env';
  try {
    const result=await runContainer({program:`const fs=await import('node:fs'); let read=false,write=false,network=false;
      try{fs.readFileSync(${JSON.stringify(secret)});read=true;}catch{}
      try{fs.writeFileSync('/app/runner.mjs','changed');write=true;}catch{}
      try{await fetch('http://1.1.1.1',{signal:AbortSignal.timeout(300)});network=true;}catch{}
      return {read,write,network,key:Boolean(process.env.DEEPSEEK_API_KEY)};`,bindings:[]},image);
    assert.deepEqual(result.value,{read:false,write:false,network:false,key:false});
  } finally {if(previous===undefined)delete process.env.DEEPSEEK_API_KEY;else process.env.DEEPSEEK_API_KEY=previous;rmSync(directory,{recursive:true});}
});

test('Abort terminates the native worker/container and invalid images are rejected',options,async()=>{
  const controller=new AbortController();setTimeout(()=>controller.abort(),500);
  const result=await runContainer({program:'while(true){}',bindings:[],signal:controller.signal},image);
  assert.equal(result.error.kind,'abort');
  assert.throws(()=>runContainer({program:'return 1;',bindings:[]},'untrusted:latest'),/unapproved/);
});
