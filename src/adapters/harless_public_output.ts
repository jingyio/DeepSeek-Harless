/** Detached browser presentation. Never rewrite the journal, model context, or file bytes. */
import { AssistantStreamAccumulator, expandAssistantStream } from '@deepseek-ai/dsh-llm';
import { humanContent, isAttachmentContext } from './harless_attachment_context.ts';

const hiddenPath = '〔内部路径已隐藏〕';
const roots = ['home', 'root', 'opt', 'srv', 'usr', 'var', 'tmp', 'etc', 'mnt', 'private', 'Users', 'user', 'workspace', 'app'];
const pathStart = `(?:/(?:${roots.join('|')})(?:/|(?=$|[\\s\u3000-\u303f\uff00-\uffef]))|[A-Za-z]:[\\\\/]|~[\\\\/])`;
const pathTail = `[^\\s\x00-\x1f\x22\x27\x60<>()[\\]{}\u3000-\u303f\uff00-\uffef]*`;
const hostPath = new RegExp(`file://[^\\s\x00-\x1f\x22\x27\x60<>()[\\]{}\u3000-\u303f\uff00-\uffef]*|(?<![\\w/])${pathStart}${pathTail}`, 'gi');
const brand = /@deepseek-ai\/dsh[\w./-]*|\bDeepSeek[\s_-]+(?:Harness|Harless)\b|\bDSH\b|\bHarness\b/gi;
const possibleStarts = [...roots.map(root => '/' + root + '/'), 'DeepSeek', 'Harness', 'DSH', '@deepseek-ai/dsh', '~/', 'file://'];

export function publicText(value: string): string {
  return value.replace(hostPath, hiddenPath).replace(brand, 'GeneLoop');
}

/** Keep only a possible private token at the tail; ordinary prose stays incremental. */
export function createPublicTextStream() {
  let pending = '';
  let left = ' ';
  return {
    push(text: string, final = false) {
      pending += text;
      let cut = pending.length;
      if (!final) {
        const lower = pending.toLowerCase();
        for (const prefix of possibleStarts) {
          for (let size = 1; size <= Math.min(prefix.length, pending.length); size++) {
            const start = pending.length - size;
            if (lower.endsWith(prefix.slice(0, size).toLowerCase()) && !/[\w/]/.test(start === 0 ? left : pending[start - 1])) cut = Math.min(cut, start);
          }
        }
        // A path is private as a whole, including chunks arriving after its root.
        for (const match of ('xx' + left + pending).matchAll(hostPath)) if (match.index! + match[0].length === pending.length + 3) cut = Math.min(cut, Math.max(0, match.index! - 3));
        const drive = /(?:^|[^\w/])([A-Za-z]:?)$/.exec('xx' + left + pending);
        if (drive) cut = Math.min(cut, pending.length - drive[1].length);
        const packageTail = /@deepseek-ai\/dsh[\w./-]*$/.exec(pending);
        if (packageTail) cut = Math.min(cut, packageTail.index);
        const frameworkTail = /\bDeepSeek[\s_-]*(?:H(?:a(?:r(?:[nl](?:e(?:s(?:s)?)?)?)?)?)?)?$/i.exec('xx' + left + pending);
        if (frameworkTail) cut = Math.min(cut, Math.max(0, frameworkTail.index - 3));
      }
      const ready = pending.slice(0, cut); pending = pending.slice(cut);
      const result = publicText('xx' + left + ready).slice(3);
      if (ready) left = ready.at(-1)!;
      return result;
    },
  };
}

const identityKeys = new Set(['id', 'sessionId', 'session_id', 'callId', 'attemptId', 'rpcId', 'requestId', 'receiptId',
  'type', 'kind', 'role', 'provider', 'model', 'sha256', 'output_sha256', 'input_sha256', 'confirmation_digest']);
function textFields(value: any, key = ''): any {
  if (typeof value === 'string') return identityKeys.has(key) ? value : publicText(value);
  if (Array.isArray(value)) return value.map(item => textFields(item));
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([name, item]) => [name, textFields(item, name)]));
  return value;
}

function messageView(message: any,expectedOriginal?:readonly any[]): any {
  if (!message) return message;
  if (isAttachmentContext(message)) return {...message,content:[]};
  if (message.source?.kind === 'user') {
    const content=humanContent(message.content??[],expectedOriginal);
    return content.length===(message.content??[]).length&&content.every((part,index)=>part===message.content[index])?message:{...message,content};
  }
  if (message.role === 'system') return { ...message, content: [{ type: 'text', text: '已应用本轮会话设置。' }],
    source: { kind: 'plugin', plugin: 'GeneLoop' } };
  return textFields(message);
}

export function createPublicStreamProjection() {
  const texts = new Map<string, ReturnType<typeof createPublicTextStream>>();
  const chunk = (value: any) => {
    if (value.type === 'text-delta' || value.type === 'reasoning-delta') {
      const key = value.type + ':' + value.index;
      if (!texts.has(key)) texts.set(key, createPublicTextStream());
      return { ...value, text: texts.get(key)!.push(value.text) };
    }
    // Tool argument deltas are private JSON fragments; the complete safe block
    // and durable call still provide details without leaking split paths.
    if (value.type === 'tool-call-delta') return { ...value, argumentsDelta: '', ...(value.name ? { name: publicText(value.name) } : {}) };
    if (value.type === 'block-end') {
      texts.delete('text-delta:' + value.index); texts.delete('reasoning-delta:' + value.index);
      return { ...value, block: textFields(value.block) };
    }
    if (value.type === 'finish') {
      const { replayState, ...safe } = value;
      return textFields(safe);
    }
    return textFields(value);
  };
  const compact = (stream: any[], settled = false) => {
    const accumulator = new AssistantStreamAccumulator();
    const projected = expandAssistantStream(stream).map(timed => ({ ...timed, chunk: chunk(timed.chunk) }));
    if (settled) for (const [key, text] of texts) {
      const last = projected.findLast(timed => timed.chunk.type + ':' + ('index' in timed.chunk ? timed.chunk.index : '') === key);
      if (last && 'text' in last.chunk) last.chunk.text += text.push('', true);
    }
    for (const timed of projected) accumulator.push(timed);
    return accumulator.snapshot();
  };
  return { chunk, compact };
}

