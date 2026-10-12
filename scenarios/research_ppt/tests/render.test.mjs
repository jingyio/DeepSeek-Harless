import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdir, mkdtemp, readFile, rm} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {inflateRawSync} from 'node:zlib';
import {buildLayout,render,validateDeck,semanticContentHash,LayoutFailure} from '../dist/render.js';
import {defaultPolicy,policyHash} from '../dist/layout-policy.js';

const source = '公开测试夹具，第 1 页；SHA256 source-fixture-only';
const slide = (extra={}) => ({title:'独立科研任务',bullets:['实际内容由模型决定，结构检查不验证科研结论。'],sources:[source],...extra});
const chart = {type:'bar',categories:['甲','乙'],series:[{name:'测试值',values:[-1.25,3.75]}],y_label:'指标'};

// 仅用于检查真实生成文件的 OOXML；不模拟 PPT 工具或模型结果。
function unzip(buffer) {
  let end=buffer.length-22;
  while(end>=0 && buffer.readUInt32LE(end)!==0x06054b50) end--;
  assert.ok(end>=0,'缺少 ZIP 目录');
  const entries=buffer.readUInt16LE(end+10), files=new Map();
  let cursor=buffer.readUInt32LE(end+16);
  for(let i=0;i<entries;i++) {
    assert.equal(buffer.readUInt32LE(cursor),0x02014b50);
    const method=buffer.readUInt16LE(cursor+10), size=buffer.readUInt32LE(cursor+20);
    const nameSize=buffer.readUInt16LE(cursor+28), extraSize=buffer.readUInt16LE(cursor+30), commentSize=buffer.readUInt16LE(cursor+32);
    const name=buffer.subarray(cursor+46,cursor+46+nameSize).toString('utf8'), local=buffer.readUInt32LE(cursor+42);
    const start=local+30+buffer.readUInt16LE(local+26)+buffer.readUInt16LE(local+28);
    const data=buffer.subarray(start,start+size);
    files.set(name,method===8?inflateRawSync(data):data);
    cursor+=46+nameSize+extraSize+commentSize;
  }
  return files;
}

function chartXml(files) {
  // PptxGenJS 的图表编号跨生成实例递增；每份夹具仍应只有一个真实图表部件。
  const paths=[...files.keys()].filter(k=>/^ppt\/charts\/chart\d+\.xml$/.test(k));
  assert.equal(paths.length,1,'应保留唯一原生可编辑图表部件');
  return files.get(paths[0]).toString('utf8');
}

test('旧计划兼容；两套科研模板的布局检查可复现且不冒充视觉或语义验收',()=>{
  const original={title:'研究汇报',slides:[slide()]};
  const first=buildLayout(original);
  assert.deepEqual(first,buildLayout(original));
  assert.equal(first.template,'academic');
  assert.equal(first.slides[0].layout,'content');
  assert.equal(first.checks.pixel_render_verified,false);
  assert.equal(first.checks.semantic_quality_verified,false);
  const lab=buildLayout({...original,template:'lab'});
  assert.equal(lab.template,'lab');
  assert.ok(lab.checks.min_body_font_size>=18);
  assert.notEqual(first.deck_sha256,lab.deck_sha256);
});

test('拒绝冲突布局、未支持的数据、外部图片与会越界的长表格',()=>{
  const invalid = [
    slide({layout:'chart'}),
    slide({chart:{...chart,series:[{name:'错误',values:[1]}]}}),
    slide({chart:{...chart,series:[{name:'错误',values:[Infinity,2]}]}}),
    slide({chart:{...chart,categories:['重复','重复']}}),
    slide({chart:{...chart,code:'execute()'}}),
    slide({image:{data:'https://example.com/figure.png',width:100,height:100}}),
    slide({chart,table:[['列'],['值']]}),
    slide({comparison:{left:{title:'甲',bullets:['内容']},right:{title:'乙',bullets:['内容']}}}),
    slide({layout:'process',bullets:[],process:{steps:[{label:'仅一步',detail:'不满足流程协议。'}]}}),
    slide({layout:'process',bullets:[],process:{steps:[{label:'第一步',detail:'内容'}, {label:'第二步',detail:'内容'}],code:'execute()'}}),
    slide({process:{steps:[{label:'第一步',detail:'内容'}, {label:'第二步',detail:'内容'}]},bullets:[]}),
    slide({takeaway:'不支持的'.repeat(30)}),
  ];
  for(const s of invalid) assert.throws(()=>validateDeck({title:'验证',slides:[s]}));
  const tooDense=slide({table:Array.from({length:6},()=>Array.from({length:4},()=> '繁'.repeat(45)))});
  assert.throws(()=>buildLayout({title:'验证',slides:[tooDense]}),/表格文本溢出/);
  assert.throws(()=>buildLayout({title:'验证',slides:[slide({title:'繁'.repeat(70)})]}),/title 文本溢出/);
});

