import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdir, mkdtemp, readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {inflateRawSync} from 'node:zlib';
import {buildLayout, render, validateDeck, semanticContentHash, LayoutFailure} from '../dist/render.js';

// 仅有公开合成来源；检查真实生成的原生对象，不模拟 MCP 或模型。
const source = 'Public synthetic paper page 2; SHA256 public-fixture-only';
const visible = 'Public synthetic paper, p. 2';
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=', 'base64');
const image = {data: 'image/png;base64,' + png.toString('base64'), width: 1, height: 1};
const table = [['Method', 'Accuracy'], ['Method A', '87.5'], ['Method B', '92.2']];
const chart = {type: 'bar', categories: ['Method A', 'Method B'],
  series: [{name: 'Accuracy', values: [87.5, 92.2]}], x_label: 'Method', y_label: 'Accuracy', unit: '%'};
const process = {steps: [{label: 'Read sources', detail: 'Keep the original figure'},
  {label: 'Verify output', detail: 'Check figures and numerical data'}]};
const note = {label: 'Conditions', text: 'Heldout split; one run, no confidence interval.', source_index: 1};
const slide = (extra = {}) => ({title: 'Scientific fixture', bullets: [], sources: [source],
  notes: 'Original speaker notes.', ...extra});
const scientific = (archetype, extra = {}) => slide({archetype, visible_sources: [visible], ...extra});

function unzip(buffer) {
  let end = buffer.length - 22;
  while (end >= 0 && buffer.readUInt32LE(end) !== 0x06054b50) end--;
  assert.ok(end >= 0, '真实产物缺少 ZIP 目录');
  const files = new Map(), count = buffer.readUInt16LE(end + 10);
  let cursor = buffer.readUInt32LE(end + 16);
  for (let i = 0; i < count; i++) {
    assert.equal(buffer.readUInt32LE(cursor), 0x02014b50);
    const method = buffer.readUInt16LE(cursor + 10), size = buffer.readUInt32LE(cursor + 20);
    const nameSize = buffer.readUInt16LE(cursor + 28), extraSize = buffer.readUInt16LE(cursor + 30), commentSize = buffer.readUInt16LE(cursor + 32);
    const name = buffer.subarray(cursor + 46, cursor + 46 + nameSize).toString('utf8'), local = buffer.readUInt32LE(cursor + 42);
    const start = local + 30 + buffer.readUInt16LE(local + 26) + buffer.readUInt16LE(local + 28);
    const raw = buffer.subarray(start, start + size);
    files.set(name, method === 8 ? inflateRawSync(raw) : raw);
    cursor += 46 + nameSize + extraSize + commentSize;
  }
  return files;
}

async function outputArea() {
  const area = fileURLToPath(new URL('../../../.local/research-ppt/scientific-layout-tests/', import.meta.url));
  await mkdir(area, {recursive: true});
  return mkdtemp(join(area, 'run-'));
}

test('科研页型拒绝未知类型、越界绑定、错类型及相互冲突主体', () => {
  const valid = scientific('evidence-focus', {image, evidence_notes: [note]});
  validateDeck({title: 'Fixture', slides: [valid]});
  const invalid = [
    {...valid, archetype: 'unknown'},
    {...valid, archetype: 1},
    {...valid, evidence_notes: [{...note, source_index: 0}]},
    {...valid, evidence_notes: [{...note, source_index: 2}]},
    {...valid, evidence_notes: [{...note, source_index: true}]},
    {...valid, evidence_notes: [{...note, source_index: '1'}]},
    {...valid, evidence_notes: Array(4).fill(note)},
    {...valid, evidence_notes: [{...note, label: 'x'.repeat(25)}]},
    {...valid, evidence_notes: [{...note, text: 'x'.repeat(111)}]},
    {...valid, evidence_notes: [{...note, text: null}]},
    {...valid, evidence_notes: [{...note, url: 'https://example.org'}]},
    {...valid, visible_sources: 'Invented citation'},
    {...valid, visible_sources: []},
    {...valid, table},
    scientific('evidence-focus', {table}),
    scientific('result-summary', {process, layout: 'process'}),
    scientific('method-map', {table}),
    slide({image, evidence_notes: [note]}),
    slide({visible_sources: [visible]}),
  ];
  for (const value of invalid) assert.throws(() => validateDeck({title: 'Rejected fixture', slides: [value]}));
});

test('方法机制页允许原生流程配简短解释，旧流程页仍保持原来的约束', () => {
  const value = scientific('method-map', {layout: 'process', process, bullets: ['The caller remains responsible for scientific meaning.']});
  const layout = buildLayout({title: 'Fixture', slides: [value]});
  assert.ok(layout.slides[0].elements.filter(e => e.role.startsWith('process_')).every(e => e.native_editable));
  assert.ok(layout.slides[0].elements.some(e => e.text === value.bullets[0]));
  assert.throws(() => validateDeck({title: 'Legacy fixture', slides: [slide({layout: 'process', process, bullets: value.bullets})]}));
});

test('改变科研页型只改变排版，证据文字或绑定索引改变必须改变内容摘要', () => {
  const original = {title: 'Fixture', slides: [scientific('evidence-focus', {image, evidence_notes: [note],
    sources: [source, 'Public synthetic second source page 3'], visible_sources: [visible, 'Second source, p. 3']})]};
  const layoutOnly = structuredClone(original);
  layoutOnly.slides[0].archetype = 'result-summary';
  assert.equal(semanticContentHash(original), semanticContentHash(layoutOnly));
  for (const update of [{text: 'An unsupported replacement condition.'}, {source_index: 2}]) {
    const changed = structuredClone(original);
    Object.assign(changed.slides[0].evidence_notes[0], update);
    assert.notEqual(semanticContentHash(original), semanticContentHash(changed));
  }
});

