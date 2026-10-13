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
export type ScientificArchetype = 'evidence-focus' | 'result-summary' | 'method-map';
export type EvidenceNote = {label: string; text: string; source_index: number};
export type Slide = { title: string; bullets: string[]; sources: string[]; notes?: string; layout?: Layout;
  image?: {data: string; width: number; height: number}; table?: string[][]; chart?: Chart; comparison?: Comparison;
  process?: Process; takeaway?: string; archetype?: ScientificArchetype; evidence_notes?: EvidenceNote[];
  /** 仅接受服务从已绑定来源生成的展示文本；外部请求入口不得透传该字段。 */
  visible_sources?: string[] };
export type Deck = {title: string; slides: Slide[]; template?: Template; layout_policy?: LayoutPolicy};
type Box = {x: number; y: number; w: number; h: number};
export type LayoutElement = Box & { role: string; native_editable: boolean; font_size?: number;
  estimated_lines?: number; text?: string; row_heights?: number[]; column_widths?: number[]; table?: string[][]; chart?: Chart;
  body_gap?: number;
  decoration?: 'body-card' | 'process-card' | 'method-module'; decoration_box?: Box;
  connector_direction?: 'right' | 'down' | 'left'; step_index?: number };
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
  slides: {page: number; layout: Layout; archetype?: ScientificArchetype; source_count: number; elements: LayoutElement[]}[];
  checks: { bounds_passed: boolean; estimated_text_fit_passed: boolean; content_overlap_passed: boolean;
    min_body_font_size: number; semantic_quality_verified: false; pixel_render_verified: false } };

const WIDTH = 13.333333, HEIGHT = 7.5;
const FONT = 'Noto Sans CJK SC';
const BODY: Box = {x: 0.7, y: 1.75, w: 11.93, h: 4.99};
const THEMES = {
  academic: { title: '17345C', accent: '117D88', body: '243247', pale: 'F2F6FA', border: 'D7DFEA' },
  lab: { title: '17345C', accent: '5E6875', body: '282C33', pale: 'F3F4F5', border: 'D7DBE0' },
};
const layouts: Layout[] = ['title','content','image','table','chart','section','comparison','process'];
const scientificArchetypes: ScientificArchetype[] = ['evidence-focus','result-summary','method-map'];

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
    if (!object(s) || !onlyKeys(s,['title','bullets','sources','notes','layout','image','table','chart','comparison','process','takeaway',
        'archetype','evidence_notes','visible_sources']) ||
        !boundedText(s.title,70) || !validBullets(s.bullets) ||
        s.bullets.join('').length > (s.image || s.table || s.chart ? 220 : 500) ||
        !Array.isArray(s.sources) || !s.sources.length || s.sources.length > (s.visible_sources !== undefined ? 22 : 20) || s.sources.some(v => !boundedText(v,250)) ||
        (s.notes !== undefined && (typeof s.notes !== 'string' || s.notes.length > 6000 ||
          /[\x00-\x08\x0B\x0C\x0E-\x1F]/.test(s.notes)))) fail('超出文本容量或缺少合法来源，请修改计划');
    if (s.takeaway !== undefined && !boundedText(s.takeaway,90)) fail('takeaway 应是 1–90 字符的短结论，必须由调用者核对来源');
    if (s.archetype !== undefined && !scientificArchetypes.includes(s.archetype)) fail('不支持的科研 archetype');
    if (s.evidence_notes !== undefined && (!s.archetype || !Array.isArray(s.evidence_notes) ||
        s.evidence_notes.length > 3 || s.evidence_notes.some(note => !object(note) ||
          !onlyKeys(note,['label','text','source_index']) || !boundedText(note.label,24) || !boundedText(note.text,110) ||
          !Number.isInteger(note.source_index) || note.source_index < 1 ||
          note.source_index > (s.visible_sources?.length ?? s.sources.length)))) {
      fail('evidence_notes 仅用于科研 archetype，最多3项 label/text 说明，source_index 必须指向本页来源');
    }
    if (s.visible_sources !== undefined && (!s.archetype || !Array.isArray(s.visible_sources) || s.visible_sources.length < 1 ||
        s.visible_sources.length > 20 || s.visible_sources.length > s.sources.length ||
        s.visible_sources.some(source => !boundedText(source,250)))) fail('visible_sources 必须与原引用逐项对应，且仅由服务生成');
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
        s.layout !== 'process' || (s.bullets.length && s.archetype !== 'method-map'))) {
      fail('process 需要 layout=process、2–5 个短 label/detail 步骤；只有 method-map 可带页级说明');
    }
    const layout = inferredLayout(s);
    if ((layout === 'image' && !s.image) || (layout === 'table' && !s.table) ||
        (layout === 'chart' && !s.chart) || (layout === 'comparison' && !s.comparison) || (layout === 'process' && !s.process) ||
        (['title','section','content'].includes(layout) && mediaCount)) fail('layout 与页面内容类型不一致');
    if ((s.archetype === 'evidence-focus' && layout !== 'image') ||
        (s.archetype === 'result-summary' && !['table','chart'].includes(layout)) ||
        (s.archetype === 'method-map' && layout !== 'process')) fail('科研 archetype 必须对应原图、结果表/图或方法流程主体');
    if (['title','section'].includes(layout) && s.bullets.length > 4) fail('封面/章节页最多 4 条短句');
  }
}

