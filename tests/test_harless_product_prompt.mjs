/** Actual upstream prompt assembly; no model, user history rewrite or network. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { memberProductProfile } from '../scripts/harless_gateway.mjs';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Context } from '@deepseek-ai/cordis';
import { createScope, scopeOf } from '@deepseek-ai/dsh-scope';
import { SystemPrompt, renderPrompt } from '@deepseek-ai/dsh-system-prompt';
import { apply as mountPersona } from '@deepseek-ai/dsh-persona';
import { bindProductPrompt, productPersona } from '../src/adapters/harless_product_prompt.ts';
import { sessionPreset, sessionWorkspace } from '../src/adapters/harless_task_scope.ts';

test('new and resumed agent scopes suppress deployment facts and keep scene/tool instructions', async () => {
  const ctx = new Context(), prompt = new SystemPrompt(ctx, {});
  prompt.section({name:'harness:source',order:10000,text:'Implementation checkout: /home/private-owner/deployment/source'});
  prompt.section({name:'app:web-surface',order:10100,text:'DeepSeek Harness Web GUI at http://127.0.0.1:12345'});
  prompt.context({name:'runtime-cwd',order:110,text:'cwd: /home/private-owner/deployment/work'});
  const tool = {name:'mcp__report__inspect_study',description:'Real permitted tool',parameters:{type:'object',properties:{}}};
  prompt.tools(() => ({schemas:[tool]}));
  const scopes = [createScope(ctx,{}), createScope(ctx,{})], disposers = [];
  try {
    const old = scopes[0];
    mountPersona(old.ctx,{prefix:'Legacy bounded task persona',suffix:'Preserve actual evidence.'});
    const before = renderPrompt(await prompt.assemble({scope:scopeOf(old.ctx)}));
    assert.match(before,/DeepSeek Harness/);
    for (const scope of scopes) {
      scope.ctx.systemPrompt.variable('literal_scene',()=> 'Keep the report token {{estimate}} literal.');
      scope.ctx.systemPrompt.section({name:'harless-scene',order:10210,text:'{{literal_scene}}'});
      disposers.push(...bindProductPrompt({ctx:scope.ctx}));
      const assembly = await prompt.assemble({scope:scopeOf(scope.ctx)});
      const text = renderPrompt(assembly);
      assert.match(text,/GeneLoop/);
      assert.doesNotMatch(text,/powered by DeepSeek Harness|Implementation checkout|private-owner|127\.0\.0\.1/);
      assert.match(text,/不要披露/);
      assert.match(text,/用户原文/);
      assert.match(text,/Keep the report token \{\{estimate\}\} literal/);
      assert.deepEqual(assembly.contexts,[]);
      assert.deepEqual(assembly.tools,[tool]);
    }
    // Product registration is scoped and leaves non-Web SDK defaults intact.
    assert.match(renderPrompt(await prompt.assemble()),/powered by DeepSeek Harness/);
    assert.equal((await prompt.assemble()).contexts.length,1);
  } finally {
    for (const dispose of disposers.reverse()) dispose();
    for (const scope of scopes) await scope.dispose();
  }
});

test('scene rebinding disposes and reapplies product policy without duplicates',async()=>{
  const ctx=new Context(), prompt=new SystemPrompt(ctx,{}), key={};
  const scope=createScope(ctx,key);
  try {
    for(let turn=0;turn<3;turn++){
      const disposers=bindProductPrompt({ctx:scope.ctx});
      const assembled=await prompt.assemble({scope:key});
      assert.equal(assembled.sections.filter(row=>row.name==='geneloop:product-policy').length,1);
      for(const dispose of disposers.reverse())dispose();
    }
  }finally{await scope.dispose();}
});

test('new bound presets use the same trusted persona without changing MCP rows',()=>{
  const directory=mkdtempSync(join(tmpdir(),'geneloop-product-prompt-'));
  try{
    const workspace=sessionWorkspace(directory,'test-session');
    const mcp={id:'sss-mcp-workspace',name:'@deepseek-ai/dsh-mcp-client',config:{cwd:'__HARLESS_SESSION_WORKSPACE__'}};
    const id=sessionPreset(directory,workspace,{id:'new-scene',adapter:'workspace',label:'普通对话',mcp_rows:[mcp]});
    const rows=JSON.parse(readFileSync(join(directory,'presets',id,'agent.cordis.yml'),'utf8'));
    assert.deepEqual(rows[0].config,productPersona());
    assert.equal(rows[1].name,mcp.name);
    assert.equal(rows[1].config.cwd,workspace);
    assert.equal(rows[0].config.complete,undefined);
  }finally{assert.ok(directory.startsWith(join(tmpdir(),'geneloop-product-prompt-')));rmSync(directory,{recursive:true,force:true});}
});

test('member startup keeps the shared persona and mounts only its public JSON even without scenes',()=>{
  const profile=memberProductProfile();
  assert.deepEqual(profile.persona,productPersona());
  assert.deepEqual(profile.sandboxArgs.slice(0,3),['--dir','/app/config','--ro-bind']);
  assert.equal(profile.sandboxArgs.length,5);
  assert.equal(profile.sandboxArgs[4],'/app/config/geneloop-persona.json');
  assert.deepEqual(JSON.parse(readFileSync(profile.sandboxArgs[3],'utf8')),productPersona());
});