test('三类新科研页真实生成原图字节、可编辑表格、图表workbook、流程和证据绑定notes', async () => {
  const area = await outputArea();
  const deck = {title: 'Native scientific evidence fixture', slides: [
    scientific('evidence-focus', {image, bullets: ['Evidence is retained, without adding a claim.'], evidence_notes: [note]}),
    scientific('result-summary', {table, evidence_notes: [note]}),
    scientific('result-summary', {chart, evidence_notes: [note]}),
    scientific('method-map', {layout: 'process', process, bullets: ['Read, then verify.'], evidence_notes: [note]}),
  ]};
  const output = join(area, 'scientific.pptx'), result = await render(deck, output);
  assert.equal(result.slides, 4);
  assert.equal(result.editable_table_count, 1);
  assert.equal(result.editable_chart_count, 1);
  assert.equal(result.editable_process_count, 1);
  const files = unzip(await readFile(output));
  assert.ok([...files.entries()].some(([name, raw]) => name.startsWith('ppt/media/') && raw.equals(png)), '不能转码或重新描绘原图');
  for (let i = 1; i <= 4; i++) {
    const xml = files.get(`ppt/slides/slide${i}.xml`).toString('utf8');
    assert.ok(xml.includes(`${note.label} [${note.source_index}]`));
    assert.ok(xml.includes(note.text));
    assert.ok(xml.includes(visible));
    const notes = files.get(`ppt/notesSlides/notesSlide${i}.xml`).toString('utf8');
    assert.ok(notes.includes(source));
    assert.ok(notes.includes('Original speaker notes.'));
    assert.ok(notes.includes(`证据说明 [1] ${note.label}：${note.text}`));
  }
  assert.ok(files.get('ppt/slides/slide2.xml').toString('utf8').includes('<a:tbl>'));
  assert.ok(files.get('ppt/slides/slide3.xml').toString('utf8').includes('<c:chart'));
  const chartFiles = [...files.entries()].filter(([name]) => /^ppt\/charts\/chart\d+\.xml$/.test(name));
  assert.equal(chartFiles.length, 1);
  assert.ok(chartFiles[0][1].toString('utf8').includes('<c:v>87.5</c:v>'));
  assert.ok(chartFiles[0][1].toString('utf8').includes('<c:v>92.2</c:v>'));
  assert.ok([...files.keys()].some(name => /^ppt\/embeddings\/.*\.xlsx$/.test(name)));
});

test('单页opt-in科研重排保持其余旧页的几何及真实slide/notes XML', async () => {
  const deck = {title: 'Local change fixture', slides: [
    slide({image, bullets: ['One unchanged observation.']}),
    slide({table}),
    slide({layout: 'process', process}),
  ]};
  const changed = structuredClone(deck);
  Object.assign(changed.slides[1], {archetype: 'result-summary', visible_sources: [visible]});
  const before = buildLayout(deck), after = buildLayout(changed);
  for (const index of [0, 2]) assert.deepEqual(before.slides[index], after.slides[index]);
  const area = await outputArea();
  await render(deck, join(area, 'before.pptx'));
  await render(changed, join(area, 'after.pptx'));
  const oldFiles = unzip(await readFile(join(area, 'before.pptx'))), newFiles = unzip(await readFile(join(area, 'after.pptx')));
  for (const page of [1, 3]) {
    for (const name of [`ppt/slides/slide${page}.xml`, `ppt/notesSlides/notesSlide${page}.xml`])
      assert.deepEqual(oldFiles.get(name), newFiles.get(name), '非目标页不得被新设计改写');
  }
});

test('证据聚焦拒绝长说明挤成缩略图，稀疏说明及窄长原图保留适用空间', () => {
  // 几何夹具：三个合法长说明可在底部三列完整放下，却挤小原图。
  // 数值不是科研事实，也不是渲染质量认证。
  const landscape = {...image, width: 1800, height: 1000};
  const dense = {title: 'Evidence size fixture', slides: [scientific('evidence-focus', {
    image: landscape,
    evidence_notes: Array.from({length: 3}, (_,i) => ({label: `条件${i+1}`,
      text: '保留原文条件'.repeat(18), source_index: 1})),
  })]};
  const original = JSON.stringify(dense);
  validateDeck(dense);
  assert.throws(() => buildLayout(dense), error => error instanceof LayoutFailure &&
    error.code === 'text_overflow' && error.page === 1 && error.role === 'image' && /证据图面积过小/.test(error.message));
  assert.equal(JSON.stringify(dense), original, '拒绝不能删除条件或修改原图');

  const sparse = {title: dense.title, slides: [scientific('evidence-focus', {
    image: landscape, evidence_notes: [{label: '条件', text: '保留完整原图和实验条件。', source_index: 1}],
  })]};
  const figure = buildLayout(sparse).slides[0].elements.find(e => e.role === 'image');
  assert.ok(figure.w * figure.h >= 10, '稀疏页完整图件应通过窄面积守卫');
  assert.ok(Math.abs(figure.w / figure.h - 1.8) < 1e-8, '必须保持原图等比');

  const tall = {title: dense.title, slides: [scientific('evidence-focus', {
    image: {...image, width: 1000, height: 5000}, bullets: ['保留全部证据。'],
  })]};
  const narrow = buildLayout(tall).slides[0].elements.find(e => e.role === 'image');
  assert.ok(narrow.w * narrow.h < 10, '极窄原图适用阈值应按无说明完整适配面积缩放，不能强制10');
  assert.ok(Math.abs(narrow.w / narrow.h - 0.2) < 1e-8);
});
