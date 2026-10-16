import test from 'node:test';
import assert from 'node:assert/strict';
import {requestedSlides} from '../src/adapters/harless_task_scope.ts';
import {readFileSync} from 'node:fs';
test('explicit slide count overrides the default without extracting ordinal citations',()=>{
  for(const text of ['制作3页，包含封面共3页','生成三页中文汇报','create 3 slides'])assert.equal(requestedSlides(text),3);
  assert.equal(requestedSlides('总结第3页文献'),6);
  assert.equal(requestedSlides('3页或5页，请先讨论'),6);
  assert.equal(requestedSlides('介绍研究'),6);
});

test('every supported slide count has an exact schema while learned read contracts stay fixed',()=>{
  const variants=JSON.parse(readFileSync(new URL('../motif-libraries/ppt/tool-schema-variants.json',import.meta.url)));
  const expected=JSON.parse(readFileSync(new URL('../motif-libraries/ppt/tool-schemas.json',import.meta.url)));
  for(let count=1;count<=30;count++){
    const schema=variants.find(items=>items.find(t=>t.name==='mcp__ppt__render_deck')?.parameters.properties.plan.properties.slides.minItems===count);
    assert.ok(schema,`missing schema for ${count} slides`);
    assert.equal(schema.find(t=>t.name==='mcp__ppt__render_deck').parameters.properties.plan.properties.slides.maxItems,count);
    for(const name of ['mcp__ppt__pin_source','mcp__ppt__read_source'])assert.deepEqual(schema.find(t=>t.name===name),expected.find(t=>t.name===name));
  }
});
