import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const options={skip:!process.features?.typescript};
test('online file runtime validates portable public seeds and rejects altered witnesses',options,async()=>{
 const {validatePublicManagementSeed}=await import('../src/adapters/management_seed.ts');
 const release=new URL('../motif-libraries/file-v7/',import.meta.url);
 const manifest=JSON.parse(readFileSync(new URL('entry.json',release)));
 for(const entry of manifest.entries){
  const bytes=readFileSync(new URL(entry.payload,release)),policy=JSON.parse(bytes),cert=JSON.parse(readFileSync(new URL(entry.certificate,release)));
  const sha=createHash('sha256').update(bytes).digest('hex');
  assert.doesNotThrow(()=>validatePublicManagementSeed(policy,cert,sha,manifest.runtime_source));
  assert.throws(()=>validatePublicManagementSeed(policy,{...cert,grants_execution:true},sha,manifest.runtime_source));
  assert.throws(()=>validatePublicManagementSeed(policy,cert,sha,{...manifest.runtime_source,'fake-source':'changed'}));
 }
});

test('historical File seeds cannot acquire execution authority after source changes',options,async()=>{
 const {validatePublicManagementSeed}=await import('../src/adapters/management_seed.ts');
 const release=new URL('../motif-libraries/file-v5/',import.meta.url),manifest=JSON.parse(readFileSync(new URL('entry.json',release)));
 const entry=manifest.entries[0],bytes=readFileSync(new URL(entry.payload,release));
 assert.throws(()=>validatePublicManagementSeed(JSON.parse(bytes),JSON.parse(readFileSync(new URL(entry.certificate,release))),createHash('sha256').update(bytes).digest('hex'),manifest.runtime_source),/seed source\/manifest changed/);
});