test('策略只改变几何与字号，来源/备注/全部文字和数据的语义摘要保持不变',()=>{
  const original={title:'结构保持检查',slides:[slide({notes:'原始 notes 前缀必须保留。',table:[['指标','数值'],['观测','真实数据']],bullets:['观察结果。']})]};
  const first=buildLayout(original);
  const changed={...original,template:'lab',layout_policy:{...defaultPolicy,media_position:'bottom',media_fraction:0.5,body_font_size:20}};
  const second=buildLayout(changed);
  assert.equal(first.semantic_content_sha256,second.semantic_content_sha256);
  assert.equal(first.semantic_content_sha256,semanticContentHash(original));
  assert.notEqual(first.layout_policy_sha256,second.layout_policy_sha256);
  assert.equal(second.layout_policy_sha256,policyHash(changed.layout_policy));
  assert.notDeepEqual(first.slides[0].elements,second.slides[0].elements);
  assert.equal(second.slides[0].source_count,1);
  assert.equal(second.checks.content_overlap_passed,true);
  assert.deepEqual(second.diagnostics,[]);
  assert.notEqual(semanticContentHash(original),semanticContentHash({...original,slides:[{...original.slides[0],notes:'擅自改过 notes'}]}));
  assert.throws(()=>buildLayout({...original,layout_policy:{...defaultPolicy,body_font_size:19}}),/布局策略/);
  assert.throws(()=>buildLayout({...original,layout_policy:{...defaultPolicy,delete_content:true}}),/布局策略/);
});

test('双栏保留全部正文顺序，过密布局按可枚举错误拒绝而不删改文字',()=>{
  const deck={title:'双栏',layout_policy:{...defaultPolicy,body_columns:2},slides:[slide({bullets:['第一条','第二条','第三条','第四条']})]};
  const page=buildLayout(deck).slides[0];
  assert.deepEqual(page.elements.filter(e=>e.role.startsWith('body_')).map(e=>e.text),deck.slides[0].bullets);
  const xs=new Set(page.elements.filter(e=>e.role.startsWith('body_')).map(e=>e.x));
  assert.equal(xs.size,2);
  const dense={title:'容量拒绝',layout_policy:{...defaultPolicy,body_columns:2,body_font_size:24},slides:[slide({bullets:Array.from({length:5},()=> '繁'.repeat(95))})]};
  assert.throws(()=>buildLayout(dense),error=>error instanceof LayoutFailure && error.code==='text_overflow' && error.page===1);
  assert.equal(dense.slides[0].bullets[0].length,95,'失败不能改动原计划');
});

test('默认按证据内容选版式；宽原图更大且不裁切，表格列宽保护完整术语',()=>{
  const figure=slide({bullets:['原图全部面板和标签必须保留。'],image:{
    data:'image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=',
    width:1800,height:630}});
  const data=slide({table:[['策略','GSM8K','MATH','HumanEval'],
    ['LLaMA2-7B LoRA(高斯)','42.85','5.50','18.35'],
    ['LLaMA2-7B PiSSA','53.22','7.47','21.92']],bullets:['三次运行均值，单位 %；全部方法与指标必须原样保留。']});
  const deck={title:'内容适配版式',slides:[figure,data]};
  const original=JSON.stringify(deck), adaptive=buildLayout(deck);
  const fixed=buildLayout({...deck,layout_policy:defaultPolicy});
  const image=adaptive.slides[0].elements.find(e=>e.role==='image');
  const oldImage=fixed.slides[0].elements.find(e=>e.role==='image');
  assert.ok(image.w*image.h>oldImage.w*oldImage.h*1.3,'宽横比原图应获得更大完整可见面积');
  assert.ok(Math.abs(image.w/image.h-1800/630)<1e-8,'保持原图宽高比，不能裁剪科研证据');
  const table=adaptive.slides[1].elements.find(e=>e.role==='table');
  assert.ok(table.w>fixed.slides[1].elements.find(e=>e.role==='table').w);
  assert.ok(table.column_widths[0]>table.column_widths[1],'长方法名列需要更宽空间');
  assert.ok((table.column_widths[3]-0.28)*72/table.font_size*0.88>=9*0.56,
    'HumanEval 需要完整英文术语宽度');
  assert.ok(Math.abs(table.column_widths.reduce((a,b)=>a+b,0)-table.w)<1e-8);
  assert.deepEqual(table.table,data.table,'版式不得改写、重排或补造数据');
  assert.equal(adaptive.semantic_content_sha256,fixed.semantic_content_sha256);
  assert.equal(adaptive.renderer_version,'research-ppt-layout-v11.2');
  assert.equal(JSON.stringify(deck),original,'普通版式适配也不能修改调用者计划');
});

