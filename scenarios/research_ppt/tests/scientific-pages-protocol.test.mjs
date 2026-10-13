/** 外部计划/明确修订的运行时协议，不用类型定义代替参数与来源守卫。 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {preflightPlan} from '../dist/delivery-adapter.js';
import {previewExplicitUpdates} from '../dist/direct-edit-cli.js';
import {ADAPTER_TOOLS} from '../dist/mcp-adapter.js';

const fixture=()=>({title:'Source-bound scientific pages',slides:[{
  title:'Results with conditions',bullets:['Same measured result.'],sources:[{source_id:'approved-a',page:2},{source_id:'approved-b',page:1}],
  table:[['Method','Metric'],['A','12']],archetype:'result-summary',
  evidence_notes:[{label:'Conditions',text:'Measured on the specified split.',source_index:1}],notes:'Retain the original conditions.',
}]});

test('公开schema新增科研页型与明确移除，不允许调用者自报可见来源',()=>{
  const render=ADAPTER_TOOLS.find(x=>x.name==='render_delivery');
  const slide=render.inputSchema.properties.plan.properties.slides.items;
  assert.equal(slide.additionalProperties,false);
  assert.deepEqual(slide.properties.archetype.enum,['evidence-focus','result-summary','method-map']);
  assert.equal(slide.properties.evidence_notes.maxItems,3);
  assert.equal(slide.properties.evidence_notes.items.properties.source_index.minimum,1);
  assert.equal(slide.properties.visible_sources,undefined);
  const changes=ADAPTER_TOOLS.find(x=>x.name==='revise_delivery').inputSchema.properties.updates.items.properties.changes;
  assert.equal(changes.additionalProperties,false);
  for (const field of ['archetype','evidence_notes']) assert.ok(changes.properties[field].anyOf.some(x=>x.type==='null'));
  assert.equal(changes.properties.visible_sources,undefined);
});

test('三类主体受约束；method-map允许说明而旧process仍拒绝页级bullets',()=>{
  assert.equal(preflightPlan(fixture(),1).valid,true);
  const method=fixture(); delete method.slides[0].table;
  Object.assign(method.slides[0],{archetype:'method-map',layout:'process',process:{steps:[{label:'Read',detail:'Read approved source.'},{label:'Deliver',detail:'Check the actual output.'}]}});
  assert.equal(preflightPlan(method,1).valid,true);
  delete method.slides[0].archetype; delete method.slides[0].evidence_notes;
  assert.throws(()=>preflightPlan(method,1));
  method.slides[0].bullets=[]; assert.equal(preflightPlan(method,1).valid,true);
  const image=fixture(); delete image.slides[0].table;
  Object.assign(image.slides[0],{archetype:'evidence-focus',image:{source_id:'approved-a',image_id:'actual-image'}});
  assert.equal(preflightPlan(image,1).valid,true);
});

test('原sources索引、非法类型和伪造visible_sources在任何渲染前拒绝',()=>{
  const mutations=[s=>s.evidence_notes[0].source_index=0,s=>s.evidence_notes[0].source_index=3,
    s=>s.evidence_notes[0].source_index=true,s=>s.evidence_notes[0].source_index='1',
    s=>s.evidence_notes[0].label='x'.repeat(25),s=>s.evidence_notes[0].text='x'.repeat(111),
    s=>s.evidence_notes[0].extra='unknown',s=>s.evidence_notes[0].text='bad\u0000text',
    s=>s.evidence_notes=Array(4).fill(s.evidence_notes[0]),s=>s.evidence_notes=null,
    s=>delete s.archetype,s=>s.archetype='unknown',s=>s.archetype='evidence-focus',
    s=>s.visible_sources=['Invented Author 2026'],s=>s.process={steps:[]}];
  for (const mutate of mutations) { const plan=fixture(); mutate(plan.slides[0]); assert.throws(()=>preflightPlan(plan,1)); }
});

test('来源重排不能静默重绑证据；明确同步更新可改变索引，越界仍拒绝',()=>{
  const plan=fixture(), before=structuredClone(plan), sources=[...plan.slides[0].sources].reverse();
  assert.throws(()=>previewExplicitUpdates(plan,[{page:1,changes:{sources}}],1),{code:'invalid_revision'});
  const notes=[{...plan.slides[0].evidence_notes[0],source_index:2}];
  const revised=previewExplicitUpdates(plan,[{page:1,changes:{sources,evidence_notes:notes}}],1);
  assert.equal(revised.plan.slides[0].evidence_notes[0].source_index,2);
  assert.deepEqual(plan,before);
  assert.throws(()=>previewExplicitUpdates(plan,[{page:1,changes:{evidence_notes:[{...notes[0],source_index:3}]}}],1));
  const removed=previewExplicitUpdates(plan,[{page:1,changes:{archetype:null,evidence_notes:null}}],1);
  assert.equal(removed.plan.slides[0].archetype,undefined); assert.equal(removed.plan.slides[0].evidence_notes,undefined);
  assert.throws(()=>previewExplicitUpdates(plan,[{page:1,changes:{archetype:null}}],1));
});
