"""V9 独立正常轨迹采集；只调用公共 Harness，不实现另一个 Agent 循环。"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time

from .cli import ROOT, SCENE, prepare, save, scenario_for
from .documents import file_hash
from .service import private_path
from .experiment import token_totals, lines
from .recovery import CheckpointPPTService

EXPERIMENT = 'research-ppt-v9-quality-20261012'
LIMITS = {'budget_usd': 0.75, 'max_steps': 40, 'max_output': 8000}


def runtime_file(path: str | Path | None) -> dict:
    """记录被选择的文件和实际落点，不读取文件内容或环境变量。"""
    if path is None:
        return {'path': None, 'exists': False, 'sha256': None}
    target = Path(path).absolute()
    sha256 = None
    if target.is_file():
        # Node与字体可能大于文档工具的30MiB输入限额；配置探针单独流式核验。
        if target.stat().st_size > 512 * 1024 * 1024:
            raise ValueError('运行依赖文件超出快照限额')
        hashed = hashlib.sha256()
        with target.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                hashed.update(block)
        sha256 = hashed.hexdigest()
    return {'path': str(target), 'resolved_path': str(target.resolve()),
            'exists': target.is_file(), 'sha256': sha256}


def node_runtime_snapshot() -> dict:
    """PATH wrapper 和 Node 实际 execPath 分开冻结；不保存 NODE_OPTIONS。"""
    selected = runtime_file(shutil.which('node'))
    value = {'selected_command': 'node', 'path_selected': selected,
             'process_executable': None, 'process_version': None, 'probe_status': 'not_found'}
    if not selected['exists']:
        return value
    script = 'process.stdout.write(JSON.stringify({execPath:process.execPath,version:process.version}))'
    try:
        result = subprocess.run(['node', '-e', script], text=True, encoding='utf-8',
                                capture_output=True, timeout=15, cwd=ROOT)
        if result.returncode != 0:
            return dict(value, probe_status='failed', probe_returncode=result.returncode)
        observed = json.loads(result.stdout)
        if not isinstance(observed, dict) or not isinstance(observed.get('execPath'), str) or not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', observed.get('version', '')):
            return dict(value, probe_status='invalid_output')
        actual = runtime_file(observed['execPath'])
        return dict(value, process_executable=actual, process_version=observed['version'],
                    selection_differs_from_process=os.path.normcase(selected['resolved_path']) != os.path.normcase(actual['resolved_path']),
                    probe_status='ok')
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError) as error:
        # stderr/环境值可能含私有信息；仅保存失败类型，详细诊断另存私有日志。
        return dict(value, probe_status='error', probe_error_type=type(error).__name__)


def node_compat_provenance() -> dict:
    """项目私有兼容方案的哈希和 recipe；不存在时不臆测已使用 wrapper。"""
    relative = '.local/research-ppt/v9-quality-20261012/harness-diagnosis/node-wrapper-evidence.json'
    evidence = ROOT / relative
    value = {'evidence_path': relative, 'evidence_sha256': file_hash(evidence) if evidence.is_file() else None,
             'status': 'absent', 'files': {}}
    if not evidence.is_file():
        return value
    try:
        if evidence.stat().st_size > 32768:
            return dict(value, status='invalid_metadata')
        row = json.loads(evidence.read_text(encoding='utf-8'))
        if not isinstance(row, dict) or row.get('scope') != 'project-private-node-wrapper':
            return dict(value, status='invalid_metadata')
        # 只收已知 recipe 字段，不复制整份 JSON 或任意环境变量。
        recipe = {key: row[key] for key in ('scope', 'node', 'reason', 'changes', 'not_changed') if key in row}
        for name, path in [('wrapper', '.local/node-compat/bin/node'), ('preload', '.local/node-compat/warm-report.cjs')]:
            observed = runtime_file(ROOT / path)
            expected = row.get(name + '_sha256')
            expected = expected if isinstance(expected, str) and re.fullmatch(r'[a-f0-9]{64}', expected) else None
            value['files'][name] = dict(observed, project_relative_path=path,
                                       declared_sha256=expected,
                                       matches_declared_sha256=expected is not None and observed['sha256'] == expected)
        return dict(value, status='recorded', recipe=recipe,
                    usage_verification='node_execPath_probe_and_path_selection;preload_activation_not_independently_proven')
    except (OSError, ValueError, TypeError) as error:
        return dict(value, status='error', error_type=type(error).__name__)


def font_configuration_snapshot() -> dict:
    """冻结字体配置和实际候选文件；宿主探针不冒充 PDF 绘制验收。"""
    configured = {name: os.environ[name] for name in ('FONTCONFIG_FILE', 'FONTCONFIG_PATH') if os.environ.get(name)}
    config = runtime_file(configured.get('FONTCONFIG_FILE'))
    probes = {}
    candidates = [shutil.which('fc-match')]
    if os.name == 'posix' and Path('/usr/bin/fc-match').is_file():
        candidates.append('/usr/bin/fc-match')  # LO 使用系统 fontconfig，Conda 探针不能替代。
    for command in dict.fromkeys(path for path in candidates if path):
        try:
            result = subprocess.run([command, '-f', '%{file}\n', 'Noto Sans CJK SC'],
                capture_output=True, text=True, encoding='utf-8', timeout=15)
            paths = result.stdout.strip().splitlines()
            probes[command] = {'returncode': result.returncode,
                'candidate_file': runtime_file(paths[0]) if result.returncode == 0 and len(paths) == 1 else None}
        except (OSError, subprocess.TimeoutExpired, ValueError) as error:
            probes[command] = {'error_type': type(error).__name__}
    return {'configured_env': configured, 'config_file': config, 'host_probes': probes,
        'scope': 'host_configuration_and_candidates;actual_visible_glyphs_checked_in_delivery',
        'stdio_forwarding': 'explicit_fontconfig_only_at_both_mcp_boundaries'}


def versions() -> dict:
    packages = {}
    for name in ['deepseek-harness-sdk', 'PyMuPDF', 'mcp', 'jsonschema']:
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = 'not_installed'
    npm_packages = {}
    for name in ['@deepseek-ai/dsh', '@deepseek-ai/dsh-llm']:
        path = ROOT / 'node_modules' / name / 'package.json'
        npm_packages[name] = json.loads(path.read_text(encoding='utf-8'))['version'] if path.is_file() else 'not_installed'
    return {'os': platform.platform(), 'python': platform.python_version(),
            'node': subprocess.check_output(['node', '--version'], text=True).strip(),
            'node_execution': node_runtime_snapshot(), 'node_compat_provenance': node_compat_provenance(),
            'render_font_configuration': font_configuration_snapshot(),
            'libreoffice': subprocess.check_output(['soffice', '--headless', '--version'], text=True).strip(),
            'python_packages': packages, 'npm_packages': npm_packages}


def snapshot(directory: Path, job: Path, scenario: Path, phase: str, *,
             experiment_id: str = EXPERIMENT, group: str = 'B0-normal-training') -> dict:
    spec = json.loads(scenario.read_text(encoding='utf-8'))
    prompt = Path(spec['prompt'])
    public_files = sorted(set([
        ROOT / 'package-lock.json', SCENE / 'package-lock.json', SCENE / 'delivery-scenario.json',
        SCENE / 'prompt.md', SCENE / 'skills/research-design/SKILL.md',
        *SCENE.glob('*.py'), *SCENE.glob('*.json'), *SCENE.glob('ts/*.ts'),
        *SCENE.glob('dist/*.js'), ROOT / 'scripts/run-scenario.py',
        ROOT / 'src/adapters/harness_runtime.py', ROOT / 'src/adapters/dsh_online_motif.mjs',
    ]))
    patch = subprocess.check_output(['git', 'diff', '--binary', 'HEAD'], cwd=ROOT)
    (directory / 'working-diff.patch').write_bytes(patch)
    (directory / 'working-diff.patch').chmod(0o600)
    data = json.loads(job.read_text(encoding='utf-8'))
    if any(file_hash(private_path(Path(row['path']))) != row['version_sha256'] for row in data['inputs']):
        raise ValueError('来源已变化，停止使用旧job')
    value = {'schema_version': 1, 'experiment_id': experiment_id, 'phase': phase,
             'code_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
             'working_diff_sha256': hashlib.sha256(patch).hexdigest(),
             'public_files_sha256': {str(p.relative_to(ROOT)).replace('\\', '/'): file_hash(p) for p in public_files},
             'job_sha256': file_hash(job), 'scenario_sha256': file_hash(scenario),
             'prompt_sha256': file_hash(prompt), 'tool_order': spec['allowed_tools'],
             'runtime': 'reliable', 'group': group, 'document_cache': data.get('document_cache', False),
             'model': 'deepseek-official/deepseek-flash', 'reasoning_effort': 'off',
             'compression': 'off', 'limits': LIMITS, 'environment': versions(),
             'source_sha256': [r['version_sha256'] for r in json.loads(job.read_text(encoding='utf-8'))['inputs']],
             'checkpoint_sha256_before': file_hash(job.parent / 'service-checkpoint.json') if (job.parent / 'service-checkpoint.json').is_file() else None,
             'configuration_missing': ['provider_facing_tool_payload_hash', 'provider_internal_retry_policy',
                'invoice', 'human_blind_review', 'human_revision_minutes', 'development_and_maintenance_cost'],
             'quality_review': 'not_reviewed', 'billing_actual': 'unknown',
             'task_independence': 'distinct_paper_and_decision_by_experiment_design_not_human_reviewed'}
    save(directory / 'config.json', value)
    return value


def collect_accounting(run: Path) -> dict:
    """完整阶段账本；失败和未知字段不按0算，预算上限不当实付。"""
    metrics = json.loads((run / 'metrics.json').read_text(encoding='utf-8')) if (run / 'metrics.json').is_file() else {}
    ledger = lines(run / 'cost-ledger.jsonl')
    requests = [row for row in ledger if 'request_id' in row]
    count = metrics.get('upstream_requests')
    complete = type(count) is int and count >= 0 and count == len(requests)
    values = [row.get('observed_peak_usd') for row in requests]
    observed_complete = bool(values) and all(isinstance(value, (int, float)) and not isinstance(value, bool)
        and math.isfinite(value) and value >= 0 for value in values)
    hashes = {name: file_hash(run / name) for name in ('manifest.json', 'preview.json', 'metrics.json',
        'agent-events.jsonl', 'cost-ledger.jsonl', 'answer.md') if (run / name).is_file()}
    return {'run_dir': str(run), 'metrics': metrics, 'raw_file_sha256': hashes,
        'paid_model_requests': count if complete else None, 'observed_request_subtotal': len(requests),
        'request_accounting_complete': complete, 'proxy_budget_accounted_usd': metrics.get('budget_accounted_usd'),
        'proxy_observed_estimate_usd': sum(values) if observed_complete else (0.0 if complete and count == 0 else None),
        'upstream_failures': sum(row.get('response_status') != 200 for row in requests),
        'actual_invoice_usd': None, **token_totals(ledger, metrics)}


def aggregate_attempts(area: Path, *, experiment_id: str = EXPERIMENT) -> dict:
    records = [json.loads(path.read_text(encoding='utf-8')) for path in sorted(area.glob('*/result.json'))]
    paid = [row for row in records if row.get('model_call_enabled') is True]
    accounting = [item for row in paid for item in row.get('accounting', [])]
    known = all(row.get('accounting_complete') is True for row in paid)
    def total(key):
        values = [row.get(key) for row in accounting]
        return sum(values) if known and all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values) else None
    value = {'schema_version': 1, 'experiment_id': experiment_id,
        'scope': 'seed_and_all_revision_attempts_including_failures; estimates_not_invoice',
        'phase_attempts': [{'phase': row['phase'], 'status': row.get('status', 'unknown'), 'returncode': row['returncode'],
            'model_call_enabled': row['model_call_enabled'], 'elapsed_seconds': row['elapsed_seconds']} for row in records],
        'paid_model_requests': total('paid_model_requests'), 'proxy_observed_estimate_usd': total('proxy_observed_estimate_usd'),
        'observed_request_subtotal': sum(row.get('observed_request_subtotal', 0) for row in accounting),
        'proxy_budget_accounted_usd': total('proxy_budget_accounted_usd'), 'actual_invoice_usd': None,
        'all_attempts_elapsed_seconds': sum(row['elapsed_seconds'] for row in records),
        'accounting_complete': known, 'quality': 'not_reviewed', 'human_revision_minutes': None,
        'tokens': {key: sum(item['tokens'][key] for item in accounting) if known and all(item['tokens'].get(key) is not None for item in accounting) else None
            for key in ('prompt_cache_miss_tokens', 'prompt_cache_hit_tokens', 'completion_tokens', 'total_tokens')}}
    save(area / 'aggregate.json', value)
    return value


def export_actual_schema(job: Path, directory: Path) -> Path:
    out = directory / 'actual-mcp-schema.json'
    env = dict(os.environ, SSS_PPT_JOB=str(job), SSS_PPT_DELIVERY_PYTHON=sys.executable)
    process = subprocess.run(['node', str(SCENE / 'dist/mcp-adapter.js'), '--job', str(job),
                              '--export-schema', str(out)], cwd=ROOT, env=env,
                             text=True, encoding='utf-8', capture_output=True, timeout=180)
    (directory / 'schema-export.log').write_text(process.stdout + process.stderr, encoding='utf-8')
    if process.returncode or not out.is_file():
        raise RuntimeError('实际 MCP schema 获取失败；未调用模型')
    return out


def invoke(directory: Path, job: Path, scenario: Path, phase: str, decision: str, call_model: bool,
           preparation_elapsed_seconds: float = 0.0, *, experiment_id: str = EXPERIMENT,
           group: str = 'B0-normal-training') -> dict:
    directory, job, scenario = private_path(directory), private_path(job), private_path(scenario)
    started = time.monotonic()
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    config = snapshot(directory, job, scenario, phase, experiment_id=experiment_id, group=group)
    schema = export_actual_schema(job, directory)
    config.update(actual_mcp_schema_sha256=file_hash(schema))
    save(directory / 'config.json', config)
    args = [sys.executable, str(ROOT / 'scripts/run-scenario.py'), '--scenario', str(scenario),
            '--budget-usd', str(LIMITS['budget_usd']), '--max-steps', str(LIMITS['max_steps']),
            '--max-output', str(LIMITS['max_output'])]
    if call_model:
        args.append('--call-model')
    env = dict(os.environ, SSS_PPT_JOB=str(job), PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    run_root = ROOT / '.local/runs'
    before = set(run_root.iterdir()) if run_root.is_dir() else set()
    # 每次尝试独立目录；失败不覆盖，不自动重试。
    with (directory / 'harness.log').open('w', encoding='utf-8') as log:
        result = subprocess.run(args, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    (directory / 'harness.log').chmod(0o600)
    (directory / 'schema-export.log').chmod(0o600)
    lines = (directory / 'harness.log').read_text(encoding='utf-8').splitlines()
    runs = []
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and isinstance(row.get('output_dir'), str):
            runs.append(row)
    # 崩溃可能没有最终stdout。只接受本次唯一schema/prompt对应的新run，不捡其它任务。
    located = []
    for run in sorted((set(run_root.iterdir()) if run_root.is_dir() else set()) - before):
        if not (run / 'manifest.json').is_file():
            continue
        manifest = json.loads((run / 'manifest.json').read_text(encoding='utf-8'))
        if manifest.get('config_sha256') == config['scenario_sha256'] and manifest.get('prompt_sha256') == config['prompt_sha256']:
            located.append(private_path(run))
    paths = {private_path(Path(row['output_dir'])) for row in runs}
    paths.update(located)
    if any(not (path / 'manifest.json').is_file() or json.loads((path / 'manifest.json').read_text(encoding='utf-8')).get('config_sha256') != config['scenario_sha256'] for path in paths):
        raise ValueError('stdout运行目录不属于本次冻结scenario')
    accounting = [collect_accounting(path) for path in sorted(paths)]
    complete = not call_model or (len(paths) == 1 and all(row['request_accounting_complete'] for row in accounting))
    record = {'experiment_id': experiment_id, 'phase': phase, 'decision_id': decision,
              'returncode': result.returncode, 'elapsed_seconds': round(time.monotonic() - started + preparation_elapsed_seconds, 3),
              'phase_preparation_elapsed_seconds': round(preparation_elapsed_seconds, 3),
              'job': str(job), 'config_sha256': file_hash(directory / 'config.json'),
              'model_call_enabled': call_model, 'quality': 'not_reviewed', 'runs': runs,
              'status': 'preview' if not call_model and result.returncode == 0 else ('runtime_completed_quality_not_reviewed' if result.returncode == 0 else 'failed_attempt'),
              'accounting': accounting, 'accounting_complete': complete,
              'accounting_missing': call_model and not complete, 'budget_cap_usd': LIMITS['budget_usd'],
              'job_sha256_after': file_hash(job), 'job_unchanged': file_hash(job) == config['job_sha256'],
              'checkpoint_sha256_after': file_hash(job.parent / 'service-checkpoint.json') if (job.parent / 'service-checkpoint.json').is_file() else None,
              'harness_log_sha256': file_hash(directory / 'harness.log'),
              'schema_export_log_sha256': file_hash(directory / 'schema-export.log')}
    save(directory / 'result.json', record)
    if len(paths) == 1 and call_model and result.returncode == 0:
        run = next(iter(paths))
        if (run / 'agent-events.jsonl').is_file() and accounting[0]['metrics'].get('status') == 'done':
            spec = importlib.util.spec_from_file_location('freeze_identity_v9', ROOT / 'scripts/freeze-dsh-task-identity.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.freeze(run, decision, 'agent-events.jsonl')
    aggregate_attempts(directory.parent, experiment_id=experiment_id)
    return record


def run_seed(source: Path, case: str, call_model: bool) -> dict:
    preparation_started = time.monotonic()
    area = ROOT / '.local/research-ppt/v9-quality-20261012/normal-traces' / case
    if area.exists():
        raise ValueError('case 已存在；不覆盖历史尝试，请使用新 case ID')
    area.mkdir(parents=True, mode=0o700)
    title = source.stem
    instruction = (f'为研究生组会制作关于 {title} 的4页中文科研汇报。'
                   '依次覆盖研究问题、机制、原文实验依据、局限。至少保留一幅完整原论文图件（如无法可靠定位应如实说明），'
                   '数值比较明确指标、方法、对照和实验条件；区分百分比与百分点，'
                   '公式使用可读ASCII记法并解释符号，保留必要下标与矩阵切片。'
                   '不编造数值、图件或条件。页数含全部页面。当前仅制作初稿，暂不局部修订。')
    job = prepare([source], instruction, 4, allow_output=True, document_cache=False)
    save(area / 'task.json', {'experiment_id': EXPERIMENT, 'case': case, 'job': str(job),
                              'source_sha256': file_hash(source), 'slides': 4,
                              'purpose': 'normal_training_no_forced_tool_path'})
    scenario = scenario_for(job, False, 'reliable')
    return invoke(area / 'seed-01', job, scenario, 'seed', case + '-seed', call_model,
                  preparation_elapsed_seconds=time.monotonic() - preparation_started)


def run_revision(case: str, attempt: str, call_model: bool) -> dict:
    preparation_started = time.monotonic()
    area = ROOT / '.local/research-ppt/v9-quality-20261012/normal-traces' / case
    task = json.loads((area / 'task.json').read_text(encoding='utf-8'))
    job = private_path(Path(task['job']))
    restored = CheckpointPPTService(job)
    initial = [row for row in restored.list_restorable_decks()['decks'] if row['validated'] and row['has_request_plan']]
    if not initial:
        raise ValueError('没有当前版本已通过实际渲染验收的初稿；不得把失败/preview称为已验收初稿')
    # 原job和checkpoint不修改；只给新会话冻结真实用户反馈。
    scenario = scenario_for(job, False, 'reliable')
    spec = json.loads(scenario.read_text(encoding='utf-8'))
    directory = area / attempt
    if directory.exists():
        raise ValueError('attempt 已存在；失败也保留，不能覆盖')
    prompt = Path(spec['prompt']).read_text(encoding='utf-8')
    prompt += ('\n当前是同一任务的后续反馈，替代原任务中的“当前仅制作初稿”：已有当前版本通过机械渲染验收的初稿；科学与视觉质量未人工审阅，'
               '请恢复并核对实际第2页，只将第2页标题改为“核心机制与适用条件”。'
               '原第2页正文、图件、引用和notes保持；其他所有页面保持，4页不变。'
               '不要重新生成整份稿件。完成后重新实际渲染验收并给出修订副本。'
               '按实际需要选择工具；无固定工具顺序要求。')
    frozen_prompt = area / (attempt + '-prompt.md')
    frozen_prompt.write_text(prompt, encoding='utf-8')
    frozen_prompt.chmod(0o600)
    spec['prompt'] = str(frozen_prompt)
    frozen_scenario = area / (attempt + '-scenario.json')
    save(frozen_scenario, spec)
    return invoke(directory, job, frozen_scenario, 'revision', case + '-revision', call_model,
                  preparation_elapsed_seconds=time.monotonic() - preparation_started)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['seed', 'revision'])
    parser.add_argument('--case', required=True)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--attempt', default='revision-01')
    parser.add_argument('--call-model', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z][a-z0-9-]{2,80}', args.case) or not re.fullmatch(r'[a-z][a-z0-9-]{2,80}', args.attempt):
        parser.error('case/attempt需要固定短标识')
    if args.phase == 'seed' and args.source is None:
        parser.error('seed需要--source')
    record = run_seed(private_path(args.source), args.case, args.call_model) if args.phase == 'seed' else run_revision(args.case, args.attempt, args.call_model)
    print(json.dumps(record, ensure_ascii=False))
    return record['returncode']


if __name__ == '__main__':
    raise SystemExit(main())