export function publicSessionEvent(event: any,expectedOriginal?:readonly any[]): any {
  if (event.type === 'user/message' && (event.data?.source?.kind === 'user'||isAttachmentContext(event.data))) {
    const data=messageView(event.data,expectedOriginal);return data===event.data?event:{...event,data};
  }
  let data = event.data;
  if (data?.message) data = { ...textFields(data), message: messageView(data.message) };
  else if (data?.role || data?.content) data = messageView(data);
  else data = textFields(data);
  if (Array.isArray(event.data?.stream)) data = { ...data, stream: createPublicStreamProjection().compact(event.data.stream, true) };
  return { ...event, data };
}

/** Also sanitize task/comparison replies; identities, hashes and download receipts stay intact. */
export function publicTaskView(value: any): any {
  if (Array.isArray(value)) return value.map(publicTaskView);
  if (!value || typeof value !== 'object') return value;
  const result = { ...value };
  for (const key of ['answer', 'answer_display', 'failure', 'fallback_reason', 'delivery_message']) {
    if (typeof result[key] === 'string') result[key] = key.startsWith('answer') && ['running', 'queued', 'preparing'].includes(result.status)
      ? createPublicTextStream().push(result[key]) : publicText(result[key]);
  }
  if (result.error) result.error = textFields(result.error);
  if(typeof result.text==='string'&&/^(?:assistant|trace)-/.test(result.id??''))result.text=['running','streaming'].includes(result.status)
    ?createPublicTextStream().push(result.text):publicText(result.text);
  for (const key of ['progress', 'activity']) if (result[key]) result[key] = textFields(result[key]);
  if (result.lanes) result.lanes = Object.fromEntries(Object.entries(result.lanes).map(([key, lane]) => [key, publicTaskView(lane)]));
  for (const key of ['tasks', 'turns', 'items', 'current_task','messages','trace']) if (result[key]) result[key] = publicTaskView(result[key]);
  return result;
}

/** Public controller methods only. inspect() remains authoritative for execution/forking. */
export function protectPublicSessionOutput(controller: any, originalFor?:(session:string,event:any)=>readonly any[]|undefined) {
  const undo: (() => void)[] = [];
  const requestedSession = (request: any): string | undefined => {
    if (typeof request === 'string') return request;
    const address = request?.address;
    const id = address === undefined ? request?.sessionId
      : address?.kind === 'session' ? address.sessionId
      : address?.kind === 'subagent' ? address.childSessionId : undefined;
    return typeof id === 'string' && id.length ? id : undefined;
  };
  // A missing address has no authority to resolve admission records. In
  // particular, never equate two absent IDs in a legacy-content callback.
  const originalContent = (id: string | undefined, event: any) => id === undefined ? undefined : originalFor?.(id, event);
  const wrap = (name: string, make: (original: any) => any) => {
    if (typeof controller[name] !== 'function') return;
    const original = controller[name]; const replacement = make(original.bind(controller));
    controller[name] = replacement;
    undo.push(() => { if (controller[name] === replacement) controller[name] = original; });
  };
  wrap('page', original => async (...args: any[]) => {
    const result = await original(...args);
    const id = requestedSession(args[0]);
    return { ...result, records: result.records.map((record: any) => ({ ...record, event: publicSessionEvent(record.event,originalContent(id,record.event)) })) };
  });
  wrap('follow', original => async function* (...args: any[]) {
    let stream = createPublicStreamProjection();
    let id = requestedSession(args[0]);
    for await (const value of original(...args)) {
      if (value.type === 'snapshot') {
        stream = createPublicStreamProjection();
        const active = value.assistantStream?.activeAttempt;
        const { cwd, ...header } = value.header;
        yield { ...value, header, records: value.records.map((record: any) => ({ ...record, event: publicSessionEvent(record.event,originalContent(id,record.event)) })),
          ...(active ? { assistantStream: { ...value.assistantStream, activeAttempt: { ...active, stream: stream.compact(active.stream) } } } : {}) };
      } else if (value.type === 'event') yield { ...value, event: publicSessionEvent(value.event,originalContent(id,value.event)) };
      else if (value.type === 'assistant-stream') {
        if (value.frame.type === 'start') stream = createPublicStreamProjection();
        yield value.frame.type === 'chunk' ? { ...value, frame: { ...value.frame, chunk: stream.chunk(value.frame.chunk) } } : value;
      } else yield value;
    }
  });
  for (const method of ['list', 'search']) wrap(method, original => async (...args: any[]) => {
    const result = await original(...args);
    return { ...result, items: result.items.map((item: any) => {
      const { cwd, ...row } = item;
      return { ...row, ...(typeof row.snippet === 'string' ? { snippet: publicText(row.snippet) } : {}) };
    }) };
  });
  wrap('control', original => async function* (...args: any[]) {
    for await (const value of original(...args)) {
      // Queue entries carry user-authored input: never rewrite them.
      if (value.type === 'baseline') yield { ...value, value: { ...value.value, jobs: textFields(value.value.jobs) } };
      else if (value.type === 'jobs') yield { ...value, jobs: textFields(value.jobs) };
      else yield value;
    }
  });
  return () => { for (const dispose of undo.reverse()) dispose(); };
}
