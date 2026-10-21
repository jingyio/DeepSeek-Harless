import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,symlinkSync,readFileSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {registerArtifactContext,artifactInvocation,fixedArtifactInput,matchesArtifactInput,hash} from '../src/adapters/artifact_motif_runtime.ts';

function fixture(){
 const workspace=mkdtempSync(join(tmpdir(),'artifact-guard-'));
 for(const p of ['inputs','code','outputs/code','command-tmp'])mkdirSync(join(workspace,p),{recursive:true});
 writeFileSync(join(workspace,'inputs','current.json'),'{"title":"current"}');
 const contract={suffix:'.json',format:'json',shape:{object:{title:'string'}}};
 const program={id:'test-recipe',inputs:[contract]};
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