test('密集图注逐页用20pt完整保留条件，证据面积明显改善；稀疏图页仍优先22pt',()=>{
  const image={data:'image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=',
    width:1800,height:630};
  // 来自实际产品遇到的密度形态；数值/名称仅作排版夹具，测试不认证科学结论。
  const dense=slide({title:'原图证据：最佳交替步数随任务变化',layout:'image',image,
    notes:'这是完整条件的排版工程夹具，保留原来源及备注。',
    takeaway:'已测试三类语言模型架构；论文测试外的架构与领域仍需验证',
    bullets:['T=0：QLoRA；T=1/5/10：LoftQ（Algorithm 1）',
      'MNLI：Uniform 2-bit DeBERTaV3-base',
      'GSM8K：LLAMA-2-13b，原图注写“NF4 2-bit”（命名待核）',
      'XSum：NF4 BART-large；最高值分别在 T=5/10/1']});
  const plain=slide({bullets:['非图页全部内容和字号保持。','不能因另一页拥挤改变全稿策略。']});
  const sparse=slide({image,bullets:['原图全部面板保留。']});
  const deck={title:'逐页图注适配',slides:[plain,dense,sparse]}, original=JSON.stringify(deck);
  const adaptive=buildLayout(deck);
  const actual=adaptive.slides[1], body=actual.elements.filter(e=>e.role.startsWith('body_'));
  assert.deepEqual(body.map(e=>e.text),dense.bullets,'全部原图条件必须保留，不能静默删图注');
  assert.ok(body.every(e=>e.font_size===20&&e.body_gap===0.08),'manifest必须反映实际图注字号与间距');
  const figure=actual.elements.find(e=>e.role==='image');
  assert.ok(figure.w*figure.h>=19,'密集图注不能把原图压缩成不可读的小缩略图');
  assert.ok(Math.abs(figure.w/figure.h-1800/630)<1e-8,'原证据不裁剪、不拉伸');
  const explicit=buildLayout({...deck,layout_policy:{...defaultPolicy,body_font_size:20,body_gap:0.08,media_fraction:0.64}});
  const explicitFigure=explicit.slides[1].elements.find(e=>e.role==='image');
  assert.ok(figure.w*figure.h>=explicitFigure.w*explicitFigure.h-1e-8,
    '逐页规则应保留可用紧凑左右布局的图件面积');
  assert.deepEqual(adaptive.slides[0].elements,buildLayout({title:deck.title,slides:[plain,sparse,dense]}).slides[0].elements,
    '非图页不受其他图页候选影响');
  assert.ok(adaptive.slides[0].elements.filter(e=>e.role.startsWith('body_')).every(e=>e.font_size===22));
  assert.ok(adaptive.slides[2].elements.filter(e=>e.role.startsWith('body_')).every(e=>e.font_size===22&&e.body_gap===0.18),
    '图面积增益不足25%时优先22pt正文');
  assert.ok(explicit.slides[0].elements.filter(e=>e.role.startsWith('body_')).every(e=>e.font_size===20),
    '显式已认证策略不能被逐页默认规则覆盖');
  assert.equal(adaptive.semantic_content_sha256,explicit.semantic_content_sha256);
  assert.equal(JSON.stringify(deck),original);
  const expanded=structuredClone(dense);
  expanded.bullets[3]='XSum：NF4 BART-large；MNLI/GSM8K/XSum 最佳 T=5/10/1';
  const expandedPage=buildLayout({title:deck.title,slides:[expanded]}).slides[0];
  assert.deepEqual(expandedPage.elements.filter(e=>e.role.startsWith('body_')).map(e=>e.text),expanded.bullets,
    '反馈增加条件后仍须完整保留全部图注');
  const expandedFigure=expandedPage.elements.find(e=>e.role==='image');
  assert.ok(expandedFigure.w*expandedFigure.h>=15,'更长条件仍须选择可用左右布局，不能回退为极小缩略图');
  assert.ok(expandedPage.elements.filter(e=>e.role.startsWith('body_')).every(e=>e.font_size===20&&e.body_gap===0.08));
});

