#!/usr/bin/env python3
"""从真实普通 Web 任务独立挖掘 Paper 文档只读 Motif；不调用模型。

dataset: {train:[{task_dir,decision_id},...], heldout:[{task_dir,decision_id}],
ledger, excluded_task_dirs?:[...]}. 恰好两个训练决定、一个留出决定。
--schemas 为当前实际 MCP 完整 schema；原始任务、问句和事件只留 .local。
只认证来源/参数流结构，不宣称论文内容质量、真实旁路或费用收益。
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scenarios.research_ppt.motif_v6 import learn, schema_tools, validate_compilation
from src.adapters.dsh_trajectory import extract_dsh_trace, infer_dsh_provenance
from src.adapters.task_identity import load_trace_identity, require_distinct_decisions
from src.adapters.tool_contract_loader import parse_tool_contracts

SCENE = ROOT / 'scenarios/paper_proofreading'
CONTRACTS = SCENE / 'document-read-contracts.json'
VERSIONS = SCENE / 'document-read-version-fields.json'
PAIR = ['mcp__paper_checks__pin_document', 'mcp__paper_checks__read_pinned_document']
TOKENS = ('prompt_tokens', 'prompt_cache_hit_tokens', 'prompt_cache_miss_tokens', 'completion_tokens', 'total_tokens')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def private(value, *, relative_to=ROOT, exists=True):
    original = Path(value)
    original = original if original.is_absolute() else relative_to / original
    target = original.resolve(strict=exists)
    if original.is_symlink() or not target.is_relative_to((ROOT / '.local').resolve()):
        raise ValueError('原始资料与编译输出必须留在本仓库 .local，不能使用符号链接')
    return target


def write(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    path.chmod(0o600)


def native_schemas(payload):
    """保留捕获的工具顺序，仅统一原生 parameters / MCP inputSchema 字段。"""
    result = []
    for row in schema_tools(payload)['tools']:
        if not isinstance(row, dict) or set(('name', 'description')) - row.keys():
            raise ValueError('实际工具 schema 缺少名称或描述')
        parameters = row.get('parameters', row.get('inputSchema'))
        if (not isinstance(row['name'], str) or not isinstance(row['description'], str)
                or not isinstance(parameters, dict)):
            raise ValueError('实际工具 schema 格式错误')
        result.append({'name': row['name'], 'description': row['description'], 'parameters': parameters})
    if len({row['name'] for row in result}) != len(result):
        raise ValueError('实际工具 schema 名称重复')
    return result


def real_ledger(path):
    raw = path.read_text(encoding='utf-8')
    result = json.loads(raw) if raw.lstrip().startswith('[') else [json.loads(line) for line in raw.splitlines() if line.strip()]
    if not isinstance(result, list) or any(not isinstance(row, dict) for row in result):
        raise ValueError('ledger 必须是实际请求行的 JSON 列表或 JSONL')
    return result


def reconcile(state, request, ledger, *, qualifying):
    rows = [row for row in ledger if row.get('task_id') == request['task_id'] and 'response_status' in row]
    stats = state.get('stats', {})
    if type(stats.get('upstream_requests')) is not int or len(rows) != stats['upstream_requests']:
        raise ValueError('真实任务请求数与精确 task_id 账本不一致')
    ids = [row['global_request_id'] for row in rows if row.get('global_request_id') is not None]
    if len(ids) != len(set(ids)):
        raise ValueError('请求账本含重复 global_request_id')
    complete = stats.get('usage_complete') is True and stats.get('pending_requests', 0) == 0 and stats.get('unknown_usage_requests', 0) == 0
    token_totals = {}
    for key in TOKENS:
        values = [(row.get('response_usage') or {}).get(key) for row in rows]
        known = all(type(value) is int and value >= 0 for value in values)
        token_totals[key] = sum(values) if known else None
        if qualifying and (not known or token_totals[key] != stats.get(key)):
            raise ValueError('provider token 用量不完整或与任务统计不一致：' + key)
    if qualifying and (not rows or not complete or any(row.get('response_status') != 200 for row in rows)):
        raise ValueError('训练/留出必须有完整、成功的真实 provider 请求与用量')
    prices = [row.get('observed_peak_usd') for row in rows]
    known_prices = all(type(value) in (int, float) and math.isfinite(value) and value >= 0 for value in prices)
    cost = sum(prices) if known_prices else None
    if qualifying and cost is None:
        raise ValueError('缺少实际请求的代理峰值估费')
    return {'requests': len(rows), 'tokens': token_totals, 'usage_complete': complete,
            'provider_response_statuses': dict(Counter(str(row['response_status']) for row in rows)),
            'proxy_peak_usd': cost, 'actual_paid_usd': None,
            'tool_calls': stats.get('tool_calls', 0), 'tool_errors': stats.get('tool_errors', 0),
            'denials': stats.get('denials', 0), 'unknown_usage_requests': stats.get('unknown_usage_requests', 0),
            'pending_requests': stats.get('pending_requests', 0)}


def structural_review(task, request, contracts):
    effective = read(task / 'effective-config.json')
    lines = (task / 'events.jsonl').read_text(encoding='utf-8').splitlines()
    start = effective.get('trace_start_index', 0)
    if type(start) is not int or not 0 <= start <= len(lines):
        raise ValueError('invalid frozen task event boundary')
    events = [json.loads(line) for line in lines[start:] if line.strip()]
    if any(event.get('ptc_analysis_source') for event in events):
        raise ValueError('不能把派生的分析事件当原始采集事件')
    trace = extract_dsh_trace(events, contracts, trace_id='actual-task', task_fingerprint=request['task_id'],
                              provenance_by_call_id=infer_dsh_provenance(events, contracts))
    # 单条采集只检查是否有原始 provenance；跨决定挖掘/认证仍仅由公共
    # witnessed compiler 完成，不能降低它至少两个独立任务的支持门槛。
    witnessed = [row for row in trace.records if row.eligible and row.name == PAIR[1]
                 and (row.parameter_sources or {}).get('source_id') == {'from_tool': PAIR[0], 'from_field': 'source_id'}
                 and set(row.arguments) <= {'source_id', 'page'}
                 and type(row.arguments.get('page', 1)) is int and row.arguments.get('page', 1) == 1]
    return {'schema_version': 1, 'reviewer_kind': 'deterministic_structural_audit',
            'scope': 'original_readonly_observations_and_source_handle_provenance_only',
            'observed_parameter_edge_present': bool(witnessed),
            'eligible_calls': dict(Counter(row.name for row in trace.records if row.eligible)),
            'barrier_reasons': dict(Counter(row.reason for row in trace.records if not row.eligible)),
            'scientific_review_complete': False, 'visual_review_complete': False,
            'quality_cost_promoted': False}


def schema_compatibility(observed, current):
    before = {row['name']: row for row in observed}
    after = {row['name']: row for row in current}
    if any(before.get(name) != after.get(name) for name in PAIR):
        raise ValueError('实际采集的两个文档工具与当前 schema 不相同，不能重认证')
    return {'collection_tool_count': len(observed), 'current_tool_count': len(current),
            'collection_whole_schema_sha256': digest(observed), 'current_whole_schema_sha256': digest(current),
            'whole_schema_unchanged': observed == current, 'candidate_two_tool_schemas_unchanged': True,
            'added_tools': sorted(after.keys() - before.keys()), 'removed_tools': sorted(before.keys() - after.keys()),
            'changed_non_candidate_tools': sorted(name for name in before.keys() & after.keys()
                                                  if name not in PAIR and before[name] != after[name]),
            'scope': 'Recompile the witnessed read edge against the captured current complete tool set; not old whole-schema equivalence.'}


def export_run(row, ledger, out, current, contracts, base, *, reuse_task_files=False):
    if not isinstance(row, dict) or not isinstance(row.get('decision_id'), str):
        raise ValueError('每条训练/留出记录必须有 task_dir 和 decision_id')
    task = private(row['task_dir'], relative_to=base)
    effective, state, request = (read(task / name) for name in ('effective-config.json', 'task-state.json', 'task.json'))
    if (state.get('status') != 'completed' or any(value.get('mode') != 'baseline' for value in (state, request, effective))
            or state.get('scene') != 'paper-proofreading' or effective.get('provider_mode') != 'real'
            or any(value.get('task_id') != request.get('task_id') for value in (state, effective))):
        raise ValueError('需要同一真实 completed Paper Baseline 任务的冻结文件')
    accounting = reconcile(state, request, ledger, qualifying=True)
    compatibility = schema_compatibility(native_schemas(effective.get('tools')), current)
    review = structural_review(task, request, contracts)
    if not review['observed_parameter_edge_present']:
        raise ValueError('真实事件没有可见证的文档参数边；应保留为 excluded_collection，不伪造轨迹')
    question = '\n'.join(part['text'] for part in request.get('content', []) if part.get('type') == 'text')
    if not question.strip():
        raise ValueError('真实任务必须含非空问句')
    out.mkdir()
    # 完整原始字节保留私有；不从答案、工具参数或人工脚本重建事件。
    for name in ('effective-config.json', 'task-state.json', 'task.json', 'events.jsonl', 'answer.md'):
        source = private(task / name)
        (os.link if reuse_task_files else shutil.copyfile)(source, out / name)
    if (task / 'answer.json').is_file():
        (os.link if reuse_task_files else shutil.copyfile)(private(task / 'answer.json'), out / 'answer.json')
    # Preserve original event bytes; previous conversation turns are context, not new witnesses.
    event_lines = (task / 'events.jsonl').read_bytes().splitlines(keepends=True)
    start = effective.get('trace_start_index', 0)
    if reuse_task_files and start == 0:
        os.link(task / 'events.jsonl', out / 'agent-events.jsonl')
    else:
        (out / 'agent-events.jsonl').write_bytes(b''.join(event_lines[start:]))
    write(out / 'structural-review.json', review)
    manifest = {'schema_version': 1, 'task_id': request['task_id'], 'question': question,
                'source_effective_sha256': sha(task / 'effective-config.json'),
                'source_state_sha256': sha(task / 'task-state.json'), 'source_request_sha256': sha(task / 'task.json'),
                'original_events_sha256': sha(task / 'events.jsonl'), 'task_event_start_index': start, 'answer_sha256': sha(task / 'answer.md'),
                'review_sha256': sha(out / 'structural-review.json'), 'provider_mode': effective['provider_mode'],
                'model': state.get('model'), 'reasoning_effort': state.get('reasoning_effort'),
                'stats': state['stats'], 'schema_compatibility': compatibility}
    write(out / 'manifest.json', manifest)
    write(out / 'task-identity.json', {'schema_version': 1, 'research_decision_id': row['decision_id'],
                                     'manifest_sha256': sha(out / 'manifest.json'), 'events_sha256': sha(out / 'agent-events.jsonl')})
    identity = load_trace_identity(out / 'task-identity.json', out / 'agent-events.jsonl', ROOT / '.local')
    return {**identity, **accounting, 'reviewer_kind': review['reviewer_kind'],
            'review_sha256': sha(out / 'structural-review.json'), 'readonly_provenance_passed': True,
            'scientific_review_complete': False, 'visual_review_complete': False,
            'effective_config_sha256': sha(task / 'effective-config.json'),
            'task_state_sha256': sha(task / 'task-state.json'), 'request_sha256': sha(task / 'task.json'),
            'answer_sha256': sha(task / 'answer.md'), 'schema_compatibility': compatibility}


def code_paths():
    paths = [Path(__file__).resolve(), CONTRACTS, VERSIONS, SCENE / 'scenario.json']
    paths += [ROOT / value for value in (
        'src/adapters/dsh_web_tasks.ts', 'src/adapters/harless_scenarios.py', 'src/adapters/harless_task_scope.ts',
        'src/adapters/harless_rsi_binding.ts', 'src/adapters/harless_rsi_bundle.py', 'src/adapters/harless_legacy_motif.ts',
        'src/adapters/dsh_online_motif.mjs', 'src/adapters/dsh_trajectory.py', 'src/adapters/dsh_event_projection.py',
        'src/adapters/task_identity.py', 'src/adapters/tool_contract_loader.py', 'src/adapters/tool_schema_contracts.py',
        'src/adapters/session_files.py', 'src/adapters/harless_attachment_text.py', 'src/adapters/session_report.py',
        'src/adapters/file_lock.py', 'src/adapters/harless_paper_learning.ts', 'scripts/learn-web-paper-tasks.py', 'src/adapters/web_task_budget.py', 'src/adapters/paper_static_checks.py', 'src/adapters/paper_archive.py',
        'src/adapters/paper_bibliography.py', 'src/adapters/paper_query_recovery.py', 'src/adapters/paper_renderer.py',
        'src/adapters/harless_paper_renderer.py', 'src/adapters/harless_paper_recovery.ts',
        'scenarios/data_analysis/table_inputs.py', 'benchmarks/research_report_agent_v2/document_engine.py',
        'src/motif_core/online_skill_runtime.mjs',
        # Native common tools are separately admitted, never learned/replayed by
        # this document-read artifact. Freeze their policy, adapters and wiring
        # so the additive runtime change still requires compatibility review.
        'config/geneloop-capabilities.json', 'config/geneloop-capabilities.md',
        'src/adapters/geneloop_capabilities.ts', 'src/adapters/geneloop_shell.ts',
        'src/adapters/geneloop_web_search.ts', 'src/adapters/geneloop_command_broker.ts',
        'src/adapters/geneloop_command_client.mjs', 'src/adapters/deepseek_cost_gate.py',
        'scripts/harness-web.py', 'scripts/harless_gateway.mjs', 'scripts/harless_member_scenes.mjs',
        'scripts/web_budget_broker.mjs', 'scripts/serve-web-budget.py',
        'scripts/check-common-capabilities.py', 'scripts/recompile-ppt-common-capabilities.py')]
    for directory in (SCENE, ROOT / 'scenarios/paper-submission'):
        paths.extend(path for path in directory.rglob('*') if path.is_file()
                     and path.suffix in ('.py', '.ts', '.mjs', '.js', '.json', '.md')
                     and not {'node_modules', '__pycache__', 'tests', '.local'} & set(path.relative_to(ROOT).parts))
    return tuple(sorted({path.resolve(strict=True) for path in paths}))


def collection_commit():
    # Installed member code has no Git checkout; exact file locks stay authoritative.
    result = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True, capture_output=True) if shutil.which('git') else None
    return result.stdout.strip() if result and result.returncode == 0 else None


def main(argv=None, *, private_publish_root=None, reuse_task_files=False):
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--schemas', type=Path, required=True, help='私有当前实际完整24工具 schema JSON')
    parser.add_argument('--out', type=Path, required=True, help='新的 .local 私有目录，不覆盖')
    parser.add_argument('--publish', type=Path, help='新的 motif-libraries 目录，不覆盖')
    args = parser.parse_args(argv)
    dataset_path = private(args.dataset)
    dataset = read(dataset_path)
    if not isinstance(dataset, dict) or len(dataset.get('train', [])) != 2 or len(dataset.get('heldout', [])) != 1:
        raise ValueError('恰好两个独立 train 决定与一个 heldout 决定')
    tree_digest = dataset.get('current_candidate_source_tree_sha256')
    if tree_digest is not None and (not isinstance(tree_digest, str) or not re.fullmatch(r'[a-f0-9]{64}', tree_digest)):
        raise ValueError('当前采集候选源码快照必须为 SHA256，不得把脏工作区冒称纯净 commit')
    if dataset.get('collection_tracked_dirty') is not None and type(dataset['collection_tracked_dirty']) is not bool:
        raise ValueError('collection_tracked_dirty 必须为布尔值')
    schemas_path = private(args.schemas)
    current = native_schemas(read(schemas_path))
    allowed = read(SCENE / 'scenario.json')['allowed_tools']
    if len(current) != 24 or sorted(row['name'] for row in current) != sorted(allowed):
        raise ValueError('必须提供当前 Paper 完整24工具的实际捕获')
    common = read(ROOT / 'config/geneloop-capabilities.json')['tools']
    if (not isinstance(common, list) or len(common) != 6
            or set(common) != {'web_search', 'web_fetch', 'bash', 'job_list', 'job_output', 'job_kill'}
            or set(common) & {row['name'] for row in current}):
        raise ValueError('原生公共6工具必须独立允许，不能混入24工具证书或扩展所学只读边')
    page = next(row['parameters'] for row in current if row['name'] == PAIR[1])
    if page.get('properties', {}).get('page', {}).get('default') != 1 or 'page' in page.get('required', []):
        raise ValueError('实际读取工具的可省略第一页默认值变化')
    ledger_path = private(dataset['ledger'], relative_to=dataset_path.parent)
    ledger = real_ledger(ledger_path)
    output = private(args.out, exists=False)
    output.mkdir(parents=True, exist_ok=False)
    contracts = parse_tool_contracts(read(CONTRACTS))
    started = time.monotonic()
    evidence, runs, source_tasks = {}, {}, set()
    for split in ('train', 'heldout'):
        evidence[split], runs[split] = [], []
        for index, row in enumerate(dataset[split], 1):
            dest = output / (split + '-' + str(index))
            item = export_run(row, ledger, dest, current, contracts, dataset_path.parent, reuse_task_files=reuse_task_files)
            if item['task_id'] in source_tasks:
                raise ValueError('训练与留出不能复用同一个真实任务')
            source_tasks.add(item['task_id']);evidence[split].append(item);runs[split].append(str(dest))
    identities = evidence['train'] + evidence['heldout']
    require_distinct_decisions(identities)
    excluded = []
    for value in dataset.get('excluded_task_dirs', []):
        task = private(value, relative_to=dataset_path.parent)
        state, request = read(task / 'task-state.json'), read(task / 'task.json')
        if request['task_id'] in source_tasks:
            raise ValueError('excluded 成本必须与训练/留出互斥且不重复')
        source_tasks.add(request['task_id'])
        review = structural_review(task, request, contracts)
        failure = state.get('failure')
        excluded.append({'task_id': request['task_id'], 'status': state['status'], 'mode': state.get('mode'),
                         'events_sha256': sha(task / 'events.jsonl'), 'failure_sha256': digest(failure) if failure else None,
                         'document_read_edge_observed': review['observed_parameter_edge_present'],
                         'exclusion_scope': 'retained_collection_attempt_not_used_for_independent_certification',
                         **reconcile(state, request, ledger, qualifying=False)})
    write(output / 'dataset.json', runs)
    write(output / 'schema.json', {'tools': [{'name': row['name'], 'description': row['description'], 'inputSchema': row['parameters']} for row in current]})
    guards = code_paths()
    manifest_path = learn(output / 'dataset.json', contracts_path=CONTRACTS, version_fields_path=VERSIONS,
                          tool_schema_path=output / 'schema.json', out_dir=output / 'compiled',
                          guard_paths=guards, mining='witnessed_edges')
    validate_compilation(manifest_path)
    manifest, library = read(manifest_path), read(manifest_path.parent / 'library.json')
    if (len(manifest.get('artifacts', [])) != 1 or len(library.get('artifacts', [])) != 1
            or manifest['artifacts'][0]['tools'] != PAIR or library['artifacts'][0]['tools'] != PAIR):
        raise ValueError('公共挖掘器没有认证唯一文档只读边；不手工补图或挑选产物')
    write(output / 'source-evidence.json', evidence)
    requests = sum(item['requests'] for item in identities)
    cost = sum(item['proxy_peak_usd'] for item in identities)
    total_costs = [item['proxy_peak_usd'] for item in identities + excluded]
    report = {'schema_version': 1, 'new_training': True, 'method': 'existing_witnessed_edge_compiler',
              'training_tasks': 2, 'heldout_tasks': 1, 'artifacts': 1,
              'library_digest': library['library_digest'], 'manifest_digest': manifest['manifest_digest'],
              'evidence_sha256': sha(output / 'source-evidence.json'), 'schema_capture_sha256': sha(schemas_path),
              'current_whole_schema_sha256': digest(current), 'current_tool_count': 24,
              'collection_source_sha': dataset.get('collection_source_sha'),
              'collection_source_sha_basis': 'optional_dataset_collection_metadata_not_inferred_from_current_checkout',
              'current_candidate_source_tree_sha256': tree_digest,
              'collection_tracked_dirty': dataset.get('collection_tracked_dirty'),
              'collection_tree_scope': 'Candidate tracked-source snapshot, including uncommitted changes when present; commit alone is not a clean-source claim.',
              'compilation_source_sha': collection_commit(),
              'compilation_source_binding': 'exact_file_code_locks_include_uncommitted_candidate',
              'compilation_model_requests': 0, 'compilation_seconds': time.monotonic() - started,
              'model_weights_trained': False, 'compilation_executes_scene_tools': False,
              'common_native_tools': common, 'common_native_tools_in_certified_mcp_schema': False,
              'common_capabilities_compatibility_scope': 'Current native network, command and job policy/adapters/wiring are code-locked; their six tools remain separately admitted and are not learned, replayed or executed by this offline compiler. The complete 24-tool MCP descriptions and parameters remain exact-match guards.',
              'trace_collection_requests': requests, 'trace_collection_proxy_usd': cost,
              'excluded_collection': excluded, 'learning_total_requests': requests + sum(item['requests'] for item in excluded),
              'learning_total_proxy_usd': sum(total_costs) if all(value is not None for value in total_costs) else None,
              'collection_cost_basis': 'exact_task_id_ledger_observed_peak_estimate_not_provider_invoice',
              'actual_paid_usd': None, 'review_scope': 'structural_provenance_only',
              'scientific_quality_reviewed': False, 'visual_quality_reviewed': False, 'quality_cost_promoted': False,
              'scope': 'model_selected_uploaded_document_default_first_page_read_not_manuscript_semantics_or_report_generation'}
    write(output / 'public-learning-report.json', report)
    if args.publish:
        target = args.publish.resolve()
        boundary = private(private_publish_root) if private_publish_root is not None else (ROOT / 'motif-libraries').resolve()
        if not target.is_relative_to(boundary) or target.exists():
            raise ValueError('publish 必须是 motif-libraries 下的新目录，禁止覆盖已有版本')
        # 再校验全部私有来源和编译文件，避免检查后被替换。
        validate_compilation(manifest_path)
        target.mkdir()
        for name in ('library.json', 'online-manifest.json'):
            shutil.copyfile(manifest_path.parent / name, target / name)
        write(target / 'tool-schemas.json', current)
        write(target / 'task.json', {'schema_version': 1, 'task_id': 'paper-web-v1-admission', 'session_id': 'paper-web-v1-admission',
                                   'intent': 'Read the default first page of a current approved document already selected and pinned by the model.',
                                   'input_version': '0' * 64, 'bindings': {},
                                   'source_versions': {name: '0' * 64 for name in manifest['version_fields']}})
        write(target / 'source-evidence.json', evidence)
        if sha(target / 'source-evidence.json') != report['evidence_sha256']:
            raise ValueError('公开证据字节与学习报告的摘要不一致')
        write(target / 'learning-report.json', report)
        locked_code = set(guards)
        for row in read(manifest_path.parent / 'evidence-lock.json')['sources']:
            path = Path(row['path']).resolve(strict=True)
            if path.is_relative_to(ROOT) and not path.is_relative_to(ROOT / '.local'):
                locked_code.add(path)
        write(target / 'certification.json', {'schema_version': 1, 'scene': 'paper-proofreading',
                    'binding_policy': 'approved_uploaded_reads_v1', 'matching_policy': 'structural_only',
                    'certification_scope': 'independent_trace_structure', 'quality_cost_promoted': False,
                    'source_evidence_sha256': sha(target / 'source-evidence.json'),
                    'learning_report_sha256': sha(target / 'learning-report.json'), 'manifest_digest': manifest['manifest_digest'],
                    'file_locks': {path.name: sha(path) for path in sorted(target.iterdir())},
                    'code_locks': {path.relative_to(ROOT).as_posix(): sha(path) for path in sorted(locked_code)}})
        write(target / 'entry.json', {'schema_version': 1, 'scene': 'paper-proofreading',
                    'runtime_kind': 'paper_document_read_v1', 'mode': 'execute', 'new_training': True,
                    'files': {path.name: sha(path) for path in sorted(target.iterdir())},
                    'scientific_quality_reviewed': False, 'quality_cost_promoted': False})
        from src.adapters.harless_rsi_bundle import load_product_bundle
        load_product_bundle(ROOT, target, 'paper-proofreading', private_root=private_publish_root)
    print(json.dumps({'compiled_manifest': str(manifest_path), 'published': str(args.publish) if args.publish else None,
                      **report}, ensure_ascii=False))


if __name__ == '__main__':
    main()
