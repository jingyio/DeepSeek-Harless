"""Run H/S/frozen controls on the same operational stream; no learning or new acceptance."""
from __future__ import annotations
import argparse
import json
import shutil
import sys
from pathlib import Path
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT));sys.path.insert(0, str(ROOT / 'scenarios/file-management'))
import auto_rsi as rsi
from common import save, sha, digest
from script_reuse_study import arms


def prepare(parent):
    p = rsi.read(parent / 'protocol.json')
    if not (parent / 'independent-audit.json').exists():
        raise ValueError('complete and independently audit RSI before running controls')
    exp = ROOT / '.local/file-management' / ('fm-auto-rsi-controls-20261014-' + uuid4().hex[:8])
    exp.mkdir(mode=0o700)
    for name in ['frozen-source', 'registry']:
        shutil.copytree(parent / name, exp / name)
    for name in ['control.patch.yml', 'launcher.py']:
        shutil.copyfile(parent / name, exp / name)
    seed = rsi.read(parent / 'seed-lock.json')
    seed['registry_file'] = str(exp / 'registry/versions/000001.json')
    assert sha(seed['registry_file']) == seed['registry_sha256']
    save(exp / 'seed-lock.json', seed)
    tasks, templates = [], []
    for c in p['tasks']:
        t = {**c, 'task_id': c['pair_id'], 'task_dir': c['template_dir']}
        t.pop('arm', None);t.pop('template_dir', None)
        templates.append(t);tasks.extend(arms(exp, t, ('H', 'S', 'F')))
    protocol = {**p, 'experiment_id': exp.name, 'type': 'same operational stream H/S/frozen controls, never learning',
                'tasks': tasks, 'templates': templates, 'probes': [], 'imported_pre_certification_evidence': [],
                'parent_experiment': str(parent), 'parent_protocol_sha256': sha(parent / 'protocol.json'),
                'source_experiment_has_two_upgrades': True, 'learning_permitted': False,
                'script_source_sha256': sha(__file__)}
    save(exp / 'protocol.json', protocol);save(exp / 'protocol-lock.json', {'sha256': sha(exp / 'protocol.json')})
    save(ROOT / '.local/file-management/auto-rsi-controls-current.json', {'experiment': str(exp)})
    return exp


def full_comparison(parent, controls):
    p = rsi.read(parent / 'protocol.json')
    original = rsi.read(parent / 'summary.json')['outcomes']
    baseline = [rsi.read(f) for f in controls.glob('tasks/*/attempts/*/outcome.json')]
    initial = p['seed_setup_cost_usd'] + p['motif_setup_cost_usd']
    improvement = [r for r in original if r['role'] in ('explore', 'certify')]
    result = {'parent_experiment': parent.name, 'controls_experiment': controls.name,
              'same_goal_materials_schema_permission_stream': True,
              'operational_controls_run_after_RSI': True, 'final_arms_rotated': True,
              'final_holdout_learning_permitted': False, 'actual_bill_verified': False, 'human_cost_monetization': 'not requested', 'arms': {}}
    for arm in 'HSFR':
        normal = [r for r in original if r['role'] == 'observe' and r['arm'] == arm] if arm == 'R' else [r for r in baseline if r['arm'] == arm]
        final = [r for r in original if r['role'] == 'holdout' and r['arm'] == arm]
        normal_cost = sum(r['run']['budget_accounted_usd'] for r in normal)
        final_cost = sum(r['run']['budget_accounted_usd'] for r in final)
        extra = sum(r['run']['budget_accounted_usd'] for r in improvement) if arm == 'R' else 0
        result['arms'][arm] = {'operational_tasks': len(normal), 'operational_passed': sum(r['acceptance']['passed'] for r in normal),
            'operational_requests': sum(r['run']['upstream_requests'] for r in normal), 'operational_cost_usd': normal_cost,
            'final_tasks': len(final), 'final_passed': sum(r['acceptance']['passed'] for r in final),
            'final_requests': sum(r['run']['upstream_requests'] for r in final), 'final_execution_cost_usd': final_cost,
            'shared_seed_cost_usd': initial if arm in 'FR' else 0, 'exploration_certification_failures_cost_usd': extra,
            'full_api_cost_usd': normal_cost + final_cost + extra + (initial if arm in 'FR' else 0)}
    # Duplicate immutable imports count once in the actual series; each arm is a separate cost alternative.
    save(parent / 'complete-cost-comparison.json', result)
    return result


def main():
    parser = argparse.ArgumentParser();parser.add_argument('--parent', type=Path, required=True)
    parser.add_argument('--experiment', type=Path);parser.add_argument('--call-model', action='store_true');args = parser.parse_args()
    parent = args.parent.resolve();exp = args.experiment.resolve() if args.experiment else prepare(parent)
    p = rsi.read(exp / 'protocol.json')
    if not args.call_model:
        print(json.dumps({'experiment': str(exp), 'paired_operational_controls': 15, 'paid': False}));return
    lock = ROOT / '.local/file-management/active.lock'
    with lock.open('x') as stream:
        stream.write(exp.name)
    try:
        seed = Path(rsi.read(exp / 'seed-lock.json')['registry_file'])
        for c in p['tasks']:
            rsi.run_task(exp, c, p, seed if c['arm'] == 'F' else None)
        value = full_comparison(parent, exp)
        print(json.dumps(value), flush=True)
    finally:
        lock.unlink()


if __name__ == '__main__':
    main()
