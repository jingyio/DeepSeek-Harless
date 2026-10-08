#!/usr/bin/env python3
"""Run the frozen four-arm local-app comparison with a per-attempt API cap."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]


def source_unchanged(app: str, scope: dict) -> bool:
    path = Path(scope['path'])
    if app == 'finder':
        actual = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in path.iterdir() if p.is_file()}
        return actual == scope['files']
    return hashlib.sha256(path.read_bytes()).hexdigest() == scope['sha256']


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, default=ROOT / '.local/benchmarks/local-app-compaction-v1/PLAN.json')
    parser.add_argument('--call-model', action='store_true')
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    if (plan['model'] != 'deepseek-flash' or plan['reasoning_effort'] != 'off'
            or plan['run_count'] != len(plan['trials'])
            or not 0 < plan['per_run_cap_usd'] <= .02
            or plan['total_cap_usd'] != len(plan['trials']) * plan['per_run_cap_usd']):
        raise ValueError('invalid frozen budget or model plan')
    base = args.plan.parent
    for index, trial in enumerate(plan['trials'], 1):
        app, case, arm, compression = (trial[key] for key in ('app', 'case', 'arm', 'compression'))
        if app not in {'numbers', 'keynote', 'finder'} or arm not in {'baseline', 'motif'} or compression not in {'raw', 'compact'}:
            raise ValueError('invalid trial arm')
        run = Path(trial['output'])
        preview = json.loads((run / 'PREVIEW.json').read_text())
        scope = json.loads((ROOT / f'.local/benchmarks/{app}-live-v1/{case}/scope.json').read_text())
        if (not source_unchanged(app, scope) or preview['scope'] != scope
                or preview['prompt_sha256'] != trial['prompt_sha256']
                or preview['tool_compaction'] != ('json_compact_v1' if compression == 'compact' else 'off')
                or scope['sha256'] != trial['source_sha256']):
            raise ValueError('frozen source or preview changed: ' + str(run))
        metrics_path = run / 'metrics.json'
        if metrics_path.exists():
            metrics = json.loads(metrics_path.read_text())
            if metrics.get('status') == 'completed':
                print(f'{index}/{len(plan["trials"])} already completed: {app}/{case}/{arm}/{compression}', flush=True)
                continue
            raise ValueError('failed attempt requires a new attempt name: ' + str(run))
        if (run / 'paid-attempt.marker').exists():
            raise ValueError('incomplete paid attempt requires investigation: ' + str(run))
        print(f'{index}/{len(plan["trials"])} running: {app}/{case}/{arm}/{compression}', flush=True)
        if not args.call_model:
            continue
        label = f'{app}-{case}-{arm}-{compression}'
        ledger = base / f'{label}.budget.jsonl'
        if ledger.exists():
            raise ValueError('budget ledger already exists without completed run: ' + str(ledger))
        command = [str(ROOT / '.venv312/bin/python'), str(ROOT / 'scripts/run-distil-dsh.py'),
                   '--mode', 'plain']
        if compression == 'compact':
            command.append('--tool-json-compact')
        command += ['--budget-usd', str(plan['per_run_cap_usd']), '--budget-max-output', '1500',
                    '--ledger', str(ledger), '--', str(ROOT / '.venv312/bin/python'),
                    str(ROOT / f'scripts/run-{app}-live-trial.py'), '--case', case,
                    '--arm', arm, '--attempt', trial['attempt'], '--call-model']
        with (base / f'{label}.log').open('w') as log:
            result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                    timeout=420, env=os.environ.copy())
        with (base / 'RUN-ORDER.jsonl').open('a') as log:
            log.write(json.dumps({'time_utc': datetime.now(timezone.utc).isoformat(),
                                  'trial': label, 'exit_code': result.returncode}, ensure_ascii=False) + '\n')
        if result.returncode:
            raise RuntimeError(f'{label} failed; see {base / (label + ".log")}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
