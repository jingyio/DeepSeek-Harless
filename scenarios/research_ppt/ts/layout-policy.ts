/** RSI 只生成有界布局参数；内容、来源、验证器和权限不属于候选协议。 */
import {createHash} from 'node:crypto';

export type LayoutPolicy = {
  schema_version: 1;
  media_position: 'right' | 'bottom';
  media_fraction: number;
  body_columns: 1 | 2;
  body_font_size: number;
  table_font_size: number;
  body_gap: number;
};

export const defaultPolicy: LayoutPolicy = Object.freeze({
  schema_version: 1, media_position: 'right', media_fraction: 0.58,
  body_columns: 1, body_font_size: 22, table_font_size: 18, body_gap: 0.18,
});

export const policySchema = {
  $schema: 'https://json-schema.org/draft/2020-12/schema',
  title: 'ResearchPPTLayoutPolicyV1', type: 'object', additionalProperties: false,
  required: ['schema_version', 'media_position', 'media_fraction', 'body_columns',
    'body_font_size', 'table_font_size', 'body_gap'],
  properties: {
    schema_version: {const: 1},
    media_position: {enum: ['right', 'bottom']},
    media_fraction: {type: 'number', minimum: 0.50, maximum: 0.72},
    body_columns: {type: 'integer', enum: [1, 2]},
    body_font_size: {type: 'integer', minimum: 20, maximum: 24},
    table_font_size: {type: 'integer', minimum: 17, maximum: 20},
    body_gap: {type: 'number', minimum: 0.08, maximum: 0.28},
  },
} as const;

const keys = [...policySchema.required].sort();

function numberIn(value: unknown, minimum: number, maximum: number, integer = false): value is number {
  return typeof value === 'number' && Number.isFinite(value) &&
    (!integer || Number.isInteger(value)) && value >= minimum && value <= maximum;
}

export function validatePolicy(value: unknown): LayoutPolicy {
  // 只接受普通数据对象，避免访问器、继承字段或符号字段绕开 onlyKeys。
  if (value === null || typeof value !== 'object' || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value))) {
    throw new Error('布局策略必须是固定 schema 的 JSON 对象');
  }
  const ownKeys = Reflect.ownKeys(value);
  if (ownKeys.some(key => typeof key !== 'string') ||
      ownKeys.map(String).sort().join(',') !== keys.join(',') ||
      ownKeys.some(key => !Object.hasOwn(Object.getOwnPropertyDescriptor(value, key)!, 'value'))) {
    throw new Error('布局策略字段必须完整且仅包含固定 schema，禁止代码、内容或权限字段');
  }
  const p = value as Record<string, unknown>;
  if (p.schema_version !== 1 || !['right', 'bottom'].includes(p.media_position as string) ||
      !numberIn(p.media_fraction, 0.50, 0.72) || ![1, 2].includes(p.body_columns as number) ||
      !numberIn(p.body_font_size, 20, 24, true) || !numberIn(p.table_font_size, 17, 20, true) ||
      !numberIn(p.body_gap, 0.08, 0.28)) {
    throw new Error('布局策略版本、枚举或数值超出固定边界');
  }
  // 固定字段顺序，使 Python/Node 可按同一规范复核摘要，不依赖模型键顺序。
  return {
    schema_version: 1, media_position: p.media_position as LayoutPolicy['media_position'],
    media_fraction: p.media_fraction, body_columns: p.body_columns as LayoutPolicy['body_columns'],
    body_font_size: p.body_font_size, table_font_size: p.table_font_size, body_gap: p.body_gap,
  };
}

export function policyHash(value: unknown): string {
  return createHash('sha256').update(JSON.stringify(validatePolicy(value)), 'utf8').digest('hex');
}
