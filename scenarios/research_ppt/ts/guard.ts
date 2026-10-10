/** RSI 生成有限的准入程序；固定外层验证器不接受任意 JavaScript。 */
import { createHash } from 'node:crypto';

export type Facts = { format: string; page_count: number; text_chars: number };
export type Program = { schema_version: 1; formats: string[]; min_text_chars: number; max_pages: number };
export const baseProgram: Program = {schema_version: 1, formats: ['pdf', 'pptx'], min_text_chars: 1, max_pages: 200};
export function validateProgram(value: unknown): Program {
  const p = value as Program;
  if (!p || Object.keys(p).sort().join(',') !== 'formats,max_pages,min_text_chars,schema_version' ||
      p.schema_version !== 1 || !Array.isArray(p.formats) || p.formats.length < 1 || p.formats.length > 2 ||
      new Set(p.formats).size !== p.formats.length || p.formats.some(f => !['pdf','pptx'].includes(f)) ||
      !Number.isInteger(p.min_text_chars) || p.min_text_chars < 1 || p.min_text_chars > 1000 ||
      !Number.isInteger(p.max_pages) || p.max_pages < 1 || p.max_pages > 200) {
    throw new Error('准入程序必须使用固定 schema，且不能放宽外层边界');
  }
  return {schema_version: 1, formats: [...p.formats].sort(), min_text_chars: p.min_text_chars, max_pages: p.max_pages};
}
export function permits(program: Program, facts: Facts): boolean {
  return ['pdf','pptx'].includes(facts.format) && Number.isInteger(facts.page_count) &&
    facts.page_count >= 1 && facts.page_count <= 200 && Number.isInteger(facts.text_chars) &&
    facts.text_chars >= 1 && program.formats.includes(facts.format) &&
    facts.page_count <= program.max_pages && facts.text_chars >= program.min_text_chars;
}
export function certify(value: unknown) {
  const program = validateProgram(value);
  // 固定、独立于候选的协议用例；通过不代表科研内容质量合格。
  const cases = [
    {id:'short_pdf', facts:{format:'pdf', page_count:1, text_chars:24}, expected:true},
    {id:'paper', facts:{format:'pdf', page_count:18, text_chars:45000}, expected:true},
    {id:'slides', facts:{format:'pptx', page_count:30, text_chars:3500}, expected:true},
    {id:'scan', facts:{format:'pdf', page_count:12, text_chars:0}, expected:false},
    {id:'unknown', facts:{format:'exe', page_count:1, text_chars:100}, expected:false},
    {id:'oversize', facts:{format:'pdf', page_count:201, text_chars:1000}, expected:false},
    {id:'invalid_count', facts:{format:'pptx', page_count:-1, text_chars:100}, expected:false},
  ];
  const failures = cases.filter(c => permits(program,c.facts) !== c.expected);
  const digest = createHash('sha256').update(JSON.stringify(program)).digest('hex');
  return {program, program_digest:digest, accepted:failures.length === 0, failures, checks:cases.length,
    scope:'structural_guard_only', verifier_version:'ppt-guard-v1'};
}
