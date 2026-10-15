/** Public execution progress assembled only from actual model/tool lifecycle events. */
export type TaskActivity = { label: string; status: 'running' | 'completed' | 'failed' | 'cancelled'; tool?: string };
export type TaskProgressSnapshot = { answer: string; progress: TaskActivity; activity: TaskActivity[] };

const toolLabels: [RegExp, string][] = [
  [/pin|list|inspect|inventory|discover/i, '检查资料'],
  [/read|extract|parse|load/i, '读取资料'],
  [/analy|statistic|fit_|regress|compute|plan_analysis/i, '分析数据'],
  [/plot|figure|chart|visual/i, '生成图表'],
  [/slide|ppt|deck/i, '制作演示文稿'],
  [/proof|revision|revise|audit_paper/i, '检查和修订论文'],
  [/verify|validate|audit|check/i, '核验结果'],
  [/report|compose|export|deliver|write|save|layout|render/i, '生成交付文件'],
];
export function taskToolLabel(name: unknown): string {
  const tool = typeof name === 'string' ? name.split('__').at(-1)! : '';
  return toolLabels.find(([pattern]) => pattern.test(tool))?.[1] ?? '执行工具';
}

/** No model reasoning or raw arguments/host paths are copied into public progress. */
export function createTaskProgress(saved?: Partial<TaskProgressSnapshot>): {
  beginAttempt(): void; chunk(value: any): void; event(value: any): void;
  finish(status: string): void; snapshot(): TaskProgressSnapshot;
} {
  const restored = (value: any): TaskActivity | undefined => value && typeof value.label === 'string' && value.label.length <= 160 &&
    ['running', 'completed', 'failed', 'cancelled'].includes(value.status)
      ? { label: value.label, status: value.status, ...(typeof value.tool === 'string' && /^[a-zA-Z0-9_-]{1,160}$/.test(value.tool) ? { tool: value.tool } : {}) } : undefined;
  let answer = typeof saved?.answer === 'string' ? saved.answer : '';
  let progress: TaskActivity = restored(saved?.progress) ?? { label: '准备处理请求', status: 'running' };
  let currentText = new Map<number, string>();
  const activities: TaskActivity[] = Array.isArray(saved?.activity) ? saved.activity.slice(-40).map(restored).filter((row): row is TaskActivity => Boolean(row)) : [];
  const tools = new Map<string, TaskActivity>();
  const setProgress = (label: string, status: TaskActivity['status'] = 'running') => { progress = { label, status }; };
  const safeTool = (name: any) => typeof name === 'string' && /^[a-zA-Z0-9_-]{1,160}$/.test(name) ? name : undefined;
  return {
    beginAttempt() { currentText = new Map(); setProgress('正在组织回复'); },
    chunk(chunk) {
      if (chunk?.type === 'text-delta' && typeof chunk.text === 'string' && Number.isSafeInteger(chunk.index)) {
        currentText.set(chunk.index, (currentText.get(chunk.index) ?? '') + chunk.text);
        answer = [...currentText.entries()].sort(([a], [b]) => a - b).map(([, text]) => text).join('\n');
        setProgress('正在回复');
      } else if (chunk?.type === 'block-end' && chunk.block?.type === 'text' && typeof chunk.block.text === 'string') {
        currentText.set(chunk.index, chunk.block.text);
        answer = [...currentText.entries()].sort(([a], [b]) => a - b).map(([, text]) => text).join('\n');
      } else if (chunk?.type === 'reasoning-delta') setProgress('正在分析请求');
      else if (chunk?.type === 'tool-call-delta' && chunk.name) setProgress('准备' + taskToolLabel(chunk.name));
    },
    event(event) {
      if (event?.type === 'tool/call') {
        const row: TaskActivity = { label: taskToolLabel(event.data?.name), status: 'running',
          ...(safeTool(event.data?.name) ? { tool: event.data.name } : {}) };
        const key = String(event.data?.callId ?? '');
        if (!key || tools.has(key)) return;
        tools.set(key, row); activities.push(row);
        if (activities.length > 40) activities.shift();
        progress = { ...row };
      } else if (event?.type === 'tool/result') {
        const key = String(event.data?.message?.source?.callId ?? event.data?.callId ?? '');
        const row = tools.get(key); if (!row) return;
        row.status = event.data?.message?.content?.some((part: any) => part.isError === true) ? 'failed' : 'completed';
        progress = { ...row };
      } else if (event?.type === 'assistant/message') {
        const content = event.data?.message?.content;
        if (Array.isArray(content)) answer = content.filter((part: any) => part.type === 'text').map((part: any) => part.text).join('\n');
      }
    },
    finish(status) {
      const state = status === 'completed' ? 'completed' : status === 'cancelled' ? 'cancelled' : 'failed';
      for (const row of activities) if (row.status === 'running') row.status = state === 'completed' ? 'failed' : state;
      setProgress(state === 'completed' ? '回复完成' : state === 'cancelled' ? '已停止' : '处理未完成', state);
    },
    snapshot() { return { answer, progress: { ...progress }, activity: activities.map(row => ({ ...row })) }; },
  };
}
