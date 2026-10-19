/** Account-local, extractive conversation names. No auxiliary model call or budget bypass. */
import { mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { publicText } from './harless_public_output.ts';

type Snapshot = { meta: any; events: any[] };
type Host = {
  inspect(id: string): Promise<Snapshot>;
  siblings(id: string): string[];
  rename(id: string, title: string): Promise<any>;
  humanContentFor?(id: string, event: any): any[];
};
const clean = (text: string) => publicText(text).replace(/\/[a-z-]+(?=\s|$)/gi, ' ')
  .replace(/https?:\/\/\S+/g, '').replace(/[\x00-\x1f`*_#<>]/g, ' ').replace(/\s+/g, ' ').trim();
export function conversationTitle(snapshot: Snapshot): string {
  return snapshot.events.findLast(row => row.type === 'session/title')?.data?.title ?? snapshot.meta?.title ?? '';
}

/** Extract the first substantive topic, so a greeting does not freeze the title forever. */
export function summarizeConversation(content: string[]): { title: string; provisional: boolean } {
  const texts = content.map(clean).filter(Boolean);
  const substantive = texts.find(text => !/^(你好|您好|嗨|哈[喽啰]|hi|hello|hey|测试|test|在吗|谢谢|好的)[!！?？。，,.\s]*$/i.test(text));
  if (!substantive) return { title: texts.length ? '日常交流' : '新会话', provisional: true };
  let title = substantive.replace(/^(?:你好|您好|嗨|哈[喽啰]|hi|hello|hey)[，,:：!！。\s]+/iu, '').split(/[\n。！？!?；;]/u)[0]
    .replace(/^(?:请(?:你)?|麻烦(?:你)?|帮我|帮助我|我想(?:要)?|我需要|能否|可以|根据(?:以上|下面|附件|这些)资料|按照(?:以上|下面)要求)[，,\s]*/u, '')
    .replace(/^(?:帮我|为我|协助我|一下)[，,\s]*/u, '').trim();
  // A small presentation-only vocabulary; this never routes tasks or tools.
  if (/(?:文献|论文).*(?:阅读|总结|解读)|(?:阅读|总结|解读).*(?:文献|论文)/u.test(title)) title = '文献阅读';
  else if (/(?:生成|制作|做|设计).*(?:PPT|幻灯片|演示文稿)|(?:PPT|幻灯片|演示文稿).*(?:生成|制作|设计)/iu.test(title)) title = '演示文稿制作';
  else if (/(?:数据|统计).*(?:分析|报告)|(?:分析|报告).*(?:数据|统计)/u.test(title)) title = '数据分析报告';
  else if (/(?:论文|文章).*(?:润色|修订|校对)|(?:润色|修订|校对).*(?:论文|文章)/u.test(title)) title = '论文修订';
  title = title.replace(/[，,:：].*$/u, '').trim() || substantive;
  const chars = [...title];
  if (/[\p{Script=Han}]/u.test(title)) title = chars.slice(0, 16).join('');
  else title = title.split(/\s+/).slice(0, 6).join(' ').slice(0, 48);
  return { title: title || '新的讨论', provisional: false };
}

export function createConversationTitles(output: string, principal: string, host: Host) {
  const path = join(output, 'conversation-titles.json');
  let entries: Record<string, { title: string; provisional: boolean; manual?: boolean }> = {};
  try {
    const saved = JSON.parse(readFileSync(path, 'utf8'));
    if (saved.version !== 1 || saved.principal !== principal || !saved.entries || Array.isArray(saved.entries)) throw Error('Invalid conversation title state');
    entries = saved.entries;
  } catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error; }
  const save = () => {
    mkdirSync(output, { recursive: true, mode: 0o700 });
    writeFileSync(path + '.tmp', JSON.stringify({ version: 1, principal, entries }), { mode: 0o600 });
    renameSync(path + '.tmp', path);
  };
  let pending: Promise<unknown> = Promise.resolve();
  const serial = <T>(fn: () => Promise<T>): Promise<T> => {
    const result = pending.then(fn); pending = result.catch(() => undefined); return result;
  };
  return {
    /** Explicit user edits are serialized with automatic edits, including an identical name. */
    rename(id: string, title: string) { return serial(async () => {
      const accepted = await host.rename(id, title);
      entries[id] = { title: accepted?.title ?? title, provisional: false, manual: true }; save();
      return accepted;
    }); },
    refresh(id: string, incoming?: string) { return serial(async () => {
      const snapshot = await host.inspect(id), current = conversationTitle(snapshot), previous = entries[id];
      if (snapshot.meta?.isSeeded || snapshot.meta?.parentSession || previous?.manual) return;
      if (previous && current !== previous.title) return;
      if (!previous && current && current !== '新会话') return;
      if (previous && !previous.provisional && !/^用户附件的只读提取结果/u.test(previous.title)) return;
      const texts = snapshot.events.filter(row => row.type === 'user/message' && row.data?.source?.kind === 'user')
        .map(row => (host.humanContentFor?.(id, row) ?? row.data.content ?? []).filter((part: any) => part.type === 'text').map((part: any) => part.text).join(' '));
      if (incoming) texts.push(incoming);
      if (!texts.length) return;
      const summary = summarizeConversation(texts);
      const used = new Set<string>();
      for (const sibling of host.siblings(id)) if (sibling !== id) {
        try { used.add(conversationTitle(await host.inspect(sibling))); } catch { /* Deleted concurrently. */ }
      }
      let title = summary.title, suffix = 1;
      while (used.has(title)) title = `${summary.title}（${++suffix}）`;
      // Another native provider or edit must not be overwritten during the reads above.
      if (conversationTitle(await host.inspect(id)) !== current) return;
      if (title !== current) await host.rename(id, title);
      entries[id] = { title, provisional: summary.provisional }; save();
    }); },
  };
}
