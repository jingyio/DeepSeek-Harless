"""V9 条件结构离线准备/独立认证。没有云调用，没有手写待发布 Motif。

prepare 只输出真实正常轨迹中的参数机会；模型提案由外部运行器负责。
certify 使用真实 MCP 与独立全计划读取 oracle。边界负例是协议输入反例，
其中权限/来源/工具失败还实际调用 MCP；不把这些边界反例当正常科研任务。
生成候选、认证通过都不等于真实旁路、科研合格或成本收益。
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
import copy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SCENE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from src.adapters.task_identity import load_trace_identity, require_distinct_decisions
from src.adapters.dsh_trajectory import ToolContract, extract_dsh_trace, infer_dsh_provenance
from scenarios.research_ppt.motif_v6 import schema_tools
from scenarios.research_ppt.documents import file_hash
from scenarios.research_ppt.delivery_smoke import params

PIN = 'mcp__ppt__pin_deck_pages'
READ = 'mcp__ppt__read_pinned_deck_pages'
ANCHORS = (PIN, READ, 'mcp__ppt__inspect_deck', 'mcp__ppt__read_deck_plan')
NEGATIVES = ('missing_state', 'conflicting_arguments', 'permission_changed', 'dependency_changed',
             'source_changed', 'schema_changed', 'tool_failure', 'result_scope_changed')
HASH = re.compile(r'^[a-f0-9]{64}$')
MANDATORY_DEPENDENCIES = tuple('scenarios/research_ppt/' + name for name in (
    'service.py', 'server.py', 'delivery_server.py', 'recovery.py', 'documents.py', 'revision.py', 'validation.py',
    'restyle.py', 'generated_tools.py', 'figure_catalog.py', 'layout_learning.py', 'document_cache.py',
    'evidence.py', 'evidence.schema.json', 'contracts.json', 'version-fields.json', 'delivery-contracts.json',
    'delivery-version-fields.json', 'package-lock.json', 'dist/render.js', 'dist/layout-policy.js',
    'dist/layout-policy-cli.js', 'dist/delivery-adapter.js', 'dist/mcp-adapter.js', 'ts/delivery-adapter.ts',
    'ts/mcp-adapter.ts', 'ts/conditional-continuation.ts', 'dist/conditional-continuation.js',
    'ts/conditional-probe-cli.ts', 'dist/conditional-probe-cli.js', 'conditional-continuation.schema.json',
    'conditional_learning.py')) + ('package-lock.json', 'src/adapters/dsh_online_motif.mjs',
        'src/adapters/dsh_scenario_guard.mjs', 'src/adapters/harness_runtime.py', 'src/motif_core/online_skill_runtime.mjs')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _pairs(rows):
    result = {}
    for key, value in rows:
        if key in result:
            raise ValueError('重复 JSON 字段不能作为认证输入')
        result[key] = value
    return result


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=_pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('非有限 JSON 数值')))


def private(path, exists=False):
    full = Path(path).resolve(strict=exists)
    if not full.is_relative_to((ROOT / '.local').resolve()):
        raise ValueError('轨迹、候选、认证材料和原始证据只能位于 .local')
    return full


def write_new(path, value):
    path = private(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    path.chmod(0o600)


def dependencies(paths):
    result = {}
    for path in [*(ROOT / name for name in MANDATORY_DEPENDENCIES), *paths]:
        full = Path(path).resolve(strict=True)
        if not full.is_relative_to(ROOT) or full.is_relative_to(ROOT / '.local') or not full.is_file():
            raise ValueError('实现依赖必须是仓库公共文件，不能是候选私人数据')
        result[full.relative_to(ROOT).as_posix()] = file_hash(full)
    if not result or len(result) > 40:
        raise ValueError('须冻结1–40个实现依赖')
    return result


def probe(request):
    node = shutil.which('node')
    script = SCENE / 'dist/conditional-probe-cli.js'
    if not node or not script.is_file():
        raise ValueError('请先 build TypeScript 条件协议')
    result = subprocess.run([node, str(script)], cwd=ROOT, input=json.dumps(request, ensure_ascii=False,
        allow_nan=False), text=True, encoding='utf-8', capture_output=True, timeout=15)
    try:
        value = json.loads(result.stdout)
    except ValueError as exc:
        raise ValueError('TS 协议探针没有返回独立可解析结果') from exc
    if result.returncode or value.get('ok') is not True:
        raise ValueError('TS 拒绝了候选/认证协议')
    return value['result']


def load_run(directory, schema_path):
    directory = private(directory, True)
    identity = load_trace_identity(directory / 'task-identity.json', directory / 'agent-events.jsonl', ROOT / '.local')
    manifest, metrics = read(directory / 'manifest.json'), read(directory / 'metrics.json')
    ledger = [json.loads(line, object_pairs_hook=_pairs) for line in (directory / 'cost-ledger.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    if manifest.get('mode') != 'baseline' or manifest.get('model_call_enabled') is not True \
        or manifest.get('reasoning_effort') != 'off' or metrics.get('status') != 'done' \
        or type(metrics.get('upstream_requests')) is not int or metrics['upstream_requests'] < 1 \
        or not any(row.get('response_status') == 200 and isinstance(row.get('response_usage'), dict) and row['response_usage'].get('total_tokens', 0) > 0 for row in ledger):
        raise ValueError('学习只接收正常完成的付费 baseline 原始轨迹；模拟/旁路/预览不得冒充训练')
    payload = read(private(schema_path, True))
    if isinstance(payload, dict) and isinstance(payload.get('actual_tools'), list):
        # 可靠 TS MCP 的真实导出保留原始短名；这里仅绑定 Harness 名称，不改 schema。
        schema = [{**row, 'name': row['name'] if row['name'].startswith('mcp__ppt__') else 'mcp__ppt__' + row['name']}
                  for row in payload['actual_tools']]
    else:
        schema = schema_tools(payload)['tools']
    offered = {}
    for row in schema:
        name = row['name']
        if not name.startswith('mcp__ppt__') or name in offered or not isinstance(row.get('inputSchema'), dict):
            raise ValueError('实际 schema 名称/类型错误或重复')
        offered[name] = row
    contracts = {}
    fields = ('source_id', 'deck_id', 'input_version', 'file_sha256', 'version_sha256', 'pages_csv')
    for name, row in offered.items():
        read_only = row.get('annotations', {}).get('readOnlyHint') is True
        contracts[name] = ToolContract(tuple(row['inputSchema'].get('required', [])), read_only,
            output_fields=fields, provenance_params=('source_id',) if name == READ else ())
    events = [json.loads(line, object_pairs_hook=_pairs) for line in (directory / 'agent-events.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    trace = extract_dsh_trace(events, contracts, trace_id=directory.name,
        task_fingerprint=identity['question_sha256'], provenance_by_call_id=infer_dsh_provenance(events, contracts))
    return {'directory': str(directory), 'schema_path': str(Path(schema_path).resolve()), 'identity': identity,
            'offered': offered, 'records': [asdict(row) for row in trace.records]}


def opportunities(run):
    """仅找有实际句柄边与同版本结果的受限路径；不跨失败/写操作屏障。"""
    result, records = [], run['records']
    for index, anchor in enumerate(records):
        if not anchor['eligible'] or anchor['name'] not in ANCHORS or not anchor['observation']:
            continue
        ao = anchor['observation']
        version_field = 'version_sha256' if anchor['name'] in (PIN, READ) else 'input_version'
        version, deck, deck_sha = ao.get(version_field), ao.get('deck_id'), ao.get('file_sha256')
        if not isinstance(deck, str) or not isinstance(version, str) or not HASH.fullmatch(version) or not isinstance(deck_sha, str) or not HASH.fullmatch(deck_sha):
            continue
        continuation, pinned = [], anchor if anchor['name'] == PIN else None
        for row in records[index + 1:]:
            if not row['eligible']:
                break
            output, args = row['observation'], row['arguments']
            if not output or not args:
                break
            if row['name'] == PIN and pinned is None and args.get('deck_id') == deck:
                if output.get('deck_id') != deck or output.get('file_sha256') != deck_sha or output.get('version_sha256') != version:
                    break
                pinned = row
                continuation.append(row)
            elif row['name'] == READ and pinned is not None and args.get('source_id') == pinned['observation'].get('source_id'):
                pages = pinned['observation'].get('pages_csv')
                scope = {'deck_id': deck, 'deck_sha256': deck_sha, 'input_version': version, 'pages_csv': pages}
                if not row.get('parameter_sources') or row['parameter_sources'].get('source_id') != {'from_tool': PIN, 'from_field': 'source_id'}:
                    break
                if _result_matches(output, 'read_pages', args, scope) and pinned['arguments'] == {'deck_id': deck, 'pages_csv': pages}:
                    continuation.append(row)
                    result.append({'anchor': anchor, 'continuation': continuation, 'scope': scope,
                        'input_version_field': version_field, 'task_fingerprint': run['identity']['question_sha256'],
                        'decision_id': run['identity']['research_decision_id']})
                break
            if len(continuation) >= 3:
                break
    return result


def prepare(train, dependency_paths, out):
    if len(train) != 2:
        raise ValueError('V9 首版只允许恰好两个正常独立训练决定')
    runs = [load_run(directory, schema) for directory, schema in train]
    require_distinct_decisions([run['identity'] for run in runs])
    evidence = [opportunity for run in runs for opportunity in opportunities(run)]
    shared = set(runs[0]['offered']) & set(runs[1]['offered'])
    frozen = {name: runs[0]['offered'][name] for name in shared
        if digest(runs[0]['offered'][name]) == digest(runs[1]['offered'][name])}
    report = {'schema_version': 1, 'status': 'opportunities_only_not_learned_or_certified',
        'training': {'task_fingerprints': [r['identity']['question_sha256'] for r in runs],
                     'trace_sha256': [r['identity']['events_sha256'] for r in runs]},
        'identities': [r['identity'] for r in runs], 'sources': [{'directory': r['directory'], 'schema_path': r['schema_path'],
            'schema_sha256': file_hash(Path(r['schema_path']))} for r in runs],
        'dependencies': dependencies(dependency_paths), 'offered': frozen, 'opportunities': evidence,
        'scope': 'model must propose predicate/branches from normal evidence; no preset calls',
        'candidate_limit': 3, 'quality': 'not_reviewed', 'real_bypass_observed': False}
    coverage = {tuple([o['anchor']['name']] + [n['name'] for n in o['continuation']]) for o in evidence}
    report['independent_shared_paths'] = [list(path) for path in sorted(coverage) if len({o['decision_id'] for o in evidence
        if tuple([o['anchor']['name']] + [n['name'] for n in o['continuation']]) == path}) == 2]
    if not report['independent_shared_paths']:
        report['status'] = 'abstain_no_independent_natural_opportunity'
    write_new(out, report)
    return report


def _same_scalar(a, b):
    return type(a) is type(b) and isinstance(a, (str, bool, int)) and a == b


def _scope_matches(output, scope, version_field):
    return isinstance(output, dict) and output.get('deck_id') == scope['deck_id'] and output.get('file_sha256') == scope['deck_sha256'] \
        and output.get(version_field) == scope['input_version'] and ('pages_csv' not in output or output['pages_csv'] == scope['pages_csv'])


def _result_matches(output, contract, args, scope):
    if not isinstance(output, dict) or output.get('isError') is True or output.get('ok') is False or output.get('error') \
        or not _scope_matches(output, scope, 'version_sha256') or not isinstance(output.get('source_id'), str) or not output['source_id']:
        return False
    if contract == 'pinned_pages':
        return output.get('pages_csv') == scope['pages_csv'] and output.get('scope') == 'explicit_pages_from_current_persisted_plan'
    try:
        pages = [int(p) for p in scope['pages_csv'].split(',')]
    except (ValueError, AttributeError):
        return False
    slides = output.get('slides')
    return output.get('source_id') == args.get('source_id') and output.get('scope') == 'explicit_pages_only_no_semantic_selection' \
        and type(output.get('total_slides')) is int and output['total_slides'] >= max(pages) and isinstance(slides, list) \
        and all(isinstance(row, dict) and isinstance(row.get('slide'), dict) for row in slides) and [row.get('page') for row in slides] == pages


def validate_candidate(candidate_path, bundle_path):
    candidate, bundle = read(private(candidate_path, True)), read(private(bundle_path, True))
    probe({'op': 'validate', 'candidate': candidate})
    if not set(MANDATORY_DEPENDENCIES).issubset(candidate['dependencies']):
        raise ValueError('候选未绑定实际执行/证据/场景守卫依赖，不能用无关文件摘要冒充版本守卫')
    if candidate.get('origin') != 'learned' or bundle.get('status') != 'opportunities_only_not_learned_or_certified' \
        or candidate['training'] != bundle['training'] or candidate['dependencies'] != bundle['dependencies']:
        raise ValueError('候选必须绑定两个正常独立训练的原始证据与当前实现')
    regenerated, runs = [], []
    for row in bundle['sources']:
        run = load_run(row['directory'], row['schema_path'])
        runs.append(run)
        if run['identity'] not in bundle['identities'] or file_hash(Path(row['schema_path'])) != row['schema_sha256']:
            raise ValueError('训练证据/实际schema锁变化')
        regenerated.extend(opportunities(run))
    if bundle['opportunities'] != regenerated:
        raise ValueError('训练机会必须由锁定原始轨迹重新推导，不能相信候选改写后的机会')
    require_distinct_decisions([run['identity'] for run in runs])
    actual_training = {'task_fingerprints': [run['identity']['question_sha256'] for run in runs],
                       'trace_sha256': [run['identity']['events_sha256'] for run in runs]}
    if len(runs) != 2 or bundle['training'] != actual_training or bundle['identities'] != [run['identity'] for run in runs]:
        raise ValueError('候选训练身份必须来自两个实际原始运行，不能自报独立fingerprint')
    shared = set(runs[0]['offered']) & set(runs[1]['offered'])
    actual_offered = {name: runs[0]['offered'][name] for name in shared
        if digest(runs[0]['offered'][name]) == digest(runs[1]['offered'][name])}
    if bundle['offered'] != actual_offered:
        raise ValueError('候选不能改写原始MCP schema/只读权限快照')
    for path, expected in candidate['dependencies'].items():
        target = (ROOT / path).resolve(strict=True)
        if not target.is_relative_to(ROOT) or target.is_relative_to(ROOT / '.local') or file_hash(target) != expected:
            raise ValueError('实现依赖发生变化')
    for tool, contract in candidate['contracts'].items():
        real = bundle['offered'].get(tool)
        if not real or real.get('annotations', {}).get('readOnlyHint') is not True or real['inputSchema'] != contract['input_schema']:
            raise ValueError('候选不能发明只读权限或工具schema')
    support = {branch: set() for branch in ('on_equal', 'on_unequal')}
    for observed in bundle['opportunities']:
        if observed['anchor']['name'] != candidate['anchor']['tool']:
            continue
        predicate = candidate['anchor']['predicate']
        output = observed['anchor']['observation']
        if predicate['field'] not in output or type(output[predicate['field']]) is not type(predicate['value']):
            continue
        branch = 'on_equal' if _same_scalar(output[predicate['field']], predicate['value']) else 'on_unequal'
        nodes = candidate['branches'][branch]
        if not nodes or [node['tool'] for node in nodes] != [row['name'] for row in observed['continuation']]:
            continue
        values, matched = {}, True
        for node, row in zip(nodes, observed['continuation'], strict=True):
            bound = {}
            for key, binding in node['bindings'].items():
                source = observed['scope'] if binding['from'] == 'task' else output if binding['from'] == 'anchor' else values.get(binding['node_id'], {})
                bound[key] = source.get(binding['field'])
            if bound != row['arguments'] or not _result_matches(row['observation'], node['output_contract'], bound, observed['scope']):
                matched = False
                break
            values[node['id']] = row['observation']
        if matched:
            support[branch].add(observed['decision_id'])
    for branch, nodes in candidate['branches'].items():
        if nodes and len(support[branch]) < 2:
            raise ValueError('每个执行分支必须有两独立训练的完整实际参数/结果证据')
    return candidate, bundle, {'status': 'validated_candidate_not_certified',
        'branch_support': {key: sorted(value) for key, value in support.items()},
        'empty_branch': 'conservative semantic deferral, not claimed learned behavior'}


def oracle(candidate, task, live, history, offered):
    """独立 Python 小 oracle，只产下一工具/完整参数或 abstain；不运行生成代码。"""
    if digest(task) != digest(live) or candidate['dependencies'] != live['dependencies']:
        return None
    offered = dict(offered)
    for name, contract in candidate['contracts'].items():
        if name not in task['allowed_tools'] or name not in offered or offered[name].get('parameters') != contract['input_schema'] \
            or offered[name].get('annotations', {}).get('readOnlyHint') is False:
            return None
    barrier = max((i for i, row in enumerate(history) if row.get('barrier')), default=-1)
    rows = history[barrier + 1:]
    anchors = [i for i, row in enumerate(rows) if row['name'] == candidate['anchor']['tool']]
    if not anchors:
        return None
    cursor = anchors[-1]
    anchor = rows[cursor]
    output, args = anchor.get('output'), anchor.get('arguments', {})
    if not anchor.get('ok') or not _scope_matches(output, task, candidate['anchor']['input_version_field']) \
        or (args.get('deck_id') is not None and args['deck_id'] != task['deck_id']) \
        or (args.get('pages_csv') is not None and args['pages_csv'] != task['pages_csv']) \
        or set(args) != set(candidate['contracts'][anchor['name']]['input_schema']['required']):
        return None
    p = candidate['anchor']['predicate']
    if p['field'] not in output or type(output[p['field']]) is not type(p['value']):
        return None
    branch = 'on_equal' if _same_scalar(output[p['field']], p['value']) else 'on_unequal'
    witnessed = {}
    for node in candidate['branches'][branch]:
        arguments = {}
        for key, binding in node['bindings'].items():
            source = task if binding['from'] == 'task' else output if binding['from'] == 'anchor' else witnessed.get(binding['node_id'], {})
            value = source.get(binding['field'])
            if not isinstance(value, str) or not value or len(value) > 500 or any(ord(ch) < 32 for ch in value):
                return None
            arguments[key] = value
        matches = [(i, row) for i, row in enumerate(rows) if i > cursor and row['name'] == node['tool'] and row['arguments'] == arguments]
        if not matches:
            return node['tool'], arguments, branch
        if any(not row['ok'] or not _result_matches(row['output'], node['output_contract'], arguments, task) for _, row in matches) \
            or len({digest(row['output']) for _, row in matches}) != 1:
            return None
        cursor, match = matches[-1]
        witnessed[node['id']] = match['output']
    return None


def ts_decide(candidate, task, live, history, offered):
    return probe({'op': 'propose', 'input': {'candidate': candidate, 'task': task, 'liveGuard': live,
        'history': history, 'availableTools': offered, 'mode': 'shadow'}})


def compare(candidate, task, live, history, offered):
    expected = oracle(candidate, task, live, history, offered)
    actual = ts_decide(candidate, task, live, history, offered)
    if expected is None:
        if actual['kind'] != 'abstain':
            raise ValueError('TS 在独立 oracle 弃权状态提出了调用')
    elif actual['kind'] != 'shadow' or len(actual['proposals']) != 1 or (actual['proposals'][0]['tool'], actual['proposals'][0]['arguments'], actual['proposals'][0]['branch']) != expected:
        raise ValueError('Python/TS 条件或参数流不一致')
    return actual


@contextmanager
def mutated(path, data):
    original = path.read_bytes()
    if original == data:
        raise ValueError('边界诊断必须实际改变字节')
    try:
        path.write_bytes(data)
        yield
    finally:
        path.write_bytes(original)


class Certifier:
    def __init__(self, out):
        self.out, self.calls, self.checks = out, [], []

    async def call(self, client, name, args, allow_error=False):
        value = (await client.call_tool(name.removeprefix('mcp__ppt__'), args)).model_dump(mode='json', by_alias=True)
        output = value.get('structuredContent')
        if not isinstance(output, dict):
            blocks = [row for row in value.get('content', []) if row.get('type') == 'text']
            output = json.loads(blocks[0]['text']) if len(blocks) == 1 else None
        error = value.get('isError') is True or not isinstance(output, dict) or output.get('ok') is False or bool(output.get('error'))
        self.calls.append({'name': name, 'arguments': args, 'response': value, 'error': error})
        if error and not allow_error:
            raise ValueError('实际 MCP 拒绝认证调用')
        return output, error

    def check(self, name, condition, evidence):
        self.checks.append({'name': name, 'passed': bool(condition), 'evidence': evidence})
        if not condition:
            raise ValueError('独立认证检查失败: ' + name)

    async def case(self, candidate, case, identity, isolated_root):
        from mcp import Client
        job = private(case['job'], True)
        data = read(job)
        source_paths = [private(row['path'], True) for row in data['inputs']]
        if not job.is_relative_to(isolated_root) or not all(path.is_relative_to(isolated_root) for path in source_paths):
            raise ValueError('认证诊断只允许 suite 的独立副本，不能改训练/评测源文件')
        async with Client(params(job), read_timeout_seconds=180) as client:
            schemas = [tool.model_dump(mode='json', by_alias=True) for tool in (await client.list_tools()).tools]
            offered = [[f"mcp__ppt__{row['name']}", {'parameters': row['inputSchema'], 'annotations': row.get('annotations', {})}] for row in schemas]
            full, _ = await self.call(client, 'mcp__ppt__read_deck_plan', {'deck_id': case['deck_id']})
            task = {'schema_version': 1, 'session_id': 'independent-certifier', 'task_fingerprint': identity['question_sha256'],
                'input_version': full['input_version'], 'deck_id': full['deck_id'], 'deck_sha256': full['file_sha256'],
                'pages_csv': case['pages_csv'], 'job_sha256': file_hash(job),
                'permission_sha256': digest({'allow_output': data['allow_output'], 'allowed_tools': [row[0] for row in offered]}),
                'dependencies': copy.deepcopy(candidate['dependencies']), 'allowed_tools': [row[0] for row in offered]}
            probe({'op': 'validate', 'candidate': candidate, 'guard': task})
            name = candidate['anchor']['tool']
            if name in (PIN, READ):
                pinned, _ = await self.call(client, PIN, {'deck_id': task['deck_id'], 'pages_csv': task['pages_csv']})
                args = {'deck_id': task['deck_id'], 'pages_csv': task['pages_csv']} if name == PIN else {'source_id': pinned['source_id']}
                anchor = pinned if name == PIN else (await self.call(client, READ, args))[0]
            else:
                args = {'deck_id': task['deck_id']}
                anchor = (await self.call(client, name, args))[0]
            history = [{'name': name, 'callId': 'actual-independent-anchor', 'ok': True,
                'arguments': args, 'output': anchor, 'inputVersion': task['input_version']}]
            predicate = candidate['anchor']['predicate']
            if predicate['field'] not in anchor or type(anchor[predicate['field']]) is not type(predicate['value']):
                raise ValueError('独立实际状态无法核验候选条件')
            branch = 'on_equal' if _same_scalar(anchor[predicate['field']], predicate['value']) else 'on_unequal'
            base = copy.deepcopy(history)
            for _ in range(4):
                result = compare(candidate, task, task, history, offered)
                if result['kind'] == 'abstain':
                    break
                p = result['proposals'][0]
                output, _ = await self.call(client, p['tool'], p['arguments'])
                verification = probe({'op': 'verify', 'proposal': p, 'execution': {'name': p['tool'], 'arguments': p['arguments']},
                    'output': output, 'liveGuard': task})
                self.check('actual_result_scope', verification['verified'] and _result_matches(output, p['output_contract'], p['arguments'], task), {'tool': p['tool']})
                if p['tool'] == READ:
                    pages = [int(page) for page in task['pages_csv'].split(',')]
                    expected = [{'page': page, 'slide': full['plan']['slides'][page - 1]} for page in pages]
                    self.check('independent_full_plan_projection', output['slides'] == expected, {'pages': pages})
                history.append({'name': p['tool'], 'callId': 'actual-' + p['node_id'], 'ok': True,
                    'arguments': p['arguments'], 'output': output, 'inputVersion': task['input_version']})
            else:
                raise ValueError('认证子图未在有限步数结束')
            self.check('branch:' + branch, compare(candidate, task, task, history, offered)['kind'] == 'abstain', {'actual_predicate': anchor[predicate['field']]})
            # 八类由 Harness 认证代码构建的边界，不读取候选的自报测试成绩。
            missing = copy.deepcopy(base); missing[0]['output'].pop(predicate['field'])
            self.check('missing_state', compare(candidate, task, task, missing, offered)['kind'] == 'abstain', {'kind': 'removed_actual_state_field'})
            conflict = copy.deepcopy(base); conflict[0]['arguments']['deck_id'] = 'invalid-independent-deck'
            self.check('conflicting_arguments', compare(candidate, task, task, conflict, offered)['kind'] == 'abstain', {'kind': 'scope_conflict'})
            changed = copy.deepcopy(data); changed['allow_output'] = not data['allow_output']
            with mutated(job, (json.dumps(changed, ensure_ascii=False) + '\n').encode()):
                live = copy.deepcopy(task); live['job_sha256'] = file_hash(job); live['permission_sha256'] = digest({'allow_output': changed['allow_output']})
                _, error = await self.call(client, PIN, {'deck_id': task['deck_id'], 'pages_csv': task['pages_csv']}, allow_error=True)
                self.check('permission_changed', error and compare(candidate, task, live, base, offered)['kind'] == 'abstain', {'actual_mcp_error': error, 'changed_job_sha256': live['job_sha256']})
            for key in ('dependency_changed', 'source_changed'):
                live = copy.deepcopy(task)
                if key == 'dependency_changed':
                    first = next(iter(candidate['dependencies']))
                    copy_path = self.out / ('dependency-boundary-' + digest(first) + '.bin')
                    if not copy_path.exists():
                        copy_path.write_bytes((ROOT / first).read_bytes() + b'\nindependent version boundary\n')
                    live['dependencies'][first] = file_hash(copy_path)
                    actual_error = None
                else:
                    source = source_paths[0]
                    with mutated(source, source.read_bytes() + b'\nindependent source version boundary\n'):
                        live['input_version'] = file_hash(source)
                        _, actual_error = await self.call(client, PIN, {'deck_id': task['deck_id'], 'pages_csv': task['pages_csv']}, allow_error=True)
                self.check(key, compare(candidate, task, live, base, offered)['kind'] == 'abstain' and (actual_error is None or actual_error),
                    {'kind': 'private_dependency_copy_hash' if actual_error is None else 'actual_source_mcp_rejection', 'actual_mcp_error': actual_error})
            altered = copy.deepcopy(offered)
            altered[0][1]['parameters'] = {'type': 'null'}
            selected = next(row for row in altered if row[0] in candidate['contracts'])
            selected[1]['parameters'] = {'type': 'null'}
            self.check('schema_changed', compare(candidate, task, task, base, altered)['kind'] == 'abstain', {'kind': 'changed_actual_schema_snapshot'})
            failed_output, error = await self.call(client, READ, {'source_id': 'invalid-independent-source'}, allow_error=True)
            failed = copy.deepcopy(base) + [{'name': READ, 'arguments': {'source_id': 'invalid-independent-source'}, 'output': failed_output, 'ok': not error, 'barrier': error}]
            self.check('tool_failure', error and compare(candidate, task, task, failed, offered)['kind'] == 'abstain', {'actual_mcp_error': error})
            positive = next((row for row in history[1:] if row['name'] in (PIN, READ)), None)
            if positive:
                changed_output = copy.deepcopy(positive['output']); changed_output['file_sha256'] = '0' * 64
                proposal = ts_decide(candidate, task, task, base, offered)['proposals'][0]
                result = probe({'op': 'verify', 'proposal': proposal, 'execution': {'name': positive['name'], 'arguments': positive['arguments']}, 'output': changed_output, 'liveGuard': task})
                self.check('result_scope_changed', not result['verified'] and not _result_matches(changed_output, proposal['output_contract'], positive['arguments'], task), {'kind': 'altered_actual_result_scope'})
            return branch


async def certify(candidate_path, bundle_path, suite_path, out):
    candidate, bundle, validity = validate_candidate(candidate_path, bundle_path)
    suite = read(private(suite_path, True))
    if set(suite) != {'schema_version', 'heldout_run', 'heldout_schema', 'isolated_root', 'cases'} or suite['schema_version'] != 1 or not isinstance(suite['cases'], list) or not 1 <= len(suite['cases']) <= 3:
        raise ValueError('独立suite需1–3个真实状态case与独立run身份')
    heldout = load_run(suite['heldout_run'], suite['heldout_schema'])
    require_distinct_decisions([*bundle['identities'], heldout['identity']])
    isolated = private(suite['isolated_root'], True)
    if not isolated.is_dir() or any(Path(row['directory']).is_relative_to(isolated) for row in bundle['sources']):
        raise ValueError('认证副本不能包括训练运行目录')
    for case in suite['cases']:
        if set(case) != {'job', 'deck_id', 'pages_csv'}:
            raise ValueError('case只允许真实job/deck/明确页范围')
        data = read(private(case['job'], True))
        question = read(Path(heldout['directory']) / 'manifest.json')['question']
        if any(row['version_sha256'] not in question for row in data['inputs']):
            raise ValueError('认证实际输入版本不属于冻结留出材料')
    # 同一候选目录至多一次隐藏suite调用；失败后不看答案修同一证书。
    write_new(Path(candidate_path).parent / 'hidden-certification-attempt.json',
        {'candidate_digest': candidate['candidate_digest'], 'suite_sha256': file_hash(Path(suite_path)), 'status': 'attempt_consumed'})
    out = private(out); out.mkdir(parents=True, exist_ok=False, mode=0o700)
    certifier, branches, error = Certifier(out), set(), None
    try:
        for case in suite['cases']:
            branches.add(await certifier.case(candidate, case, heldout['identity'], isolated))
        certifier.check('both_actual_branches', branches == {'on_equal', 'on_unequal'}, {'branches': sorted(branches)})
        certifier.check('all_negative_boundaries', all(any(row['name'] == name and row['passed'] for row in certifier.checks) for name in NEGATIVES), {'required': list(NEGATIVES)})
        validate_candidate(candidate_path, bundle_path)
    except Exception as exc:
        error = {'error_type': type(exc).__name__, 'reason': str(exc)}
    evidence = {'schema_version': 1, 'candidate_digest': candidate['candidate_digest'], 'validity': validity,
        'heldout_identity': heldout['identity'], 'suite_sha256': file_hash(Path(suite_path)),
        'calls': certifier.calls, 'checks': certifier.checks, 'actual_branches': sorted(branches), 'error': error,
        'status': 'failed_not_promoted' if error else 'mechanically_certified_not_quality_or_cost_promoted',
        'scope': 'real MCP + full-plan oracle; protocol boundary negatives; no model invocation',
        'quality': 'not_reviewed', 'model_requests': 0, 'real_bypass_observed': False}
    evidence_path = out / 'certification-evidence.json'; write_new(evidence_path, evidence)
    if not error:
        admission = {'schema_version': 1, 'certifier': 'python-independent-v1', 'status': 'passed',
            'candidate_digest': candidate['candidate_digest'], 'training_task_fingerprints': candidate['training']['task_fingerprints'],
            'validation_task_fingerprints': [heldout['identity']['question_sha256']], 'validation_evidence_sha256': [file_hash(evidence_path)],
            'branches_tested': sorted(branches), 'negative_cases': list(NEGATIVES)}
        admission['certificate_digest'] = digest(admission)
        write_new(out / 'admission.json', admission)
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('prepare'); p.add_argument('--train', nargs=2, action='append', required=True, metavar=('RUN', 'ACTUAL_SCHEMA'))
    p.add_argument('--dependency', type=Path, action='append', required=True); p.add_argument('--out', type=Path, required=True)
    p = commands.add_parser('validate-candidate'); p.add_argument('--candidate', type=Path, required=True); p.add_argument('--bundle', type=Path, required=True)
    p = commands.add_parser('certify'); p.add_argument('--candidate', type=Path, required=True); p.add_argument('--bundle', type=Path, required=True)
    p.add_argument('--suite', type=Path, required=True); p.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare(args.train, args.dependency, args.out)
        print(json.dumps({'status': result['status'], 'opportunity_count': len(result['opportunities']), 'out': str(args.out)}, ensure_ascii=False))
    elif args.command == 'validate-candidate':
        print(json.dumps(validate_candidate(args.candidate, args.bundle)[2], ensure_ascii=False))
    else:
        result = asyncio.run(certify(args.candidate, args.bundle, args.suite, args.out))
        print(json.dumps({'status': result['status'], 'error': result['error'], 'out': str(args.out)}, ensure_ascii=False))
        if result['error']:
            return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
