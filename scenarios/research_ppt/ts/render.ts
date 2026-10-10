/** 确定性科研版式，不调用模型；事实、选材、图表数据及解释由调用者负责。 */
import pptxgen from 'pptxgenjs';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { defaultPolicy, policyHash, validatePolicy, type LayoutPolicy } from './layout-policy.js';

export type Template = 'academic' | 'lab';
export type Layout = 'title' | 'content' | 'image' | 'table' | 'chart' | 'section' | 'comparison' | 'process';
export type Chart = { type: 'bar' | 'line'; categories: string[];
  series: { name: string; values: number[] }[]; x_label?: string; y_label?: string; unit?: string };
export type Comparison = { left: { title: string; bullets: string[] }; right: { title: string; bullets: string[] } };
export type Process = {steps: {label: string; detail: string}[]};
export type Slide = { title: string; bullets: string[]; sources: string[]; notes?: string; layout?: Layout;
  image?: {data: string; width: number; height: number}; table?: string[][]; chart?: Chart; comparison?: Comparison;
  process?: Process; takeaway?: string };
export type Deck = {title: string; slides: Slide[]; template?: Template; layout_policy?: LayoutPolicy};
type Box = {x: number; y: number; w: number; h: number};
export type LayoutElement = Box & { role: string; native_editable: boolean; font_size?: number;
  estimated_lines?: number; text?: string; row_heights?: number[]; table?: string[][]; chart?: Chart;
  decoration?: 'body-card' | 'process-card'; decoration_box?: Box;
  connector_direction?: 'right' | 'down'; step_index?: number };
export type LayoutFailureCode = 'text_overflow' | 'table_overflow' | 'chart_label_overflow' | 'out_of_bounds' | 'content_overlap';
export class LayoutFailure extends Error {
  readonly code: LayoutFailureCode;
  readonly page?: number;
  readonly role?: string;
  constructor(code: LayoutFailureCode, message: string, page?: number, role?: string) {
    super(`${page === undefined ? '' : `第 ${page} 页：`}[${code}] ${message}`);
    this.name = 'LayoutFailure'; this.code = code; this.page = page; this.role = role;
  }
}
export type LayoutManifest = { schema_version: 1; renderer_version: string; template: Template;
  width: number; height: number; font_face: string; deck_sha256: string;
  layout_policy: LayoutPolicy; layout_policy_sha256: string; semantic_content_sha256: string;
  diagnostics: {code: LayoutFailureCode; page: number; role?: string; message: string}[];
  slides: {page: number; layout: Layout; source_count: number; elements: LayoutElement[]}[];
  checks: { bounds_passed: boolean; estimated_text_fit_passed: boolean; content_overlap_passed: boolean;
    min_body_font_size: number; semantic_quality_verified: false; pixel_render_verified: false } };

const WIDTH = 13.333333, HEIGHT = 7.5;
const FONT = 'Noto Sans CJK SC';
const BODY: Box = {x: 0.7, y: 1.85, w: 11.93, h: 4.89};
const THEMES = {
  academic: { title: '17345C', accent: '117D88', body: '243247', pale: 'F2F6FA', border: 'D7DFEA' },
  lab: { title: '164A46', accent: '207C6B', body: '243B39', pale: 'F1F7F4', border: 'D5E4DE' },
};
const layouts: Layout[] = ['title','content','image','table','chart','section','comparison','process'];

