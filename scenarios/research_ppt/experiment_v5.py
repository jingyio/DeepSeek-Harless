"""V5 科研设计 Skill / Motif / 受限布局 RSI 的真实串行对照；默认只预览。

只复用公共 Harness 入口，不创建第二个 Agent 循环。运行资料与账本留在
.local，日志留在 test-logs；resume 不重跑已结束或中断且费用未知的运行。
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from contextlib import contextmanager
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scenarios.research_ppt.cli import prepare
from scenarios.research_ppt.documents import file_hash
from scenarios.research_ppt.experiment import (
    ID, ORDERS, lines, motif_dependencies, read, token_totals,
    verified_deliveries, version,
)
from scenarios.research_ppt.layout_learning import validate_certificate
from scenarios.research_ppt.service import SCENE, private_path
from src.adapters.dsh_event_projection import is_original_tool_result
from src.adapters.dsh_trajectory import _observation_digest

EXPERIMENT_ID = 'research-ppt-v5-design-rsi-20261010'
GROUPS = ('steps_baseline', 'motif', 'motif_rsi')
MANIFEST = ROOT / '.local/research-ppt/libraries/e556e3dc732c4b8b891c11120eb27618/online-manifest.json'
GUARD = ROOT / '.local/research-ppt/rsi/v2-20261010/active-guard.json'
MAX_TOTAL_USD = 15.0
MAX_RUN_USD = 0.75


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def write(path: Path, value):
    """原子落盘，避免恢复时把截断 summary 当成完整账本。"""
    path = private_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2,
        allow_nan=False) + '\n', encoding='utf-8')
    temporary.chmod(0o600)
    temporary.replace(path)


@contextmanager
def exclusive_run(area: Path):
    """进程级排他锁；崩溃遗留锁需先人工核对进程和账本，不能自动清除。"""
    lock = area / 'driver.lock'
    try:
        with lock.open('x', encoding='utf-8') as stream:
            stream.write(json.dumps({'pid': os.getpid(), 'started_utc': datetime.now(timezone.utc).isoformat()}))
        lock.chmod(0o600)
    except FileExistsError:
        raise ValueError('实验目录已被锁定；先核对运行进程和费用，不并行恢复或自动重复付费') from None
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


def default_tasks(inputs: Path) -> list[dict]:
    """五个来源有重叠的独立任务，不声称五份完全独立数据集。"""
    rows = [
        ('V1-rag-briefing', ['rag'], 8, 'lab',
         '为了解生成模型但尚未实现检索增强的同学制作8页中文组会汇报，约10分钟。'
         '围绕为什么加入检索、检索与生成如何连接、论文证据和局限组织；'
         '至少一页可编辑的方法流程，至少一张经图注定位的论文原图，讲清实验指标与对照条件。'
         '封面也计入8页，具体叙事和各页内容由你根据原文决定，不编造数字。'),
        ('V2-qlora-deployment', ['qlora'], 7, 'academic',
         '制作7页中文工程决策汇报，回答有限显存时QLoRA如何使大模型微调可行。'
         '解释量化、适配器与优化器的关系，使用可编辑流程和一张真实原图；'
         '如果引用显存或效果数值，保留模型规模、硬件、指标和比较条件。'
         '最后给出适用条件与原文未证明的边界，避免把训练结论直接说成推理加速。'),
        ('V3-preference-comparison', ['instructgpt', 'dpo'], 10, 'lab',
         '为正在选择偏好对齐训练路线的研究同学制作10页中文方法比较汇报。'
         '比较InstructGPT中的RLHF流程与DPO的直接偏好优化：训练阶段、数据要求、'
         '优化目标、成本来源和限制。用可编辑流程及统一维度的比较页面，至少引用一张相关原图。'
         '不同模型、数据和评测条件不能拼成统一效果排行榜；明确哪些比较只是机制分析。'),
        ('V4-knowledge-access', ['t5', 'rag'], 9, 'academic',
         '制作9页中文研究讨论PPT，围绕知识密集型任务中参数内知识与外部检索各承担什么职责。'
         '从T5统一text-to-text框架和RAG方法提取证据，解释训练与使用时的信息流及更新方式；'
         '至少一张真实原图、一页可编辑流程和一页适用条件比较。'
         '两篇论文并非同条件替代实验，不把跨论文数字视为公平优劣结论；用清楚短结论推进讨论。'),
        ('V5-research-pipeline', ['rag', 'qlora', 'instructgpt', 'dpo'], 12, 'lab',
         '为课题组规划一个知识问答助手，制作12页中文研究方案评审PPT。'
         '根据这四篇论文讨论检索增强、低显存微调和偏好对齐分别解决的问题，'
         '说明模块如何组合、RLHF与DPO何时需要选择、哪些组合只是待验证的设计推论。'
         '包含可编辑总流程、至少两篇论文的相关原图、可复算或可验证的评测计划及风险。'
         '保留所有事实的来源和条件，不能暗示论文已经实测了这套完整组合系统。'),
    ]
    return [{'task_id': task_id, 'inputs': [str(inputs / (name + '.pdf')) for name in names],
             'slides': slides, 'template': template, 'operation': 'generate', 'instruction': instruction}
            for task_id, names, slides, template, instruction in rows]


def load_tasks(args) -> dict:
    if args.matrix:
        matrix = read(private_path(args.matrix.resolve(strict=True)))
        if not isinstance(matrix, dict) or matrix.get('schema_version') != 1:
            raise ValueError('自定义 matrix 需要 schema_version=1 和 tasks')
        tasks = matrix.get('tasks')
        base = args.matrix.resolve().parent
    else:
        tasks, base = default_tasks(args.inputs.resolve()), ROOT
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= 30:
        raise ValueError('需要1–30个任务')
    seen = set()
    for index, task in enumerate(tasks):
        if not isinstance(task, dict) or not ID.fullmatch(task.get('task_id', '')) or task['task_id'] in seen:
            raise ValueError('task_id 必须是独立的安全标识')
        seen.add(task['task_id'])
        paths = task.get('inputs')
        if not isinstance(paths, list) or not 1 <= len(paths) <= 8:
            raise ValueError('任务需要1–8份输入')
        resolved = [private_path((Path(p) if Path(p).is_absolute() else base / p).resolve(strict=True)) for p in paths]
        if any(p.suffix.lower() not in {'.pdf', '.pptx'} for p in resolved):
            raise ValueError('输入必须为私有 PDF/PPTX')
        task['inputs'] = [str(p) for p in resolved]
        task['input_versions'] = [file_hash(p) for p in resolved]
        if type(task.get('slides')) is not int or not 1 <= task['slides'] <= 30:
            raise ValueError('slides 必须为1–30的整数')
        if not isinstance(task.get('instruction'), str) or not 1 <= len(task['instruction'].strip()) <= 10000:
            raise ValueError('任务需要不超过10000字符的 instruction')
        if task.get('template', 'academic') not in {'lab', 'academic'} or task.get('operation', 'generate') not in {'generate', 'restyle'}:
            raise ValueError('无效 template / operation')
        order = task.get('group_order', [GROUPS[i] for i in ORDERS[index % len(ORDERS)]])
        if not isinstance(order, list) or len(order) != 3 or set(order) != set(GROUPS):
            raise ValueError('group_order 必须是三组的排列')
        task['group_order'] = order
    if args.task and any(name not in seen for name in args.task):
        raise ValueError('--task 含未知任务')
    return {'schema_version': 1, 'experiment_id': EXPERIMENT_ID, 'groups': list(GROUPS), 'tasks': tasks,
            'task_origin': 'researcher_authored_real_paper_tasks', 'sources_overlap': True,
            'manifest': str(args.manifest.resolve()), 'guard': str(args.guard.resolve()),
            'quality': 'quality_not_reviewed'}


def source_hashes() -> dict:
    suffixes = {'.py', '.ts', '.js', '.mjs', '.json', '.md', '.txt', '.yml', '.yaml'}
    files = [p for p in SCENE.rglob('*') if p.is_file() and p.suffix in suffixes
             and not any(part in {'node_modules', '__pycache__', '.local', '.git'} for part in p.relative_to(SCENE).parts)]
    files += [ROOT / name for name in (
        'scripts/run-scenario.py', 'scripts/prepare-online-motif.py', 'src/adapters/scenario.py',
        'src/adapters/harness_runtime.py', 'src/adapters/native_budget.py', 'src/adapters/deepseek_cost_gate.py',
        'src/adapters/dsh_scenario_guard.mjs', 'src/adapters/dsh_online_motif.mjs',
        'src/motif_core/online_skill_runtime.mjs', 'config/semantic-sdk.patch.yml', 'package-lock.json')]
    return {str(p.relative_to(ROOT)): file_hash(p) for p in sorted(set(files)) if p.is_file()}


def runtime_hashes(hashes: dict) -> dict:
    # README/归因文档和回归测试也留快照，执行守卫只检查影响本次运行的文件。
    return {path: value for path, value in hashes.items() if '/tests/' not in path
            and Path(path).name not in {'README.md', 'SOURCES.md'} }


async def advertised_schema(job: Path) -> dict:
    from mcp import Client, StdioServerParameters
    allowed = read(SCENE / 'scenario.json')['allowed_tools']
    params = StdioServerParameters(command=sys.executable, args=[str(SCENE / 'server.py')],
        cwd=ROOT, env={'PYTHONPATH': str(ROOT), 'SSS_PPT_JOB': str(job)})
    async with Client(params, read_timeout_seconds=30) as client:
        tools = (await client.list_tools()).tools
        offered = {f'mcp__ppt__{t.name}': t.model_dump(mode='json', by_alias=True) for t in tools}
        if any(name not in offered for name in allowed):
            raise ValueError('MCP 实际 schema 缺少批准工具')
        ordered = [{'harness_tool_name': name, 'mcp_tool': offered[name]} for name in allowed]
        return {'allowed_tool_order': allowed, 'mcp_advertised_order': [t.name for t in tools],
                'ordered_allowed_mcp_schemas': ordered, 'mcp_schema_sha256': digest(ordered),
                'scope': 'real_mcp_list_tools_not_provider_request_payload',
                'provider_facing_schema_sha256': None}


def certificate_record(path: Path | None) -> tuple[dict | None, str | None]:
    if path is None:
        return None, '未提供独立机械认证证书；第三组明确跳过'
    try:
        path = private_path(path.resolve(strict=True))
        certificate = validate_certificate(path)
        return {'path': str(path), 'sha256': file_hash(path),
                'policy_digest': certificate['policy_digest'], 'policy': certificate['policy'],
                'suite_sha256': certificate['suite_sha256'],
                'proposal_sha256': certificate['proposal_sha256'], 'renderer_version': certificate['renderer_version'],
                'mechanical_certified': True, 'visual_quality_certified': False,
                'scientific_quality_certified': False}, None
    except (KeyError, OSError, ValueError, TypeError) as exc:
        return None, f'布局证书无效，第三组跳过：{exc}'


def snapshot(matrix: dict, args, motif: dict | None, certificate: dict | None, schema: dict) -> dict:
    versions = {}
    for name in ('deepseek-harness-sdk', 'mcp', 'pypdf', 'PyMuPDF', 'python-pptx'):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = 'missing'
    hashes = source_hashes()
    return {'schema_version': 1, 'experiment_id': EXPERIMENT_ID,
        'recorded_utc': datetime.now(timezone.utc).isoformat(), 'matrix_sha256': digest(matrix),
        'commit': version(['git', 'rev-parse', 'HEAD']),
        'tracked_worktree_status': version(['git', 'status', '--porcelain', '--untracked-files=no']),
        'source_hashes': hashes, 'runtime_hashes': runtime_hashes(hashes),
        'os': platform.platform(), 'python': platform.python_version(), 'node': version(['node', '--version']),
        'libreoffice': version(['libreoffice', '--version']), 'packages': versions,
        'design_skill_enabled_in_all_groups': True,
        'design_skill_sha256': file_hash(SCENE / 'skills/research-design/SKILL.md'),
        'tool_schema': schema, 'provider': 'deepseek-official', 'model': 'deepseek-flash',
        'reasoning_effort': 'off', 'compression': 'disabled_by_public_entry_default',
        'execution': 'steps', 'max_output_tokens': 6000, 'max_steps': args.max_steps,
        'total_budget_cap_usd': args.total_budget_usd, 'per_run_budget_cap_usd': args.per_run_budget_usd,
        'interval_seconds': args.interval_seconds, 'retry_policy': 'no_automatic_experiment_retry',
        'embedding_model': 'structural-only', 'semantic_matching': 'disabled',
        'matching_thresholds': {'min_similarity': os.environ.get('SSS_MOTIF_MIN_SIMILARITY', '0.8'),
                               'min_margin': os.environ.get('SSS_MOTIF_MIN_MARGIN', '0.1')},
        'motif': motif, 'layout_certificate': certificate,
        'missing_configuration': ['provider_facing_tool_schema_hash_and_order', 'provider_internal_retry_policy',
                                  'provider_invoice', 'independent_human_blind_review', 'human_revision_minutes'],
        'group_interpretation': {'steps_baseline': '新设计 Skill + 默认渲染 + 普通 DSH',
                                'motif': '相同设计 Skill + 默认渲染 + 已认证来源读取 Motif',
                                'motif_rsi': '相同设计 Skill + 已认证 Motif + 冻结的机械认证布局策略'},
        'rsi_boundary': '受限布局策略；不是模型生成工具或新 Motif；机械认证不证明美学或科学质量'}


def check_versions(task: dict, config: dict, motif, certificate) -> str | None:
    if [file_hash(Path(p)) for p in task['inputs']] != task['input_versions']:
        return 'source_version_changed'
    if runtime_hashes(source_hashes()) != config['runtime_hashes']:
        return 'runtime_version_changed'
    if motif and (file_hash(Path(motif['manifest'])) != motif['manifest_sha256'] or
                  file_hash(Path(motif['guard'])) != motif['guard_sha256']):
        return 'motif_version_changed'
    if certificate:
        if file_hash(Path(certificate['path'])) != certificate['sha256']:
            return 'layout_certificate_changed'
        validate_certificate(Path(certificate['path']))
    return None


def terminate_tree(process):
    if process is None or process.poll() is not None:
        return
    # 本驱动只在服务器运行；子进程单独进程组，避免留下继续计费的 Harness。
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=15)


def collect(row: dict, job: Path, output_dir: Path | None) -> dict:
    metrics, ledger = {}, []
    if output_dir is not None:
        row['run_dir'] = str(output_dir)
        if (output_dir / 'metrics.json').is_file():
            metrics = read(output_dir / 'metrics.json')
        ledger = lines(output_dir / 'cost-ledger.jsonl')
        row.update(metrics=metrics, ledger=ledger, paid_model_requests=metrics.get('upstream_requests'),
                   model_requests=metrics.get('model_requests'), api_cost_usd=metrics.get('budget_accounted_usd'),
                   reasoning_tokens=metrics.get('reasoningTokens'),
                   verified_model_requests_skipped=metrics.get('model_requests_skipped_verified'),
                   upstream_429=any(r.get('response_status') == 429 for r in ledger))
        if metrics.get('status'):
            row['status'] = metrics['status']
        row.update(token_totals(ledger, metrics))
        requests = [r for r in ledger if 'request_id' in r]
        known = [r['observed_peak_usd'] for r in requests if isinstance(r.get('observed_peak_usd'), (int, float))]
        row['ledger_observed_peak_cost_usd'] = sum(known) if known else None
        row['ledger_usage_requests'] = len(requests)
        row['ledger_cost_complete'] = bool(requests) and len(known) == len(requests)
        names, delivered = {}, []
        for event in lines(output_dir / 'agent-events.jsonl'):
            data = event.get('data', {})
            if event.get('type') == 'tool/call':
                names[data.get('callId')] = data.get('name')
            elif is_original_tool_result(event):
                name = names.get(data.get('message', {}).get('source', {}).get('callId'), '')
                if name in {'mcp__ppt__deliver_deck', 'mcp__ppt__build_delivery'}:
                    passed, _, observed = _observation_digest(event, name)
                    if passed and observed and observed.get('delivered', True):
                        delivered.append(observed)
        row['delivery'] = {'observed_successful_tool_results': delivered, 'confirmed_tool_results': []}
        if (output_dir / 'preview.json').is_file():
            row['effective_public_preview'] = read(output_dir / 'preview.json')
        row['raw_records'] = [{'path': str(path), 'sha256': file_hash(path)} for path in
            sorted([*(output_dir.glob('*.json')), *(output_dir.glob('*.jsonl')),
                    *(output_dir.glob('.local/online-motif/*.jsonl'))]) if path.is_file()]
    reports = []
    for path in (ROOT / '.local/research-ppt/validation').glob('*/report.json'):
        report = read(path)
        if Path(report['pptx_path']).resolve().is_relative_to(job.parent / 'outputs'):
            reports.append({'path': str(path), **report})
    row['validation'] = {'reports': reports}
    row.setdefault('delivery', {'observed_successful_tool_results': [], 'confirmed_tool_results': []})
    row['delivery']['produced_pptx'] = [{'path': str(p), 'sha256': file_hash(p)}
        for p in sorted((job.parent / 'outputs').glob('*/presentation.pptx'))]
    row['delivery']['confirmed_tool_results'] = verified_deliveries(row, job)
    row['delivery_completed'] = bool(row['delivery']['confirmed_tool_results'])
    if row['status'] == 'done' and not row['delivery_completed']:
        row['status'] = 'not_delivered'
    prompt = job.parent / 'prompt.md'
    row['effective_prompt_sha256'] = file_hash(prompt) if prompt.is_file() else None
    invocation = list(job.parent.glob('invocation-*.json'))
    row['scenario_invocation'] = read(invocation[0]) if len(invocation) == 1 else None
    row['feedback_path'] = str(job.parent / 'feedback.jsonl')
    row['layout_policy_fallbacks'] = [r for r in lines(job.parent / 'feedback.jsonl')
                                    if r.get('kind') == 'layout_policy_fallback']
    cost = row.get('api_cost_usd')
    if isinstance(cost, (int, float)) and math.isfinite(cost) and cost >= 0:
        row['accounted_for_cap_usd'] = cost
        row['accounting_missing'] = False
    else:
        row['accounting_missing'] = row.get('model_call_enabled') is True
    row['billing'] = 'proxy_estimate_or_unsettled_reservation_not_invoice'
    return row


def run_one(task: dict, group: str, args, motif, certificate, area: Path, index: int, config: dict) -> dict:
    row = {'task_id': task['task_id'], 'group': group, 'run_index': index,
           'status': 'preparing', 'model_call_enabled': args.call_model,
           'model_run_started': False,
           'quality': 'quality_not_reviewed', 'delivery_completed': False,
           'started_utc': datetime.now(timezone.utc).isoformat(), 'accounted_for_cap_usd': 0.0}
    record = area / f'run-{index:02d}.json'
    write(record, row)
    if group != 'steps_baseline' and motif is None:
        row['status'] = 'skip_missing_motif'
        write(record, row); return row
    if group == 'motif_rsi' and certificate is None:
        row['status'] = 'skip_missing_certificate'
        write(record, row); return row
    changed = check_versions(task, config, motif, certificate)
    if changed:
        row['status'] = changed
        write(record, row); return row
    job = prepare([Path(p) for p in task['inputs']], task['instruction'], task['slides'], args.call_model,
                  template=task.get('template', 'academic'), operation=task.get('operation', 'generate'),
                  design_skill=True, layout_policy=Path(certificate['path']) if group == 'motif_rsi' else None)
    row['job_path'] = str(job)
    if group != 'steps_baseline':
        data = read(job); data['rsi_dir'] = str(Path(motif['guard']).parent); write(job, data)
    observed_schema = asyncio.run(advertised_schema(job))
    row['effective_mcp_schema_sha256'] = observed_schema['mcp_schema_sha256']
    if observed_schema['mcp_schema_sha256'] != config['tool_schema']['mcp_schema_sha256']:
        row['status'] = 'tool_schema_changed'
        write(record, row); return row
    command = [sys.executable, '-u', '-m', 'scenarios.research_ppt.cli', 'run', '--job', str(job),
               '--mode', 'baseline' if group == 'steps_baseline' else 'execute', '--execution', 'steps',
               '--budget-usd', str(args.per_run_budget_usd), '--max-steps', str(args.max_steps)]
    if group != 'steps_baseline':
        command += ['--manifest', motif['manifest']]
    if args.call_model:
        command.append('--call-model')
    log = ROOT / 'test-logs' / f'{area.name}-{index:02d}-{task["task_id"]}-{group}.log'
    log.parent.mkdir(parents=True, exist_ok=True)
    row.update(command=command, log_path=str(log), status='running',
               accounted_for_cap_usd=args.per_run_budget_usd if args.call_model else 0.0,
               accounting_missing=args.call_model)
    write(record, row)  # 启动前预留整个单次上限，中断后不自动重复付费。
    process, output_dir, started = None, None, time.monotonic()
    try:
        with log.open('x', encoding='utf-8') as stream:
            process = subprocess.Popen(command, cwd=ROOT,
                env=dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8'),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                encoding='utf-8', errors='replace', bufsize=1, start_new_session=True)
            row.update(process_pid=process.pid, model_run_started=args.call_model); write(record, row)
            for line in process.stdout:
                stream.write(line); stream.flush(); print(line, end='', flush=True)
                try:
                    value = json.loads(line)
                    if isinstance(value, dict) and value.get('output_dir'):
                        output_dir = private_path(Path(value['output_dir']))
                        row['run_dir'] = str(output_dir); write(record, row)
                except (ValueError, TypeError):
                    pass
            row['returncode'] = process.wait()
            row['status'] = 'preview' if not args.call_model and row['returncode'] == 0 else 'error'
    except BaseException as exc:
        terminate_tree(process)
        row.update(status='interrupted' if isinstance(exc, KeyboardInterrupt) else 'runner_error',
                   runner_error_type=type(exc).__name__)
        collect(row, job, output_dir)
        row['elapsed_seconds'] = round(time.monotonic() - started, 3)
        write(record, row)
        raise
    row['elapsed_seconds'] = round(time.monotonic() - started, 3)
    collect(row, job, output_dir)
    write(record, row)
    return row


def aggregate(rows: list[dict]) -> dict:
    groups = {}
    for group in GROUPS:
        paid = [r for r in rows if r['group'] == group and r.get('model_run_started')]
        def total(key):
            values = [r.get(key) for r in paid]
            return sum(values) if values and all(isinstance(v, (int, float)) for v in values) else None
        groups[group] = {'attempts': len(paid), 'confirmed_deliveries': sum(r.get('delivery_completed') is True for r in paid),
            'statuses': {status: sum(r['status'] == status for r in rows if r['group'] == group)
                         for status in sorted({r['status'] for r in rows if r['group'] == group})},
            'paid_model_requests': total('paid_model_requests'), 'api_cost_usd': total('api_cost_usd'),
            'elapsed_seconds': total('elapsed_seconds'), 'verified_skips': total('verified_model_requests_skipped'),
            'tokens': {key: sum(r['tokens'][key] for r in paid)
                      if paid and all(type(r.get('tokens', {}).get(key)) is int for r in paid) else None
                      for key in ('prompt_cache_hit_tokens', 'prompt_cache_miss_tokens', 'completion_tokens', 'total_tokens')},
            'same_quality_established': False}
    return {'groups': groups, 'total_accounted_for_cap_usd': sum(r.get('accounted_for_cap_usd', 0.0) for r in rows),
            'quality': 'quality_not_reviewed', 'billing': 'proxy_estimate_not_invoice',
            'warning': '须逐题独立人工盲评合格后比较成本；跨任务总量不证明质量等价或因果节省'}


def identity(config: dict) -> dict:
    keys = ('matrix_sha256', 'runtime_hashes', 'design_skill_sha256', 'tool_schema', 'model', 'provider',
            'os', 'python', 'node', 'libreoffice', 'packages',
            'reasoning_effort', 'compression', 'execution', 'max_output_tokens', 'max_steps',
            'total_budget_cap_usd', 'per_run_budget_cap_usd', 'motif', 'layout_certificate', 'matching_thresholds')
    return {key: config[key] for key in keys}


def execute_schedule(matrix: dict, args, motif, certificate, config: dict, area: Path, summary: dict) -> int:
    # run文件先于summary落盘，是中断恢复的权威记录。running不猜测已失败，不重跑。
    rows = [read(p) for p in sorted(area.glob('run-*.json'))]
    schedule = [(task, group) for task in matrix['tasks'] for group in task['group_order']]
    requested = [(index, task, group) for index, (task, group) in enumerate(schedule, 1)
                 if (not args.task or task['task_id'] in args.task) and (not args.group or group in args.group)]
    existing = {(r['task_id'], r['group']): r for r in rows}
    # 已执行项不再预留；依赖缺失的组跳过，不发请求。
    pending_cap = sum(args.per_run_budget_usd for _, task, group in requested
                     if (task['task_id'], group) not in existing and
                     (group == 'steps_baseline' or motif is not None) and
                     (group != 'motif_rsi' or certificate is not None))
    spent = sum(r.get('accounted_for_cap_usd', 0.0) for r in rows)
    if args.call_model and spent + pending_cap > args.total_budget_usd + 1e-9:
        raise ValueError('累计已记账/未知保留上限与待运行上限之和超过总防失控预算')
    summary.update(runs=rows, aggregate=aggregate(rows), latest_selection={'tasks': args.task, 'groups': args.group},
                   pending_cap_sum_usd=pending_cap, stopped_reason=None)
    write(area / 'summary.json', summary)
    print(json.dumps({'experiment_dir': str(area), 'call_model': args.call_model,
        'per_run_budget_cap_usd': args.per_run_budget_usd, 'total_budget_cap_usd': args.total_budget_usd,
        'max_steps': args.max_steps, 'task_ids': [t['task_id'] for t in matrix['tasks']],
        'selected_runs': len(requested), 'motif_dependency_error': summary.get('motif_dependency_error'),
        'layout_certificate_error': summary.get('layout_certificate_error')}, ensure_ascii=False), flush=True)
    if any(r.get('status') in {'preparing', 'running', 'interrupted'} for r in rows):
        summary['stopped_reason'] = 'unreconciled_interrupted_run_no_automatic_paid_retry'
        write(area / 'summary.json', summary)
        print(json.dumps({'summary_path': str(area / 'summary.json'), 'stopped_reason': summary['stopped_reason']}, ensure_ascii=False))
        return 2
    failures429, executed = 0, False
    for index, task, group in requested:
        if (task['task_id'], group) in existing:
            continue
        eligible = group == 'steps_baseline' or motif is not None
        eligible = eligible and (group != 'motif_rsi' or certificate is not None)
        if args.call_model and executed and eligible:
            for remaining in range(args.interval_seconds, 0, -15):
                print(f'串行间隔剩余{remaining}秒；下一题 {task["task_id"]}/{group}', flush=True)
                time.sleep(min(15, remaining))
        try:
            row = run_one(task, group, args, motif, certificate, area, index, config)
        except BaseException:
            summary.update(runs=[read(p) for p in sorted(area.glob('run-*.json'))], stopped_reason='driver_interrupted_or_error')
            summary['aggregate'] = aggregate(summary['runs']); write(area / 'summary.json', summary)
            raise
        rows.append(row); existing[(task['task_id'], group)] = row
        executed = executed or (args.call_model and eligible)
        summary.update(runs=sorted(rows, key=lambda r: r['run_index']), aggregate=aggregate(rows))
        spent = summary['aggregate']['total_accounted_for_cap_usd']
        if row['status'].endswith('_changed') or spent > args.total_budget_usd + 1e-9:
            summary['stopped_reason'] = row['status'] if row['status'].endswith('_changed') else 'accounting_exceeds_total_cap'
        failures429 = failures429 + 1 if row.get('upstream_429') else (failures429 if not eligible else 0)
        if failures429 >= 3:
            summary['stopped_reason'] = 'three_consecutive_upstream_429'
        write(area / 'summary.json', summary)
        print(json.dumps({'completed': {'task_id': row['task_id'], 'group': row['group'], 'status': row['status'],
            'delivery_completed': row.get('delivery_completed'), 'paid_model_requests': row.get('paid_model_requests'),
            'api_cost_usd': row.get('api_cost_usd')}, 'summary_path': str(area / 'summary.json')}, ensure_ascii=False), flush=True)
        if summary.get('stopped_reason'):
            break
    print(json.dumps({'summary_path': str(area / 'summary.json'), 'aggregate': summary['aggregate'],
                      'stopped_reason': summary.get('stopped_reason')}, ensure_ascii=False), flush=True)
    if summary.get('stopped_reason'):
        return 2
    return 0 if all(r['status'] in {'done', 'preview', 'skip_missing_certificate'}
                    and not r.get('returncode') for r in rows) else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, default=ROOT / '.local/research-ppt/v5-inputs')
    parser.add_argument('--matrix', type=Path, help='可选私有 JSON：schema_version=1、tasks；不限定内置任务')
    parser.add_argument('--manifest', type=Path, default=MANIFEST)
    parser.add_argument('--guard', type=Path, default=GUARD)
    parser.add_argument('--certificate', type=Path, help='独立真实布局机械认证的 certificate/active-policy.json')
    parser.add_argument('--task', nargs='+', help='只执行这些 task_id；恢复时可换选待执行子集')
    parser.add_argument('--group', choices=GROUPS, nargs='+', help='只执行所选组，顺序由各题 counterbalance 决定')
    parser.add_argument('--resume', type=Path, help='原实验私有目录；版本变化或预览/真实类型变化拒绝恢复')
    parser.add_argument('--call-model', action='store_true')
    parser.add_argument('--per-run-budget-usd', type=float, default=MAX_RUN_USD)
    parser.add_argument('--total-budget-usd', type=float, default=MAX_TOTAL_USD)
    parser.add_argument('--max-steps', type=int, default=40)
    parser.add_argument('--interval-seconds', type=int, default=30)
    args = parser.parse_args()
    if ROOT.resolve() != Path('/root/autodl-tmp/xjj'):
        parser.error('本轮所有预览和实验仅在服务器 /root/autodl-tmp/xjj 执行')
    if not 1 <= args.max_steps <= 40 or not 0 <= args.interval_seconds <= 3600:
        parser.error('max-steps 为1–40，interval-seconds 为0–3600')
    if any(not math.isfinite(value) or value <= 0 for value in (args.per_run_budget_usd, args.total_budget_usd)) or args.per_run_budget_usd > MAX_RUN_USD or args.total_budget_usd > MAX_TOTAL_USD:
        parser.error('本轮单次上限最多$0.75，总防失控上限最多$15；允许降低，不自动放宽')
    matrix = load_tasks(args)
    motif, motif_error = motif_dependencies(matrix, ROOT)
    certificate, certificate_error = certificate_record(args.certificate)
    schema_job = prepare([Path(matrix['tasks'][0]['inputs'][0])], '只读取实际MCP契约，不调用模型或生成PPT。', 1)
    schema = asyncio.run(advertised_schema(schema_job))
    config = snapshot(matrix, args, motif, certificate, schema)
    experiment_type = 'real_api_execution' if args.call_model else 'preview'
    if args.resume:
        area = private_path(args.resume.resolve(strict=True))
        old = read(area / 'config.json'); summary = read(area / 'summary.json')
        if summary.get('config_sha256') != file_hash(area / 'config.json'):
            raise ValueError('原配置快照被修改，拒绝恢复')
        if identity(old) != identity(config) or summary.get('experiment_type') != experiment_type:
            raise ValueError('恢复依赖/题目/预算/模式已变化；保留旧结果并创建新实验')
        config = old
    else:
        area = ROOT / '.local/research-ppt/experiments' / (EXPERIMENT_ID + '-' + uuid4().hex[:8])
        write(area / 'matrix.json', matrix); write(area / 'config.json', config)
        summary = {'schema_version': 1, 'experiment_id': EXPERIMENT_ID, 'experiment_type': experiment_type,
                   'config_path': str(area / 'config.json'), 'config_sha256': file_hash(area / 'config.json'),
                   'motif_dependency_error': motif_error, 'layout_certificate_error': certificate_error,
                   'runs': [], 'quality': 'quality_not_reviewed', 'billing': 'proxy_estimate_not_invoice'}
        write(area / 'summary.json', summary)
    with exclusive_run(area):
        return execute_schedule(matrix, args, motif, certificate, config, area, summary)


if __name__ == '__main__':
    raise SystemExit(main())
