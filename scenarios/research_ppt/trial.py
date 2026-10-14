"""科研 PPT 双路试用：同一任务、固定工具、隔离输出和完整费用记录。

复用公共 run-scenario.py 启动 DSH；本模块不实现 Agent 循环。默认只
准备和预览。steps/composed 比较的是普通工程策略，不冒称 RSI 收益。
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from uuid import uuid4

from . import cli
from .documents import file_hash
from .accounting import token_totals, collect_accounting
from .runtime_snapshot import versions
from .feedback_learning import (DEFAULT_STORE, FeedbackStore, _execution_policy_binding,
                                _host_receipt, COMPOSED_TOOLS, HOST_ROUTES)
from .service import ROOT, SCENE, private_path, validate_minimum_original_figures
from src.adapters.deepseek_cost_gate import PEAK_USD_PER_MILLION, CACHE_HIT_PEAK_USD_PER_MILLION
from src.adapters.dsh_trajectory import _observation_digest
from src.adapters.dsh_event_projection import is_original_tool_result

GROUPS = ('baseline', 'optimized')
REVIEW_FIELDS = ('scientific_facts', 'figures_and_citations', 'editable_and_rendered', 'usable_presentation')


def save_new(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    path.chmod(0o600)


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def read_rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            if type(row) is not dict:
                raise ValueError('非对象行')
        except ValueError:
            row = {'kind': 'malformed_record', 'line_sha256': hashlib.sha256(line.encode()).hexdigest()}
        rows.append(row)
    return rows


def command_value(args: list[str]) -> str | None:
    try:
        run = subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                             encoding='utf-8', errors='replace', timeout=15)
        return run.stdout.strip() if run.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def code_snapshot() -> dict:
    """绑定线上源文件与实际构建产物，不收集 .local/ 用户文件和凭证。"""
    files = set()
    for directory in (SCENE, ROOT / 'src/adapters', ROOT / 'src/motif_core'):
        for path in directory.rglob('*'):
            if (path.is_file() and not set(path.parts).intersection({'node_modules', '__pycache__', 'tests'})
                    and path.suffix in {'.py', '.ts', '.mjs', '.js', '.json', '.md', '.svg', '.yml'}
                    and (path.suffix != '.md' or path.name in {'prompt.md', 'rsi-prompt.md', 'layout-rsi-prompt.md', 'SKILL.md'})):
                files.add(path)
    files.update(path for path in (ROOT / 'scripts/run-scenario.py', ROOT / 'package-lock.json',
                                   ROOT / 'config/semantic-sdk.patch.yml') if path.is_file())
    hashes = {str(path.relative_to(ROOT)).replace('\\', '/'): file_hash(path)
              for path in sorted(files) if not path.is_symlink()}
    status = command_value(['git', 'status', '--porcelain', '--untracked-files=normal'])
    return {'commit': command_value(['git', 'rev-parse', 'HEAD']),
            'worktree_status': status, 'files': hashes, 'sha256': digest(hashes)}


def environment_snapshot() -> dict:
    return {**versions(), 'harness_npm_package_lock_sha256': file_hash(ROOT / 'package-lock.json')}


def validate_options(budget: float, max_steps: int, max_output: int) -> None:
    if (not math.isfinite(budget) or not 0 < budget <= 20
            or not 1 <= max_steps <= 60 or not 1 <= max_output <= 8000):
        raise ValueError('双路总预算应在 (0,20] 美元，每路步数 [1,60]、输出上限 [1,8000]')


def preview_invocation(args: list[str], env: dict, directory: Path, group: str,
                       *, active_fallback=False) -> tuple[list[str], subprocess.CompletedProcess, str | None, Path | None]:
    job = Path(args[args.index('--job') + 1])
    before = set(job.parent.glob('invocation-*.json'))
    result = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8')
    created = set(job.parent.glob('invocation-*.json')) - before
    fallback = None
    if result.returncode and active_fallback:
        (directory / 'optimized-active-preview.log').write_text(result.stdout + result.stderr, encoding='utf-8')
        args = args[:args.index('--mode') + 1] + ['baseline']
        fallback = '已晋级版本不适用于当前任务，继续普通工程执行；详见私有预览日志'
        result = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8')
        created = set(job.parent.glob('invocation-*.json')) - before - created
    (directory / (group + '-preview.log')).write_text(result.stdout + result.stderr, encoding='utf-8')
    if result.returncode == 0 and len(created) != 1:
        raise ValueError('公共cli预览没有唯一有效运行配置，拒绝冻结')
    return args, result, fallback, next(iter(created)) if created else None


def prepare_trial(inputs: list[Path], instruction: str, slides: int, *, budget=3.0,
                  max_steps=60, max_output=8000, template='lab', operation='generate',
                  allow_output=False, order='baseline-first', collect_feedback=False,
                  use_active_learning=False, feedback_store: Path = DEFAULT_STORE,
                  candidate_version: str | None = None, use_auto_candidate=False,
                  document_cache=False,
                  execution_policy='controlled', minimum_original_figures: int = 0) -> Path:
    validate_options(budget, max_steps, max_output)
    validate_minimum_original_figures(minimum_original_figures, slides, operation)
    if order not in ('baseline-first', 'optimized-first'):
        raise ValueError('无效运行顺序')
    if use_active_learning and candidate_version:
        raise ValueError('active 与候选评测不能同时启用')
    if use_auto_candidate and not use_active_learning:
        raise ValueError('自动候选需要同时读取已晋级版本')
    if type(document_cache) is not bool or execution_policy not in ('controlled', 'legacy_model_selected'):
        raise ValueError('需明确document_cache布尔值和controlled/legacy_model_selected策略')
    # 源文件必须已由用户上传私有目录，不把用户原件写回或作为共享学习资料。
    inputs = [private_path(path).resolve(strict=True) for path in inputs]
    trial_id = 'trial-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:8]
    directory = ROOT / '.local/research-ppt/trials' / trial_id
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    feedback_store = private_path(feedback_store)
    store = FeedbackStore(feedback_store)
    active, active_fallback, auto_candidate_version = None, None, None
    if candidate_version:
        active = store.candidate_manifest(candidate_version)
    elif use_active_learning:
        try:
            active = store.active_manifest()
        except (ValueError, OSError) as exc:
            active_fallback = '已晋级版本校验失败，维持普通工程执行: ' + type(exc).__name__
        if active is None and active_fallback is None:
            active_fallback = '没有已晋级版本，继续普通工程对照'
        if active is None and use_auto_candidate:
            from .auto_learning import candidate_for_next_trial
            auto_candidate_version = candidate_for_next_trial(store)
            if auto_candidate_version:
                active = store.candidate_manifest(auto_candidate_version)
                active_fallback = None
    groups = {}
    for group in GROUPS:
        strategy = (('baseline_steps' if group == 'baseline' else 'host_delivery')
                    if execution_policy == 'controlled' else ('steps' if group == 'baseline' else 'composed'))
        job = cli.prepare(inputs, instruction, slides, allow_output=allow_output,
                          allow_rsi=False, template=template, operation=operation,
                          design_skill=True, document_cache=document_cache,
                          execution_policy=strategy if execution_policy == 'controlled' else None,
                          minimum_original_figures=minimum_original_figures)
        requested_mode = 'execute' if group == 'optimized' and active else 'baseline'
        args = [sys.executable, '-m', 'scenarios.research_ppt.cli', 'run', '--job', str(job),
                '--budget-usd', str(budget / 2), '--max-steps', str(max_steps), '--max-output', str(max_output),
                '--runtime', 'reliable', '--execution', strategy,
                '--mode', requested_mode]
        if requested_mode == 'execute':
            args.extend(['--manifest', str(active['manifest'])])
        env = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
        args, result, fallback, invocation_path = preview_invocation(
            args, env, directory, group,
            active_fallback=bool(group == 'optimized' and use_active_learning and active))
        if fallback:
            active = None
            requested_mode = 'baseline'
            active_fallback = fallback
            auto_candidate_version = None
        if result.returncode:
            raise ValueError('公共cli预览/证书守卫失败；详见本次私有preview.log，无付费请求')
        if invocation_path is None:
            raise ValueError('新job没有有效公共运行配置，拒绝冻结')
        invocation = read_json(invocation_path)
        if group == 'optimized' and invocation['effective_mode'] != 'execute' and active:
            if candidate_version:
                raise ValueError('隔离候选未进入 execute，拒绝将候选评测记为普通运行')
            active_fallback = invocation.get('fallback_reason') or '当前任务不适用已晋级结构'
            active = None
            auto_candidate_version = None
            args = args[:args.index('--mode') + 1] + ['baseline']
            args, result, _, invocation_path = preview_invocation(args, env, directory, group)
            if result.returncode or invocation_path is None:
                raise ValueError('Motif 回退后普通模式预览失败，拒绝冻结')
            invocation = read_json(invocation_path)
            if invocation['effective_mode'] != 'baseline':
                raise ValueError('Motif 回退后普通模式未生效，拒绝冻结')
            requested_mode = 'baseline'
        scenario = job.parent / 'scenario.json'
        spec = read_json(scenario)
        prompt = Path(spec['prompt'])
        shared = prompt.read_text(encoding='utf-8').split('\n本次执行方式：', 1)[0]
        prompt.chmod(0o600)
        groups[group] = {'job': str(job), 'job_sha256': file_hash(job), 'job_id': read_json(job)['job_id'],
                         'scenario': str(scenario), 'scenario_sha256': file_hash(scenario),
                         'prompt': str(prompt), 'prompt_sha256': file_hash(prompt),
                         'shared_prompt_sha256': hashlib.sha256(shared.encode()).hexdigest(),
                         'configured_tool_order': spec['allowed_tools'],
                         'output_directory': str(job.parent / 'outputs'),
                         'execution': strategy,
                         'mode': requested_mode, 'effective_mode': invocation['effective_mode'],
                         'invocation': str(invocation_path), 'invocation_sha256': file_hash(invocation_path),
                         'guard_digest': invocation.get('guard_digest'), 'fallback_reason': invocation.get('fallback_reason'),
                         'budget_cap_usd': budget / 2, 'run_arguments': args}
    if (groups['baseline']['configured_tool_order'] != groups['optimized']['configured_tool_order']
            or groups['baseline']['shared_prompt_sha256'] != groups['optimized']['shared_prompt_sha256']):
        raise ValueError('两组工具/公共提示不一致，拒绝创建不公平对照')
    data = {'schema_version': 1, 'trial_id': trial_id, 'created_utc': datetime.now(timezone.utc).isoformat(),
            'task': {'instruction': instruction, 'slides': slides, 'template': template, 'operation': operation,
                     'minimum_original_figures': minimum_original_figures,
                     'inputs': read_json(Path(groups['baseline']['job']))['inputs']},
            'groups': groups, 'order': list(GROUPS) if order == 'baseline-first' else list(reversed(GROUPS)),
            'budget_cap_usd_total': budget, 'model': 'deepseek-flash', 'provider': 'deepseek-official',
            'reasoning_effort': 'off', 'context_compression': 'off', 'document_cache': document_cache,
            'execution_policy': execution_policy,
            'max_agent_steps_per_group': max_steps, 'max_output_tokens_per_request': max_output,
            'allow_output': bool(allow_output), 'semantic_matching': 'disabled',
            'rsi_enabled': groups['optimized']['effective_mode'] == 'execute',
            'collect_feedback': bool(collect_feedback),
            'feedback_store': str(feedback_store), 'use_active_learning': bool(use_active_learning),
            'candidate_evaluation': bool(candidate_version or auto_candidate_version),
            'auto_candidate_selection': bool(auto_candidate_version),
            'active_learning': active,
            'active_learning_fallback': active_fallback,
            'comparison': ('普通DSH逐步 vs 同schema宿主固定交付脚本；两组禁止模型直接选组合工具'
                           if execution_policy == 'controlled' else '历史普通DSH逐步 vs 同底座模型选择普通工程组合') +
                          ('＋隔离认证候选Motif；差额不能全归因RSI' if candidate_version or auto_candidate_version else
                           '＋显式晋级Motif；差额不能全归因RSI' if groups['optimized']['effective_mode'] == 'execute'
                           else '；不是RSI对照'),
            'code': code_snapshot(), 'environment': environment_snapshot(),
            'price_table': {'miss_and_output_usd_per_million': PEAK_USD_PER_MILLION,
                            'hit_usd_per_million': CACHE_HIT_PEAK_USD_PER_MILLION,
                            'sha256': digest([PEAK_USD_PER_MILLION, CACHE_HIT_PEAK_USD_PER_MILLION])},
            'unknowns': ['Provider完整有效payload与工具排序未独立采集；实际MCP schema在付费前冻结',
                         '真实账单、人工修订时间、CPU/维护费用待补录'],
            'learning_cost': {'usd': 0, 'model_requests': 0, 'note': '本入口不生成或认证新工具；历史学习投入不计零，应另报'}}
    path = directory / 'trial.json'
    save_new(path, data)
    save_new(directory / 'review-template.json', {
        'trial_id': trial_id, 'reviewer': None,
        'groups': {group: {**{field: None for field in REVIEW_FIELDS}, 'revision_minutes': None,
                            'major_errors': [], 'notes': ''} for group in GROUPS},
        'provider_bill_usd_total': None,
        'instruction': '逐页核对真实来源和预览；true/false分别表示合格/不合格，null表示未评审。'})
    return path


def checked_trial(path: Path) -> tuple[Path, dict]:
    path = private_path(path).resolve(strict=True)
    data = read_json(path)
    if (data.get('schema_version') != 1 or set(data.get('groups', {})) != set(GROUPS)
            or sorted(data.get('order', [])) != sorted(GROUPS)
            or type(data.get('rsi_enabled')) is not bool or data.get('reasoning_effort') != 'off'
            or data.get('context_compression') != 'off'):
        raise ValueError('试用配置不完整或包含未批准的运行模式')
    if (data.get('execution_policy', 'legacy_model_selected') not in ('controlled', 'legacy_model_selected')
            or type(data.get('document_cache', False)) is not bool):
        raise ValueError('执行策略或缓存冻结字段无效')
    task = data.get('task', {})
    minimum_original_figures = task.get('minimum_original_figures', 0)
    if 'minimum_original_figures' in task:
        validate_minimum_original_figures(minimum_original_figures, task['slides'], task.get('operation', 'generate'))
    validate_options(data['budget_cap_usd_total'], data['max_agent_steps_per_group'], data['max_output_tokens_per_request'])
    if any(data['groups'][group]['budget_cap_usd'] != data['budget_cap_usd_total'] / 2 for group in GROUPS):
        raise ValueError('两路预算与预览不一致')
    for group in GROUPS:
        row = data['groups'][group]
        for key in ('job', 'scenario', 'prompt', 'invocation'):
            actual = private_path(Path(row[key])).resolve(strict=True)
            if file_hash(actual) != row[key + '_sha256']:
                raise ValueError(f'{group} 的 {key} 版本改变，请重新准备')
        job = read_json(Path(row['job']))
        if (job['allow_output'] != data['allow_output'] or job.get('allow_rsi')
                or job.get('document_cache', False) != data.get('document_cache', False) or job.get('generated_tool_certificate')
                or job.get('minimum_original_figures', 0) != minimum_original_figures
                or job.get('layout_policy_certificate')):
            raise ValueError('job权限或候选工具配置与试用冻结值不一致')
        expected_policy = (None if data.get('execution_policy', 'legacy_model_selected') == 'legacy_model_selected'
                           else {'schema_version': 1, 'strategy': 'baseline_steps' if group == 'baseline' else 'host_delivery'})
        if (job.get('execution_policy') != expected_policy
                or (expected_policy and row['execution'] != expected_policy['strategy'])):
            raise ValueError('真实job宿主策略与冻结对照不同')
        for source in job['inputs']:
            if file_hash(private_path(Path(source['path']))) != source['version_sha256']:
                raise ValueError('来源版本改变，请重新准备，不重用旧预览')
        if read_json(Path(row['scenario']))['allowed_tools'] != row['configured_tool_order']:
            raise ValueError('工具集合或顺序改变')
    if code_snapshot()['sha256'] != data['code']['sha256']:
        raise ValueError('源代码或实际构建产物改变，请重新准备，不重签旧任务')
    if data.get('active_learning'):
        store = FeedbackStore(private_path(Path(data['feedback_store'])))
        active = (store.candidate_manifest(data['active_learning']['version']) if data.get('candidate_evaluation')
                  else store.active_manifest())
        if active != data['active_learning']:
            raise ValueError('离线晋级版本已变化或失效，请重新准备')
    return path, data


def preview(path: Path, data: dict) -> dict:
    return {'trial': str(path), 'trial_id': data['trial_id'], 'mode': 'preview',
            'task': data['task'], 'comparison': data['comparison'], 'run_order': data['order'],
            'budget_cap_usd_total': data['budget_cap_usd_total'],
            'budget_cap_usd_per_group': data['budget_cap_usd_total'] / 2,
            'reasoning_effort': 'off', 'context_compression': 'off', 'rsi_enabled': data['rsi_enabled'],
            'active_learning_fallback': data.get('active_learning_fallback'),
            'output_authorized': data['allow_output'],
            'feedback_collection_authorized': data.get('collect_feedback', False),
            'outputs': {group: data['groups'][group]['output_directory'] for group in GROUPS},
            'impact': '真实运行会串行调用两份DSH并创建两套私有交付；不覆盖输入。双路总支出不能当优化单路费用。',
            'quality': '未评审；机械通过与科研/视觉合格分别记录',
            'execute': shlex.join(['python', '-m', 'scenarios.research_ppt.trial', '--trial', str(path), '--call-model'])}


def freeze_schema(row: dict, target: Path) -> dict:
    env = dict(os.environ, SSS_PPT_JOB=row['job'], SSS_PPT_DELIVERY_PYTHON=sys.executable,
               PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    result = subprocess.run(['node', str(SCENE / 'dist/mcp-adapter.js'), '--job', row['job'],
                             '--export-schema', str(target)], cwd=ROOT, env=env, capture_output=True,
                            text=True, encoding='utf-8', errors='replace', timeout=120)
    target.with_suffix('.log').write_text(result.stdout + result.stderr, encoding='utf-8')
    if result.returncode or not target.is_file():
        raise ValueError('实际MCP schema预检失败；安装/构建依赖后使用新的试用预览，不发付费请求')
    schema = read_json(target)
    names = ['mcp__ppt__' + name for name in schema['advertised_tool_order']]
    if names != row['configured_tool_order']:
        raise ValueError('实际MCP顺序与场景白名单不一致，拒绝付费对照')
    return {'path': str(target), 'file_sha256': file_hash(target),
            'schema_sha256': schema['schema_sha256'], 'advertised_tool_order': names,
            'scope': schema['scope']}


def locate_run(log: Path, before: set[str], row: dict) -> Path | None:
    """正常完成读公共回执；中断时通过新manifest定位，不漏已有付费账本。"""
    reported = []
    for line in log.read_text(encoding='utf-8', errors='replace').splitlines():
        try:
            value = json.loads(line)
            if isinstance(value, dict) and isinstance(value.get('output_dir'), str):
                reported.append(private_path(Path(value['output_dir'])))
        except ValueError:
            pass
    candidates = list(reported)
    runs = ROOT / '.local/runs'
    if runs.is_dir():
        candidates.extend(child for child in runs.iterdir() if child.is_dir() and child.name not in before)
    matches = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if not candidate.is_relative_to(runs.resolve()) or not (candidate / 'manifest.json').is_file():
            continue
        manifest = read_json(candidate / 'manifest.json')
        if (manifest.get('config_sha256') == row['scenario_sha256']
                and manifest.get('prompt_sha256') == row['prompt_sha256']):
            matches.add(candidate)
    if len(matches) > 1:
        raise ValueError('出现多份同任务运行manifest，费用归属有歧义，保留证据但不发布降本数字')
    return next(iter(matches), None)


def summarize_ledger(rows: list[dict], metrics: dict) -> dict:
    calls = [row for row in rows if 'request_id' in row]
    shared = token_totals(rows, metrics)
    parse_errors = sum(row.get('kind') == 'malformed_record' for row in rows)
    count_complete = not parse_errors and type(metrics.get('upstream_requests')) is int and metrics['upstream_requests'] == len(calls)
    complete = count_complete and shared['token_accounting_complete']
    tokens = shared['tokens']
    prompt = tokens['prompt_cache_miss_tokens'] + tokens['prompt_cache_hit_tokens'] if all(
        tokens[key] is not None for key in ('prompt_cache_miss_tokens', 'prompt_cache_hit_tokens')) else None
    measured = [row['observed_peak_usd'] for row in calls if type(row.get('observed_peak_usd')) in (int, float)]
    # HTTP失败或usage缺失的预留也保留在预算账本；不得仅统计成功请求。
    accounted = sum(row['observed_peak_usd'] if type(row.get('observed_peak_usd')) in (int, float)
                    else row.get('reserved_upper_usd', 0) for row in calls)
    return {'upstream_requests': metrics.get('upstream_requests') if count_complete else None,
            'ledger_requests': len(calls), **tokens, 'prompt_tokens': prompt, 'usage_complete': complete,
            'token_sources': shared['token_sources'], 'ledger_observed_subtotals': shared['ledger_observed_subtotals'],
            'observed_proxy_usd': round(sum(measured), 10) if count_complete and len(measured) == len(calls) else None,
            'observed_proxy_subtotal_usd': round(sum(measured), 10),
            'unsettled_request_count': len(calls) - len(measured),
            'budget_accounted_usd': metrics.get('budget_accounted_usd'),
            'budget_accounted_observed_subtotal_usd': round(accounted, 10),
            'provider_bill_usd': None,
            'upstream_failed_requests': sum(row.get('response_status') != 200 for row in calls),
            'upstream_seconds': round(sum(row.get('elapsed_seconds', 0) for row in calls), 3),
            'request_count_matches_ledger': count_complete,
            'ledger_parse_errors': parse_errors,
            'recovery_cost_usd': None,
            'recovery_note': '全部失败与恢复已计入总账；现有公共事件不足以精确拆分每次恢复的模型费用，不能写0。'}


def summarize_tools(events: list[dict], allowed_tools: list[str],
                    execution_evidence: dict | None = None) -> tuple[dict, list[dict]]:
    # 挖掘器故意不保留写操作observation；记账必须从原始配对结果读取，
    # 不能伪造read_only契约让写操作成为学习证据。
    called, arguments, results = {}, {}, {}
    for event in events:
        data = event.get('data', {})
        if not isinstance(data, dict):
            continue
        if event.get('type') == 'tool/call' and isinstance(data.get('callId'), str):
            called.setdefault(data['callId'], data.get('name'))
            try:
                arguments[data['callId']] = json.loads(data.get('arguments', ''))
            except (TypeError, ValueError):
                arguments[data['callId']] = None
        elif is_original_tool_result(event):
            message = data.get('message', {})
            source = message.get('source', {}) if isinstance(message, dict) else {}
            if isinstance(source, dict) and isinstance(source.get('callId'), str):
                results.setdefault(source['callId'], event)
    calls = Counter(name for name in called.values() if isinstance(name, str))
    failures, deliveries, host_deliveries, successful_composed = 0, [], [], 0
    for call_id, name in called.items():
        event = results.get(call_id)
        success, _, value = _observation_digest(event, name) if event else (False, None, None)
        if not success or value is None or value.get('ok') is False or value.get('passed') is False or value.get('delivered') is False:
            failures += 1
        if (success and isinstance(value, dict) and isinstance(name, str)
                and name.removeprefix('mcp__ppt__') in COMPOSED_TOOLS and value.get('ok') is not False):
            successful_composed += 1
        original_delivery = name in {'mcp__ppt__deliver_deck', 'mcp__ppt__render_delivery', 'mcp__ppt__build_delivery'}
        host_delivery = (execution_evidence and execution_evidence['strategy'] == 'host_delivery'
                         and isinstance(name, str) and isinstance(value, dict)
                         and _host_receipt(value, name, arguments.get(call_id), execution_evidence))
        if (success and isinstance(value, dict) and name in allowed_tools
                and (original_delivery or host_delivery)
                and value.get('delivered') is not False and isinstance(value.get('path'), str)
                and isinstance(value.get('file_sha256'), str) and isinstance(value.get('validation_id'), str)):
            deliveries.append(value)
            if host_delivery:
                host_deliveries.append(value['execution_policy']['script_execution_id'])
    return {'tool_calls': sum(calls.values()), 'tool_call_counts': dict(calls),
            'failed_or_unparseable_tool_results': failures,
            'revision_calls': sum(count for name, count in calls.items() if name.endswith(('__revise_deck', '__revise_delivery'))),
            'render_calls': sum(count for name, count in calls.items() if name.endswith(('__render_deck', '__render_delivery', '__build_delivery', '__restyle_deck'))),
            'pending_plan_read_calls': calls.get('mcp__ppt__read_pending_plan', 0),
            'pending_plan_repair_calls': calls.get('mcp__ppt__repair_pending_plan', 0),
            'successful_model_selected_composed_calls': successful_composed,
            'host_script_delivered_count': len(set(host_deliveries)),
            'retry_count': None, 'retry_note': '重复读取/生成不必然是重试；保留逐调用事件，不凭重复工具名虚构重试次数。'}, deliveries


def policy_evidence(row: dict) -> tuple[dict | None, dict | None]:
    """Collect and verify actual host audit; old previews retain old scope."""
    if row['execution'] not in ('baseline_steps', 'host_delivery'):
        return None, None
    job = private_path(Path(row['job'])).resolve(strict=True)
    audit = private_path(job.parent / 'delivery-adapter-audit.jsonl').resolve(strict=True)
    loaded = [item for item in read_rows(audit) if item.get('kind') == 'execution_policy_loaded']
    if not loaded:
        raise ValueError('没有实际宿主策略加载审计')
    evidence = {'job_path': str(job), 'job_sha256': file_hash(job),
                'audit_path': str(audit), 'audit_sha256': file_hash(audit),
                'policy_sha256': loaded[-1].get('policy_sha256')}
    record = {'execution_policy_evidence': evidence,
              'evidence_lock': {str(job): evidence['job_sha256'], str(audit): evidence['audit_sha256']}}
    checked = _execution_policy_binding(record, {'execution_strategy': row['execution']})
    return evidence, checked


def verified_artifacts(deliveries: list[dict], output: Path, validation_reports: dict | None = None) -> list[dict]:
    """只接受实际成功交付回执并核字节；这只证明机械交付，不判科学质量。"""
    verified = []
    for receipt in deliveries:
        report = (validation_reports or {}).get(receipt['validation_id'])
        if (not isinstance(report, dict) or report.get('passed') is not True
                or report.get('deck_id') != receipt.get('deck_id')
                or report.get('file_sha256') != receipt.get('file_sha256')
                or report.get('input_version') != receipt.get('input_version')
                or report.get('artifacts') != receipt.get('artifacts')):
            continue
        rows = [{'kind': 'pptx', 'path': receipt['path'], 'sha256': receipt['file_sha256']}, *receipt.get('artifacts', [])]
        if not rows:
            continue
        try:
            for row in rows:
                path = private_path(Path(row['path'])).resolve(strict=True)
                # 真实PDF/PNG在已有validation私有目录，可能不在job/outputs。
                if row['kind'] == 'pptx' and not path.is_relative_to(output.resolve()):
                    raise ValueError('交付PPT越出当前job输出')
                if file_hash(path) != row['sha256']:
                    raise ValueError('交付文件版本不符')
            verified.append({'validation_id': receipt['validation_id'], 'deck_id': receipt.get('deck_id'),
                             'files': rows, 'receipt_sha256': digest(receipt)})
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return verified


def prompt_feedback_evidence(row: dict) -> dict:
    """从实际冻结prompt字节分出稳定指导、同题正文与策略，保留完整版本。"""
    path = private_path(Path(row['prompt'])).resolve(strict=True)
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != row['prompt_sha256']:
        raise ValueError('反馈prompt版本与任务冻结值不符，不登记虚假的前缀证据')
    task_marker = '\n本次任务：\n'.encode('utf-8')
    prefix, marker, _ = raw.partition(task_marker)
    if raw.count(task_marker) != 1 or not marker or not prefix.strip():
        raise ValueError('实际prompt缺少公开任务分界，无法证明稳定前缀')
    execution_marker = '\n本次执行方式：'.encode('utf-8')
    shared, strategy_marker, strategy = raw.partition(execution_marker)
    if raw.count(execution_marker) != 1 or not strategy_marker or not strategy.strip():
        raise ValueError('实际prompt缺少公开策略分界，无法证明同题不同策略')
    shared_sha = hashlib.sha256(shared).hexdigest()
    if shared_sha != row['shared_prompt_sha256']:
        raise ValueError('实际共享任务prompt与双路预览不符')
    return {'path': str(path), 'sha256': actual,
            'prefix_sha256': hashlib.sha256(prefix).hexdigest(),
            'shared_prompt_sha256': shared_sha,
            'strategy_sha256': hashlib.sha256(strategy).hexdigest(),
            'scope': 'actual_prompt_bytes_before_public_task_and_execution_markers'}


def feedback_record(data: dict, group: str, result: dict, evidence: Path,
                    review_evidence: Path | None = None) -> dict:
    """绑定实际prompt与交付证据；科学/视觉pending不作为学习认证。"""
    account = result.get('accounting') or {}
    row = data['groups'][group]
    run_dir = result.get('model_run_directory')
    prompt_evidence = prompt_feedback_evidence(row)
    record = {
        'schema_version': 1, 'run_id': Path(run_dir).name if run_dir else data['trial_id'] + '-' + group,
        'task_identity': digest(data['task']), 'pair_id': data['trial_id'], 'group': group,
        'consent': {'collect': True, 'learn': False},
        'source_evidence': [{'source_id': item['document_id'], 'sha256': item['version_sha256']}
                            for item in data['task']['inputs']],
        'versions': {'model': data['model'], 'provider': data['provider'], 'reasoning_effort': 'off',
                     'tool_schema_sha256': result['tool_schema_sha256'], 'prompt_sha256': prompt_evidence['sha256'],
                     'prompt_prefix_sha256': prompt_evidence['prefix_sha256'],
                     'template_sha256': digest({'template': data['task']['template'],
                                                'renderer': data['code']['files'].get('scenarios/research_ppt/dist/render.js')}),
                     'runtime_sha256': data['code']['sha256']},
        'quality': {'delivery': 'passed' if result['mechanical_delivery_verified'] else 'failed',
                    'scientific': 'pending', 'visual': 'pending', 'reviewer': 'unreviewed', 'revision_minutes': None},
        'cost': {'requests': account.get('upstream_requests'),
                 'cache_hit_input_tokens': account.get('prompt_cache_hit_tokens'),
                 'cache_miss_input_tokens': account.get('prompt_cache_miss_tokens'),
                 'output_tokens': account.get('completion_tokens'), 'proxy_usd': account.get('observed_proxy_usd'),
                 'billed_usd': None, 'recovery_usd': None, 'elapsed_seconds': result['elapsed_seconds']},
        'run_dir': run_dir, 'identity_confirmed': False,
        'candidate_version': result.get('candidate_version') or (
            data['active_learning']['version'] if group == 'optimized' and data.get('active_learning') else None),
        'execution_strategy': row['execution'], 'effective_mode': result.get('effective_mode'),
        'shared_prompt_sha256': prompt_evidence['shared_prompt_sha256'],
        'prompt_evidence': prompt_evidence,
        'delivery_evidence': {'path': str(evidence), 'sha256': file_hash(evidence)},
    }
    if result.get('execution_policy_evidence') is not None:
        record['execution_policy_evidence'] = result['execution_policy_evidence']
    if review_evidence is not None:
        review_evidence = private_path(review_evidence).resolve(strict=True)
        record['review_evidence'] = {'path': str(review_evidence), 'sha256': file_hash(review_evidence)}
    return record


def collect_feedback(data: dict, group: str, result: dict, evidence: Path) -> None:
    """显式同意后保存pending反馈；反馈故障不影响双路真实交付。"""
    path = evidence.parent / (group + '-feedback.json')
    try:
        record = feedback_record(data, group, result, evidence)
        save_new(path, record)
        from .feedback_learning import FeedbackStore
        stored = FeedbackStore(private_path(Path(data['feedback_store']))).collect(record)
        save_new(evidence.parent / (group + '-feedback-receipt.json'), stored)
    except Exception as exc:
        # 反馈收集故障不丢交付，也不伪造已采集/已学习。
        save_new(evidence.parent / (group + '-feedback-error.json'), {'error_type': type(exc).__name__,
                 'message': str(exc)[:1000], 'record': str(path), 'delivery_affected': False})


def run_trial(path: Path) -> tuple[int, Path]:
    path, data = checked_trial(path)
    directory = path.parent
    if not data['allow_output']:
        raise ValueError('预览未授权输出；使用 --allow-output 重新准备，付费执行不暗中提高权限')
    # 每份冻结预览只运行一次；中断也保留，下一次必须新ID。
    save_new(directory / 'execution-started.json', {'trial_sha256': file_hash(path),
             'started_utc': datetime.now(timezone.utc).isoformat(), 'code_sha256': data['code']['sha256']})
    schemas = {group: freeze_schema(data['groups'][group], directory / (group + '-schema.json')) for group in GROUPS}
    if schemas['baseline']['schema_sha256'] != schemas['optimized']['schema_sha256']:
        raise ValueError('两组实际schema不同，拒绝付费对照')
    save_new(directory / 'effective-runtime.json', {'schemas': schemas, 'config': data,
             'credentials_recorded': False, 'context_compression': 'off', 'reasoning_effort': 'off'})
    results = {}
    for group in data['order']:
        checked_trial(path)  # 两路开始前都重新查来源/源码，拒绝过程中的变更。
        row = data['groups'][group]
        env = dict(os.environ, SSS_PPT_JOB=row['job'], PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
        args = [*row['run_arguments'], '--call-model']
        started = time.monotonic()
        log = directory / (group + '-harness.log')
        runs = ROOT / '.local/runs'
        before = {child.name for child in runs.iterdir() if child.is_dir()} if runs.is_dir() else set()
        print(json.dumps({'running_group': group, 'budget_cap_usd': row['budget_cap_usd'],
                          'log': str(log)}, ensure_ascii=False), flush=True)
        with log.open('x', encoding='utf-8') as stream:
            run = subprocess.run(args, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
        log.chmod(0o600)
        metrics, events, ledger = {}, [], None
        run_dir = locate_run(log, before, row)
        if run_dir:
            metrics = read_json(run_dir / 'metrics.json') if (run_dir / 'metrics.json').is_file() else {}
            events = read_rows(run_dir / 'agent-events.jsonl')
            ledger = read_rows(run_dir / 'cost-ledger.jsonl')
        frozen_policy, checked_policy, policy_error = None, None, None
        try:
            frozen_policy, checked_policy = policy_evidence(row)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            policy_error = type(exc).__name__ + ': ' + str(exc)[:500]
        tool_summary, receipts = summarize_tools(events, row['configured_tool_order'], checked_policy)
        invocation_files = [item for item in Path(row['job']).parent.glob('invocation-*.json')
                            if item.resolve() != Path(row['invocation']).resolve()]
        effective_invocation = read_json(invocation_files[0]) if len(invocation_files) == 1 else {}
        combo_calls = sum(tool_summary['tool_call_counts'].get('mcp__ppt__' + name, 0)
                          for name in ('build_delivery', 'render_delivery', 'revise_delivery'))
        if row['execution'] in ('baseline_steps', 'host_delivery'):
            strategy_adherence = (checked_policy is not None and not policy_error
                                  and tool_summary['successful_model_selected_composed_calls'] == 0
                                  and (row['execution'] == 'baseline_steps'
                                       or tool_summary['host_script_delivered_count'] > 0))
        else:
            strategy_adherence = combo_calls == 0 if group == 'baseline' else combo_calls > 0
        validation_reports, validation_error = {}, None
        try:
            from .recovery import CheckpointPPTService
            service = CheckpointPPTService(Path(row['job']))
            for receipt in receipts:
                report = service.validations.get(receipt['validation_id'])
                if report is not None and report.get('passed') is True:
                    service.checked_validation_artifacts(report)
                    validation_reports[receipt['validation_id']] = report
        except Exception as exc:
            validation_reports = {}
            validation_error = type(exc).__name__
        artifacts = verified_artifacts(receipts, Path(row['output_directory']), validation_reports)
        result = {'group': group, 'execution': row['execution'],
                  'rsi_enabled': effective_invocation.get('effective_mode') == 'execute',
                  'requested_mode': row['mode'], 'effective_mode': effective_invocation.get('effective_mode'),
                  'fallback_reason': effective_invocation.get('fallback_reason'),
                  'effective_invocation': effective_invocation,
                  'strategy_adherence': strategy_adherence,
                  'execution_policy_evidence': frozen_policy, 'execution_policy_error': policy_error,
                  'candidate_version': data['active_learning']['version']
                                       if group == 'optimized' and data.get('active_learning') else None,
                  'returncode': run.returncode, 'status': metrics.get('status', 'startup_failed'),
                  'elapsed_seconds': round(time.monotonic() - started, 3),
                  'model_run_directory': str(run_dir) if run_dir else None, 'log': str(log),
                  'tool_schema_sha256': schemas[group]['schema_sha256'],
                  'model_metrics': metrics, 'tools': tool_summary,
                  'accounting': {**collect_accounting(run_dir), **summarize_ledger(ledger, metrics)}
                                if run_dir is not None and ledger is not None else None,
                  'mechanical_delivery_verified': bool(artifacts), 'deliveries': artifacts,
                  'validation_state_error_type': validation_error,
                  'scientific_quality': '未评审', 'visual_quality': '未评审',
                  'manual_revision_minutes': None, 'qualified_total_cost_usd': None,
                  'failure': None if run.returncode == 0 and artifacts else
                             '未确认完整机械交付；查看私有Harness日志、metrics和工具失败记录，不因文件存在判成功'}
        evidence = directory / (group + '-delivery-receipts.json')
        save_new(evidence, {'schema_version': 1, 'mechanical_delivery_verified': bool(artifacts),
            'files': [file for delivery in artifacts for file in delivery['files']],
            'source': str(run_dir / 'agent-events.jsonl') if run_dir else None,
            'run_events_sha256': file_hash(run_dir / 'agent-events.jsonl')
            if run_dir and (run_dir / 'agent-events.jsonl').is_file() else None, 'receipts': receipts,
            'execution_policy_evidence': frozen_policy})
        save_new(directory / (group + '-result.json'), result)
        if data.get('collect_feedback'):
            collect_feedback(data, group, result, evidence)
        results[group] = result
    accounts = [result['accounting'] for result in results.values()]
    report = {'trial_id': data['trial_id'], 'trial_sha256': file_hash(path),
              'comparison': data['comparison'], 'results': results,
              'double_run_total_proxy_usd': round(sum(account['observed_proxy_usd'] for account in accounts), 10)
              if all(account is not None and account['observed_proxy_usd'] is not None for account in accounts) else None,
              'double_run_budget_accounted_usd': round(sum(account['budget_accounted_usd'] for account in accounts), 10)
              if all(account is not None and account['budget_accounted_usd'] is not None for account in accounts) else None,
              'budget_cap_usd_total': data['budget_cap_usd_total'], 'provider_bill_usd_total': None,
              'quality': '未评审', 'same_quality_cost_reduction': None,
              'learning_cost': data['learning_cost'], 'review_template': str(directory / 'review-template.json'),
              'conclusion': '先逐页评审再比较合格成本；局部请求差和组合脚本不算RSI效果。'}
    report_path = directory / 'comparison.json'
    save_new(report_path, report)
    return (0 if all(result['returncode'] == 0 and result['mechanical_delivery_verified']
                     and result['strategy_adherence'] for result in results.values()) else 2), report_path


def review_trial(path: Path, review_path: Path) -> Path:
    """人评追加新结果；历史交付和原成绩不追改，也不据此自动晋级工具。"""
    path = private_path(path).resolve(strict=True)
    review_path = private_path(review_path).resolve(strict=True)
    data, review = read_json(path), read_json(review_path)
    report_path = path.parent / 'comparison.json'
    report = read_json(report_path)
    if (report.get('trial_sha256') != file_hash(path) or review.get('trial_id') != data['trial_id']
            or set(review.get('groups', {})) != set(GROUPS)
            or not isinstance(review.get('reviewer'), str) or not review['reviewer'].strip()):
        raise ValueError('评审必须关联原冻结任务并填写实际评审人')
    reviewer_kind = review.get('reviewer_kind', 'ai-assisted' if review['reviewer'] == 'ai-assisted' else 'human')
    if reviewer_kind not in ('human', 'user', 'ai-assisted'):
        raise ValueError('reviewer_kind 需 human/user/ai-assisted，不能混称独立人评')
    if review['reviewer'].strip() == 'ai-assisted' and reviewer_kind != 'ai-assisted':
        raise ValueError('AI辅助评审不能通过 reviewer_kind 改称独立人评')
    qualified = {}
    for group in GROUPS:
        row = review['groups'][group]
        if any(row.get(field) is not None and type(row[field]) is not bool for field in REVIEW_FIELDS):
            raise ValueError('评审项只接受true/false/null')
        minutes = row.get('revision_minutes')
        if minutes is not None and (type(minutes) not in (int, float) or not math.isfinite(minutes) or minutes < 0):
            raise ValueError('人工修改分钟数须为非负有限数或null')
        result = report['results'][group]
        if row.get('editable_and_rendered') is True and not result['mechanical_delivery_verified']:
            raise ValueError('没有真实机械交付证据，不能仅靠填写true判通过')
        qualified[group] = (result['mechanical_delivery_verified']
                            and result.get('strategy_adherence') is not False
                            and all(row.get(field) is True for field in REVIEW_FIELDS))
    reduction = None
    if all(qualified.values()):
        baseline, optimized = (report['results'][group]['accounting'] for group in GROUPS)
        if (baseline and optimized and baseline['usage_complete'] and optimized['usage_complete']
                and not baseline['unsettled_request_count'] and not optimized['unsettled_request_count']
                and baseline['observed_proxy_usd'] > 0):
            reduction = {'baseline_proxy_usd': baseline['observed_proxy_usd'],
                         'optimized_proxy_usd': optimized['observed_proxy_usd'],
                         'proxy_cost_reduction_fraction': 1 - optimized['observed_proxy_usd'] / baseline['observed_proxy_usd'],
                         'scope': ('同任务AI辅助评审条件下的单路代理模型费用；不是独立人评或生产准入；人工/维护/学习及实付未知'
                                   if reviewer_kind == 'ai-assisted' else
                                   '同任务用户评审合格后的单路代理模型费用；未折算人工/维护/学习，不等于账单实付')}
    out = path.parent / ('reviewed-' + uuid4().hex + '.json')
    save_new(out, {'trial_id': data['trial_id'], 'original_comparison_sha256': file_hash(report_path),
                  'review_sha256': file_hash(review_path), 'review': review, 'qualified': qualified,
                  'reviewer_kind': reviewer_kind, 'independent_human_review': reviewer_kind in ('human', 'user'),
                  'same_quality_model_cost_comparison': reduction,
                  'manual_revision_minutes': {group: review['groups'][group].get('revision_minutes') for group in GROUPS},
                  'automatic_rsi_promotion': False})
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trial', type=Path, help='重新使用冻结预览；一份预览只执行一次')
    parser.add_argument('--review', type=Path, help='关联--trial追加人工评审，不运行模型、不自动晋级')
    parser.add_argument('--input', type=Path, nargs='+')
    parser.add_argument('--instruction', default='根据资料制作清楚、准确、自然的中文科研汇报，优先原图与实验条件。')
    parser.add_argument('--slides', type=int, default=6)
    parser.add_argument('--min-original-figures', type=int, default=0,
                        help='两路相同的显式最低完整原图数；默认0，不从题面推断')
    parser.add_argument('--template', choices=('academic', 'lab'), default='lab')
    parser.add_argument('--operation', choices=('generate', 'restyle'), default='generate')
    parser.add_argument('--budget-usd', type=float, default=3.0, help='双路总预算上限，每路各半，不是预计费用')
    parser.add_argument('--max-steps', type=int, default=60)
    parser.add_argument('--max-output', type=int, default=8000)
    parser.add_argument('--order', choices=('baseline-first', 'optimized-first'), default='baseline-first')
    parser.add_argument('--allow-output', action='store_true')
    parser.add_argument('--collect-feedback', action='store_true', help='允许留存轨迹/费用和待评审反馈；默认不授权学习')
    parser.add_argument('--use-active-learning', action='store_true', help='显式继承已晋级且仍有效的Motif，保留公共版本/准入守卫')
    parser.add_argument('--candidate-version', help='显式在隔离双路任务评测已认证候选；不更改active，不代表收益已准入')
    parser.add_argument('--feedback-store', type=Path, default=DEFAULT_STORE)
    parser.add_argument('--document-cache', action='store_true', help='两组使用相同持久解析缓存；冻结实际开关，不冒称RSI')
    parser.add_argument('--execution-policy', choices=('controlled', 'legacy_model_selected'), default='controlled',
                        help='默认宿主强制两组禁止直接组合；legacy仅历史诊断兼容')
    parser.add_argument('--call-model', action='store_true')
    args = parser.parse_args()
    try:
        if args.review:
            if not args.trial or args.input or args.call_model:
                raise ValueError('追加评审需 --trial 与 --review，不能同时启动模型或新输入')
            print(json.dumps({'reviewed_comparison': str(review_trial(args.trial, args.review))}, ensure_ascii=False))
            return 0
        if args.trial and args.input:
            raise ValueError('--trial 与 --input 不能同时使用；已冻结参数从trial读取')
        if args.trial:
            path, data = checked_trial(args.trial)
        else:
            if not args.input:
                raise ValueError('请提供已上传到仓库 .local 的 --input PDF/PPTX')
            path = prepare_trial(args.input, args.instruction, args.slides, budget=args.budget_usd,
                                 max_steps=args.max_steps, max_output=args.max_output, template=args.template,
                                 operation=args.operation, allow_output=args.allow_output, order=args.order,
                                 collect_feedback=args.collect_feedback, use_active_learning=args.use_active_learning,
                                 feedback_store=args.feedback_store, candidate_version=args.candidate_version,
                                 document_cache=args.document_cache, execution_policy=args.execution_policy,
                                 minimum_original_figures=args.min_original_figures)
            data = read_json(path)
        print(json.dumps(preview(path, data), ensure_ascii=False, indent=2), flush=True)
        if not args.call_model:
            return 0
        status, report = run_trial(path)
        print(json.dumps({'comparison': str(report), 'status': status,
                          'quality': '未评审', 'review': str(path.parent / 'review-template.json')}, ensure_ascii=False), flush=True)
        return status
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as exc:
        print(json.dumps({'ok': False, 'error_type': type(exc).__name__, 'message': str(exc),
                          'recovery': '保留本次失败目录和账本；修复依赖/输入后创建新预览，不覆盖旧结果。'}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