function boundedText(value: unknown, max: number): value is string {
  return typeof value === 'string' && value.trim().length > 0 && value.length <= max &&
    !/[\x00-\x08\x0B\x0C\x0E-\x1F]/.test(value);
}
function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}
function onlyKeys(value: Record<string, unknown>, allowed: string[]) {
  return Object.keys(value).every(k => allowed.includes(k));
}
function validBullets(value: unknown, count = 5, length = 150): value is string[] {
  return Array.isArray(value) && value.length <= count && value.every(v => boundedText(v, length));
}
function inferredLayout(s: Slide): Layout {
  return s.layout ?? (s.process ? 'process' : s.comparison ? 'comparison' : s.image ? 'image' : s.table ? 'table' : s.chart ? 'chart' : 'content');
}
export function validateDeck(deck: Deck) {
  if (!object(deck) || !onlyKeys(deck, ['title','slides','template','layout_policy']) || !boundedText(deck.title,100) ||
      !Array.isArray(deck.slides) || deck.slides.length < 1 || deck.slides.length > 30 ||
      (deck.template !== undefined && !['academic','lab'].includes(deck.template))) {
    throw new Error('需要标题、1–30 页幻灯片及可选 academic/lab 模板');
  }
  if (deck.layout_policy !== undefined) validatePolicy(deck.layout_policy);
  for (const [index, s] of deck.slides.entries()) {
    const fail = (message: string): never => {throw new Error(`第 ${index+1} 页：${message}`);};
    if (!object(s) || !onlyKeys(s,['title','bullets','sources','notes','layout','image','table','chart','comparison','process','takeaway']) ||
        !boundedText(s.title,70) || !validBullets(s.bullets) ||
        s.bullets.join('').length > (s.image || s.table || s.chart ? 220 : 500) ||
        !Array.isArray(s.sources) || !s.sources.length || s.sources.length > 20 || s.sources.some(v => !boundedText(v,250)) ||
        (s.notes !== undefined && (typeof s.notes !== 'string' || s.notes.length > 6000 ||
          /[\x00-\x08\x0B\x0C\x0E-\x1F]/.test(s.notes)))) fail('超出文本容量或缺少合法来源，请修改计划');
    if (s.takeaway !== undefined && !boundedText(s.takeaway,90)) fail('takeaway 应是 1–90 字符的短结论，必须由调用者核对来源');
    if (s.layout !== undefined && !layouts.includes(s.layout)) fail('不支持的 layout');
    const mediaCount = [s.image,s.table,s.chart,s.comparison,s.process].filter(v => v !== undefined).length;
    if (mediaCount > 1) fail('每页只能选择图片、表格、数据图、双栏比较或流程图之一');
    if (s.image && (!object(s.image) || !onlyKeys(s.image,['data','width','height']) ||
        typeof s.image.data !== 'string' || !/^image\/(png|jpeg);base64,[A-Za-z0-9+/=]+$/.test(s.image.data) ||
        !Number.isFinite(s.image.width) || !Number.isFinite(s.image.height) || s.image.width <= 0 || s.image.height <= 0 ||
        s.image.width > 10000 || s.image.height > 10000 || s.image.data.length > 16000000)) fail('图片格式或尺寸无效');
    if (s.table && (!Array.isArray(s.table) || s.table.length < 2 || s.table.length > 6 ||
        !s.table[0]?.length || s.table[0].length > 4 ||
        s.table.some(r => !Array.isArray(r) || r.length !== s.table![0].length || r.some(v => !boundedText(v,45))))) {
      fail('表格需要 2–6 行、1–4 列及短单元格');
    }
    if (s.chart) {
      const chart = s.chart;
      if (!object(chart) || !onlyKeys(chart,['type','categories','series','x_label','y_label','unit']) ||
          !['bar','line'].includes(chart.type) || !Array.isArray(chart.categories) ||
          chart.categories.length < 2 || chart.categories.length > 10 || chart.categories.some(v => !boundedText(v,25)) ||
          new Set(chart.categories).size !== chart.categories.length || !Array.isArray(chart.series) ||
          chart.series.length < 1 || chart.series.length > 3 || chart.series.some(series =>
            !object(series) || !onlyKeys(series,['name','values']) || !boundedText(series.name,30) ||
            !Array.isArray(series.values) || series.values.length !== chart.categories.length ||
            series.values.some(v => typeof v !== 'number' || !Number.isFinite(v))) ||
          [chart.x_label,chart.y_label,chart.unit].some(v => v !== undefined && !boundedText(v,40))) {
        fail('数据图只接受 bar/line、2–10 个分类、1–3 组对应的有限数值；请勿猜测数据');
      }
    }
    if (s.comparison) {
      if (!object(s.comparison) || !onlyKeys(s.comparison,['left','right']) ||
          [s.comparison.left,s.comparison.right].some(col => !object(col) || !onlyKeys(col,['title','bullets']) ||
            !boundedText(col.title,35) || !validBullets(col.bullets,4,100) || col.bullets.join('').length > 240) ||
          s.bullets.length) fail('双栏比较需要 left/right 的 title 和 bullets，页级 bullets 留空');
    }
    if (s.process && (!object(s.process) || !onlyKeys(s.process,['steps']) || !Array.isArray(s.process.steps) ||
        s.process.steps.length < 2 || s.process.steps.length > 5 || s.process.steps.some(step =>
          !object(step) || !onlyKeys(step,['label','detail']) || !boundedText(step.label,28) || !boundedText(step.detail,90)) ||
        s.layout !== 'process' || s.bullets.length)) fail('process 需要 layout=process、2–5 个短 label/detail 步骤，页级 bullets 留空');
    const layout = inferredLayout(s);
    if ((layout === 'image' && !s.image) || (layout === 'table' && !s.table) ||
        (layout === 'chart' && !s.chart) || (layout === 'comparison' && !s.comparison) || (layout === 'process' && !s.process) ||
        (['title','section','content'].includes(layout) && mediaCount)) fail('layout 与页面内容类型不一致');
    if (['title','section'].includes(layout) && s.bullets.length > 4) fail('封面/章节页最多 4 条短句');
  }
}

