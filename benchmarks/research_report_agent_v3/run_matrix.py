"""Run a declared v3 matrix sequentially through the ordinary DSH entrypoint.

Preview is the default and needs no key. --call-model uses one inherited key
and the global persistent budget ledger, without placing secrets in arguments.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent


def validate_jobs(jobs):
    if not isinstance(jobs, list) or not jobs:
        raise ValueError('A nonempty explicit matrix is required')
    names = [job.get('name') for job in jobs]
    if any(not isinstance(name, str) or not re.fullmatch(r'[a-z0-9_]{1,80}', name) for name in names) or len(set(names)) != len(names):
        raise ValueError('Run names must be unique scoped identifiers')
    for index, job in enumerate(jobs):
        if job.get('mode') not in ('baseline', 'execute') or job.get('experiment_role') not in ('train', 'certification', 'evaluation', 'pilot'):
            raise ValueError('Every job needs an explicit mode and experiment_role')
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', job.get('case', '')):
            raise ValueError('Every job needs a scoped case identifier')
        if job.get('matrix_order') != index + 1 or type(job.get('repeat_id')) is not int or job['repeat_id'] < 1:
            raise ValueError('matrix_order must follow the declared sequence and repeat_id must be positive')
        if job['mode'] == 'execute' and not job.get('library'):
            raise ValueError('Every execute job needs an explicitly named compiled library')
        if job['experiment_role'] in ('train', 'certification') and job['mode'] != 'baseline':
            raise ValueError('Learning and certification must use ordinary baseline runs')


def make_command(args, job, matrix_sha):
    cmd = [sys.executable, str(HERE / 'runner.py'), '--mode', job['mode'],
           '--out', str(args.experiment / 'runs' / job['name']), '--budget-cny', '100',
           '--experiment-id', args.experiment_id, '--experiment-role', job['experiment_role'],
           '--repeat-id', str(job['repeat_id']), '--matrix-order', str(job['matrix_order']),
           '--matrix-sha256', matrix_sha, '--budget-ledger', str(args.budget_ledger),
           '--max-output', str(args.max_output), '--max-requests', str(args.max_requests),
           '--data-root', str(args.data_root), '--case', job['case']]
    if job.get('library'):
        library = Path(job['library'])
        if not library.is_absolute():
            library = args.experiment / library
        cmd += ['--library', str(library)]
    if args.call_model:
        cmd += ['--call-model']
    return cmd


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--matrix', type=Path, required=True)
    p.add_argument('--data-root', type=Path, required=True)
    p.add_argument('--experiment', type=Path, required=True)
    p.add_argument('--experiment-id', default='research-report-agent-v3-20261010')
    p.add_argument('--budget-ledger', type=Path, required=True)
    p.add_argument('--workers', type=int, default=1, choices=(1,), help='Main protocol requires sequential counterbalanced order')
    p.add_argument('--max-output', type=int, default=6144)
    p.add_argument('--max-requests', type=int, default=35)
    p.add_argument('--key-stdin', action='store_true')
    p.add_argument('--call-model', action='store_true')
    args = p.parse_args()
    args.experiment, args.data_root = args.experiment.resolve(), args.data_root.resolve()
    jobs = json.loads(args.matrix.read_text(encoding='utf-8'))
    validate_jobs(jobs)
    matrix_sha = hashlib.sha256(args.matrix.read_bytes()).hexdigest()
    commands = [make_command(args, job, matrix_sha) for job in jobs]
    if not args.call_model:
        print(json.dumps({'preview': True, 'api_calls': 0, 'workers': 1, 'jobs': jobs,
                          'matrix_sha256': matrix_sha, 'commands': commands}, ensure_ascii=False, indent=2))
        return 0
    # Reject every accidental overwrite before making the first paid request.
    result_path = args.experiment / ('matrix-result-' + args.matrix.stem + '.json')
    execution_path = args.experiment / ('matrix-execution-' + args.matrix.stem + '.json')
    if result_path.exists() or execution_path.exists():
        raise ValueError('Matrix already executed; retain its evidence and use a newly declared matrix')
    for job in jobs:
        if (args.experiment / 'runs' / job['name']).exists():
            raise ValueError('Refusing to overwrite a prior run: ' + job['name'])
    api_key = sys.stdin.readline().strip() if args.key_stdin else os.environ.get('DEEPSEEK_API_KEY', '')
    if not api_key:
        raise ValueError('A key is required for --call-model')
    log_dir = args.experiment / 'execution-logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(DEEPSEEK_API_KEY=api_key, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    execution = {'experiment_id': args.experiment_id, 'matrix_sha256': matrix_sha,
                 'jobs': jobs, 'workers': 1, 'declared_runs_denominator': len(jobs),
                 'started_utc_epoch': time.time(), 'status': 'running'}
    def save(path, value):
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        path.chmod(0o600)
    save(execution_path, execution)
    results = []
    for job, cmd in zip(jobs, commands):
        started = time.time()
        print(json.dumps({'event': 'run_started', **job, 'started_utc_epoch': started}, ensure_ascii=False), flush=True)
        log_path = log_dir / (job['name'] + '.log')
        with log_path.open('w', encoding='utf-8') as log:
            log_path.chmod(0o600)
            completed = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, env=env)
        ended = time.time()
        row = {**job, 'exit_code': completed.returncode, 'started_utc_epoch': started,
               'ended_utc_epoch': ended, 'elapsed_seconds': ended - started}
        metrics_path = args.experiment / 'runs' / job['name'] / 'metrics.json'
        if metrics_path.exists():
            metrics = json.loads(metrics_path.read_text(encoding='utf-8'))
            row.update({key: metrics.get(key) for key in ('status', 'delivered', 'report_quality_passed',
                        'upstream_requests', 'tool_calls', 'verified_motif_bypasses', 'peak_estimate_cny')})
        else:
            row['status'] = 'no_metrics'
        results.append(row)
        save(result_path, results)  # Partial matrix survives interruption; no dropped failures.
        print(json.dumps({'event': 'run_finished', **row}, ensure_ascii=False), flush=True)
    execution.update(status='finished', ended_utc_epoch=time.time(), attempted_runs=len(results))
    save(execution_path, execution)
    return 0 if all(row['exit_code'] == 0 and row.get('delivered') and row.get('report_quality_passed') for row in results) else 2


if __name__ == '__main__':
    raise SystemExit(main())