function textUnits(text: string) {
  return Array.from(text).reduce((n,c) => n + (c.charCodeAt(0)>255 ? 1 : 0.56),0);
}
/** 保守估算完整拉丁词的换行；列宽优先留出术语空间，不改写原文。 */
function lines(text: string, width: number, fontSize: number) {
  const capacity = Math.max(1, (width * 72 / fontSize) * 0.88);
  return text.split('\n').reduce((sum,line) => {
    let count=1, occupied=0;
    // 中文允许逐字换行；常见英文术语、数值和公式片段作为完整 token。
    const tokens=line.match(/[A-Za-z0-9_]+(?:[-./^][A-Za-z0-9_]+)*|\s+|[^A-Za-z0-9_\s]/gu)??[];
    for(const token of tokens) {
      const width=textUnits(token);
      if(occupied+width>capacity+1e-8 && occupied>0) { count++; occupied=0; }
      if(width>capacity) {
        // 无法容纳的完整词仍保守计行，不能通过估算把超长词隐藏。
        count+=Math.ceil(width/capacity)-1; occupied=width%capacity || capacity;
      } else occupied+=width;
    }
    return sum+count;
  },0);
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
    const textWidth = box.w - 0.32;
    const textHeight = lines(bullet,textWidth,fontSize) * fontSize / 72 * 1.28 + 0.06;
    const itemHeight = Math.max(0.50,textHeight+0.10);
    if (y+itemHeight > box.y+box.h+0.01) throw new LayoutFailure('text_overflow','正文文本溢出，请缩短或分成两页',undefined,prefix);
    const e = textElement(`${prefix}_${index+1}`,bullet,{x:box.x+0.32,y:y+0.04,w:textWidth,h:textHeight},fontSize);
    elements.push({...e,decoration:'body-card',decoration_box:{x:box.x,y,w:box.w,h:itemHeight}});
    y += itemHeight + gap;
  }
}
function bulletHeight(bullets: string[], width: number, policy: LayoutPolicy) {
  return bullets.reduce((height,text) => height+Math.max(0.50,
    lines(text,width-0.32,policy.body_font_size)*policy.body_font_size/72*1.28+0.16),0)+
    Math.max(0,bullets.length-1)*policy.body_gap;
}
function tableGeometry(table: string[][], width: number, fontSize: number) {
  const padding=0.28, count=table[0].length;
  const demands=Array.from({length:count},(_,c)=>Math.max(...table.map(row=>textUnits(row[c]))));
  const wordWidths=Array.from({length:count},(_,c)=>Math.max(0,...table.flatMap(row=>
    (row[c].match(/[A-Za-z0-9_]+(?:[-./^][A-Za-z0-9_]+)*/g)??[]).map(textUnits))));
  const minimums=wordWidths.map(units=>Math.max(0.86,padding+units*fontSize/72/0.88+0.05));
  if(minimums.reduce((sum,w)=>sum+w,0)>width+0.01) {
    throw new LayoutFailure('table_overflow','表格完整术语无法容纳，请使用更宽版式或减少列数；不会拆词、删内容或缩小字号',undefined,'table');
  }
  // 长方法名称需要更宽的列，纯数值列只占必要空间；不再强制等宽。
  const desired=demands.map((units,c)=>Math.max(minimums[c],Math.min(width*0.45,padding+units*fontSize/72/0.88)));
  const minTotal=minimums.reduce((sum,w)=>sum+w,0), desiredTotal=desired.reduce((sum,w)=>sum+w,0);
  const ratio=desiredTotal>minTotal?Math.min(1,(width-minTotal)/(desiredTotal-minTotal)):0;
  const columns=minimums.map((w,c)=>w+(desired[c]-w)*ratio);
  const remainder=(width-columns.reduce((sum,w)=>sum+w,0))/count;
  const columnWidths=columns.map(w=>w+remainder);
  const rowHeights=table.map(row=>Math.max(0.58,...row.map((text,c)=>
    lines(text,columnWidths[c]-padding,fontSize)*fontSize/72*1.35+0.22)));
  return {columnWidths,rowHeights,height:rowHeights.reduce((a,b)=>a+b,0)};
}
function mediaBoxes(s: Slide, body: Box, policy: LayoutPolicy, explicitPolicy: boolean) {
  const style={copy_font_size:policy.body_font_size,copy_gap:policy.body_gap};
  if(!s.bullets.length) return {media:{...body},copy:undefined,...style};
  const gap=0.34;
  const right=(fraction: number)=>{
    const media={...body,w:(body.w-gap)*fraction};
    const copy={...body,w:body.w-gap-media.w}; media.x=body.x+copy.w+gap;
    return {media,copy};
  };
  const bottom=(copyHeight: number)=>({media:{...body,y:body.y+copyHeight+gap,h:body.h-copyHeight-gap},
    copy:{...body,h:copyHeight}});
  if(explicitPolicy) return {...(policy.media_position==='right'?right(policy.media_fraction):
    bottom((body.h-gap)*(1-policy.media_fraction))),...style};
  // 普通确定性适配：同一事实完整保留，选可容纳正文且证据可见面积最大的布局。
  // 显式的认证策略仍由调用者控制，不在此覆盖其几何选择。
  const choose=(copyPolicy: LayoutPolicy)=>{
    const candidates=[right(0.58),right(0.64),right(0.72),
      bottom(bulletHeight(s.bullets,body.w,copyPolicy))];
    let boxes: ReturnType<typeof right>|undefined, score=-Infinity;
    for(const candidate of candidates) {
      try {
        if(candidate.media.h<0.6 || candidate.copy.w<0.8) continue;
        addBullets([],s.bullets,candidate.copy,copyPolicy.body_font_size,'body',copyPolicy.body_gap);
        let value=candidate.media.w;
        if(s.image) {
          const scale=Math.min(candidate.media.w/s.image.width,candidate.media.h/s.image.height);
          value=s.image.width*s.image.height*scale*scale;
        } else if(s.table) {
          if(tableGeometry(s.table,candidate.media.w,policy.table_font_size).height>candidate.media.h+0.01) continue;
        }
        if(value>score) {boxes=candidate;score=value;}
      } catch(error) {if(!(error instanceof LayoutFailure)) throw error;}
    }
    return {boxes,score,copy_font_size:copyPolicy.body_font_size,copy_gap:copyPolicy.body_gap};
  };
  let best=choose(policy);
  if(s.image && policy.body_font_size>20) {
    const compact=choose({...policy,body_font_size:20,body_gap:0.08});
    // 逐页保留更大的正文；仅明显改善证据面积时采用可读下限，绝不低于20pt。
    if(compact.boxes && (!best.boxes || compact.score>=best.score*1.25)) best=compact;
  }
  const selected=best.boxes;
  if(!selected && s.table) throw new LayoutFailure('table_overflow','表格文本溢出，或表格与正文无法同时容纳，请分成多页；不会删改内容',undefined,'table');
  if(!selected) throw new LayoutFailure('text_overflow','正文与证据无法同时容纳，请分成多页；不会删改内容',undefined,'body');
  return {...selected,copy_font_size:best.copy_font_size,copy_gap:best.copy_gap};
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
        {x:card.x+0.22,y:card.y+0.82,w:width-0.44,h:labelHeight},24);
      elements.push({...heading,decoration:'process-card',decoration_box:card,step_index:i+1});
      const detailY=heading.y+labelHeight+0.28;
      elements.push(textElement(`process_${i+1}_detail`,step.detail,
        {x:card.x+0.22,y:detailY,w:width-0.44,h:card.y+card.h-detailY-0.24},policy.body_font_size));
      if(i<count-1) elements.push({role:`process_connector_${i+1}`,x:card.x+card.w+0.06,y:card.y+card.h/2,
        w:gap-0.12,h:0.015,native_editable:true,connector_direction:'right'});
    }
  } else {
    const gap=0.08, rowHeight=(box.h-gap*(count-1))/count;
    const labelWidth=Math.max(2.1,Math.min(3.4,Math.max(...process.steps.map(step=>
      textUnits(step.label)))*policy.body_font_size/72/0.88));
    for(const [i,step] of process.steps.entries()) {
      const y=box.y+i*(rowHeight+gap), card={x:box.x+0.76,y,w:box.w-0.76,h:rowHeight};
      elements.push({...textElement(`process_${i+1}_heading`,step.label,
        {x:card.x+0.2,y:y+0.05,w:labelWidth,h:rowHeight-0.1},policy.body_font_size),
        decoration:'process-card',decoration_box:card,step_index:i+1});
      elements.push(textElement(`process_${i+1}_detail`,step.detail,
        {x:card.x+labelWidth+0.46,y:y+0.05,w:card.w-labelWidth-0.68,h:rowHeight-0.1},policy.body_font_size));
      const numberY=y+(rowHeight-0.44)/2;
      elements.push({...textElement(`process_${i+1}_number`,String(i+1),
        {x:box.x+0.02,y:numberY,w:0.44,h:0.44},20),step_index:i+1});
      if(i<count-1) elements.push({role:`process_connector_${i+1}`,x:box.x+0.235,y:numberY+0.48,
        w:0.015,h:rowHeight+gap-0.52,native_editable:true,connector_direction:'down'});
    }
  }
}