/** 保守的几何估算；不裁剪内容、不缩到小字号，也不宣称像素级视觉验收。 */
function lines(text: string, width: number, fontSize: number) {
  const capacity = Math.max(1, (width * 72 / fontSize) * 0.88);
  return text.split('\n').reduce((sum,line) => sum + Math.max(1, Math.ceil(
    Array.from(line).reduce((n,c) => n + (c.charCodeAt(0)>255 ? 1 : 0.56),0) / capacity)),0);
}
function textElement(role: string, text: string, box: Box, fontSize: number): LayoutElement {
  const estimated = lines(text,box.w,fontSize);
  if (estimated * fontSize / 72 * 1.28 + 0.05 > box.h + 0.01) {
    throw new LayoutFailure('text_overflow',`${role} 文本溢出，请缩短正文、标题或分成多页；不会自动删改科研内容`,undefined,role);
  }
  return {...box,role,text,font_size:fontSize,estimated_lines:estimated,native_editable:true};
}
function addBullets(elements: LayoutElement[], bullets: string[], box: Box, fontSize: number, prefix = 'body', gap = 0.18) {
  let y = box.y;
  for (const [index,bullet] of bullets.entries()) {
    const textWidth = box.w - 0.6;
    const textHeight = lines(bullet,textWidth,fontSize) * fontSize / 72 * 1.28 + 0.06;
    const cardHeight = Math.max(0.66,textHeight+0.22);
    if (y+cardHeight > box.y+box.h+0.01) throw new LayoutFailure('text_overflow','正文文本溢出，请缩短或分成两页',undefined,prefix);
    const e = textElement(`${prefix}_${index+1}`,bullet,{x:box.x+0.4,y:y+0.14,w:textWidth,h:textHeight},fontSize);
    elements.push({...e,decoration:'body-card',decoration_box:{x:box.x,y,w:box.w,h:cardHeight}});
    y += cardHeight + gap;
  }
}
function overlap(a: Box, b: Box) {
  const epsilon = 0.005;
  return Math.min(a.x+a.w,b.x+b.w)-Math.max(a.x,b.x)>epsilon &&
    Math.min(a.y+a.h,b.y+b.h)-Math.max(a.y,b.y)>epsilon;
}
function addProcess(elements: LayoutElement[], process: Process, box: Box, policy: LayoutPolicy) {
  const count=process.steps.length;
  if (count<=3) {
    const gap=0.44, width=(box.w-gap*(count-1))/count;
    for(const [i,step] of process.steps.entries()) {
      const card={x:box.x+i*(width+gap),y:box.y,w:width,h:box.h};
      const labelHeight=lines(step.label,width-0.44,24)*24/72*1.28+0.06;
      const heading=textElement(`process_${i+1}_heading`,step.label,
        {x:card.x+0.22,y:card.y+0.76,w:width-0.44,h:labelHeight},24);
      elements.push({...heading,decoration:'process-card',decoration_box:card,step_index:i+1});
      const detailY=heading.y+labelHeight+0.22;
      elements.push(textElement(`process_${i+1}_detail`,step.detail,
        {x:card.x+0.22,y:detailY,w:width-0.44,h:card.y+card.h-detailY-0.24},policy.body_font_size));
      if(i<count-1) elements.push({role:`process_connector_${i+1}`,x:card.x+card.w+0.06,y:card.y+card.h/2,
        w:gap-0.12,h:0.015,native_editable:true,connector_direction:'right'});
    }
  } else {
    const gap=0.04, rowHeight=(box.h-gap*(count-1))/count;
    for(const [i,step] of process.steps.entries()) {
      const y=box.y+i*(rowHeight+gap), card={x:box.x+0.76,y,w:box.w-0.76,h:rowHeight};
      elements.push({...textElement(`process_${i+1}_heading`,step.label,
        {x:card.x+0.2,y:y+0.05,w:2.8,h:rowHeight-0.1},policy.body_font_size),
        decoration:'process-card',decoration_box:card,step_index:i+1});
      elements.push(textElement(`process_${i+1}_detail`,step.detail,
        {x:card.x+3.2,y:y+0.05,w:card.w-3.42,h:rowHeight-0.1},policy.body_font_size));
      const numberY=y+(rowHeight-0.44)/2;
      elements.push({...textElement(`process_${i+1}_number`,String(i+1),
        {x:box.x+0.02,y:numberY,w:0.44,h:0.44},20),step_index:i+1});
      if(i<count-1) elements.push({role:`process_connector_${i+1}`,x:box.x+0.235,y:numberY+0.48,
        w:0.015,h:rowHeight+gap-0.52,native_editable:true,connector_direction:'down'});
    }
  }
}
function canonical(value: unknown): unknown {
  if(Array.isArray(value)) return value.map(canonical);
  if(object(value)) return Object.fromEntries(Object.keys(value).sort().filter(k=>value[k]!==undefined).map(k=>[k,canonical(value[k])]));
  return value;
}
/** 只核对结构是否保留输入内容；不能证明事实正确或图注/结论忠实。 */
export function semanticContentHash(deck: Deck): string {
  const content={title:deck.title,slides:deck.slides.map(({layout:_layout,...slide})=>slide)};
  return createHash('sha256').update(JSON.stringify(canonical(content)),'utf8').digest('hex');
}
export function buildLayout(deck: Deck): LayoutManifest {
  validateDeck(deck);
  const policy = validatePolicy(deck.layout_policy ?? defaultPolicy);
  const pages: LayoutManifest['slides'] = deck.slides.map((s,index) => {
    const layout = inferredLayout(s), elements: LayoutElement[] = [];
    const add = (role: string, text: string, box: Box, fontSize: number) => elements.push(textElement(role,text,box,fontSize));
    try {
      if (layout === 'title' || layout === 'section') {
        add('title',s.title,{x:0.9,y:1.78,w:11.35,h:1.47},36);
        const introY = 3.42;
        if (s.takeaway) {
          const h = lines(s.takeaway,11.0,22)*22/72*1.28+0.07;
          add('takeaway',s.takeaway,{x:0.95,y:introY,w:11.0,h},22);
          addBullets(elements,s.bullets,{x:0.9,y:introY+h+0.25,w:11.35,h:6.65-introY-h-0.25},policy.body_font_size,'body',policy.body_gap);
        } else addBullets(elements,s.bullets,{x:0.9,y:introY,w:11.35,h:6.74-introY},policy.body_font_size,'body',policy.body_gap);
      } else {
        add('title',s.title,{x:0.7,y:0.4,w:11.93,h:1.12},30);
        const body = {...BODY};
        if (s.takeaway) {
          const h=lines(s.takeaway,11.35,20)*20/72*1.28+0.08;
          add('takeaway',s.takeaway,{x:0.98,y:BODY.y+0.12,w:11.35,h},20);
          body.y=BODY.y+h+0.39; body.h=BODY.y+BODY.h-body.y;
        }
        if (s.comparison) {
          const colGap=0.38, colWidth=(body.w-colGap)/2;
          const cols = [{name:'left',x:body.x,value:s.comparison.left},{name:'right',x:body.x+colWidth+colGap,value:s.comparison.right}];
          for (const col of cols) {
            const headingHeight=lines(col.value.title,colWidth-0.42,24)*24/72*1.28+0.07;
            add(`${col.name}_heading`,col.value.title,{x:col.x+0.21,y:body.y+0.18,w:colWidth-0.42,h:headingHeight},24);
            const bulletY=body.y+headingHeight+0.48;
            addBullets(elements,col.value.bullets,{x:col.x,y:bulletY,w:colWidth,h:body.y+body.h-bulletY},policy.body_font_size,col.name,policy.body_gap);
          }
        } else if (s.process) {
          addProcess(elements,s.process,body,policy);
        } else if (s.image || s.table || s.chart) {
          const split = s.bullets.length > 0;
          const media: Box = {...body};
          if (split) {
            const gap=0.4, copy={...body};
            if (policy.media_position==='right') {
              media.w=(body.w-gap)*policy.media_fraction;
              copy.w=body.w-gap-media.w; media.x=body.x+copy.w+gap;
            } else {
              media.h=(body.h-gap)*policy.media_fraction;
              copy.h=body.h-gap-media.h; media.y=body.y+copy.h+gap;
            }
            addBullets(elements,s.bullets,copy,policy.body_font_size,'body',policy.body_gap);
          }
          if (s.image) {
            const scale = Math.min(media.w/s.image.width,media.h/s.image.height);
            const w=s.image.width*scale,h=s.image.height*scale;
            elements.push({role:'image',x:media.x+(media.w-w)/2,y:media.y+(media.h-h)/2,w,h,native_editable:false});
          }
          if (s.table) {
            const fs=policy.table_font_size, cellWidth=media.w/s.table[0].length-0.28;
            const rowHeights = s.table.map(row => Math.max(0.56,...row.map(v => lines(v,cellWidth,fs)*fs/72*1.35+0.22)));
            const h = rowHeights.reduce((a,b)=>a+b,0);
            if(h>media.h+0.01) throw new LayoutFailure('table_overflow','表格文本溢出，请缩短单元格或分成多页',undefined,'table');
            elements.push({...media,y:media.y+(media.h-h)/2,h,role:'table',native_editable:true,font_size:fs,row_heights:rowHeights,table:s.table});
          }
          if (s.chart) {
            const maxLabelWidth = (media.w-1.2)/s.chart.categories.length;
            if(s.chart.categories.some(v=>lines(v,maxLabelWidth,18)>2)) throw new LayoutFailure('chart_label_overflow','图表分类标签过长，请缩短标签或减少分类',undefined,'chart');
            elements.push({...media,role:'chart',native_editable:true,font_size:18,chart:s.chart});
          }
        } else {
          const columns=policy.body_columns;
          const colWidth=(body.w-(columns-1)*0.4)/columns;
          const perColumn=Math.ceil(s.bullets.length/columns);
          for(let c=0;c<columns;c++) addBullets(elements,s.bullets.slice(c*perColumn,(c+1)*perColumn),
            {x:body.x+c*(colWidth+0.4),y:body.y,w:colWidth,h:body.h},policy.body_font_size,
            columns===1?'body':`body_col${c+1}`,policy.body_gap);
        }
      }
      add('footer','来源见讲者备注',{x:0.7,y:7.06,w:4.0,h:0.24},10);
      add('page',`${index+1} / ${deck.slides.length}`,{x:11.7,y:7.02,w:0.93,h:0.3},12);
      for (const e of elements) {
        for(const box of [e,...(e.decoration_box?[e.decoration_box]:[])]) if(box.x<0 || box.y<0 || box.w<=0 || box.h<=0 || box.x+box.w>WIDTH+0.01 || box.y+box.h>HEIGHT+0.01) {
          throw new LayoutFailure('out_of_bounds',`${e.role} 超出版面边界`,undefined,e.role);
        }
      }
      for(let i=0;i<elements.length;i++) for(let j=i+1;j<elements.length;j++) {
        if(overlap(elements[i],elements[j])) throw new LayoutFailure('content_overlap',`${elements[i].role} 与 ${elements[j].role} 版面重叠`,undefined,elements[i].role);
      }
    } catch(error) {
      if (error instanceof LayoutFailure) throw new LayoutFailure(error.code,error.message.replace(/^\[[^\]]+\] /,''),index+1,error.role);
      throw new Error(`第 ${index+1} 页：${error instanceof Error?error.message:String(error)}`);
    }
    return {page:index+1,layout,source_count:s.sources.length,elements};
  });
  const bodySizes=pages.flatMap(s=>s.elements.filter(e=>e.font_size && !['title','footer','page'].includes(e.role)).map(e=>e.font_size!));
  return {schema_version:1,renderer_version:'research-ppt-layout-v5',template:deck.template??'academic',width:WIDTH,height:HEIGHT,
    font_face:FONT,deck_sha256:createHash('sha256').update(JSON.stringify(deck)).digest('hex'),slides:pages,
    layout_policy:policy,layout_policy_sha256:policyHash(policy),semantic_content_sha256:semanticContentHash(deck),diagnostics:[],
    checks:{bounds_passed:true,estimated_text_fit_passed:true,content_overlap_passed:true,
      min_body_font_size:bodySizes.length?Math.min(...bodySizes):18,semantic_quality_verified:false,pixel_render_verified:false}};
}

