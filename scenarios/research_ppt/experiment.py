"""私有任务矩阵的真实 DSH 对照；默认仅预览，付费必须显式给出两级预算。"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scenarios.research_ppt.cli import prepare, save
from scenarios.research_ppt.documents import file_hash
from scenarios.research_ppt.service import SCENE, private_path
from src.adapters.dsh_trajectory import _observation_digest
from src.adapters.dsh_event_projection import is_original_tool_result

GROUPS = {'steps_baseline': ('baseline', 'steps'), 'composed': ('baseline', 'composed'), 'motif': ('execute', 'steps')}
ORDERS = ((0,1,2), (1,2,0), (2,0,1), (0,2,1), (2,1,0))
ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')


def read(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def lines(path: Path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()] if path.is_file() else []


def version(command: list[str]):
    try:
        return subprocess.check_output(command, cwd=ROOT, text=True, encoding='utf-8', timeout=15).strip()
    except (OSError, subprocess.SubprocessError):
        return 'unknown'


def token_totals(ledger: list[dict], metrics: dict):
    """未知计数保持 None；metrics 回退仅是可见消息的观测量。"""
    fields = {'prompt_cache_miss_tokens':'inputTokens', 'prompt_cache_hit_tokens':'cacheReadTokens',
              'completion_tokens':'outputTokens', 'total_tokens':'totalTokens'}
    requests = [r for r in ledger if 'request_id' in r]
    totals, sources, partial = {}, {}, {}
    for field, metric in fields.items():
        values = [r.get('response_usage', {}).get(field) for r in requests]
        known = [v for v in values if type(v) is int and v >= 0]
        if values and len(known) == len(values):
            totals[field], sources[field] = sum(known), 'upstream_ledger'
        else:
            fallback = metrics.get(metric)
            seen = metrics.get('model_requests')
            evidence = (type(seen) is int and seen > 0) or metrics.get('upstream_requests') == 0
            totals[field] = fallback if evidence and type(fallback) is int and fallback >= 0 else None
            sources[field] = 'metrics_observed_only' if totals[field] is not None else 'unknown'
            partial[field] = sum(known) if known else None
    return {'tokens': totals, 'token_sources': sources, 'ledger_observed_subtotals': partial,
            'token_accounting_complete': all(s == 'upstream_ledger' for s in sources.values()) or metrics.get('upstream_requests') == 0}


def verified_deliveries(row: dict, job: Path):
    feedback = {r.get('validation_id'): r.get('deck_id') for r in lines(job.parent / 'feedback.jsonl')
                if r.get('kind') == 'delivery_validation' and r.get('passed') is True}
    accepted = []
    for result in row.get('delivery', {}).get('observed_successful_tool_results', []):
        try:
            target = Path(result['path']).resolve(strict=True)
            digest = result['file_sha256']
            reports = row.get('validation', {}).get('reports', [])
            if (target.is_relative_to(job.parent / 'outputs') and feedback.get(result.get('validation_id')) == result.get('deck_id')
                and result.get('deck_id') is not None and file_hash(target) == digest and any(
                    r.get('passed') is True and r.get('pptx_sha256') == digest and Path(r['pptx_path']).resolve() == target for r in reports)):
                accepted.append(result)
        except (KeyError, OSError, ValueError, TypeError):
            pass
    return accepted


def load_matrix(path: Path):
    data = read(private_path(path))
    if data.get('schema_version') != 1 or not ID.fullmatch(data.get('experiment_id', '')):
        raise ValueError('matrix 需要 schema_version=1 及安全的 experiment_id')
    groups = data.get('groups', list(GROUPS))
    if not isinstance(groups, list) or not groups or len(set(groups)) != len(groups) or any(g not in GROUPS for g in groups):
        raise ValueError('groups 只能是不重复的 steps_baseline/composed/motif')
    tasks = data.get('tasks')
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= 30:
        raise ValueError('需要 1–30 个独立 tasks')
    seen = set()
    for task_index, task in enumerate(tasks):
        if not isinstance(task, dict) or not ID.fullmatch(task.get('task_id', '')) or task['task_id'] in seen:
            raise ValueError('每个 task_id 必须合法且独立')
        seen.add(task['task_id'])
        order = task.get('group_order', [list(GROUPS)[i] for i in ORDERS[task_index % len(ORDERS)] if list(GROUPS)[i] in groups])
        if not isinstance(order, list) or len(order) != len(groups) or set(order) != set(groups):
            raise ValueError('task.group_order 必须是全部 groups 的一个排列')
        task['group_order'] = order
        if not isinstance(task.get('inputs'), list) or not 1 <= len(task['inputs']) <= 8:
            raise ValueError('每个任务需要 1–8 个 PDF/PPTX 输入')
        task['inputs'] = [str((Path(p) if Path(p).is_absolute() else path.parent / p).resolve(strict=True)) for p in task['inputs']]
        if any(Path(p).suffix.lower() not in {'.pdf', '.pptx'} for p in task['inputs']):
            raise ValueError('输入仅接受 PDF/PPTX')
        task['input_versions'] = [file_hash(Path(p)) for p in task['inputs']]
        if type(task.get('slides')) is not int or not 1 <= task['slides'] <= 30:
            raise ValueError('任务 slides 必须是 1–30 的整数')
        if not isinstance(task.get('instruction'), str) or not 1 <= len(task['instruction'].strip()) <= 10000:
            raise ValueError('任务需要 instruction')
        if task.get('template', 'academic') not in {'academic', 'lab'} or task.get('operation', 'generate') not in {'generate', 'restyle'}:
            raise ValueError('任务的 template/operation 无效')
    data['groups'] = groups
    return data


def motif_dependencies(matrix: dict, base: Path):
    try:
        manifest = private_path((base / matrix['manifest']).resolve(strict=True))
        guard = private_path((base / matrix.get('guard', str(ROOT / '.local/research-ppt/rsi/active-guard.json'))).resolve(strict=True))
        if guard.name != 'active-guard.json' or not read(guard).get('program_digest'):
            raise ValueError('缺少已认证 active-guard.json')
        online = read(manifest)
        if not online.get('manifest_digest') or not online.get('artifacts') or any(
            not a.get('certified_digest') or any(not t.startswith('mcp__ppt__') for t in a.get('tools', [])) for a in online['artifacts']):
            raise ValueError('manifest 不是本 PPT 场景的已认证库')
        compiled = read(manifest.parent / 'compile.json')
        if len(compiled.get('train', [])) < 2 or len(compiled.get('heldout', [])) < 1:
            raise ValueError('需要两个真实训练任务与一个独立留出任务的 compile.json')
        evidence = []
        for trace in compiled['train'] + compiled['heldout']:
            events = private_path(Path(trace['events']).resolve(strict=True))
            metrics = read(events.parent / 'metrics.json')
            ledger = lines(events.parent / 'cost-ledger.jsonl')
            if metrics.get('status') != 'done' or not metrics.get('upstream_requests') or not any(r.get('response_status') == 200 for r in ledger):
                raise ValueError('训练/认证轨迹缺少成功真实 API 运行账本；不使用模拟轨迹')
            evidence.append({'events_sha256': file_hash(events), 'run_dir': str(events.parent)})
        return {'manifest': str(manifest), 'guard': str(guard), 'manifest_digest': online['manifest_digest'],
                'source_library_digest': online.get('source_library_digest'), 'manifest_sha256': file_hash(manifest),
                'guard_sha256': file_hash(guard), 'evidence': evidence}, None
    except (KeyError, OSError, ValueError, TypeError) as exc:
        return None, f'Motif 依赖缺失或失效：{exc}'


def snapshot(matrix: dict, args, motif):
    files = [*SCENE.glob('*.py'), *SCENE.glob('*.md'), *SCENE.glob('*.json'), *SCENE.glob('*.txt'),
             *SCENE.glob('ts/*.ts'), ROOT / 'scripts/run-scenario.py', ROOT / 'src/adapters/deepseek_cost_gate.py',
             ROOT / 'src/adapters/harness_runtime.py', ROOT / 'src/adapters/dsh_online_motif.mjs', ROOT / 'src/motif_core/online_skill_runtime.mjs']
    versions = {}
    for package in ('deepseek-harness-sdk', 'mcp', 'pypdf', 'PyMuPDF', 'python-pptx'):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = 'missing'
    return {'schema_version': 1, 'recorded_utc': datetime.now(timezone.utc).isoformat(), 'matrix_sha256': file_hash(args.matrix),
            'commit': version(['git', 'rev-parse', 'HEAD']), 'tracked_worktree_status': version(['git', 'status', '--porcelain', '--untracked-files=no']),
            'code_hashes': {str(p.relative_to(ROOT)): file_hash(p) for p in files if p.is_file()},
            'os': platform.platform(), 'python': platform.python_version(), 'node': version(['node', '--version']), 'packages': versions,
            'tool_order': read(SCENE / 'scenario.json')['allowed_tools'], 'model': 'deepseek-flash', 'provider': 'deepseek-official',
            'reasoning_effort': 'off', 'compression': 'disabled_by_public_entry_default', 'retry_policy': 'no_experiment_retries',
            'embedding_model': 'structural-only', 'semantic_matching': 'disabled',
            'matching_thresholds': {'min_similarity': os.environ.get('SSS_MOTIF_MIN_SIMILARITY', '0.8'),
                                    'min_margin': os.environ.get('SSS_MOTIF_MIN_MARGIN', '0.1'),
                                    'scope': 'semantic fallback disabled; closed structural paths use execution evidence'},
            'total_budget_cap_usd': args.total_budget_usd, 'per_run_budget_cap_usd': args.per_run_budget_usd,
            'max_steps': args.max_steps, 'max_output_tokens': 6000, 'interval_seconds': args.interval_seconds, 'motif': motif,
            'group_order_by_task': {t['task_id']: list(reversed(t['group_order'])) if args.reverse else t['group_order'] for t in matrix['tasks']},
            'inputs': {t['task_id']: [{'path': p, 'sha256': file_hash(Path(p))} for p in t['inputs']] for t in matrix['tasks']},
            'missing_configuration': ['actual_model_facing_tool_schema_hash', 'provider_internal_retry_policy', 'human_review', 'provider_invoice']}


def run_one(task: dict, group: str, args, motif: dict | None, area: Path, index: int):
    if group == 'motif' and motif is None:
        return {'task_id': task['task_id'], 'group': group, 'status': 'missing_dependency', 'quality': 'quality_not_reviewed'}
    if group == 'motif' and (file_hash(Path(motif['manifest'])) != motif['manifest_sha256']
                             or file_hash(Path(motif['guard'])) != motif['guard_sha256']):
        return {'task_id': task['task_id'], 'group': group, 'status': 'motif_version_changed', 'quality': 'quality_not_reviewed'}
    if [file_hash(Path(p)) for p in task['inputs']] != task['input_versions']:
        return {'task_id': task['task_id'], 'group': group, 'status': 'source_version_changed', 'quality': 'quality_not_reviewed'}
    job = prepare([Path(p) for p in task['inputs']], task['instruction'], task['slides'], args.call_model,
                  template=task.get('template', 'academic'), operation=task.get('operation', 'generate'))
    if group == 'motif':
        data = read(job); data['rsi_dir'] = str(Path(motif['guard']).parent); save(job, data)
    mode, execution = GROUPS[group]
    command = [sys.executable, '-u', '-m', 'scenarios.research_ppt.cli', 'run', '--job', str(job), '--mode', mode,
               '--execution', execution, '--budget-usd', str(args.per_run_budget_usd or 0.25), '--max-steps', str(args.max_steps)]
    if group == 'motif':
        command += ['--manifest', motif['manifest']]
    if args.call_model:
        command.append('--call-model')
    log = ROOT / 'test-logs' / f'{area.name}-{index:02d}-{task["task_id"]}-{group}.log'
    log.parent.mkdir(parents=True, exist_ok=True)
    started, output_dir = time.monotonic(), None
    before = set((ROOT / '.local/research-ppt/validation').glob('*/report.json'))
    with log.open('x', encoding='utf-8') as stream:
        process = subprocess.Popen(command, cwd=ROOT, env=dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8'),
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', bufsize=1)
        for line in process.stdout:
            stream.write(line); stream.flush(); print(line, end='', flush=True)
            try:
                value = json.loads(line)
                if isinstance(value, dict) and value.get('output_dir'):
                    output_dir = private_path(Path(value['output_dir']))
            except (ValueError, TypeError):
                pass
        returncode = process.wait()
    row = {'task_id': task['task_id'], 'group': group, 'status': 'preview' if not args.call_model and not returncode else 'error',
           'returncode': returncode, 'job_path': str(job), 'log_path': str(log), 'command': command,
           'elapsed_seconds': round(time.monotonic() - started, 3), 'quality': 'quality_not_reviewed'}
    if output_dir:
        metrics = read(output_dir / 'metrics.json'); ledger = lines(output_dir / 'cost-ledger.jsonl')
        row.update(status=metrics['status'], run_dir=str(output_dir), metrics=metrics, model_requests=metrics.get('model_requests'),
                   paid_model_requests=metrics.get('upstream_requests'), api_cost_usd=metrics.get('budget_accounted_usd'),
                   billing='proxy_estimate_not_invoice', ledger=ledger, upstream_429=any(r.get('response_status') == 429 for r in ledger))
        row.update(token_totals(ledger, metrics))
        names, deliveries = {}, []
        for event in lines(output_dir / 'agent-events.jsonl'):
            data = event.get('data', {})
            if event.get('type') == 'tool/call':
                names[data.get('callId')] = data.get('name')
            elif is_original_tool_result(event):
                name = names.get(data.get('message', {}).get('source', {}).get('callId'), '')
                if name in {'mcp__ppt__deliver_deck', 'mcp__ppt__build_delivery'}:
                    passed, _, observed = _observation_digest(event, name)
                    if passed and observed and observed.get('delivered', True):
                        deliveries.append(observed)
        row['delivery'] = {'observed_successful_tool_results': deliveries, 'confirmed_tool_results': [], 'produced_pptx': [
            {'path': str(p), 'sha256': file_hash(p)} for p in sorted((job.parent / 'outputs').glob('*/presentation.pptx'))]}
    elif args.call_model:
        row.update(api_cost_usd=None, accounted_upper_usd=args.per_run_budget_usd,
                   accounting_missing=True, upstream_429='RATE_LIMIT' in log.read_text(encoding='utf-8'))
    reports = set((ROOT / '.local/research-ppt/validation').glob('*/report.json')) - before
    row['validation'] = {'reports': [{'path': str(p), **read(p)} for p in sorted(reports)
                                    if Path(read(p)['pptx_path']).is_relative_to(job.parent / 'outputs')]}
    if output_dir:
        confirmed = verified_deliveries(row, job)
        row['delivery']['confirmed_tool_results'] = confirmed
        row['delivery_completed'] = bool(confirmed)
        if metrics['status'] == 'done' and not confirmed:
            row['status'] = 'not_delivered'
    prompt = job.parent / 'prompt.md'
    row['effective_prompt_sha256'] = file_hash(prompt) if prompt.is_file() else None
    invocations = list(job.parent.glob('invocation-*.json'))
    row['scenario_invocation'] = read(invocations[0]) if len(invocations) == 1 else None
    if output_dir:
        row['effective_public_preview'] = read(output_dir / 'preview.json')
    save(area / f'run-{index:02d}.json', row)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matrix', type=Path, required=True)
    parser.add_argument('--call-model', action='store_true')
    parser.add_argument('--total-budget-usd', type=float)
    parser.add_argument('--per-run-budget-usd', type=float)
    parser.add_argument('--max-steps', type=int, default=24)
    parser.add_argument('--interval-seconds', type=int, default=60)
    parser.add_argument('--reverse', action='store_true', help='反转每个任务的组顺序')
    args = parser.parse_args(); args.matrix = private_path(args.matrix.resolve(strict=True))
    if not 1 <= args.max_steps <= 40:
        parser.error('max-steps 应在 1–40')
    if not 0 <= args.interval_seconds <= 3600:
        parser.error('interval-seconds 应在 0–3600')
    if any(v is not None and (not math.isfinite(v) or v <= 0) for v in (args.total_budget_usd, args.per_run_budget_usd)) or (args.per_run_budget_usd or 0) > 10:
        parser.error('两级预算均须为有限正数；单次守护上限不超过 $10')
    matrix = load_matrix(args.matrix)
    planned = len(matrix['tasks']) * len(matrix['groups']) * (args.per_run_budget_usd or 0)
    if args.call_model and (args.total_budget_usd is None or args.per_run_budget_usd is None or planned > args.total_budget_usd + 1e-9):
        parser.error('付费执行需明确两级运行守护上限；全部运行上限之和不能超过总守护上限')
    motif, missing = motif_dependencies(matrix, args.matrix.parent) if 'motif' in matrix['groups'] else (None, None)
    area = ROOT / '.local/research-ppt/experiments' / f'{matrix["experiment_id"]}-{uuid4().hex[:8]}'
    save(area / 'matrix.json', matrix); save(area / 'config.json', snapshot(matrix, args, motif))
    summary = {'experiment_id': matrix['experiment_id'], 'experiment_type': 'real_api_execution' if args.call_model else 'preview',
               'config': {'snapshot_path': str(area / 'config.json'), 'planned_cap_sum_usd': planned}, 'runs': [],
               'quality': 'quality_not_reviewed', 'billing': 'proxy_estimate_not_invoice', 'motif_dependency_error': missing}
    print(json.dumps({'preview': summary, 'call_model': args.call_model}, ensure_ascii=False), flush=True)
    schedule = [(t,g) for t in matrix['tasks'] for g in (list(reversed(t['group_order'])) if args.reverse else t['group_order'])]
    failures429, executed = 0, False
    for index, (task, group) in enumerate(schedule, 1):
        if args.call_model and executed and not (group == 'motif' and motif is None):
            for remaining in range(args.interval_seconds, 0, -20):
                print(f'串行调用间隔：剩余 {remaining} 秒；下个任务 {task["task_id"]}/{group}', flush=True); time.sleep(min(20, remaining))
        row = run_one(task, group, args, motif, area, index); summary['runs'].append(row)
        executed = executed or (args.call_model and row['status'] != 'missing_dependency')
        summary['total_accounted_usd'] = sum(r.get('api_cost_usd') or r.get('accounted_upper_usd', 0) for r in summary['runs'])
        save(area / 'summary.json', summary)
        if row['status'] in {'source_version_changed', 'motif_version_changed'} or (args.call_model and summary['total_accounted_usd'] > args.total_budget_usd):
            summary['stopped_reason'] = row['status'] if row['status'] in {'source_version_changed', 'motif_version_changed'} else 'budget_accounting_exceeds_cap'
            save(area / 'summary.json', summary); break
        failures429 = failures429 + 1 if row.get('upstream_429') else (failures429 if row['status'] == 'missing_dependency' else 0)
        if failures429 >= 3:
            summary['stopped_reason'] = 'three_consecutive_upstream_429'; save(area / 'summary.json', summary); break
    print(json.dumps({'summary_path': str(area / 'summary.json'), **summary}, ensure_ascii=False), flush=True)
    return 0 if all(r['status'] in {'done','preview'} and not r.get('returncode') for r in summary['runs']) else 2


if __name__ == '__main__':
    raise SystemExit(main())