type ScientificBlock = {role: string; text: string; label?: string};
const SCIENTIFIC_BODY_SIZE = 20;
const SCIENTIFIC_LABEL_SIZE = 16;
/** 新页的混排术语留额外换行余量；旧lines/旧版式完全保持。 */
function scientificLines(text: string, width: number, fontSize: number) {
  return lines(text,width*(/[A-Za-z]/.test(text)?0.80:0.94),fontSize);
}
function scientificTextElement(role: string, text: string, box: Box, fontSize: number): LayoutElement {
  const estimated=scientificLines(text,box.w,fontSize);
  if(estimated*fontSize/72*1.28+0.05>box.h+0.01) throw new LayoutFailure('text_overflow',
    `${role} 完整文本超出科研页容量，请拆页；不会删改条件或缩小正文`,undefined,role);
  return {...box,role,text,font_size:fontSize,estimated_lines:estimated,native_editable:true};
}
function scientificBlocks(s: Slide): ScientificBlock[] {
  return [
    ...s.bullets.map((text,i)=>({role:`body_${i+1}`,text})),
    ...(s.evidence_notes ?? []).map((note,i)=>({role:`evidence_note_${i+1}`,text:note.text,
      label:`${note.label} [${note.source_index}]`})),
  ];
}
function scientificBlockHeight(block: ScientificBlock, width: number) {
  const label=block.label===undefined?0:scientificLines(block.label,width,SCIENTIFIC_LABEL_SIZE)*
    SCIENTIFIC_LABEL_SIZE/72*1.28+0.13;
  return label+scientificLines(block.text,width,SCIENTIFIC_BODY_SIZE)*SCIENTIFIC_BODY_SIZE/72*1.28+0.08;
}
/** 保留每个原句，不猜测条件标签；按行优先放置短条件/有来源的说明。 */
function scientificCopy(elements: LayoutElement[], blocks: ScientificBlock[], box: Box, columns: number) {
  if(!blocks.length) return 0;
  const gap=0.34, width=(box.w-gap*(columns-1))/columns;
  let y=box.y;
  for(let offset=0;offset<blocks.length;offset+=columns) {
    const row=blocks.slice(offset,offset+columns);
    const height=Math.max(...row.map(block=>scientificBlockHeight(block,width)));
    if(y+height>box.y+box.h+0.01) throw new LayoutFailure('text_overflow',
      '科研证据说明无法完整容纳；请明确分成多页，不会自动删改条件或缩小正文',undefined,'body');
    for(const [c,block] of row.entries()) {
      let textY=y;
      const x=box.x+c*(width+gap);
      if(block.label!==undefined) {
        const h=scientificLines(block.label,width,SCIENTIFIC_LABEL_SIZE)*SCIENTIFIC_LABEL_SIZE/72*1.28+0.06;
        elements.push(scientificTextElement(`${block.role}_heading`,block.label,{x,y:textY,w:width,h},SCIENTIFIC_LABEL_SIZE));
        textY+=h+0.07;
      }
      const h=scientificLines(block.text,width,SCIENTIFIC_BODY_SIZE)*SCIENTIFIC_BODY_SIZE/72*1.28+0.08;
      elements.push(scientificTextElement(block.role,block.text,{x,y:textY,w:width,h},SCIENTIFIC_BODY_SIZE));
    }
    y+=height+0.12;
  }
  return y-box.y-0.12;
}
function scientificGridHeight(blocks: ScientificBlock[], width: number, columns: number) {
  const columnWidth=(width-0.34*(columns-1))/columns;
  let height=0;
  for(let offset=0;offset<blocks.length;offset+=columns) {
    height+=Math.max(...blocks.slice(offset,offset+columns).map(block=>scientificBlockHeight(block,columnWidth)))+
      (offset?0.12:0);
  }
  return height;
}
function addScientificMedia(elements: LayoutElement[], s: Slide, media: Box) {
  if(s.image) {
    const scale=Math.min(media.w/s.image.width,media.h/s.image.height);
    const w=s.image.width*scale,h=s.image.height*scale;
    elements.push({role:'image',x:media.x+(media.w-w)/2,y:media.y+(media.h-h)/2,w,h,native_editable:false});
    return w*h;
  }
  if(s.table) {
    const {columnWidths,rowHeights,height:h}=tableGeometry(s.table,media.w,20);
    if(h>media.h+0.01) throw new LayoutFailure('table_overflow',
      '科研结果表无法完整容纳；请分成多页，不会删除实验行列',undefined,'table');
    elements.push({...media,y:media.y+(media.h-h)/2,h,role:'table',native_editable:true,
      font_size:20,row_heights:rowHeights,column_widths:columnWidths,table:s.table});
    return media.w*h;
  }
  if(s.chart) {
    const maxLabelWidth=(media.w-1.2)/s.chart.categories.length;
    if(media.w<4.2 || media.h<2.0 || s.chart.categories.some(v=>scientificLines(v,maxLabelWidth,18)>2)) {
      throw new LayoutFailure('chart_label_overflow',
        '科研结果图的分类标签或坐标轴无法完整容纳；请拆页，不会改动数据',undefined,'chart');
    }
    elements.push({...media,role:'chart',native_editable:true,font_size:18,chart:s.chart});
    return media.w*media.h;
  }
  throw new Error('科研证据页缺少原图、表格或数据图');
}
function scientificEvidence(elements: LayoutElement[], s: Slide, body: Box) {
  const blocks=scientificBlocks(s);
  if(!blocks.length) {addScientificMedia(elements,s,body);return;}
  // 窄工程守卫：说明不能把证据主体挤成缩略图；不是完整可读性或科学认证。
  const fullImageScale=s.archetype==='evidence-focus' && s.image?
    Math.min(body.w/s.image.width,body.h/s.image.height):0;
  const minimumImageArea=s.archetype==='evidence-focus' && s.image?
    Math.min(10,s.image.width*s.image.height*fullImageScale*fullImageScale*0.5):0;
  const candidates: {media: Box; copy: Box; columns: number}[]=[];
  // 横向原图优先完整宽面板；说明只占实际需要的高度，不生成装饰卡片。
  for(const columns of [1,2,3]) {
    if(columns>blocks.length) continue;
    const h=scientificGridHeight(blocks,body.w,columns);
    candidates.push({media:{...body,h:body.h-h-0.20},copy:{...body,y:body.y+body.h-h,h},columns});
  }
  for(const width of [3.15,3.65,4.1]) {
    candidates.push({media:{...body,w:body.w-width-0.45},
      copy:{...body,x:body.x+body.w-width,w:width},columns:1});
  }
  let selected: LayoutElement[]|undefined, bestScore=-Infinity;
  let failure: LayoutFailure|undefined;
  let imageTooSmall=false;
  for(const candidate of candidates) {
    if(candidate.media.h<0.8 || candidate.media.w<2) continue;
    try {
      const proposed: LayoutElement[]=[];
      const area=addScientificMedia(proposed,s,candidate.media);
      scientificCopy(proposed,blocks,candidate.copy,candidate.columns);
      if(area+1e-8<minimumImageArea) {imageTooSmall=true;continue;}
      // 只比较完整证据的可见面积；表格/图表仍保持原生数据和全部文字。
      if(area>bestScore) {selected=proposed;bestScore=area;}
    } catch(error) {
      if(!(error instanceof LayoutFailure)) throw error;
      failure=error;
    }
  }
  if(!selected && imageTooSmall) throw new LayoutFailure('text_overflow',
    '证据图面积过小；请减少重复说明并保留事实，或拆分页面。不会缩小正文、删改条件或裁切原图',undefined,'image');
  if(!selected) throw failure ?? new LayoutFailure('text_overflow',
    '主体证据与完整条件无法同时容纳，请分成多页',undefined,'body');
  // Manifest按原语义顺序记录文字，PPTX视觉位置由完整box独立决定。
  const copyOrder=new Map(blocks.flatMap((block,i)=>[[block.role,i*2+1] as const,[`${block.role}_heading`,i*2] as const]));
  selected.sort((a,b)=>(copyOrder.get(a.role)??-1)-(copyOrder.get(b.role)??-1));
  elements.push(...selected);
}
/** 流程顺序来自输入steps；4/5节点使用蛇形两层以保留方向，不臆造分支。 */
function addScientificProcess(elements: LayoutElement[], process: Process, box: Box) {
  const count=process.steps.length, columns=count<=3?count:count===4?2:3;
  const rows=Math.ceil(count/columns), gapX=0.44, gapY=0.48;
  const width=(box.w-gapX*(columns-1))/columns;
  const headingSize=rows>1?20:22, headingWidth=width-(rows>1?0.98:0.44);
  const headingHeights=process.steps.map(step=>scientificLines(step.label,headingWidth,headingSize)*headingSize/72*1.28+0.08);
  const detailHeights=process.steps.map(step=>scientificLines(step.detail,width-0.44,20)*20/72*1.28+0.08);
  const moduleHeights=process.steps.map((_,i)=>Math.max(rows>1?1.5:2.0,
    (rows>1?0.18:0.62)+headingHeights[i]+0.18+detailHeights[i]+0.18));
  const rowHeights=Array.from({length:rows},(_,r)=>Math.max(...moduleHeights.slice(r*columns,(r+1)*columns)));
  const fullHeight=rowHeights.reduce((sum,h)=>sum+h,0)+gapY*(rows-1);
  if(fullHeight>box.h+0.01) throw new LayoutFailure('text_overflow',
    '方法模块的完整标签与解释无法容纳，请拆页，不会删改机制描述',undefined,'process');
  const top=box.y+(box.h-fullHeight)/2;
  const cards: Box[]=[];
  for(const [i,step] of process.steps.entries()) {
    const row=Math.floor(i/columns), offset=i%columns, column=row%2?columns-1-offset:offset;
    const rowY=top+rowHeights.slice(0,row).reduce((sum,h)=>sum+h,0)+row*gapY;
    const card={x:box.x+column*(width+gapX),y:rowY,w:width,h:rowHeights[row]};
    cards.push(card);
    const number=scientificTextElement(`process_${i+1}_number`,String(i+1).padStart(2,'0'),
      {x:card.x+0.22,y:card.y+0.18,w:0.48,h:0.34},14);
    const headingH=headingHeights[i];
    const heading=scientificTextElement(`process_${i+1}_heading`,step.label,
      {x:card.x+(rows>1?0.76:0.22),y:card.y+(rows>1?0.18:0.62),w:headingWidth,h:headingH},headingSize);
    elements.push({...heading,decoration:'method-module',decoration_box:card,step_index:i+1});
    elements.push({...number,step_index:i+1});
    const detailY=heading.y+headingH+0.18;
    elements.push(scientificTextElement(`process_${i+1}_detail`,step.detail,
      {x:card.x+0.22,y:detailY,w:width-0.44,h:detailHeights[i]},20));
  }
  for(let i=0;i<cards.length-1;i++) {
    const from=cards[i], to=cards[i+1];
    if(to.y>from.y+0.01) {
      elements.push({role:`process_connector_${i+1}`,x:from.x+from.w/2,y:from.y+from.h+0.07,
        w:0.015,h:gapY-0.14,native_editable:true,connector_direction:'down'});
    } else {
      const right=to.x>from.x;
      elements.push({role:`process_connector_${i+1}`,x:(right?from:to).x+width+0.06,y:from.y+from.h/2,
        w:gapX-0.12,h:0.015,native_editable:true,connector_direction:right?'right':'left'});
    }
  }
}
function scientificMethod(elements: LayoutElement[], s: Slide, body: Box) {
  const blocks=scientificBlocks(s);
  if(!blocks.length) {addScientificProcess(elements,s.process!,body);return;}
  let failure: LayoutFailure|undefined;
  for(const columns of [Math.min(3,blocks.length),Math.min(2,blocks.length),1]) {
    const h=scientificGridHeight(blocks,body.w,columns);
    const proposed: LayoutElement[]=[];
    try {
      const media={...body,h:body.h-h-0.20};
      if(media.h<1.5) continue;
      addScientificProcess(proposed,s.process!,media);
      scientificCopy(proposed,blocks,{...body,y:body.y+body.h-h,h},columns);
      elements.push(...proposed);return;
    } catch(error) {if(!(error instanceof LayoutFailure)) throw error;failure=error;}
  }
  throw failure ?? new LayoutFailure('text_overflow','方法模块与全部说明无法同时容纳，请拆页',undefined,'process');
}
/** 三类科研页型独立于旧布局策略；不改变任何未opt-in页面的元素或样式。 */
function addScientificSlide(elements: LayoutElement[], s: Slide, page: number, count: number, template: Template) {
  const label={'evidence-focus':'EVIDENCE','result-summary':'RESULTS','method-map':'METHOD'}[s.archetype!];
  if(template!=='lab') elements.push(scientificTextElement('scientific_label',label,{x:0.7,y:0.13,w:10.5,h:0.28},11));
  const titleH=scientificLines(s.title,11.93,28)*28/72*1.28+0.07;
  if(titleH>1.1) throw new LayoutFailure('text_overflow','科研标题超过两行，请明确缩短标题',undefined,'title');
  elements.push(scientificTextElement('title',s.title,{x:0.7,y:0.43,w:11.93,h:titleH},28));
  let y=Math.max(1.18,0.43+titleH+0.15);
  if(s.takeaway) {
    const h=scientificLines(s.takeaway,11.93,20)*20/72*1.28+0.08;
    elements.push(scientificTextElement('takeaway',s.takeaway,{x:0.7,y,w:11.93,h},20));
    y+=h+0.20;
  }
  const visible=s.visible_sources?.join('  ·  ') ??
    `${s.sources.map((_,i)=>`[${i+1}]`).join(' ')} 完整来源见讲者备注`;
  const footerH=scientificLines(visible,11.04,10)*10/72*1.28+0.07;
  if(footerH>0.85) throw new LayoutFailure('text_overflow','可见来源超过页脚容量，请分开引用来源，不会截断来源',undefined,'footer');
  const footerY=7.14-footerH;
  const body={x:0.7,y,w:11.93,h:footerY-0.22-y};
  if(body.h<1.3) throw new LayoutFailure('text_overflow','标题、结论和来源占用过多空间，请拆页',undefined,'body');
  if(s.archetype==='method-map') scientificMethod(elements,s,body);
  else scientificEvidence(elements,s,body);
  elements.push(scientificTextElement('footer',visible,{x:0.7,y:footerY,w:11.04,h:footerH},10));
  elements.push(scientificTextElement('page',`${page} / ${count}`,{x:11.84,y:footerY,w:0.79,h:0.3},11));
}
function canonical(value: unknown): unknown {
  if(Array.isArray(value)) return value.map(canonical);
  if(object(value)) return Object.fromEntries(Object.keys(value).sort().filter(k=>value[k]!==undefined).map(k=>[k,canonical(value[k])]));
  return value;
}
/** 只核对结构是否保留输入内容；不能证明事实正确或图注/结论忠实。 */
export function semanticContentHash(deck: Deck): string {
  const content={title:deck.title,slides:deck.slides.map(({layout:_layout,archetype:_archetype,visible_sources:_visible,...slide})=>slide)};
  return createHash('sha256').update(JSON.stringify(canonical(content)),'utf8').digest('hex');
}
export function buildLayout(deck: Deck): LayoutManifest {
  validateDeck(deck);
  const policy = validatePolicy(deck.layout_policy ?? defaultPolicy);
  const pages: LayoutManifest['slides'] = deck.slides.map((s,index) => {
    const layout = inferredLayout(s), elements: LayoutElement[] = [];
    const add = (role: string, text: string, box: Box, fontSize: number) => elements.push(textElement(role,text,box,fontSize));
    try {
      if(s.archetype) {
        addScientificSlide(elements,s,index+1,deck.slides.length,deck.template??'academic');
      } else if (layout === 'title' || layout === 'section') {
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
          const {media,copy,copy_font_size,copy_gap}=mediaBoxes(s,body,policy,deck.layout_policy!==undefined);
          if(copy) {
            const start=elements.length;
            addBullets(elements,s.bullets,copy,copy_font_size,'body',copy_gap);
            if(s.image) for(const element of elements.slice(start)) element.body_gap=copy_gap;
          }
          if (s.image) {
            const scale = Math.min(media.w/s.image.width,media.h/s.image.height);
            const w=s.image.width*scale,h=s.image.height*scale;
            elements.push({role:'image',x:media.x+(media.w-w)/2,y:media.y+(media.h-h)/2,w,h,native_editable:false});
          }
          if (s.table) {
            const fs=policy.table_font_size;
            const {columnWidths,rowHeights,height:h}=tableGeometry(s.table,media.w,fs);
            if(h>media.h+0.01) throw new LayoutFailure('table_overflow','表格文本溢出，请缩短单元格或分成多页',undefined,'table');
            elements.push({...media,y:media.y+Math.min(0.28,(media.h-h)/2),h,role:'table',native_editable:true,
              font_size:fs,row_heights:rowHeights,column_widths:columnWidths,table:s.table});
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
      if(!s.archetype) {
        add('footer','来源见讲者备注',{x:0.7,y:7.06,w:4.0,h:0.24},10);
        add('page',`${index+1} / ${deck.slides.length}`,{x:11.7,y:7.02,w:0.93,h:0.3},12);
      }
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
    return {page:index+1,layout,...(s.archetype?{archetype:s.archetype}:{}),source_count:s.sources.length,elements};
  });
  const bodySizes=pages.flatMap(s=>s.elements.filter(e=>e.font_size && !['title','footer','page','scientific_label'].includes(e.role) &&
    (!s.archetype || (!e.role.endsWith('_number') && !(e.role.startsWith('evidence_note_') && e.role.endsWith('_heading'))))).map(e=>e.font_size!));
  return {schema_version:1,renderer_version:deck.template==='lab'?'research-ppt-layout-v15-lab.1':'research-ppt-layout-v11.2',template:deck.template??'academic',width:WIDTH,height:HEIGHT,
    font_face:FONT,deck_sha256:createHash('sha256').update(JSON.stringify(deck)).digest('hex'),slides:pages,
    layout_policy:policy,layout_policy_sha256:policyHash(policy),semantic_content_sha256:semanticContentHash(deck),diagnostics:[],
    checks:{bounds_passed:true,estimated_text_fit_passed:true,content_overlap_passed:true,
      min_body_font_size:bodySizes.length?Math.min(...bodySizes):18,semantic_quality_verified:false,pixel_render_verified:false}};
}

export async function render(deck: Deck, output: string) {
  const manifest = buildLayout(deck), theme = THEMES[manifest.template];
  const plainLab = manifest.template==='lab';
  const pptx = new pptxgen();
  pptx.layout = 'LAYOUT_WIDE'; pptx.author = 'SSS Research PPT'; pptx.subject = 'Research presentation';
  pptx.title = deck.title;
  pptx.theme = {headFontFace:FONT,bodyFontFace:FONT};
  for (const [index,s] of deck.slides.entries()) {
    const page = manifest.slides[index], slide = pptx.addSlide();
    slide.background = {color:'FFFFFF'};
    if(s.archetype || plainLab) {
      // 不使用默认粗分隔线/卡片；版面由证据、条件与克制的字体层次组成。
    } else if(page.layout==='title' || page.layout==='section') {
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
        if(e.decoration==='method-module') slide.addShape(pptx.ShapeType.rect,
          {...e.decoration_box,line:{color:'DBE2EB',width:0.7},fill:{color:'FFFFFF'}});
        if(e.decoration==='process-card') {
          const card=e.decoration_box;
          if(s.process && s.process.steps.length<=3) {
            slide.addShape(pptx.ShapeType.line,{x:card.x+0.22,y:card.y+0.64,w:card.w-0.44,h:0,
              line:{color:theme.border,width:1}});
          } else {
            slide.addShape(pptx.ShapeType.line,{x:card.x+0.2,y:card.y+card.h,w:card.w-0.4,h:0,
              line:{color:theme.border,width:0.7}});
          }
        }
        if(e.decoration==='body-card') slide.addShape(pptx.ShapeType.rect,
          {x:e.decoration_box.x+0.03,y:e.y+0.14,w:0.08,h:0.08,
            line:{color:theme.accent,transparency:100},fill:{color:theme.accent}});
        if(e.decoration==='process-card' && s.process && s.process.steps.length<=3) {
          slide.addText(String(e.step_index).padStart(2,'0'),{x:e.decoration_box.x+0.22,y:e.decoration_box.y+0.17,w:0.8,h:0.44,
            fontFace:FONT,fontSize:22,bold:true,color:theme.accent,margin:0});
        }
      }
      if(e.role==='takeaway' && !s.archetype && !plainLab) slide.addShape(pptx.ShapeType.line,
        {x:e.x-0.18,y:e.y,w:0,h:e.h,line:{color:theme.accent,width:2}});
      if(e.role.endsWith('_number') && !s.archetype && !plainLab) slide.addShape(pptx.ShapeType.ellipse,
        {...box,line:{color:theme.accent,transparency:100},fill:{color:theme.accent}});
      if(e.text !== undefined) {
        const mainTitle=e.role==='title', footer=['footer','page'].includes(e.role), heading=e.role.endsWith('_heading');
        const takeaway=e.role==='takeaway', number=e.role.endsWith('_number');
        slide.addText(e.text,{...box,fontFace:FONT,fontSize:e.font_size,bold:mainTitle||heading||takeaway||number,
          color:plainLab?(footer?'667388':mainTitle||heading?theme.title:theme.body):
            s.archetype?(footer?'667388':number||e.role==='scientific_label'?'6B7F99':mainTitle||heading?'17345C':'26344A'):
            number?'FFFFFF':footer?'667388':takeaway?theme.accent:mainTitle||heading?theme.title:theme.body,margin:0,breakLine:false,
          valign:mainTitle||number?'middle':'top',align:number&&!s.archetype?'center':e.role==='page'?'right':'left',
          ...(footer?{}:{lineSpacingMultiple:1.15,paraSpaceAfter:8})});
      } else if(e.connector_direction) {
        slide.addShape(pptx.ShapeType.line,{...box,
          line:{color:s.archetype?'8699AE':theme.accent,width:s.archetype?1:1.5,
            ...(e.connector_direction==='left'?{beginArrowType:'triangle' as const}:{endArrowType:'triangle' as const})}});
      } else if(e.role==='image' && s.image) {
        slide.addImage({...box,data:s.image.data,altText:`${s.title}；原图来源见讲者备注`});
      } else if(e.table) {
        slide.addTable(e.table.map((row,i)=>row.map(text=>({text,options:{bold:i===0,
          color:i===0?theme.title:theme.body,fill:{color:s.archetype?(i===0?'EEF3F8':'FFFFFF'):
            i===0?theme.pale:i%2===0?'FFFFFF':'FAFBFD'}}}))),
          {...box,fontFace:FONT,fontSize:e.font_size,border:{pt:s.archetype?0.35:0.5,color:theme.border},margin:0.12,
            rowH:e.row_heights,colW:e.column_widths,autoPage:false,valign:'middle'});
      } else if(e.chart) {
        const chart=e.chart;
        slide.addChart(chart.type==='bar'?pptx.ChartType.bar:pptx.ChartType.line,
          chart.series.map(series=>({name:series.name,labels:chart.categories,values:series.values})),
          {...box,catAxisLabelFontFace:FONT,catAxisLabelFontSize:18,valAxisLabelFontFace:FONT,valAxisLabelFontSize:18,
            legendFontFace:FONT,legendFontSize:18,legendPos:'b',showLegend:chart.series.length>1,
            catAxisTitle:chart.x_label,showCatAxisTitle:!!chart.x_label,
            catAxisTitleFontFace:FONT,catAxisTitleFontSize:18,
            valAxisTitle:[chart.y_label,chart.unit].filter(Boolean).join(' / '),
            showValAxisTitle:!!(chart.y_label || chart.unit),valAxisTitleFontFace:FONT,valAxisTitleFontSize:18,
            catAxisLineColor:theme.border,valAxisLineColor:theme.border,
            chartColors:plainLab?['315B89','667388','ADB9C8']:s.archetype?['315B89','7594B5','ADB9C8']:[theme.accent,'496CA2','AA7235'],chartArea:{fill:{color:'FFFFFF'}},
            plotArea:{fill:{color:'FFFFFF'}},valGridLine:{color:theme.border,size:0.5},
            showValue:false,showTitle:false,barDir:'col',barGrouping:'clustered',
            lineSize:2,lineDataSymbol:'circle',lineDataSymbolSize:5,lineSmooth:false,
            altText:`${s.title}；原生可编辑数据图，数据来源见讲者备注`});
      }
    }
    slide.addNotes([s.notes ?? '', ...(s.takeaway?[`页面结论（必须核对来源支持）：${s.takeaway}`]:[]),
      ...(s.evidence_notes??[]).map(note=>`证据说明 [${note.source_index}] ${note.label}：${note.text}`),
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
