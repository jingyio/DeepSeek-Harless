import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {hash} from '../src/adapters/artifact_motif_runtime.ts';
import {witnessedHeldoutInputs,sealArtifactLibrary} from '../scripts/certify-artifact-motifs.mjs';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';

test('optional non-SVG profile cannot invalidate the persisted library digest',()=>{
 const library=sealArtifactLibrary({version:1,programs:[{id:'non-svg',output_profile:undefined,interface:'中文完整接口'}]});
 const roundtrip=JSON.parse(JSON.stringify(library)),{digest:claimed,...body}=roundtrip;
 assert.equal(claimed,digest(body));
 assert.equal(Object.hasOwn(body.programs[0],'output_profile'),false);
 assert.throws(()=>sealArtifactLibrary({metric:NaN}),/must_be_json/);
 assert.throws(()=>sealArtifactLibrary({parameters:[undefined]}),/must_be_json/);
});

test('actual heldout argument flow wins over unrelated same-shaped JSON files',()=>{
 const workspace=mkdtempSync(join(tmpdir(),'artifact-binding-'));
 const path=join(workspace,'current.json'),other=join(workspace,'draft.json');
 writeFileSync(path,'{"title":"final"}');writeFileSync(other,'{"title":"draft"}');
 const program={id:'diagnostic',source_sha256:'same-native-source',inputs:[{suffix:'.json',format:'json',shape:{object:{title:'string'}}}],input_argument_indices:[0]};
 const row={...program,witness:{input_paths:{0:path},input_sha256:{0:hash('{"title":"final"}')}}};
 assert.equal(witnessedHeldoutInputs(program,{workspace,candidates:[row]}).bound[0].host,path);
 assert.equal(witnessedHeldoutInputs(program,{workspace,candidates:[{...row,source_sha256:'different'}]}),null);
 writeFileSync(path,'{"title":"changed"}');
 assert.throws(()=>witnessedHeldoutInputs(program,{workspace,candidates:[row]}),/input_changed/);
});

test('two different witnessed input versions remain ambiguous',()=>{
 const workspace=mkdtempSync(join(tmpdir(),'artifact-binding-'));
 const program={id:'diagnostic',source_sha256:'same-native-source',inputs:[{suffix:'.json',format:'json',shape:{object:{title:'string'}}}],input_argument_indices:[0]};
 const candidates=['one','two'].map(title=>{const path=join(workspace,title+'.json'),data=JSON.stringify({title});writeFileSync(path,data);return {...program,witness:{input_paths:{0:path},input_sha256:{0:hash(data)}}};});
 assert.throws(()=>witnessedHeldoutInputs(program,{workspace,candidates}),/binding_ambiguous/);
});
