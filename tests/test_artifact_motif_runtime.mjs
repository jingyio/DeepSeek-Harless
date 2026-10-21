import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,symlinkSync,readFileSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {registerArtifactContext,artifactInvocation,fixedArtifactInput,matchesArtifactInput,hash,runArtifactProgram} from '../src/adapters/artifact_motif_runtime.ts';

function fixture(){
 const workspace=mkdtempSync(join(tmpdir(),'artifact-guard-'));
 for(const p of ['inputs','code','outputs/code','command-tmp'])mkdirSync(join(workspace,p),{recursive:true});
 writeFileSync(join(workspace,'inputs','current.json'),'{"title":"current"}');
 writeFileSync(join(workspace,'approved-inputs.json'),'{"files":{}}');
 const contract={suffix:'.json',format:'json',shape:{object:{title:'string'}}};
 const program={id:'test-recipe',inputs:[contract],certification:{}};
 return {workspace,contract,program,library:{programs:[program],digest:'diagnostic'},allowOutput:true,audit(){}};
}
const command=(value={})=>'geneloop-recipe '+JSON.stringify({id:'test-recipe',inputs:['/work/inputs/current.json'],output:'/work/outputs/fresh',...value});

test('explicit current binding and output authority are required',()=>{
 const f=fixture();registerArtifactContext('own',f);
 const job=artifactInvocation('own',command());
 assert.equal(job.bound[0].sha256,hash(readFileSync(join(f.workspace,'inputs/current.json'))));
 assert.throws(()=>artifactInvocation('foreign',command()),/not_admitted/);
 registerArtifactContext('own',{...f,allowOutput:false});
 assert.throws(()=>artifactInvocation('own',command()),/not_authorized/);
});
test('traversal, overwrite, schema mismatch and symlink bindings fail closed',()=>{
 const f=fixture();registerArtifactContext('paths',f);
 for(const output of ['/work/outputs/../inputs','/etc','/work/outputs/a/b'])assert.throws(()=>artifactInvocation('paths',command({output})),/directory_required/);
 mkdirSync(join(f.workspace,'outputs/code/fresh'));
 assert.throws(()=>artifactInvocation('paths',command()),/already_exists/);
 assert.throws(()=>fixedArtifactInput(f.workspace,'/work/inputs/../current.json'),/path_invalid/);
 assert.equal(matchesArtifactInput(f.contract,'a.json',Buffer.from('{"title":1}')),false);
});
test('current input bytes are returned rather than old source values',()=>{
 const f=fixture();const path=join(f.workspace,'inputs/current.json');
 const old=fixedArtifactInput(f.workspace,'/work/inputs/current.json');
 writeFileSync(path,'{"title":"different"}');
 const fresh=fixedArtifactInput(f.workspace,'/work/inputs/current.json');
 assert.notEqual(hash(old.data),hash(fresh.data));
});
test('unchanged training/certification policy files are version guarded',()=>{
 const f=fixture();f.program.certification.invariant_input_versions={0:hash(readFileSync(join(f.workspace,'inputs/current.json')))};
 registerArtifactContext('policy',f);
 artifactInvocation('policy',command());
 writeFileSync(join(f.workspace,'inputs/current.json'),'{"title":"policy changed"}');
 assert.throws(()=>artifactInvocation('policy',command()),/fixed_protocol_changed/);
});
test('real namespace preserves inputs, publishes fresh outputs, rejects aliases',{skip:process.platform!=='linux'},()=>{
 const f=fixture(),input=fixedArtifactInput(f.workspace,'/work/inputs/current.json');
 const program={id:'diagnostic',source:'import json,sys\nfrom pathlib import Path\nd=json.load(open(sys.argv[1]))\nPath(sys.argv[2],"result.txt").write_text(d["title"])\n',
  inputs:[f.contract],argument_count:2,input_argument_indices:[0],output_argument_index:1};
 const job={workspace:f.workspace,program,bound:[{...input,sha256:hash(input.data)}],output:'/work/outputs/fresh',destination:join(f.workspace,'outputs/code/fresh'),audit(){}};
 const result=runArtifactProgram(job);
 assert.equal(readFileSync(join(result.output,'result.txt'),'utf8'),'current');
 assert.equal(hash(readFileSync(input.host)),hash(input.data));
 assert.throws(()=>runArtifactProgram(job),/changed_before_publish/);
 const bad={...job,certification:true,program:{...program,source:'import sys\nopen(sys.argv[1],"w").write("corrupt")\n'}};
 assert.throws(()=>runArtifactProgram(bad),/program_failed/);
 assert.equal(readFileSync(input.host,'utf8'),'{"title":"current"}');
 const link={...job,certification:true,program:{...program,source:'import os,sys\nos.symlink(sys.argv[1],os.path.join(sys.argv[2],"link"))\n'}};
 assert.throws(()=>runArtifactProgram(link),/link_output_rejected/);
});
