"""V11 科研设计真实新任务：复用公共Harness、预算与有效配置账本。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import time

from .cli import ROOT, prepare, save, scenario_for
from .documents import file_hash
from .experiment_v9 import invoke
from .service import private_path

EXPERIMENT = 'research-ppt-v11-scientific-design-20261012'


def run_seed(inputs: list[Path], case: str, instruction: str, slides: int, call_model: bool) -> dict:
    started = time.monotonic()
    area = ROOT / '.local/research-ppt' / EXPERIMENT / 'normal-traces' / case
    area.mkdir(parents=True, exist_ok=False)
    inputs = [private_path(path.resolve(strict=True)) for path in inputs]
    job = prepare(inputs, instruction, slides, allow_output=True, document_cache=False)
    save(area / 'task.json', {'experiment_id': EXPERIMENT, 'job': str(job), 'slides': slides,
                             'inputs_sha256': [file_hash(path) for path in inputs],
                             'purpose': 'new_task_design_delivery_not_RSI_or_cost_comparison'})
    return invoke(area / 'seed-01', job, scenario_for(job, False, 'reliable'), 'seed', case,
                  call_model, time.monotonic() - started, experiment_id=EXPERIMENT,
                  group='B1-human-designed-archetypes-new-task')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, nargs='+', type=Path)
    parser.add_argument('--instruction', required=True)
    parser.add_argument('--slides', required=True, type=int)
    parser.add_argument('--case', required=True)
    parser.add_argument('--call-model', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z][a-z0-9-]{2,80}', args.case):
        parser.error('case使用新的固定短标识，不覆盖历史尝试')
    value = run_seed(args.input, args.case, args.instruction, args.slides, args.call_model)
    print(json.dumps(value, ensure_ascii=False))
    return value['returncode']


if __name__ == '__main__':
    raise SystemExit(main())