export async function render(deck: Deck, output: string) {
  const manifest = buildLayout(deck), theme = THEMES[manifest.template];
  const pptx = new pptxgen();
  pptx.layout = 'LAYOUT_WIDE'; pptx.author = 'SSS Research PPT'; pptx.subject = 'Research presentation';
  pptx.title = deck.title;
  pptx.theme = {headFontFace:FONT,bodyFontFace:FONT};
  for (const [index,s] of deck.slides.entries()) {
    const page = manifest.slides[index], slide = pptx.addSlide();
    slide.background = {color:'FFFFFF'};
    if(page.layout==='title' || page.layout==='section') {
      slide.addText(page.layout==='title'?'RESEARCH BRIEF':'RESEARCH / SECTION',
        {x:0.95,y:0.79,w:8.0,h:0.3,fontFace:FONT,fontSize:12,bold:true,charSpacing:2,color:theme.accent,margin:0});
      slide.addShape(pptx.ShapeType.rect,{x:0.95,y:1.36,w:0.84,h:0.065,line:{color:theme.accent,transparency:100},fill:{color:theme.accent}});
      slide.addShape(pptx.ShapeType.line,{x:0.95,y:6.9,w:11.0,h:0,line:{color:theme.border,width:1}});
    } else {
      slide.addShape(pptx.ShapeType.rect,{x:0.7,y:0.25,w:0.62,h:0.04,line:{color:theme.accent,transparency:100},fill:{color:theme.accent}});
      slide.addShape(pptx.ShapeType.line,{x:0.7,y:1.6,w:11.93,h:0,line:{color:theme.border,width:0.7}});
    }
    if(s.comparison) {
      for(const heading of page.elements.filter(e=>e.role==='left_heading'||e.role==='right_heading')) {
        slide.addShape(pptx.ShapeType.line,{x:heading.x,y:heading.y+heading.h+0.12,w:heading.w,h:0,
          line:{color:theme.border,width:0.8}});
      }
    }
    for(const e of page.elements) {
      const box = {x:e.x,y:e.y,w:e.w,h:e.h};
      if(e.decoration_box) {
        if(e.decoration==='process-card') slide.addShape(pptx.ShapeType.roundRect,{...e.decoration_box,rectRadius:0.08,
          line:{color:theme.border,width:0.55},fill:{color:theme.pale}});
        if(e.decoration==='body-card') slide.addShape(pptx.ShapeType.rect,
          {x:e.decoration_box.x+0.15,y:e.y+0.06,w:0.045,h:Math.min(0.26,e.h),
            line:{color:theme.accent,transparency:100},fill:{color:theme.accent}});
        if(e.decoration==='process-card' && s.process && s.process.steps.length<=3) {
          slide.addText(String(e.step_index).padStart(2,'0'),{x:e.decoration_box.x+0.22,y:e.decoration_box.y+0.17,w:0.8,h:0.44,
            fontFace:FONT,fontSize:22,bold:true,color:theme.accent,margin:0});
        }
      }
      if(e.role==='takeaway') slide.addShape(pptx.ShapeType.line,
        {x:e.x-0.18,y:e.y,w:0,h:e.h,line:{color:theme.accent,width:2}});
      if(e.role.endsWith('_number')) slide.addShape(pptx.ShapeType.ellipse,
        {...box,line:{color:theme.accent,transparency:100},fill:{color:theme.accent}});
      if(e.text !== undefined) {
        const mainTitle=e.role==='title', footer=['footer','page'].includes(e.role), heading=e.role.endsWith('_heading');
        const takeaway=e.role==='takeaway', number=e.role.endsWith('_number');
        slide.addText(e.text,{...box,fontFace:FONT,fontSize:e.font_size,bold:mainTitle||heading||takeaway||number,
          color:number?'FFFFFF':footer?'667388':takeaway?theme.accent:mainTitle||heading?theme.title:theme.body,margin:0,breakLine:false,
          valign:mainTitle||number?'middle':'top',align:number?'center':e.role==='page'?'right':'left',
          ...(footer?{}:{lineSpacingMultiple:1.15,paraSpaceAfter:8})});
      } else if(e.connector_direction) {
        slide.addShape(pptx.ShapeType.line,{...box,
          line:{color:theme.accent,width:1.5,endArrowType:'triangle'}});
      } else if(e.role==='image' && s.image) {
        slide.addImage({...box,data:s.image.data,altText:`${s.title}；原图来源见讲者备注`});
      } else if(e.table) {
        slide.addTable(e.table.map((row,i)=>row.map(text=>({text,options:{bold:i===0,
          color:i===0?'FFFFFF':theme.body,fill:{color:i===0?theme.title:i%2===0?'FFFFFF':theme.pale}}}))),
          {...box,fontFace:FONT,fontSize:e.font_size,border:{pt:0.5,color:theme.border},margin:0.12,
            rowH:e.row_heights,colW:e.w/e.table[0].length,autoPage:false,valign:'middle'});
      } else if(e.chart) {
        const chart=e.chart;
        slide.addChart(chart.type==='bar'?pptx.ChartType.bar:pptx.ChartType.line,
          chart.series.map(series=>({name:series.name,labels:chart.categories,values:series.values})),
          {...box,catAxisLabelFontFace:FONT,catAxisLabelFontSize:18,valAxisLabelFontFace:FONT,valAxisLabelFontSize:18,
            legendFontFace:FONT,legendFontSize:18,legendPos:'b',showLegend:chart.series.length>1,
            catAxisTitle:chart.x_label,catAxisTitleFontFace:FONT,catAxisTitleFontSize:18,
            valAxisTitle:[chart.y_label,chart.unit].filter(Boolean).join(' / '),valAxisTitleFontFace:FONT,valAxisTitleFontSize:18,
            catAxisLineColor:theme.border,valAxisLineColor:theme.border,
            chartColors:[theme.accent,'496CA2','AA7235'],chartArea:{fill:{color:'FFFFFF'}},
            plotArea:{fill:{color:'FFFFFF'}},valGridLine:{color:theme.border,size:0.5},
            showValue:false,showTitle:false,barDir:'col',barGrouping:'clustered',
            lineSize:2,lineDataSymbol:'circle',lineDataSymbolSize:5,lineSmooth:false,
            altText:`${s.title}；原生可编辑数据图，数据来源见讲者备注`});
      }
    }
    slide.addNotes([s.notes ?? '', ...(s.takeaway?[`页面结论（必须核对来源支持）：${s.takeaway}`]:[]),
      '来源（必须核对内容与来源是否相符）：', ...s.sources].join('\n'));
  }
  await pptx.writeFile({fileName:output,compression:true});
  const manifestPath = /\.pptx$/i.test(output) ? output.replace(/\.pptx$/i,'.layout.json') : `${output}.layout.json`;
  writeFileSync(manifestPath,JSON.stringify(manifest,null,2),'utf8');
  return {slides:deck.slides.length,editable_text:true,template:manifest.template,layout_manifest:manifest,
    layout_manifest_path:manifestPath,layout_checks:manifest.checks,
    editable_table_count:deck.slides.filter(s=>s.table).length,editable_chart_count:deck.slides.filter(s=>s.chart).length,
    editable_process_count:deck.slides.filter(s=>s.process).length};
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const result = await render(JSON.parse(readFileSync(process.argv[2],'utf8')),process.argv[3]);
    console.log(JSON.stringify(result));
  } catch(error) {
    console.error(JSON.stringify({ok:false,error:error instanceof Error?error.message:String(error),
      code:error instanceof LayoutFailure?error.code:'invalid_plan_or_policy',
      page:error instanceof LayoutFailure?error.page:undefined,role:error instanceof LayoutFailure?error.role:undefined}));
    process.exitCode=1;
  }
}