test('密集图注实际写入20pt原生文本，全部来源/notes/原图仍在真实PPTX',async()=>{
  const area=fileURLToPath(new URL('../../../.local/research-ppt/node-render-tests/',import.meta.url));
  await mkdir(area,{recursive:true});
  const temporary=await mkdtemp(join(area,'dense-caption-'));
  try {
    const image='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=';
    const deck={title:'密集图注原生文本验收',slides:[slide({title:'完整图注与条件',
      takeaway:'已测试三类语言模型架构；论文测试外的架构与领域仍需验证',
      notes:'完整备注仍需审阅来源，不能用几何判断科学内容。',
      image:{data:`image/png;base64,${image}`,width:1800,height:630},
      bullets:['T=0：QLoRA；T=1/5/10：LoftQ（Algorithm 1）',
        'MNLI：Uniform 2-bit DeBERTaV3-base',
        'GSM8K：LLAMA-2-13b，原图注写“NF4 2-bit”（命名待核）',
        'XSum：NF4 BART-large；MNLI/GSM8K/XSum 最佳 T=5/10/1']})]};
    const output=join(temporary,'captions.pptx'), result=await render(deck,output);
    const files=unzip(await readFile(output)), xml=files.get('ppt/slides/slide1.xml').toString('utf8');
    for(const text of deck.slides[0].bullets) {
      const paragraph=[...xml.matchAll(/<a:p>([\s\S]*?)<\/a:p>/g)].find(m=>m[1].includes(`<a:t>${text}</a:t>`));
      assert.ok(paragraph,'条件应为完整可编辑原生文本');
      assert.ok(paragraph[1].includes('sz="2000"'),'实际PPTX图注必须是20pt，不能仅manifest声称');
    }
    const notes=files.get('ppt/notesSlides/notesSlide1.xml').toString('utf8');
    assert.ok(notes.includes(source)&&notes.includes(deck.slides[0].notes));
    assert.ok([...files.entries()].some(([path,data])=>/^ppt\/media\//.test(path)&&data.equals(Buffer.from(image,'base64'))));
    assert.ok(result.layout_manifest.slides[0].elements.filter(e=>e.role.startsWith('body_'))
      .every(e=>e.font_size===20&&e.body_gap===0.08));
  } finally {await rm(temporary,{recursive:true,force:true});}
});

test('适配列宽真正进入可编辑表格；原文字/行列/notes与原图字节保持',async()=>{
  const area=fileURLToPath(new URL('../../../.local/research-ppt/node-render-tests/',import.meta.url));
  await mkdir(area,{recursive:true});
  const temporary=await mkdtemp(join(area,'adaptive-'));
  try {
    const image='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=';
    const deck={title:'原生适配验收',slides:[slide({notes:'保留全部表格条件与来源。',bullets:[],
      table:[['方法','HumanEval','数值'],['LLaMA2-7B LoRA','完整指标','18.35'],['PiSSA','完整指标','21.92']]}),
      slide({image:{data:`image/png;base64,${image}`,width:1,height:1}})]};
    const output=join(temporary,'adaptive.pptx'), result=await render(deck,output);
    const files=unzip(await readFile(output)), table=result.layout_manifest.slides[0].elements.find(e=>e.role==='table');
    const xml=files.get('ppt/slides/slide1.xml').toString('utf8');
    const widths=[...xml.matchAll(/<a:gridCol w="(\d+)"\/>/g)].map(m=>Number(m[1]));
    assert.equal(widths.length,3,'必须生成原生可编辑表格列');
    table.column_widths.forEach((width,i)=>assert.ok(Math.abs(width*914400-widths[i])<=1));
    const rows=[...xml.matchAll(/<a:tr\b[^>]*>([\s\S]*?)<\/a:tr>/g)].map(row=>
      [...row[1].matchAll(/<a:tc>([\s\S]*?)<\/a:tc>/g)].map(cell=>
        [...cell[1].matchAll(/<a:t>([\s\S]*?)<\/a:t>/g)].map(m=>m[1]).join('')));
    assert.deepEqual(rows,deck.slides[0].table,'必须保留实际行列内容和顺序');
    assert.ok(files.get('ppt/notesSlides/notesSlide1.xml').toString('utf8').includes(deck.slides[0].notes));
    assert.ok([...files.entries()].some(([path,data])=>/^ppt\/media\//.test(path)&&data.equals(Buffer.from(image,'base64'))),
      '科研原图应以原字节进入PPTX，不能重绘或裁剪');
  } finally {await rm(temporary,{recursive:true,force:true});}
});

test('真实生成2/3/4/5步原生流程与结论框；全部内容、来源及原始notes保留',async()=>{
  const area=fileURLToPath(new URL('../../../.local/research-ppt/node-render-tests/',import.meta.url));
  await mkdir(area,{recursive:true});
  const temporary=await mkdtemp(join(area,'process-'));
  try {
    const deck={title:'原生流程编辑性检查',slides:[2,3,4,5].map(count=>slide({
      title:`${count} 步真实编辑性夹具`,layout:'process',bullets:[],
      notes:`原始备注-${count}`,
      ...(count<=3?{takeaway:'步骤只是结构夹具，未验证科研结论。'}:{}),
      process:{steps:Array.from({length:count},(_,i)=>({label:`步骤${i+1}`,detail:`保留内容${i+1}`}))},
    }))};
    const result=await render(deck,join(temporary,'process.pptx'));
    assert.equal(result.editable_process_count,4);
    const files=unzip(await readFile(join(temporary,'process.pptx')));
    assert.equal([...files.keys()].filter(k=>/^ppt\/media\//.test(k)&&!k.endsWith('/')).length,0,'流程不应栅格化为图片');
    for(const [i,s] of deck.slides.entries()) {
      const xml=files.get(`ppt/slides/slide${i+1}.xml`).toString('utf8');
      const notes=files.get(`ppt/notesSlides/notesSlide${i+1}.xml`).toString('utf8');
      for(const step of s.process.steps) {
        assert.ok(xml.includes(`<a:t>${step.label}</a:t>`));
        assert.ok(xml.includes(`<a:t>${step.detail}</a:t>`));
      }
      assert.ok(xml.includes('tailEnd type="triangle"'),'连接应为可编辑原生箭头');
      assert.ok(notes.includes(`原始备注-${s.process.steps.length}`));
      assert.ok(notes.includes(source));
      if(s.takeaway) {
        assert.ok(xml.includes(`<a:t>${s.takeaway}</a:t>`));
        assert.ok(notes.includes(s.takeaway));
      }
    }
  } finally {
    await rm(temporary,{recursive:true,force:true});
  }
});

test('五步加短结论真实可编辑生成；合法但过长的detail按位置拒绝且不删内容',async()=>{
  const area=fileURLToPath(new URL('../../../.local/research-ppt/node-render-tests/',import.meta.url));
  await mkdir(area,{recursive:true});
  const temporary=await mkdtemp(join(area,'five-step-'));
  try {
    const deck={title:'五步流程容量验收',slides:[slide({
      title:'五步机制与结论',layout:'process',bullets:[],takeaway:'来源支持的短结论。',
      notes:'每步条件和来源均须保留。',
      process:{steps:Array.from({length:5},(_,i)=>({label:`步骤${i+1}`,detail:`保留步骤${i+1}的条件。`}))},
    })]};
    const path=join(temporary,'short.pptx');
    const result=await render(deck,path);
    assert.equal(result.editable_process_count,1);
    const files=unzip(await readFile(path));
    const xml=files.get('ppt/slides/slide1.xml').toString('utf8');
    const notes=files.get('ppt/notesSlides/notesSlide1.xml').toString('utf8');
    assert.equal([...files.keys()].filter(k=>/^ppt\/media\//.test(k)&&!k.endsWith('/')).length,0,'流程与结论均应保持原生可编辑');
    assert.equal([...xml.matchAll(/tailEnd type="triangle"/g)].length,4);
    for(const step of deck.slides[0].process.steps) {
      assert.ok(xml.includes(`<a:t>${step.label}</a:t>`));
      assert.ok(xml.includes(`<a:t>${step.detail}</a:t>`));
    }
    assert.ok(xml.includes(`<a:t>${deck.slides[0].takeaway}</a:t>`));
    assert.ok(notes.includes(deck.slides[0].notes));
    assert.ok(notes.includes(source));
    assert.ok(notes.includes(deck.slides[0].takeaway));

    const dense=structuredClone(deck);
    dense.slides[0].process.steps[2].detail='繁'.repeat(60);
    const original=JSON.stringify(dense), rejectedPath=join(temporary,'dense.pptx');
    validateDeck(dense); // schema 上限合法，仍必须通过实际容量检查。
    await assert.rejects(render(dense,rejectedPath),error=>error instanceof LayoutFailure &&
      error.code==='text_overflow' && error.page===1 && error.role==='process_3_detail');
    assert.equal(JSON.stringify(dense),original,'拒绝不能删文字、改来源或缩短用户计划');
    await assert.rejects(readFile(rejectedPath),error=>error.code==='ENOENT','拒绝不能生成可误交付的PPTX');
  } finally {
    await rm(temporary,{recursive:true,force:true});
  }
});

test('两种策略真实生成后保留相同原生文字/notes/图表数据，17pt表格实际进入OOXML',async()=>{
  const area=fileURLToPath(new URL('../../../.local/research-ppt/node-render-tests/',import.meta.url));
  await mkdir(area,{recursive:true});
  const temporary=await mkdtemp(join(area,'policy-'));
  try {
    const deck={title:'策略回放内容保持',slides:[
      slide({notes:'原始正文备注',bullets:['需要保留的第一条','需要保留的第二条']}),
      slide({notes:'原始表格备注',table:[['指标','数据'],['甲','保留值']],bullets:[]}),
      slide({notes:'原始图表备注',chart,bullets:['数据须核对来源。']}),
    ]};
    const outputs=[];
    for(const [name,policy] of [['default',defaultPolicy],['candidate',{...defaultPolicy,body_columns:2,body_font_size:20,
      media_position:'bottom',media_fraction:0.5,table_font_size:17}]]) {
      const path=join(temporary,`${name}.pptx`);
      const result=await render({...deck,layout_policy:policy},path);
      outputs.push({files:unzip(await readFile(path)),manifest:result.layout_manifest});
    }
    assert.equal(outputs[0].manifest.semantic_content_sha256,outputs[1].manifest.semantic_content_sha256);
    const textValues=xml=>[...xml.matchAll(/<a:t>([\s\S]*?)<\/a:t>/g)].map(m=>m[1]);
    for(let i=1;i<=3;i++) {
      for(const part of [`ppt/slides/slide${i}.xml`,`ppt/notesSlides/notesSlide${i}.xml`]) {
        assert.deepEqual(textValues(outputs[0].files.get(part).toString('utf8')),textValues(outputs[1].files.get(part).toString('utf8')));
      }
    }
    const cacheValues=xml=>[...xml.matchAll(/<c:v>([\s\S]*?)<\/c:v>/g)].map(m=>m[1]);
    assert.deepEqual(cacheValues(chartXml(outputs[0].files)),cacheValues(chartXml(outputs[1].files)));
    const tableXml=outputs[1].files.get('ppt/slides/slide2.xml').toString('utf8');
    assert.ok(tableXml.includes('sz="1700"'),'表格字体策略必须真正写入OOXML');
    assert.equal(outputs[1].manifest.slides[1].elements.find(e=>e.role==='table').font_size,17);
  } finally {
    await rm(temporary,{recursive:true,force:true});
  }
});

test('真实生成15页：可编辑文字、表格和原生数据图保留数据及每页来源notes',async()=>{
  const area=fileURLToPath(new URL('../../../.local/research-ppt/node-render-tests/',import.meta.url));
  await mkdir(area,{recursive:true});
  const temporary=await mkdtemp(join(area,'deck-'));
  try {
    const deck={title:'多来源组会汇报结构验收',template:'lab',slides:[
      slide({title:'科研汇报',layout:'title',bullets:['这是生成与编辑性验证夹具。']}),
      slide({layout:'section',bullets:['进入方法比较。']}),
      slide({table:[['检查项','状态'],['可编辑文字','验证'],['来源备注','验证']]}),
      slide({chart,bullets:[]}),
      slide({comparison:{left:{title:'普通执行',bullets:['模型发起工具调用。']},
        right:{title:'结构执行',bullets:['Runtime 发起已认证调用。']}},bullets:[]}),
      slide({layout:'image',image:{data:'image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=',width:1,height:1}}),
      ...Array.from({length:9},(_,i)=>slide({title:`内容页 ${i+1}`})),
    ]};
    const output=join(temporary,'presentation.pptx'), result=await render(deck,output);
    const manifest=JSON.parse(await readFile(result.layout_manifest_path,'utf8'));
    assert.equal(result.slides,15);
    assert.equal(result.editable_table_count,1);
    assert.equal(result.editable_chart_count,1);
    assert.deepEqual(result.layout_manifest,manifest);
    const files=unzip(await readFile(output));
    assert.equal([...files.keys()].filter(k=>/^ppt\/slides\/slide\d+\.xml$/.test(k)).length,15);
    for(let i=1;i<=15;i++) {
      const xml=files.get(`ppt/slides/slide${i}.xml`).toString('utf8');
      assert.ok(xml.includes('<a:t>'),'文字应为原生文本');
      const notes=files.get(`ppt/notesSlides/notesSlide${i}.xml`).toString('utf8');
      assert.ok(notes.includes('公开测试夹具'),'每页应保留来源');
      assert.ok(notes.includes('SHA256 source-fixture-only'));
    }
    assert.ok(files.get('ppt/slides/slide3.xml').toString('utf8').includes('<a:tbl>'));
    assert.ok(files.get('ppt/slides/slide4.xml').toString('utf8').includes('<c:chart'));
    assert.ok(files.get('ppt/slides/slide6.xml').toString('utf8').includes('<p:pic>'));
    const dataXml=chartXml(files);
    assert.ok(dataXml.includes('-1.25'));
    assert.ok(dataXml.includes('3.75'));
    assert.ok([...files.keys()].some(k=>/^ppt\/embeddings\/.*\.xlsx$/.test(k)),'图表应携带可编辑数据工作簿');
  } finally {
    await rm(temporary,{recursive:true,force:true});
  }
});

test('真实图表显式写入轴变量与单位；不添加缺省的虚构轴标题，数值缓存保持',async()=>{
  const area=fileURLToPath(new URL('../../../.local/research-ppt/node-render-tests/',import.meta.url));
  await mkdir(area,{recursive:true});
  const temporary=await mkdtemp(join(area,'axis-titles-'));
  try {
    const labeled={...chart,x_label:'Method',y_label:'Measured latency',unit:'ms'};
    const deck={title:'轴标题保留回归',slides:[
      slide({chart:labeled,bullets:[]}),
      slide({chart:{...labeled,type:'line'},bullets:[]}),
      slide({chart:{type:'bar',categories:chart.categories,series:chart.series},bullets:[]}),
    ]};
    const output=join(temporary,'axes.pptx');
    await render(deck,output);
    const files=unzip(await readFile(output));
    const parts=[...files.keys()].filter(k=>/^ppt\/charts\/chart\d+\.xml$/.test(k));
    assert.equal(parts.length,3);
    for(const [index,part] of parts.entries()) {
      const xml=files.get(part).toString('utf8');
      assert.ok(xml.includes('<c:v>-1.25</c:v>'));
      assert.ok(xml.includes('<c:v>3.75</c:v>'));
      const category=xml.match(/<c:catAx>[\s\S]*?<\/c:catAx>/)?.[0];
      const value=xml.match(/<c:valAx>[\s\S]*?<\/c:valAx>/)?.[0];
      assert.ok(category&&value,'两条轴应保持为原生图表');
      if(index<2) {
        assert.ok(category.includes('<a:t>Method</a:t>'),'必须真正生成分类轴标题');
        assert.ok(value.includes('<a:t>Measured latency / ms</a:t>'),'指标与单位必须真正进入值轴标题');
      } else {
        assert.ok(!category.includes('<c:title>')&&!value.includes('<c:title>'),'无标注时不能凭空添加 Axis Title');
      }
    }
  } finally {
    await rm(temporary,{recursive:true,force:true});
  }
});
