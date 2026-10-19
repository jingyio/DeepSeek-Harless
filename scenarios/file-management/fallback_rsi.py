"""Fresh paired fallback diagnostics; no prior final materials are opened or learned."""
from __future__ import annotations
import argparse
import json
import shutil
from pathlib import Path
from uuid import uuid4
import auto_rsi as rsi
from common import ROOT, save, sha, source_code
from script_reuse_study import arms

GOALS = (
    'Consolidate the listed original files by exact byte identity. Use the actual merge notice to choose the full-path representative and permitted output directory. Keep every original and verify the result.',
    'Prepare a deduplicated delivery from workflow source_paths: read the current merge instructions, retain a single representative for each equal-byte class, preserve originals and report verified current files.',
    'Produce the merge delivery required by the actual rules file, using current hashes and the authorized destination. Resolve identical content once per group and retain different content even when names coincide.',
)


def freeze_sources(exp, p):
    names = sorted(set(n for n in source_code() if not n.endswith('.md')) | set(rsi.h.EXTRA) | set(rsi.EXTRA))
    for n in names:
        q = exp / 'frozen-source' / n
        q.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / n, q)
    p['source_code'] = {n: sha(ROOT / n) for n in names}


def rewrite_goal(t, goal):
    td = Path(t['task_dir'])
    spec = rsi.read(td / 'input-template.json')
    spec['objective'] = goal
    save(td / 'input-template.json', spec)
    prompt = td / 'prompt.md'
    prompt.write_text(prompt.read_text() + '\n当前真实目标覆盖前述目标表述：' + goal)
    t.update(input_template_sha256=sha(td / 'input-template.json'), prompt_sha256=sha(prompt))
    return t


def prepare_diagnostic(parent, phase):
    prior = rsi.read(parent / 'protocol.json')
    exp = ROOT / '.local/file-management' / ('fm-fallback-' + phase + '-20261014-' + uuid4().hex[:8])
    exp.mkdir(mode=0o700)
    shutil.copytree(parent / 'registry', exp / 'registry')
    # Only the immutable last registry version is imported, never final tasks/outcomes/oracles.
    last = rsi.read(exp / 'registry/current.json')['file']
    registry = exp / 'registry' / last
    for n in ('control.patch.yml', 'launcher.py'):
        shutil.copyfile(parent / n, exp / n)
    templates, tasks = [], []
    for i in range(6):
        t, _ = rsi.make(exp, 'diagnose', 'FM05:max', bool(i % 2), i % 2, 'fresh-' + str(i), ())
        rewrite_goal(t, GOALS[i % len(GOALS)])
        templates.append(t)
        tasks.extend(arms(exp, t, ('H', 'F') if i % 2 == 0 else ('F', 'H')))
    p = {**prior, 'experiment_id': exp.name, 'type': 'fresh direct ordinary versus verified no-match ordinary fallback',
         'phase': phase, 'parent_registry_file': str(registry), 'parent_registry_sha256': sha(registry),
         'templates': templates, 'tasks': tasks, 'probes': [], 'imported_pre_certification_evidence': [],
         'learning_permitted': False, 'final_holdout_learning_permitted': False, 'batch_cap_usd': 100,
         'test_sources': {n: sha(exp / n) for n in ('control.patch.yml', 'launcher.py')}}
    freeze_sources(exp, p)
    save(exp / 'protocol.json', p)
    save(exp / 'protocol-lock.json', {'sha256': sha(exp / 'protocol.json')})
    save(ROOT / '.local/file-management' / ('fallback-' + phase + '-current.json'), {'experiment': str(exp)})
    print(json.dumps({'experiment': str(exp), 'paid': False, 'new_pairs': 6, 'per_task_usd': 5,
                      'max_repairs': 2, 'series_cap_usd': 1000, 'batch_cap_usd': 100}), flush=True)
    return exp


def summarize(exp, p):
    rows = [rsi.read(f) for f in exp.glob('tasks/*/attempts/*/outcome.json')]
    value = {'experiment_id': exp.name, 'phase': p['phase'], 'attempts': len(rows), 'learning_permitted': False,
             'old_final_holdout_opened': False, 'actual_bill_verified': False, 'arms': {}}
    for arm in ('H', 'F'):
        rr = [o for o in rows if o['arm'] == arm]
        value['arms'][arm] = {'attempts': len(rr), 'passed': sum(o['acceptance']['passed'] for o in rr),
            'requests': sum(o['run']['upstream_requests'] for o in rr),
            'cost_usd': sum(o['run']['budget_accounted_usd'] for o in rr),
            'repairs': sum(o['acceptance_repairs'] for o in rr),
            'selected': sum(bool(o['experience_selected']) for o in rr),
            'reasons': [o['experience_deferred'] for o in rr],
            'failures': [{'task_id': o['task_id'], 'errors': o['acceptance']['errors']} for o in rr if not o['acceptance']['passed']]}
    save(exp / 'summary.json', value)
    return value


def execute_diagnostic(exp, p):
    if sha(p['parent_registry_file']) != p['parent_registry_sha256']:
        raise ValueError('diagnostic frozen registry changed')
    for c in p['tasks']:
        rsi.run_task(exp, c, p, Path(p['parent_registry_file']) if c['arm'] == 'F' else None)
        summarize(exp, p)
    return summarize(exp, p)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--parent', type=Path)
    parser.add_argument('--phase', choices=('before', 'after', 'after-v2'), default='before')
    parser.add_argument('--experiment', type=Path)
    parser.add_argument('--call-model', action='store_true')
    args = parser.parse_args()
    if not args.experiment:
        if not args.parent:
            parser.error('--parent required for preparing new materials')
        prepare_diagnostic(args.parent.resolve(), args.phase)
        return
    exp = args.experiment.resolve()
    p = rsi.read(exp / 'protocol.json')
    if not args.call_model:
        print(json.dumps({'experiment': str(exp), 'paid': False, 'phase': p['phase'], 'pairs': 6}))
        return
    lock = ROOT / '.local/file-management/active.lock'
    with lock.open('x') as f:
        f.write(exp.name)
    try:
        print(json.dumps(execute_diagnostic(exp, p)), flush=True)
    finally:
        lock.unlink()


if __name__ == '__main__':
    main()
