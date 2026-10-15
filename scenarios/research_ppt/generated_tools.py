"""模型生成的纯 JSON TypeScript 工具宿主。

本模块不包含图件目录算法。候选在私有目录编译成模块，通过固定入口真实
执行；AST 白名单、Node 权限与资源限制共同约束执行。编译成功只是训练
候选，独立实跑证据齐备后才可加载。来源/科研语义正确性由场景独立核验。
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
from uuid import uuid4

SCENE = Path(__file__).resolve().parent
ROOT = SCENE.parents[1]
LIMIT = 3
MAX_JSON_BYTES = 1_000_000
MAX_CODE_BYTES = 24_000
SCHEMA_KEYS = {'type', 'properties', 'required', 'additionalProperties', 'items',
               'minimum', 'maximum', 'minItems', 'maxItems', 'minLength', 'maxLength',
               'enum', 'const', 'description', 'title', '$schema'}
DANGEROUS_KEYS = {'__proto__', 'constructor', 'prototype'}

# 这是固定验证器，不拼接/求值候选源码。TS 7 的 API 子进程只解析指定项目。
AST_CHECKER = r'''import {pathToFileURL} from 'node:url';
const apiModule = await import(pathToFileURL(process.argv[2] + '/dist/api/sync/api.js'));
const astModule = await import(pathToFileURL(process.argv[2] + '/dist/ast/index.js'));
const {API} = apiModule, {SyntaxKind: K} = astModule;
const api = new API({cwd:process.argv[3]});
const errors = [];
let nodes = 0;
try {
  const snapshot = api.updateSnapshot({openProjects:[process.argv[3] + '/ast-project.json']});
  const project = snapshot.getProjects()[0];
  const file = project?.program.getSourceFile(process.argv[3] + '/candidate.ts');
  if (!file) throw new Error('TypeScript AST source missing');
  const syntax = project.program.getSyntacticDiagnostics(file.fileName);
  for (const d of syntax) errors.push({message:String(d.messageText),position:d.start ?? 0});
  const fail = (node, message) => {
    const p=file.getLineAndCharacterOfPosition(node.getStart(file));
    errors.push({message,kind:K[node.kind],line:p.line+1,column:p.character+1});
  };
  const allowed = new Set(`SourceFile EndOfFile FunctionDeclaration ExportKeyword Parameter
    AnyKeyword UnknownKeyword ObjectKeyword StringKeyword NumberKeyword BooleanKeyword
    VoidKeyword NeverKeyword TypeReference TypeLiteral PropertySignature IndexSignature
    ArrayType UnionType LiteralType TupleType TypeOperator ReadonlyKeyword
    Block ReturnStatement IfStatement VariableStatement VariableDeclarationList
    VariableDeclaration Identifier NumericLiteral StringLiteral NoSubstitutionTemplateLiteral
    TrueKeyword FalseKeyword NullKeyword ObjectLiteralExpression PropertyAssignment
    ShorthandPropertyAssignment ArrayLiteralExpression SpreadElement SpreadAssignment
    PropertyAccessExpression ElementAccessExpression CallExpression ArrowFunction
    BinaryExpression ParenthesizedExpression PrefixUnaryExpression ConditionalExpression
    ExpressionStatement ForOfStatement BreakStatement ContinueStatement ThrowStatement
    EmptyStatement TypeOfExpression TryStatement CatchClause
    EqualsToken PlusEqualsToken MinusEqualsToken PlusToken MinusToken AsteriskToken SlashToken
    PercentToken LessThanToken GreaterThanToken LessThanEqualsToken GreaterThanEqualsToken
    EqualsEqualsEqualsToken ExclamationEqualsEqualsToken EqualsEqualsToken ExclamationEqualsToken
    AmpersandAmpersandToken BarBarToken QuestionQuestionToken ExclamationToken
    EqualsGreaterThanToken QuestionToken QuestionDotToken ColonToken`.split(/\s+/).map(name=>K[name]));
  const globals = new Set(['Array','Object','Math','Number','String','Boolean']);
  const forbidden = new Set(['__proto__','constructor','prototype','process','global','globalThis',
    'require','module','exports','eval','Function','fetch','console','Buffer','arguments',
    'WebAssembly','Deno','Bun','Proxy','Reflect','Promise','Date','RegExp','Symbol','Intl',
    'setTimeout','setInterval','queueMicrotask','Atomics','SharedArrayBuffer']);
  const methods = new Set(['map','flatMap','filter','find','findIndex','some','every','reduce',
    'slice','concat','includes','indexOf','join','sort','push','pop','shift','unshift','reverse',
    'trim','trimStart','trimEnd','toLowerCase','toUpperCase','startsWith','endsWith','split',
    'substring','substr','charAt','replace','replaceAll','toFixed','toString']);
  const statics = {Array:new Set(['isArray']),Object:new Set(['keys','values','entries','fromEntries']),
    Math:new Set(['abs','min','max','floor','ceil','round','trunc']),
    Number:new Set(['isFinite','isInteger','isSafeInteger','parseInt','parseFloat'])};
  const bound = new Set(['run']), typeNames = new Set(['Record','Array','ReadonlyArray']);
  const gather = node => {
    if (node.kind===K.VariableDeclaration || node.kind===K.Parameter) {
      if (node.name.kind!==K.Identifier) fail(node,'Destructuring is outside the pure JSON subset');
      else {
        const name=String(node.name.text);
        if (globals.has(name)) fail(node,'Built-in bindings cannot be shadowed');
        bound.add(name);
      }
    }
    node.forEachChild(gather);
  };
  gather(file);
  if (file.statements.length!==1 || file.statements[0].kind!==K.FunctionDeclaration)
    fail(file,'Only one exported function run(input) is permitted');
  const fn=file.statements[0];
  if (fn?.kind===K.FunctionDeclaration && (fn.name?.text!=='run' || fn.parameters.length!==1 ||
      !fn.body || fn.modifiers?.length!==1 || fn.modifiers[0].kind!==K.ExportKeyword || fn.asteriskToken))
    fail(fn,'Expected export function run(input): object, synchronous and non-generator');
  if (file.referencedFiles.length || file.typeReferenceDirectives.length || file.libReferenceDirectives.length)
    fail(file,'Reference directives are forbidden');
  const visit = node => {
    nodes++;
    if (nodes>6000) throw new Error('AST node limit exceeded');
    if (!allowed.has(node.kind)) fail(node,'Syntax is outside the pure JSON subset');
    if (node.kind===K.FunctionDeclaration && node!==fn) fail(node,'Nested functions are forbidden');
    if (node.kind===K.Identifier) {
      const name=String(node.text), parent=node.parent;
      if (forbidden.has(name)) fail(node,'Forbidden identifier');
      const property = (parent?.kind===K.PropertyAccessExpression && parent.name===node) ||
        (parent?.kind===K.PropertyAssignment && parent.name===node) ||
        (parent?.kind===K.PropertySignature && parent.name===node);
      if (!property && !bound.has(name) && !globals.has(name) && !typeNames.has(name) && name!=='undefined')
        fail(node,'Unbound identifier');
    }
    if ((node.kind===K.StringLiteral || node.kind===K.NoSubstitutionTemplateLiteral) && forbidden.has(node.text))
      fail(node,'Forbidden property literal');
    if (node.kind===K.ElementAccessExpression && node.argumentExpression?.kind!==K.NumericLiteral)
      fail(node,'Computed property access is forbidden; use named fields or a literal numeric index');
    if (node.kind===K.CallExpression) {
      const callee=node.expression;
      if (callee.kind===K.Identifier) {
        if (!['Number','String','Boolean'].includes(String(callee.text))) fail(node,'Arbitrary function calls are forbidden');
      } else if (callee.kind===K.PropertyAccessExpression) {
        const receiver=callee.expression, method=String(callee.name.text);
        if (receiver.kind===K.Identifier && globals.has(String(receiver.text))) {
          if (!statics[String(receiver.text)]?.has(method)) fail(node,'Built-in method is not permitted');
        } else if (!methods.has(method)) fail(node,'Method is outside the pure JSON subset');
        // Replacement functions can execute arbitrary callbacks; validated arrows remain allowed.
      } else fail(node,'Indirect calls are forbidden');
    }
    if (node.kind===K.ForOfStatement && node.awaitModifier) fail(node,'Async iteration is forbidden');
    if (node.kind===K.ArrowFunction && node.modifiers?.length) fail(node,'Async callbacks are forbidden');
    node.forEachChild(visit);
  };
  visit(file);
  snapshot.dispose();
  process.stdout.write(JSON.stringify({accepted:errors.length===0,nodes,diagnostics:errors.slice(0,80)}));
} catch(e) {
  process.stdout.write(JSON.stringify({accepted:false,nodes,diagnostics:[{message:String(e)}]}));
} finally { api.close(); }
'''

# 固定模块导入与固定 run 调用，不使用 eval / Function / vm。
RUNNER = r'''import {readFileSync} from 'node:fs';
import {run} from './compiled/candidate.js';
function freeze(value) {
  if (value && typeof value==='object') {
    for (const item of Object.values(value)) freeze(item);
    Object.freeze(value);
  }
  return value;
}
try {
  const input=freeze(JSON.parse(readFileSync(0,'utf8')));
  const result=run(input);
  if (!result || typeof result!=='object' || Array.isArray(result)) throw new Error('Output must be a JSON object');
  const text=JSON.stringify(result, (key,value) => {
    if (['__proto__','constructor','prototype'].includes(key)) throw new Error('Forbidden output key');
    if (value===undefined || typeof value==='function' || typeof value==='symbol' || typeof value==='bigint' ||
        (typeof value==='number' && !Number.isFinite(value))) throw new Error('Non-JSON output');
    return value;
  });
  if (Buffer.byteLength(text,'utf8')>1000000) throw new Error('Output byte limit exceeded');
  process.stdout.write(text);
} catch(error) {
  process.stderr.write(String(error).slice(0,1200)); process.exitCode=2;
}
'''


def _private(path: Path | str) -> Path:
    path = Path(path).resolve()
    if not path.is_relative_to((ROOT / '.local').resolve()):
        raise ValueError('生成工具数据必须位于仓库 .local')
    return path


def _hash(path: Path | str) -> str:
    return hashlib.sha256(_private(path).read_bytes()).hexdigest()


def _canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _read(path: Path | str) -> dict:
    value = json.loads(_private(path).read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('生成工具证据必须为 JSON 对象')
    return value


def _write(path: Path | str, value: dict, *, exclusive=True) -> Path:
    path = _private(path)
    with path.open('x' if exclusive else 'w', encoding='utf-8') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    return path


def _freeze(path: Path | str, value: dict) -> Path:
    path = _write(path, value)
    _private(str(path) + '.sha256').write_text(_hash(path), encoding='ascii')
    return path


def _frozen(path: Path | str) -> dict:
    path = _private(path)
    if _private(str(path) + '.sha256').read_text(encoding='ascii').strip() != _hash(path):
        raise ValueError('生成工具冻结证据已变化')
    return _read(path)


def _version() -> dict:
    # 源码与依赖变化必须重新认证。版本哈希不依赖本机绝对路径。
    return {name: hashlib.sha256((SCENE / name).read_bytes()).hexdigest()
            for name in ('generated_tools.py', 'package-lock.json', 'node_modules/typescript/package.json')}


def _json_value(value, depth=0, counter=None):
    counter = [0] if counter is None else counter
    counter[0] += 1
    if depth > 32 or counter[0] > 50000:
        raise ValueError('JSON 深度或节点数量超限')
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for item in value:
            _json_value(item, depth + 1, counter)
        return
    if type(value) is dict:
        for key, item in value.items():
            if not isinstance(key, str) or key in DANGEROUS_KEYS:
                raise ValueError('JSON 含禁止的属性名')
            _json_value(item, depth + 1, counter)
        return
    raise ValueError('仅允许有限 JSON 值')


def _schema(schema: dict, depth=0):
    if (not isinstance(schema, dict) or depth > 16 or set(schema) - SCHEMA_KEYS or
            schema.get('type') not in {'object', 'array', 'string', 'number', 'integer', 'boolean', 'null'}):
        raise ValueError('input_schema 需使用支持的有限 JSON Schema 子集')
    _json_value(schema)
    for key in ('minItems', 'maxItems', 'minLength', 'maxLength'):
        if key in schema and (type(schema[key]) is not int or not 0 <= schema[key] <= 50000):
            raise ValueError('schema 容量约束无效')
    for key in ('minimum', 'maximum'):
        if key in schema and type(schema[key]) not in (int, float):
            raise ValueError('schema 数值约束无效')
    for low, high in (('minimum', 'maximum'), ('minItems', 'maxItems'), ('minLength', 'maxLength')):
        if low in schema and high in schema and schema[low] > schema[high]:
            raise ValueError('schema 约束上下限相反')
    if 'enum' in schema and (not isinstance(schema['enum'], list) or not schema['enum']):
        raise ValueError('schema enum 必须为非空列表')
    if schema['type'] == 'object':
        properties, required = schema.get('properties', {}), schema.get('required', [])
        if (not isinstance(properties, dict) or not isinstance(required, list) or
                any(not isinstance(key, str) or key not in properties for key in required) or
                len(required) != len(set(required))):
            raise ValueError('schema properties/required 无效')
        for item in properties.values():
            _schema(item, depth + 1)
        extra = schema.get('additionalProperties', False)
        if type(extra) is not bool:
            _schema(extra, depth + 1)
    elif schema['type'] == 'array':
        if 'items' not in schema:
            raise ValueError('schema array 必须声明 items')
        _schema(schema['items'], depth + 1)


def _validate(value, schema: dict, location='$'):
    kind = schema['type']
    valid = {'object': type(value) is dict, 'array': type(value) is list,
             'string': type(value) is str, 'number': type(value) in (int, float),
             'integer': type(value) is int, 'boolean': type(value) is bool,
             'null': value is None}[kind]
    if not valid:
        raise ValueError(f'{location} 不符合 schema type={kind}')
    if 'const' in schema and _canonical(value) != _canonical(schema['const']):
        raise ValueError(f'{location} 不符合 const')
    if 'enum' in schema and not any(_canonical(value) == _canonical(item) for item in schema['enum']):
        raise ValueError(f'{location} 不符合 enum')
    if kind == 'object':
        properties = schema.get('properties', {})
        if set(schema.get('required', [])) - set(value):
            raise ValueError(f'{location} 缺少 required 字段')
        for key, item in value.items():
            if key in properties:
                _validate(item, properties[key], location + '.' + key)
            elif schema.get('additionalProperties', False) is False:
                raise ValueError(f'{location} 有未声明字段 {key}')
            elif isinstance(schema['additionalProperties'], dict):
                _validate(item, schema['additionalProperties'], location + '.' + key)
    if kind in {'string', 'array'}:
        low, high = ('minLength', 'maxLength') if kind == 'string' else ('minItems', 'maxItems')
        if len(value) < schema.get(low, 0) or len(value) > schema.get(high, 50000):
            raise ValueError(f'{location} 容量超出 schema')
    if kind == 'array':
        for index, item in enumerate(value):
            _validate(item, schema['items'], location + f'[{index}]')
    if kind in {'integer', 'number'} and (value < schema.get('minimum', -math.inf) or
                                         value > schema.get('maximum', math.inf)):
        raise ValueError(f'{location} 数值超出 schema')


def _evidence(path: str, digest: str) -> dict:
    if not isinstance(path, str) or not Path(path).is_absolute() or not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise ValueError('生成工具证据需私有绝对路径和 SHA256')
    if _hash(path) != digest:
        raise ValueError('生成工具来源/运行证据版本已变化')
    return {'path': str(_private(path)), 'sha256': digest}


def _job(job_path: Path | str, *, write=False) -> tuple[dict, Path]:
    path = _private(job_path)
    job = _read(path)
    if not isinstance(job.get('job_id'), str):
        raise ValueError('生成工具需要明确 job_id')
    if write and (job.get('allow_rsi') is not True or job.get('allow_output') is not True):
        raise ValueError('生成工具需任务明确允许 RSI 和私有输出')
    return job, path.parent / 'generated-tools'


def candidate_status(job_path: Path | str) -> dict:
    _, area = _job(job_path)
    used = sum((area / f'attempt-{index}.json').exists() for index in range(1, LIMIT + 1))
    return {'attempts_used': used, 'attempts_remaining': LIMIT - used,
            'training_closed': (area / 'certification-attempt.json').exists()}


def _reserve(area: Path, job_id: str) -> int:
    area = _private(area)
    area.mkdir(parents=True, exist_ok=True)
    if (area / 'certification-attempt.json').exists():
        raise ValueError('独立认证已开始，禁止根据留出反馈再修改候选')
    for index in range(1, LIMIT + 1):
        try:
            _write(area / f'attempt-{index}.json', {'job_id': job_id, 'attempt': index})
            return index
        except FileExistsError:
            continue
    raise ValueError('生成工具已达持久化 3 次提案上限，失败同样计数')


def _clean_env() -> dict:
    # 编译器/执行器不继承模型密钥或用户 NODE_OPTIONS。
    return {key: os.environ[key] for key in ('PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'LANG')
            if key in os.environ}


def _process(args: list[str], directory: Path, *, data='', timeout=30) -> dict:
    try:
        result = subprocess.run(args, cwd=directory, input=data, text=True, encoding='utf-8',
                                capture_output=True, timeout=timeout, env=_clean_env())
        return {'returncode': result.returncode, 'stdout': result.stdout[:MAX_JSON_BYTES + 1],
                'stderr': result.stderr[-8000:], 'timeout': False}
    except subprocess.TimeoutExpired as error:
        return {'returncode': None, 'stdout': '', 'stderr': str(error)[-1200:], 'timeout': True}


def propose_candidate(job_path: Path | str, candidate: dict, provenance: dict) -> dict:
    """最多三次真实候选编译；失败也落盘，绝不因编译通过自动认证。"""
    job, area = _job(job_path, write=True)
    attempt = _reserve(area, job['job_id'])
    directory = _private(area / ('candidate-' + uuid4().hex))
    directory.mkdir()
    diagnostics = []
    try:
        if (not isinstance(candidate, dict) or set(candidate) != {'name', 'description', 'input_schema', 'code'} or
                not isinstance(candidate['name'], str) or not re.fullmatch(r'read_pinned_[a-z0-9_]{1,48}', candidate['name']) or
                not isinstance(candidate['description'], str) or not 1 <= len(candidate['description']) <= 2000 or
                not isinstance(candidate['code'], str) or not 1 <= len(candidate['code'].encode()) <= MAX_CODE_BYTES):
            raise ValueError('候选须为 name/description/input_schema/code；name 使用 read_pinned_ 前缀')
        _schema(candidate['input_schema'])
        if candidate['input_schema']['type'] != 'object' or candidate['input_schema'].get('additionalProperties') is not False:
            raise ValueError('input_schema 根对象必须 additionalProperties=false')
        _json_value(candidate)
        if re.search(r'@ts-(?:ignore|nocheck|expect-error)|^\s*///', candidate['code'], re.M):
            raise ValueError('禁止 TypeScript 忽略检查或引用指令')
        needed = {'provider', 'model', 'run_id', 'reasoning_effort', 'response_path', 'response_sha256',
                  'trajectory_path', 'trajectory_sha256', 'training_run_ids'}
        if not isinstance(provenance, dict) or set(provenance) != needed or provenance['reasoning_effort'] != 'off':
            raise ValueError('提案 provenance 字段不完整或思考模式未关闭')
        if any(not isinstance(provenance[key], str) or not 1 <= len(provenance[key]) <= 160
               for key in ('provider', 'model', 'run_id')):
            raise ValueError('提案 provider/model/run_id 无效')
        if (not isinstance(provenance['training_run_ids'], list) or not provenance['training_run_ids'] or
                any(not isinstance(item, str) or not item for item in provenance['training_run_ids'])):
            raise ValueError('提案需声明真实训练轨迹 run_id')
        _evidence(provenance['response_path'], provenance['response_sha256'])
        _evidence(provenance['trajectory_path'], provenance['trajectory_sha256'])
        _freeze(directory / 'candidate.json', candidate)
        _freeze(directory / 'provenance.json', provenance)
        (directory / 'candidate.ts').write_text(candidate['code'], encoding='utf-8')
        (directory / 'ast-check.mjs').write_text(AST_CHECKER, encoding='utf-8')
        (directory / 'runner.mjs').write_text(RUNNER, encoding='utf-8')
        _write(directory / 'package.json', {'type': 'module'})
        _write(directory / 'ast-project.json', {'compilerOptions': {'noResolve': True, 'noLib': True, 'types': []},
                                               'files': ['candidate.ts']})
        ast = _process(['node', str(directory / 'ast-check.mjs'), str(SCENE / 'node_modules/typescript'),
                        str(directory)], directory)
        _freeze(directory / 'ast-result.json', ast)
        checked = json.loads(ast['stdout']) if ast['returncode'] == 0 and not ast['timeout'] else {}
        if checked.get('accepted') is not True:
            raise ValueError('AST 拒绝: ' + _canonical(checked.get('diagnostics', [ast['stderr']]))[:3000])
        _write(directory / 'compile-project.json', {'compilerOptions': {'target': 'ES2022', 'module': 'ES2022',
               'strict': True, 'types': [], 'lib': ['ES2022'], 'noResolve': True, 'noEmitOnError': True,
               'skipLibCheck': True, 'outDir': 'compiled'}, 'files': ['candidate.ts']})
        compile_result = _process(['node', str(SCENE / 'node_modules/typescript/lib/tsc.js'),
                                   '--project', str(directory / 'compile-project.json')], directory)
        _freeze(directory / 'compile-result.json', compile_result)
        if compile_result['returncode'] != 0 or compile_result['timeout'] or not (directory / 'compiled/candidate.js').exists():
            raise ValueError('TypeScript 编译失败: ' + compile_result['stdout'][-3000:] + compile_result['stderr'][-1000:])
        files = ['candidate.json', 'provenance.json', 'candidate.ts', 'runner.mjs', 'ast-check.mjs',
                 'package.json', 'ast-project.json', 'compile-project.json', 'compiled/candidate.js',
                 'ast-result.json', 'compile-result.json']
        manifest = {'schema_version': 1, 'job_path': str(_private(job_path)), 'job_id': job['job_id'],
                    'attempt': attempt, 'tool_name': candidate['name'], 'version': _version(),
                    'files': {name: _hash(directory / name) for name in files}, 'compiled': True,
                    'code_sha256': _hash(directory / 'candidate.ts'),
                    'input_schema_sha256': hashlib.sha256(_canonical(candidate['input_schema']).encode()).hexdigest()}
        _freeze(directory / 'manifest.json', manifest)
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as error:
        diagnostics.append(str(error))
    result = {'candidate_path': str(directory / 'manifest.json') if not diagnostics else None,
              'attempt': attempt, 'attempts_remaining': LIMIT - attempt, 'compile_passed': not diagnostics,
              'certified': False, 'diagnostics': diagnostics, 'diagnostic_path': str(directory / 'proposal-result.json')}
    _freeze(directory / 'proposal-result.json', result)
    return result


def _load(candidate_path: Path | str) -> tuple[dict, dict, Path]:
    path = _private(candidate_path)
    manifest = _frozen(path)
    if manifest.get('schema_version') != 1 or manifest.get('compiled') is not True or manifest.get('version') != _version():
        raise ValueError('生成工具宿主或编译器版本变化，需重新认证')
    directory = path.parent
    for name, digest in manifest['files'].items():
        if _hash(directory / name) != digest:
            raise ValueError('生成工具代码/schema/编译产物或诊断证据已变化')
    candidate = _frozen(directory / 'candidate.json')
    _frozen(directory / 'provenance.json')
    job, _ = _job(manifest['job_path'], write=True)
    if job['job_id'] != manifest['job_id']:
        raise ValueError('生成工具任务权限或身份已变化')
    return manifest, candidate, directory


def run_candidate(candidate_path: Path | str, value: dict) -> dict:
    """实际调用冻结 JS 模块；仅供训练/认证，MCP 使用 run_certified_tool。"""
    manifest, candidate, directory = _load(candidate_path)
    _json_value(value)
    _validate(value, candidate['input_schema'])
    raw = _canonical(value)
    if len(raw.encode()) > MAX_JSON_BYTES:
        raise ValueError('生成工具输入超过 1MB')
    result = _process(['node', '--experimental-permission', '--allow-fs-read=' + str(directory),
                       '--disable-proto=throw', '--disallow-code-generation-from-strings',
                       '--frozen-intrinsics', '--max-old-space-size=64', str(directory / 'runner.mjs')],
                      directory, data=raw, timeout=4)
    record = {'candidate_manifest_sha256': _hash(candidate_path),
              'input_sha256': hashlib.sha256(raw.encode()).hexdigest(), **result}
    log = directory / ('run-' + uuid4().hex + '.json')
    _freeze(log, record)
    if result['returncode'] != 0 or result['timeout']:
        raise ValueError('生成工具真实执行失败，私有诊断: ' + str(log) + '; ' + result['stderr'][-1200:])
    try:
        output = json.loads(result['stdout'])
    except json.JSONDecodeError as error:
        raise ValueError('生成工具输出不是完整 JSON 对象') from error
    _json_value(output)
    if not isinstance(output, dict):
        raise ValueError('生成工具输出必须为 JSON 对象')
    # 防止运行期间替换代码或来源证据。
    _load(candidate_path)
    return {'output': output, 'execution_evidence': str(log), 'execution_sha256': _hash(log),
            'code_sha256': manifest['code_sha256'], 'input_schema_sha256': manifest['input_schema_sha256']}


def evaluate_candidate(candidate_path: Path | str, cases: list[dict], *, split='train') -> dict:
    """真实执行候选并与独立导出的 reference JSON 比较；不调用模型。"""
    manifest, _, directory = _load(candidate_path)
    if split not in {'train', 'heldout'} or not isinstance(cases, list) or not 1 <= len(cases) <= 20:
        raise ValueError('评测需 train/heldout 和 1–20 个真实用例')
    rows, ids, references = [], set(), []
    for case in cases:
        fields = {'id', 'task_id', 'run_id', 'input_path', 'input_sha256', 'expected_path', 'expected_sha256', 'source_evidence'}
        if (not isinstance(case, dict) or set(case) != fields or
                any(not isinstance(case[key], str) or not 1 <= len(case[key]) <= 160 for key in ('id', 'task_id', 'run_id')) or
                case['id'] in ids or not isinstance(case['source_evidence'], list) or not case['source_evidence']):
            raise ValueError('评测用例字段无效或重复')
        ids.add(case['id'])
        refs = [_evidence(case['input_path'], case['input_sha256']), _evidence(case['expected_path'], case['expected_sha256'])]
        for source in case['source_evidence']:
            if not isinstance(source, dict) or set(source) != {'path', 'sha256'}:
                raise ValueError('source_evidence 需 path/sha256')
            refs.append(_evidence(source['path'], source['sha256']))
        references.extend(refs)
        try:
            executed = run_candidate(candidate_path, _read(case['input_path']))
            expected = _read(case['expected_path'])
            passed = _canonical(executed['output']) == _canonical(expected)
            row = {**case, 'passed': passed, 'execution_evidence': executed['execution_evidence'],
                   'execution_sha256': executed['execution_sha256'],
                   'output_sha256': hashlib.sha256(_canonical(executed['output']).encode()).hexdigest(),
                   'diagnostics': [] if passed else ['真实输出与独立 reference JSON 不一致']}
        except ValueError as error:
            row = {**case, 'passed': False, 'diagnostics': [str(error)]}
        rows.append(row)
    result = {'schema_version': 1, 'split': split, 'candidate_path': str(_private(candidate_path)),
              'candidate_sha256': _hash(candidate_path), 'version': manifest['version'],
              'passed': all(row['passed'] for row in rows), 'cases': rows, 'references': references,
              'quality_scope': 'pure_json_functional_reference_comparison; not scientific or aesthetic certification'}
    path = _freeze(directory / ('evaluation-' + split + '-' + uuid4().hex + '.json'), result)
    return {'evaluation_path': str(path), 'evaluation_sha256': _hash(path), 'passed': result['passed'], 'cases': rows}


def _evaluation(path: Path | str, candidate_path: Path | str) -> dict:
    value = _frozen(path)
    if (value.get('schema_version') != 1 or value.get('candidate_path') != str(_private(candidate_path)) or
            value.get('candidate_sha256') != _hash(candidate_path) or value.get('version') != _version()):
        raise ValueError('功能评测与当前候选版本不一致')
    for reference in value['references']:
        _evidence(reference['path'], reference['sha256'])
    for row in value['cases']:
        if row.get('execution_evidence'):
            _evidence(row['execution_evidence'], row['execution_sha256'])
            execution = _frozen(row['execution_evidence'])
            actual = json.loads(execution['stdout'])
            if (execution['returncode'] != 0 or execution['timeout'] or
                    row['output_sha256'] != hashlib.sha256(_canonical(actual).encode()).hexdigest() or
                    bool(row['passed']) != (_canonical(actual) == _canonical(_read(row['expected_path'])))):
                raise ValueError('功能评测真实执行结果与 reference 不一致')
    if value.get('passed') is not all(row.get('passed') is True for row in value['cases']):
        raise ValueError('功能评测通过状态无效')
    return value


def certify_candidate(candidate_path: Path | str, training_path: Path | str, heldout_cases: list[dict]) -> dict:
    """冻结训练后只做一次独立认证；失败不激活、不继续使用留出修订。"""
    manifest, _, directory = _load(candidate_path)
    training = _evaluation(training_path, candidate_path)
    provenance = _frozen(directory / 'provenance.json')
    if training['split'] != 'train' or training['passed'] is not True or len(training['cases']) < 2:
        raise ValueError('晋级需至少两个真实训练用例全部通过')
    if provenance['provider'] in {'engineering-diagnostic', 'synthetic', 'mock'}:
        raise ValueError('工程诊断候选不可作为真实模型生成工具晋级')
    train_runs = {row['run_id'] for row in training['cases']} | set(provenance['training_run_ids']) | {provenance['run_id']}
    train_tasks = {row['task_id'] for row in training['cases']}
    train_sources = {item['sha256'] for row in training['cases'] for item in row['source_evidence']}
    if not isinstance(heldout_cases, list) or not heldout_cases:
        raise ValueError('晋级需独立留出用例')
    for case in heldout_cases:
        if (not isinstance(case, dict) or case.get('run_id') in train_runs or case.get('task_id') in train_tasks or
                any(item.get('sha256') in train_sources for item in case.get('source_evidence', []))):
            raise ValueError('认证任务/run/source 必须独立于训练与提案')
    _, area = _job(manifest['job_path'], write=True)
    try:
        _freeze(area / 'certification-attempt.json', {'candidate_path': str(_private(candidate_path)),
                  'candidate_sha256': _hash(candidate_path), 'training_path': str(_private(training_path)),
                  'training_sha256': _hash(training_path)})
    except FileExistsError as error:
        raise ValueError('独立认证仅允许一次；保留失败证据并使用旧工具') from error
    heldout_result = evaluate_candidate(candidate_path, heldout_cases, split='heldout')
    if not heldout_result['passed']:
        return {'certified': False, 'heldout_evaluation': heldout_result, 'certificate_path': None}
    certificate = {'schema_version': 1, 'candidate_path': str(_private(candidate_path)),
                   'candidate_sha256': _hash(candidate_path), 'training_path': str(_private(training_path)),
                   'training_sha256': _hash(training_path), 'heldout_path': heldout_result['evaluation_path'],
                   'heldout_sha256': heldout_result['evaluation_sha256'], 'version': _version(),
                   'code_sha256': manifest['code_sha256'], 'input_schema_sha256': manifest['input_schema_sha256'],
                   'functional_certified': True, 'generated_tool': True, 'learned_motif': False,
                   'quality_scope': 'real_json_reference_correctness_only; domain_oracle_required'}
    path = _freeze(directory / 'certificate.json', certificate)
    return {'certified': True, 'heldout_evaluation': heldout_result, 'certificate_path': str(path),
            'certificate_sha256': _hash(path)}


def load_certified_tool(certificate_path: Path | str) -> dict:
    certificate = _frozen(certificate_path)
    if (certificate.get('schema_version') != 1 or certificate.get('functional_certified') is not True or
            certificate.get('version') != _version()):
        raise ValueError('生成工具缺少有效独立认证')
    candidate_path = certificate['candidate_path']
    manifest, candidate, directory = _load(candidate_path)
    if certificate['candidate_sha256'] != _hash(candidate_path):
        raise ValueError('认证候选版本变化')
    for key in ('training', 'heldout'):
        _evidence(certificate[key + '_path'], certificate[key + '_sha256'])
        evaluation = _evaluation(certificate[key + '_path'], candidate_path)
        if evaluation['split'] != ('train' if key == 'training' else 'heldout') or evaluation['passed'] is not True:
            raise ValueError('认证缺少真实通过的训练/独立留出执行证据')
    provenance = _frozen(directory / 'provenance.json')
    _evidence(provenance['response_path'], provenance['response_sha256'])
    _evidence(provenance['trajectory_path'], provenance['trajectory_sha256'])
    return {'name': candidate['name'], 'description': candidate['description'],
            'input_schema': copy.deepcopy(candidate['input_schema']), 'candidate_path': candidate_path,
            'code_sha256': manifest['code_sha256'], 'input_schema_sha256': manifest['input_schema_sha256'],
            'certificate_path': str(_private(certificate_path)), 'certificate_sha256': _hash(certificate_path),
            'functional_certified': True, 'learned_motif': False}


def run_certified_tool(certificate_path: Path | str, value: dict) -> dict:
    tool = load_certified_tool(certificate_path)
    result = run_candidate(tool['candidate_path'], value)
    load_certified_tool(certificate_path)
    return {**result, 'tool_name': tool['name'], 'certificate_sha256': tool['certificate_sha256']}
