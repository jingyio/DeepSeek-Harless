/** 精确公开契约和两组同工具集回归；schema检查不是科学质量或真实降本结论。 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { advertisedTools, ADAPTER_TOOLS } from '../dist/mcp-adapter.js';
import { SLIDE_KEYS, digest } from '../dist/delivery-adapter.js';
import { ExecutionPolicy } from '../dist/execution-policy.js';

const BASE_NAMES=['list_inputs','list_templates','pin_source','read_source','read_page','extract_figure',
  'inspect_deck','deliver_deck','read_deck_plan','list_restorable_decks','render_deck','restyle_deck','revise_deck','validate_deck','build_delivery'];
const base=()=>BASE_NAMES.map(name=>({name,description:'Backend original '+name,inputSchema:{type:'object',properties:{},additionalProperties:false}}));
const byName=(tools,name)=>{const value=tools.find(tool=>tool.name===name);assert.ok(value,'missing '+name);return value;};

test('普通与宿主配置共享21工具、契约与顺序，差异只由冻结执行策略控制',()=>{
  const inputs=base(),original=structuredClone(inputs),ordinary=advertisedTools(inputs,15),host=advertisedTools(base(),15);
  assert.deepEqual(inputs,original);assert.deepEqual(ordinary,host);assert.equal(digest(ordinary),digest(host));
  assert.equal(host.length,21);assert.equal(new Set(host.map(tool=>tool.name)).size,21);
  assert.deepEqual(host.map(tool=>tool.name),[...BASE_NAMES,...ADAPTER_TOOLS.map(tool=>tool.name)]);
  assert.deepEqual(ADAPTER_TOOLS.map(tool=>tool.name),['render_delivery','revise_delivery','pin_deck_pages','read_pinned_deck_pages','read_pending_plan','repair_pending_plan']);
  const b0=new ExecutionPolicy({schema_version:1,strategy:'baseline_steps'}),b1=new ExecutionPolicy({schema_version:1,strategy:'host_delivery'});
  assert.deepEqual(b0.snapshot().disabled_recovery_tools,['read_pending_plan','repair_pending_plan']);
  assert.deepEqual(b1.snapshot().disabled_recovery_tools,[]);
  assert.deepEqual(b0.snapshot().disabled_tools,b1.snapshot().disabled_tools);
});

test('render_deck明确顶层title与精确总页数，来源与科学页字段契约保持',()=>{
  const tool=byName(advertisedTools(base(),15),'render_deck');assert.deepEqual(tool.inputSchema.required,['plan']);
  assert.equal(tool.inputSchema.additionalProperties,false);const plan=tool.inputSchema.properties.plan;
  assert.deepEqual(plan.required,['title','slides']);assert.equal(plan.additionalProperties,false);
  assert.equal(plan.properties.title.minLength,1);assert.equal(plan.properties.title.maxLength,100);
  assert.equal(plan.properties.slides.minItems,15);assert.equal(plan.properties.slides.maxItems,15);
  assert.deepEqual(plan.properties.template.enum,['academic','lab']);const slide=plan.properties.slides.items;
  assert.deepEqual(slide.required,['title','sources']);assert.equal(slide.additionalProperties,false);
  assert.deepEqual(Object.keys(slide.properties).sort(),[...SLIDE_KEYS].sort());
  assert.equal(slide.properties.title.maxLength,70);assert.equal(slide.properties.sources.minItems,1);
  assert.deepEqual(slide.properties.sources.items.required,['source_id','page']);assert.equal(slide.properties.sources.items.properties.page.minimum,1);
  assert.deepEqual(slide.properties.archetype.enum,['evidence-focus','result-summary','method-map']);
  const six=byName(advertisedTools(base(),6),'render_deck').inputSchema.properties.plan;
  assert.equal(six.properties.slides.minItems,6);assert.equal(six.properties.slides.maxItems,6);
  assert.equal(plan.properties.slides.maxItems,15,'不得跨调用污染已有精确契约');
});

test('provider schema对深层页型使用有界object投影，运行时仍由preflight独立认证',()=>{
  const properties=byName(advertisedTools(base(),15),'render_deck').inputSchema.properties.plan.properties.slides.items.properties;
  assert.deepEqual(properties.chart,{type:'object'});
  assert.deepEqual(properties.process,{type:'object'});
  assert.deepEqual(properties.comparison,{type:'object'});
});

test('局部恢复只接受明确句柄、版本、页和修改；patch契约复用原页型，不暴露完整plan执行参数',()=>{
  const tools=advertisedTools(base(),15),read=byName(tools,'read_pending_plan'),repair=byName(tools,'repair_pending_plan');
  assert.deepEqual(read.inputSchema.required,['draft_id','version_sha256','pages']);assert.equal(read.inputSchema.additionalProperties,false);
  assert.equal(read.inputSchema.properties.pages.minItems,1);assert.equal(read.inputSchema.properties.pages.maxItems,5);
  assert.equal(read.inputSchema.properties.pages.uniqueItems,undefined);assert.equal(read.annotations.readOnlyHint,true);
  assert.deepEqual(repair.inputSchema.required,['draft_id','version_sha256']);assert.equal(repair.inputSchema.additionalProperties,false);
  assert.equal(repair.inputSchema.properties.plan,undefined);assert.equal(repair.annotations.readOnlyHint,false);
  assert.deepEqual(Object.keys(repair.inputSchema.properties),['draft_id','version_sha256','metadata','updates','replacements','deletions','insertions']);
  assert.equal(repair.inputSchema.properties.metadata.type,'object');
  assert.deepEqual(repair.inputSchema.properties.updates.items.required,['page','changes']);
  assert.deepEqual(repair.inputSchema.properties.updates.items.properties.changes,{type:'object'});
  assert.deepEqual(repair.inputSchema.properties.replacements.items.required,['page','slide']);
  assert.deepEqual(repair.inputSchema.properties.insertions.items.required,['before_page','slide']);
  assert.equal(repair.inputSchema.properties.insertions.items.properties.before_page.maximum,31);
  assert.equal(repair.inputSchema.properties.deletions.uniqueItems,undefined);
  assert.deepEqual(repair.inputSchema.properties.replacements.items.properties.slide,{type:'object'});
  assert.deepEqual(repair.inputSchema.properties.insertions.items.properties.slide,{type:'object'});
});
