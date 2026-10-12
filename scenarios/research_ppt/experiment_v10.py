"""V10 产品验证：复用公共 Harness 和完整账本；默认预览。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import time

from .cli import ROOT, prepare, save, scenario_for
from .documents import file_hash
from .experiment_v9 import invoke
from .recovery import CheckpointPPTService
from .service import private_path

EXPERIMENT = 'research-ppt-v10-product-20261012'


def run_revision(job: Path, deck: str, case: str, updates: Path, call_model: bool) -> dict:
    started = time.monotonic()
    job, updates = private_path(job), private_path(updates)
    payload = json.loads(updates.read_text(encoding='utf-8'))
    if not isinstance(payload, list) or not payload:
        raise ValueError('updates 必须是明确 page/changes 列表')
    current = CheckpointPPTService(job).read_deck_plan(deck)
    scenario = scenario_for(job, False, 'reliable')
    spec = json.loads(scenario.read_text(encoding='utf-8'))
    area = ROOT / '.local/research-ppt' / EXPERIMENT / 'normal-traces' / case
    area.mkdir(parents=True, exist_ok=False)
    prompt = Path(spec['prompt']).read_text(encoding='utf-8')
    prompt += ('\n本次明确反馈替代原始生成要求：修订下面指定的现有 deck，按 updates 只改明确字段。'
               '其余文字、图件、notes、来源及非目标页全部保持，页数不变。不要重做初稿。'
               '完成真实渲染验收并交付新副本。按实际需要选择工具，无固定工具顺序要求。\n'
               + json.dumps({'deck_id': deck, 'file_sha256': current['file_sha256'],
                             'updates': payload}, ensure_ascii=False))
    frozen_prompt = area / 'prompt.md'
    frozen_prompt.write_text(prompt, encoding='utf-8')
    spec['prompt'] = str(frozen_prompt)
    frozen_scenario = area / 'scenario.json'
    save(frozen_scenario, spec)
    save(area / 'task.json', {'experiment_id': EXPERIMENT, 'job': str(job), 'deck_id': deck,
                             'starting_deck_sha256': current['file_sha256'], 'updates': payload,
                             'updates_sha256': file_hash(updates), 'group': 'B0-Harness-explicit-edit'})
    return invoke(area / 'revision-01', job, frozen_scenario, 'revision', case, call_model,
                  time.monotonic() - started, experiment_id=EXPERIMENT, group='B0-Harness-explicit-edit')


def run_seed(inputs: list[Path], case: str, instruction: str, slides: int, call_model: bool,
             certificate: Path | None = None) -> dict:
    started = time.monotonic()
    area = ROOT / '.local/research-ppt' / EXPERIMENT / 'normal-traces' / case
    area.mkdir(parents=True, exist_ok=False)
    job = prepare(inputs, instruction, slides, allow_output=True, document_cache=False,
                  layout_policy=certificate)
    save(area / 'task.json', {'experiment_id': EXPERIMENT, 'job': str(job), 'slides': slides,
                             'inputs_sha256': [file_hash(path) for path in inputs],
                             'layout_certificate_sha256': file_hash(certificate) if certificate else None})
    return invoke(area / 'seed-01', job, scenario_for(job, False, 'reliable'), 'seed', case, call_model,
                  time.monotonic() - started, experiment_id=EXPERIMENT,
                  group='RSI-policy-new-task' if certificate else 'B0-Harness-new-task')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='phase', required=True)
    revision = sub.add_parser('revision')
    revision.add_argument('--job', required=True, type=Path)
    revision.add_argument('--deck', required=True)
    revision.add_argument('--updates', required=True, type=Path)
    seed = sub.add_parser('seed')
    seed.add_argument('--input', required=True, nargs='+', type=Path)
    seed.add_argument('--instruction', required=True)
    seed.add_argument('--slides', required=True, type=int)
    seed.add_argument('--certificate', type=Path)
    for command in (revision, seed):
        command.add_argument('--case', required=True)
        command.add_argument('--call-model', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z][a-z0-9-]{2,80}', args.case):
        parser.error('case 使用新的固定短标识；不覆盖历史尝试')
    if args.phase == 'revision':
        value = run_revision(args.job, args.deck, args.case, args.updates, args.call_model)
    else:
        value = run_seed(args.input, args.case, args.instruction, args.slides,
                         args.call_model, args.certificate)
    print(json.dumps(value, ensure_ascii=False))
    return value['returncode']


if __name__ == '__main__':
    raise SystemExit(main())
