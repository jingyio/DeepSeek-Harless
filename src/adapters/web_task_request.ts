/**
 * SSS 业务任务的请求边界；不创建 Agent，也不读取文件或解析资料引用。
 *
 * Harness 0.1.5-rc.3 的 SessionPromptRequest 使用 text、image(base64)、
 * file(receiptId)。receipt 必须由官方同一 Session 的上传接口生成；持久
 * attachmentId 不能冒充 receipt。真正的文件授权、图片解码和模型能力检查
 * 仍由官方 Controller 执行。SSS mode 与其 queue/steer delivery 无关。
 */
import { createHash, randomUUID } from 'node:crypto';

export type ExecutionMode = 'baseline' | 'shadow' | 'execute';
export type PromptPart =
  | { type: 'text'; text: string }
  | { type: 'image'; mediaType: 'image/png' | 'image/jpeg' | 'image/webp' | 'image/gif'; data: string; name?: string }
  | { type: 'file'; receiptId: string };
/** version 是客户端期望的版本，未经后端 resolver 验证，不能作为证据。 */
export type ResourceReference = { resource_id: string; version?: string };
export type RequestContext = {
  task_id: string;
  session_id: string;
  default_mode: ExecutionMode;
  default_budget_usd: number;
  max_budget_usd: number;
  default_profile: string;
  allowed_profiles: readonly string[];
  max_content_bytes?: number;
  max_parts?: number;
  max_messages?: number;
  max_resources?: number;
};
export type ContentSummary =
  | { type: 'text'; bytes: number; sha256: string }
  | { type: 'image'; mediaType: string; bytes: number; sha256: string; name?: string }
  | { type: 'file'; receipt_sha256: string };
export type NormalizedWebTask = {
  schema_version: 1;
  task_id: string;
  session_id: string;
  request_id: string;
  capability_profile: string;
  input_kind: 'text' | 'instruction' | 'content' | 'messages';
  content: PromptPart[];
  resources: ResourceReference[];
  mode: ExecutionMode;
  budget_usd: number;
  /** 单文本保持其原始 SHA；其他形式覆盖整个有序内容。 */
  prompt_sha256: string;
  /** 始终覆盖全部文本、媒体 payload、receipt、显示名称和顺序。 */
  content_sha256: string;
  /** 业务配置、资料引用和内容的摘要，不依赖服务端生成的 task/session。 */
  request_sha256: string;
  /** 审计使用摘要，不复制 base64 图片或整段正文。 */
  summary: { content: ContentSummary[]; resources: ResourceReference[] };
};

export class WebTaskRequestError extends TypeError {
  readonly code: string;
  readonly field: string;
  constructor(code: string, field: string, explanation: string) {
    super(`${field}: ${explanation}`);
    this.name = 'WebTaskRequestError';
    this.code = code;
    this.field = field;
  }
}

const sha = (value: string | Uint8Array): string => createHash('sha256').update(value).digest('hex');
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value !== null && typeof value === 'object') {
    const object = value as Record<string, unknown>;
    return `{${Object.keys(object).sort().map(key => `${JSON.stringify(key)}:${canonical(object[key])}`).join(',')}}`;
  }
  return JSON.stringify(value) ?? fail('request', 'unsupported non-JSON value');
}
const fail = (field: string, explanation: string, code = 'invalid_request'): never => {
  throw new WebTaskRequestError(code, field, explanation);
};
function object(value: unknown, field: string): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value))) fail(field, 'must be a JSON object');
  return value as Record<string, unknown>;
}
function keys(value: Record<string, unknown>, allowed: readonly string[], field: string): void {
  for (const key of Object.keys(value)) {
    if (!allowed.includes(key)) fail(`${field}.${key}`, 'unsupported field', 'unsupported_field');
  }
}
function token(value: unknown, field: string, maximum = 512): string {
  if (typeof value !== 'string' || !value.length || value.length > maximum || /[\x00-\x1f\x7f]/.test(value)) {
    fail(field, 'must be a non-empty bounded identifier');
  }
  return value;
}
function text(value: unknown, field: string): string {
  if (typeof value !== 'string' || value.includes('\0')) fail(field, 'must be text without NUL');
  return value;
}
function mode(value: unknown, field: string): ExecutionMode {
  if (value !== 'baseline' && value !== 'shadow' && value !== 'execute') fail(field, 'must be baseline, shadow or execute');
  return value;
}
function amount(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) fail(field, 'must be a finite non-negative number');
  return value;
}
function limit(value: number | undefined, fallback: number, field: string): number {
  if (value === undefined) return fallback;
  if (!Number.isSafeInteger(value) || value < 1) fail(field, 'server limit must be a positive integer', 'invalid_context');
  return value;
}

