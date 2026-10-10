import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {defaultPolicy, policyHash, policySchema, validatePolicy} from '../dist/layout-policy.js';

const cli = fileURLToPath(new URL('../dist/layout-policy-cli.js', import.meta.url));
const invoke = (input) => {
  const result = spawnSync(process.execPath, [cli], {input, encoding: 'utf8', timeout: 10000});
  assert.equal(result.error, undefined);
  assert.equal(result.stderr, '');
  return {status: result.status, response: JSON.parse(result.stdout)};
};

test('布局策略支持全部边界值，返回独立的规范化对象', () => {
  assert.deepEqual(validatePolicy(defaultPolicy), defaultPolicy);
  assert.notEqual(validatePolicy(defaultPolicy), defaultPolicy);
  for (const policy of [
    {...defaultPolicy, media_position: 'bottom', media_fraction: 0.50, body_columns: 2,
      body_font_size: 20, table_font_size: 17, body_gap: 0.08},
    {...defaultPolicy, media_fraction: 0.72, body_font_size: 24, table_font_size: 20, body_gap: 0.28},
  ]) assert.deepEqual(validatePolicy(policy), policy);
  assert.equal(policySchema.additionalProperties, false);
  assert.ok(Object.isFrozen(defaultPolicy));
});

test('拒绝非法数值、类型、未知版本和枚举，不能静默回到默认值', () => {
  const invalid = [null, [], 'default', 1, {...defaultPolicy, schema_version: 2},
    {...defaultPolicy, media_position: 'left'}, {...defaultPolicy, body_columns: 3},
    {...defaultPolicy, body_columns: '2'}, {...defaultPolicy, body_font_size: 20.5},
    {...defaultPolicy, table_font_size: 18.5}];
  for (const [field, low, high] of [
    ['media_fraction', 0.50, 0.72], ['body_font_size', 20, 24],
    ['table_font_size', 17, 20], ['body_gap', 0.08, 0.28],
  ]) {
    for (const value of [NaN, Infinity, -Infinity, low - 0.001, high + 0.001, String(low), null]) {
      invalid.push({...defaultPolicy, [field]: value});
    }
  }
  for (const policy of invalid) assert.throws(() => validatePolicy(policy));
});

test('onlyKeys 阻止内容、执行、来源和权限字段及隐藏属性', () => {
  for (const field of ['code', 'eval', 'action', 'slides', 'sources', 'validator', 'permission', '__proto__']) {
    assert.throws(() => validatePolicy({...defaultPolicy, [field]: '不允许'}));
  }
  for (const field of Object.keys(defaultPolicy)) {
    const partial = {...defaultPolicy};
    delete partial[field];
    assert.throws(() => validatePolicy(partial));
  }
  assert.throws(() => validatePolicy(Object.create(defaultPolicy)));
  assert.throws(() => validatePolicy({...defaultPolicy, [Symbol('code')]: 'hidden'}));
  const hidden = {...defaultPolicy};
  Object.defineProperty(hidden, 'code', {value: 'hidden', enumerable: false});
  assert.throws(() => validatePolicy(hidden));
  const accessor = {...defaultPolicy};
  Object.defineProperty(accessor, 'body_gap', {get() {assert.fail('不应执行访问器');}});
  assert.throws(() => validatePolicy(accessor), /固定 schema/);
});

test('摘要按固定字段顺序归一化；策略变化产生新版本摘要', () => {
  const canonical = '{"schema_version":1,"media_position":"right","media_fraction":0.58,"body_columns":1,"body_font_size":22,"table_font_size":18,"body_gap":0.18}';
  const expected = createHash('sha256').update(canonical, 'utf8').digest('hex');
  assert.equal(policyHash(defaultPolicy), expected);
  assert.equal(policyHash(Object.fromEntries(Object.entries(defaultPolicy).reverse())), expected);
  assert.notEqual(policyHash({...defaultPolicy, body_columns: 2}), expected);
  assert.throws(() => policyHash({...defaultPolicy, code: 'arbitrary()'}));
});

test('CLI 格式校验返回完整策略、schema 和摘要，永不冒充认证或自动启用', () => {
  const direct = invoke(JSON.stringify(defaultPolicy));
  const wrapped = invoke(JSON.stringify({action: 'validate', policy: defaultPolicy}));
  assert.equal(direct.status, 0);
  assert.deepEqual(direct, wrapped);
  assert.equal(direct.response.valid, true);
  assert.equal(direct.response.certified, false);
  assert.equal(direct.response.active, false);
  assert.equal(direct.response.scope, 'layout_parameters_only');
  assert.deepEqual(direct.response.policy, defaultPolicy);
  assert.equal(direct.response.policy_digest, policyHash(defaultPolicy));
  assert.deepEqual(direct.response.schema, policySchema);
  const schema = invoke('{"action":"schema"}');
  assert.equal(schema.status, 0);
  assert.deepEqual(schema.response.schema, policySchema);
  assert.equal(schema.response.certified, false);
  assert.equal(schema.response.active, false);
  assert.equal(Object.hasOwn(schema.response, 'valid'), false);
});

test('CLI 拒绝未知 action、额外字段、缺项和坏 JSON，返回非零且无合法或认证假象', () => {
  for (const input of ['{', 'null', '{"action":"activate","policy":{}}',
    JSON.stringify({action: 'schema', code: 'exit()'}), JSON.stringify({action: 'validate'}),
    JSON.stringify({action: 'validate', policy: defaultPolicy, accepted: true}),
    JSON.stringify({...defaultPolicy, body_font_size: NaN})]) {
    const {status, response} = invoke(input);
    assert.equal(status, 2);
    assert.equal(response.valid, false);
    assert.equal(response.certified, false);
    assert.equal(response.active, false);
    assert.equal(Object.hasOwn(response, 'policy_digest'), false);
    assert.ok(response.error);
  }
});