/** Preserve every supplied text byte and part order; no trim, rewriting or file access. */
export function normalizeWebTaskRequest(input: unknown, context: RequestContext): NormalizedWebTask {
  const taskId = token(context.task_id, 'context.task_id');
  const sessionId = token(context.session_id, 'context.session_id');
  const defaultMode = mode(context.default_mode, 'context.default_mode');
  const maximumBudget = amount(context.max_budget_usd, 'context.max_budget_usd');
  const defaultBudget = amount(context.default_budget_usd, 'context.default_budget_usd');
  if (defaultBudget > maximumBudget) fail('context.default_budget_usd', 'exceeds server maximum', 'invalid_context');
  if (!Array.isArray(context.allowed_profiles) || !context.allowed_profiles.length ||
      context.allowed_profiles.some(profile => typeof profile !== 'string' || !profile.length)) {
    fail('context.allowed_profiles', 'must contain trusted registered profiles', 'invalid_context');
  }
  if (!context.allowed_profiles.includes(context.default_profile)) {
    fail('context.default_profile', 'not registered by the server', 'invalid_context');
  }
  const maximumBytes = limit(context.max_content_bytes, 20 * 1024 * 1024, 'context.max_content_bytes');
  const maximumParts = limit(context.max_parts, 64, 'context.max_parts');
  const maximumMessages = limit(context.max_messages, 32, 'context.max_messages');
  const maximumResources = limit(context.max_resources, 64, 'context.max_resources');
  let contentBytes = 0;
  const countBytes = (value: string, field: string): void => {
    contentBytes += Buffer.byteLength(value, 'utf8');
    if (contentBytes > maximumBytes) fail(field, 'content exceeds server byte limit', 'request_too_large');
  };
  const part = (value: unknown, field: string): PromptPart => {
    const row = object(value, field);
    if (row.type === 'text') {
      keys(row, ['type', 'text'], field);
      const value = text(row.text, `${field}.text`); countBytes(value, field);
      return { type: 'text', text: value };
    }
    if (row.type === 'file') {
      keys(row, ['type', 'receiptId'], field);
      return { type: 'file', receiptId: token(row.receiptId, `${field}.receiptId`) };
    }
    if (row.type === 'image') {
      keys(row, ['type', 'mediaType', 'data', 'name'], field);
      if (!['image/png', 'image/jpeg', 'image/webp', 'image/gif'].includes(row.mediaType as string)) {
        fail(`${field}.mediaType`, 'unsupported official image media type');
      }
      const data = text(row.data, `${field}.data`); countBytes(data, field);
      if (!data.length || data.length % 4 !== 0 || !/^[A-Za-z0-9+/]*={0,2}$/.test(data) ||
          Buffer.from(data, 'base64').toString('base64') !== data) fail(`${field}.data`, 'must be canonical base64');
      const result: PromptPart = { type: 'image', mediaType: row.mediaType as 'image/png', data };
      if (row.name !== undefined) result.name = token(row.name, `${field}.name`);
      return result;
    }
    fail(`${field}.type`, 'unsupported prompt part; use text, image or file receipt');
  };
  const parts = (value: unknown, field: string): PromptPart[] => {
    if (typeof value === 'string') return [part({ type: 'text', text: value }, field)];
    if (!Array.isArray(value) || !value.length || value.length > maximumParts) fail(field, 'must be non-empty text or a bounded content list');
    return value.map((item, index) => part(item, `${field}[${index}]`));
  };

  let inputKind: NormalizedWebTask['input_kind'];
  let content: PromptPart[];
  const envelope = typeof input === 'string' ? {} : object(input, 'request');
  keys(envelope, ['instruction', 'content', 'messages', 'inputs', 'mode', 'budget_usd', 'request_id', 'capability_profile'], 'request');
  if (typeof input === 'string') {
    inputKind = 'text'; content = parts(input, 'request');
  } else {
    const forms = ['instruction', 'content', 'messages'].filter(key => envelope[key] !== undefined);
    if (forms.length !== 1) fail('request', 'provide exactly one of instruction, content or messages');
    inputKind = forms[0] as NormalizedWebTask['input_kind'];
    if (inputKind === 'instruction') content = parts(text(envelope.instruction, 'request.instruction'), 'request.instruction');
    else if (inputKind === 'content') content = parts(envelope.content, 'request.content');
    else {
      const messages = envelope.messages;
      if (!Array.isArray(messages) || !messages.length || messages.length > maximumMessages) {
        fail('request.messages', 'must be a non-empty bounded user-message list');
      }
      content = [];
      messages.forEach((message, index) => {
        const field = `request.messages[${index}]`, row = object(message, field);
        keys(row, ['role', 'content'], field);
        if (row.role !== 'user') fail(`${field}.role`, 'client messages may only contain user input', 'untrusted_history');
        const messageParts = parts(row.content, `${field}.content`);
        if (!messageParts.some(row => row.type !== 'text' || row.text.trim().length > 0)) {
          fail(`${field}.content`, 'must contain non-whitespace text or an official attachment');
        }
        if (messages.length > 1) content.push(part({ type: 'text', text: `${index ? '\n\n' : ''}[用户输入 ${index + 1}]\n` }, field));
        content.push(...messageParts);
      });
    }
  }
  if (content.length > maximumParts) fail('request.content', 'too many normalized parts', 'request_too_large');
  if (!content.some(row => row.type !== 'text' || row.text.trim().length > 0)) {
    fail('request.content', 'must contain non-whitespace text or an official attachment');
  }

  let resources: ResourceReference[] = [];
  if (envelope.inputs !== undefined) {
    if (!Array.isArray(envelope.inputs) || envelope.inputs.length > maximumResources) fail('request.inputs', 'must be a bounded resource-reference list');
    resources = envelope.inputs.map((value, index) => {
      const field = `request.inputs[${index}]`, row = object(value, field);
      keys(row, ['resource_id', 'version'], field);
      const reference: ResourceReference = { resource_id: token(row.resource_id, `${field}.resource_id`) };
      if (row.version !== undefined) reference.version = token(row.version, `${field}.version`);
      return reference;
    });
  }
  const requestId = envelope.request_id === undefined ? randomUUID() : token(envelope.request_id, 'request.request_id', 128);
  const selectedProfile = envelope.capability_profile === undefined ? context.default_profile : token(envelope.capability_profile, 'request.capability_profile');
  if (!context.allowed_profiles.includes(selectedProfile)) fail('request.capability_profile', 'not registered by the server', 'profile_not_allowed');
  const selectedMode = envelope.mode === undefined ? defaultMode : mode(envelope.mode, 'request.mode');
  const budget = envelope.budget_usd === undefined ? defaultBudget : amount(envelope.budget_usd, 'request.budget_usd');
  if (budget > maximumBudget) fail('request.budget_usd', 'exceeds server maximum', 'budget_not_allowed');
  const contentDigest = sha(canonical(content));
  const promptDigest = content.length === 1 && content[0].type === 'text' ? sha(content[0].text) : contentDigest;
  const summary: NormalizedWebTask['summary'] = {
    content: content.map(row => {
      if (row.type === 'text') return { type: 'text', bytes: Buffer.byteLength(row.text, 'utf8'), sha256: sha(row.text) };
      if (row.type === 'file') return { type: 'file', receipt_sha256: sha(row.receiptId) };
      const bytes = Buffer.from(row.data, 'base64');
      return { type: 'image', mediaType: row.mediaType, bytes: bytes.length, sha256: sha(bytes), ...(row.name === undefined ? {} : { name: row.name }) };
    }),
    resources: resources.map(row => ({ ...row })),
  };
  return {
    schema_version: 1, task_id: taskId, session_id: sessionId, request_id: requestId,
    capability_profile: selectedProfile, input_kind: inputKind, content, resources,
    mode: selectedMode, budget_usd: budget, prompt_sha256: promptDigest, content_sha256: contentDigest,
    request_sha256: sha(canonical({ schema_version: 1, request_id: requestId,
      capability_profile: selectedProfile, mode: selectedMode, budget_usd: budget,
      content_sha256: contentDigest, resources })), summary,
  };
}
