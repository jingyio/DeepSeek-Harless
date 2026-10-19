"""Prospective fixed-horizon quality/full-cost comparison after effect-guard repair."""
from __future__ import annotations
import argparse
import json
import shutil
from pathlib import Path
from uuid import uuid4
import auto_rsi as rsi
import fallback_rsi as fresh
from common import ROOT, sha, save, digest
from script_reuse_study import arms
from src.motif_core.offline.experience_registry import ExperienceRegistry, durable

NOVEL_GOALS={
    'FM05:max':fresh.GOALS[0],
    'FM17:filtered':'Make a verified backup and recovery drill of the actual original roster using the current selection notice. Determine eligibility from authorized metadata, preserve every original, finish backups before recovering from their actual identities, and retain relative subdirectories.'}


def old_learning_cost(parent, prior):
    """Only operational exploration/certification; do not open a previous final set."""
    files = {Path(r['outcome_file']) for r in prior.get('imported_pre_certification_evidence', []) if r['kind']=='explore'}
    for pattern in ('exploration-*-materials.json', 'supplemental-exploration-*-materials.json', 'certification-*-materials.json'):
        for material in parent.glob(pattern):
            for c in rsi.read(material)['tasks']:
                files.add(next(Path(c['task_dir']).glob('attempts/*/outcome.json')))
    rows = [rsi.read(f) for f in files]
    if any(o['role'] not in ('explore', 'certify') for o in rows):
        raise ValueError('prior library costs must be non-holdout construction evidence')
    return {'cost_usd':sum(o['run']['budget_accounted_usd'] for o in rows),
            'outcomes':{str(f):sha(f) for f in sorted(files)}}


def diagnostic_costs():
    records = []
    for phase in ('before', 'after', 'after-v2'):
        directory=Path(rsi.read(ROOT/'.local/file-management'/('fallback-'+phase+'-current.json'))['experiment'])
        summary=rsi.read(directory/'summary.json')
        if summary['attempts']!=12 or summary['learning_permitted'] is not False:
            raise ValueError('finish and retain all six-pair diagnostic revisions before fixing cost horizon')
        if phase=='after-v2' and (summary['arms']['H']['passed']!=6 or summary['arms']['F']['passed']!=6):
            raise ValueError('latest fallback quality must pass the frozen new diagnostic before the cost study')
        records.append({'experiment':str(directory),'summary_sha256':sha(directory/'summary.json'),
                        'cost_usd':sum(v['cost_usd'] for v in summary['arms'].values())})
    return records


def prepare(parent):
    prior = rsi.read(parent / 'protocol.json')
    legacy_learning=old_learning_cost(parent,prior)
    diagnosis=diagnostic_costs()
    exp = ROOT / '.local/file-management' / ('fm-continual-rsi-20261014-' + uuid4().hex[:8])
    exp.mkdir(mode=0o700)
    shutil.copytree(parent / 'registry', exp / 'registry')
    for n in ('control.patch.yml', 'launcher.py'):
        shutil.copyfile(parent / n, exp / n)
    registry = ExperienceRegistry(exp / 'registry')
    retained = registry.load()
    registry.publish(disable=[e['entry_id'] for e in retained['entries'] if e['state']=='active'],
                     reason='MCP effect guard changed: preserve originals; require fresh ordinary learning and independent certification')
    templates, seeds, tasks = [], [], []
    for number, business in enumerate(('FM05:min','FM17:all','FM05:max','FM17:filtered'),1):
        origins = []
        for i in (0, 1):
            t, rr = rsi.make(exp, 'explore', business, bool(i), i, 'new-seed-' + str(number) + '-' + str(i), ('H',))
            templates.append(t);origins.extend(rr)
        seeds.append({'round': number, 'origins': origins})
    stream = [('FM05:max', False, 0), ('FM05:max', True, 1),
              ('FM05:max', False, 1), ('FM05:max', True, 0),
              ('FM17:filtered', False, 0), ('FM17:filtered', True, 1),
              ('FM17:filtered', False, 1), ('FM17:filtered', True, 0),
              ('FM05:max', True, 1), ('FM17:filtered', True, 1)]
    for i, (business, layout, size) in enumerate(stream):
        t, _ = rsi.make(exp, 'observe', business, layout, size, 'stream-' + str(i), ())
        fresh.rewrite_goal(t,NOVEL_GOALS[business])
        templates.append(t)
        order = tuple('HSFR');offset = i % 4
        tasks.extend(arms(exp, t, order[offset:] + order[:offset]))
    p = {**prior, 'experiment_id': exp.name, 'type': 'fresh fixed-horizon rotated operational H/S/F/R plus sealed final evaluation',
         'templates': templates, 'tasks': tasks, 'seeds': seeds, 'probes': [], 'imported_pre_certification_evidence': [],
         'batch_cap_usd': 300, 'seed_relearning_due_to_service_change': True, 'seed_roles': ['explore', 'certify'],
         'prior_nonholdout_learning_cost':legacy_learning, 'diagnostic_cost_sources':diagnosis,
         'operational_pairs': len(stream), 'old_final_holdout_opened': False,
         'automatic_upgrade_rounds': [5, 6], 'upgrade_after_stream_indices': [1, 5],
         'final_conditions_frozen_in_protocol': ['min-base', 'all-base', 'max-base', 'max-dirs',
             'filtered-base', 'filtered-dirs', 'unknown-max-base', 'unknown-max-dirs', 'version-max', 'version-filtered'],
         'final_materials_created_only_after_upgrades': True, 'final_holdout_learning_permitted': False,
         'test_sources': {n: sha(exp / n) for n in ('control.patch.yml', 'launcher.py')}}
    fresh.freeze_sources(exp, p)
    save(exp / 'protocol.json', p);save(exp / 'protocol-lock.json', {'sha256': sha(exp / 'protocol.json')})
    save(ROOT / '.local/file-management/continual-rsi-current.json', {'experiment': str(exp)})
    rsi.state_event(exp, 'prepared', {'stream_pairs': len(stream), 'final_conditions': 10, 'batch_usd': 300,
                                    'original_permissions_preserved': True, 'old_final_not_opened': True})
    print(json.dumps({'experiment': str(exp), 'paid': False, 'batch_cap_usd': 300, 'per_task_usd': 5,
                      'max_requests': 96, 'max_repairs': 2, 'model': p['model'], 'stream_pairs': 10,
                      'final_holdout_exists': False}), flush=True)
    return exp


def build_seed(exp, p):
    if (exp / 'seed-lock.json').exists():
        return rsi.read(exp / 'seed-lock.json')
    for part in p['seeds']:
        n = part['round'];origins = part['origins']
        if (exp / f'upgrade-{n}/activation.json').exists():
            continue
        exploration = {'tasks': origins}
        for c in origins:
            rsi.run_task(exp, c, p)
        lock = rsi.learn_candidate(exp, p, n, exploration)
        if not lock['scripts']:
            rsi.state_event(exp, 'seed_candidate_rejected', {'round': n, 'excluded': lock['excluded']})
            supplement = rsi.material_set(exp, f'seed-supplement-{n}', 'explore', origins, 'H')
            for c in supplement['tasks']:
                rsi.run_task(exp, c, p)
            exploration = {'tasks': origins + supplement['tasks']}
            lock = rsi.learn_candidate(exp, p, n, exploration, attempt=2)
        if len(lock['scripts']) != 1:
            raise ValueError('fresh current-version seed unsupported; bounded failures retained')
        cert_materials = rsi.material_set(exp, f'certification-{n}', 'certify', origins, 'C')
        cert = rsi.certify_candidate(exp, p, n, lock, cert_materials)
        if rsi.read(cert)['status'] != 'certified_v2':
            raise ValueError('fresh seed did not pass independent certification')
        reg = ExperienceRegistry(exp / 'registry')
        entries = [reg.entry('script_v2', r['path'], rsi.runtime_source('script_v2', p), cert) for r in lock['scripts']]
        file = reg.publish(entries, reason='new service version; independently certified fresh shared seed')
        activation = {'round': n, 'registry_file': str(file), 'registry_sha256': sha(file),
                      'new_entries': [e['entry_id'] for e in entries], 'certificate_sha256': sha(cert),
                      'automatic': True, 'holdout_used': False, 'seed_recertification': True}
        durable(exp / f'upgrade-{n}/activation.json', activation, exclusive=True)
        rsi.state_event(exp, 'shared_seed_candidate_activated', activation)
    reg = ExperienceRegistry(exp / 'registry');pointer = rsi.read(exp / 'registry/current.json')
    seed = {'registry_file': str(exp / 'registry' / pointer['file']), 'registry_sha256': pointer['sha256'],
            'registry_digest': reg.load()['registry_digest'], 'generation': reg.load()['generation'],
            'historical_seed_cost_usd': p['seed_setup_cost_usd'] + p['motif_setup_cost_usd'],
            'prior_upgrade_build_cost_usd': p['prior_nonholdout_learning_cost']['cost_usd'],
            'prior_upgrade_cost_source': p['prior_nonholdout_learning_cost']['outcomes'],
            'fresh_seed_cost_usd': sum(rsi.read(f)['run']['budget_accounted_usd'] for f in exp.glob('tasks/*/attempts/*/outcome.json'))}
    durable(exp / 'seed-lock.json', seed, exclusive=True)
    rsi.state_event(exp, 'shared_seed_frozen', seed)
    return seed


def final_materials(exp, p):
    file = exp / 'final-materials.json'
    if file.exists():
        return rsi.read(file)
    if not all((exp / f'upgrade-{n}/activation.json').exists() for n in (5, 6)):
        raise ValueError('two actual operational upgrades required before final materials')
    choices = [('FM05:min', False, 0, 'min-base'), ('FM17:all', False, 0, 'all-base'),
               ('FM05:max', False, 0, 'max-base'), ('FM05:max', True, 1, 'max-dirs'),
               ('FM17:filtered', False, 0, 'filtered-base'), ('FM17:filtered', True, 1, 'filtered-dirs'),
               ('FM05:max', False, 1, 'unknown-max-base'), ('FM05:max', True, 0, 'unknown-max-dirs'),
               ('FM05:max', False, 0, 'V'), ('FM17:filtered', True, 1, 'V')]
    templates, tasks = [], []
    for i, (business, layout, size, label) in enumerate(choices):
        t, _ = rsi.make(exp, 'holdout', business, layout, size, label, ())
        if label.startswith('unknown-'):
            fresh.rewrite_goal(t, fresh.GOALS[1 if layout else 2])
        elif business in NOVEL_GOALS:
            fresh.rewrite_goal(t,NOVEL_GOALS[business])
        templates.append(t);order = tuple('HSFR');offset = i % 4
        tasks.extend(arms(exp, t, order[offset:] + order[:offset]))
    pointer = rsi.read(exp / 'registry/current.json')
    value = {'templates': templates, 'tasks': tasks, 'seed': rsi.read(exp / 'seed-lock.json'),
             'registry_file': str(exp / 'registry' / pointer['file']), 'registry_sha256': pointer['sha256'],
             'learning_from_holdout_permitted': False, 'frozen_before_final_execution': True,
             'final_model_calls_when_frozen': 0}
    durable(file, value, exclusive=True);durable(exp / 'final-lock.json', {'sha256': sha(file)}, exclusive=True)
    rsi.state_event(exp, 'final_holdout_frozen', {'pairs': 10, 'learning_disabled': True})
    return value


def summarize(exp, p):
    rows = [rsi.read(f) for f in exp.glob('tasks/*/attempts/*/outcome.json')]
    seed = rsi.read(exp / 'seed-lock.json') if (exp / 'seed-lock.json').exists() else None
    shared = sum(seed[k] for k in ('historical_seed_cost_usd', 'prior_upgrade_build_cost_usd', 'fresh_seed_cost_usd')) if seed else 0
    validation = sum(r['cost_usd'] for r in p['diagnostic_cost_sources'])
    seed_ids = {c['task_id'] for part in p['seeds'] for c in part['origins']}
    for file in list(exp.glob('seed-supplement-*-materials.json')) + [exp / f'certification-{part["round"]}-materials.json' for part in p['seeds']]:
        if file.exists():seed_ids.update(c['task_id'] for c in rsi.read(file)['tasks'])
    improvement = [o for o in rows if o['role'] in ('explore', 'certify') and o['task_id'] not in seed_ids]
    groups = {}
    for arm in 'HSFR':
        op = [o for o in rows if o['role']=='observe' and o['arm']==arm]
        held = [o for o in rows if o['role']=='holdout' and o['arm']==arm]
        operational = sum(o['run']['budget_accounted_usd'] for o in op)
        final = sum(o['run']['budget_accounted_usd'] for o in held)
        extra = sum(o['run']['budget_accounted_usd'] for o in improvement) if arm=='R' else 0
        groups[arm] = {'operational_tasks': len(op), 'operational_passed': sum(o['acceptance']['passed'] for o in op),
            'final_tasks': len(held), 'positive_final_conditions': sum(o['condition']!='V' for o in held),
            'positive_final_passed': sum(o['condition']!='V' and o['acceptance']['passed'] for o in held),
            'version_stops': sum(o['condition']=='V' and o['condition_passed'] for o in held),
            'execution_requests': sum(o['run']['upstream_requests'] for o in op+held),
            'operational_cost_usd': operational, 'final_cost_usd': final, 'repairs': sum(o['acceptance_repairs'] for o in op+held),
            'shared_seed_cost_usd': shared if arm in 'FR' else 0, 'new_learning_certification_failures_cost_usd': extra,
            'common_effect_guard_diagnostic_cost_usd':validation,
            'incremental_api_cost_usd': operational+final+extra,
            'full_api_cost_usd': operational+final+extra+(shared if arm in 'FR' else 0)+validation}
    f,r=groups['F'],groups['R']
    equal_quality = bool(f['positive_final_conditions']==r['positive_final_conditions']==8 and
                         f['positive_final_passed']==r['positive_final_passed']==8 and
                         f['operational_tasks']==r['operational_tasks']==10 and
                         f['operational_passed']==r['operational_passed']==10)
    value = {'experiment_id': exp.name, 'attempts':len(rows), 'arms':groups,
             'requests':sum(o['run']['upstream_requests'] for o in rows),
             'cost_usd':sum(o['run']['budget_accounted_usd'] for o in rows),
             'equal_delivery_quality_F_R':equal_quality, 'observed_net_API_benefit':equal_quality and r['full_api_cost_usd']<f['full_api_cost_usd'],
             'final_holdout_learned':False, 'old_final_holdout_opened':False, 'actual_bill_verified':False,
             'human_cost_monetization':'not requested; development and maintenance not zero',
             'fixed_horizon_not_extended_for_positive_results':True}
    save(exp / 'summary.json', value)
    return value


def execute(exp, p):
    seed = build_seed(exp, p)
    current = lambda: exp / 'registry' / rsi.read(exp / 'registry/current.json')['file']
    grouped = {}
    for c in p['tasks']:
        grouped.setdefault(c['pair_id'], []).append(c)
    observed = []
    for index, cases in enumerate(grouped.values()):
        for c in cases:
            o=rsi.run_task(exp,c,p,Path(seed['registry_file']) if c['arm']=='F' else current() if c['arm']=='R' else None)
            if c['arm']=='R':observed.append((c,o))
            summarize(exp,p)
        if index in (1,5):
            number=5 if index==1 else 6
            rsi.cycle(exp,p,number,[c for c,o in observed[-2:]])
        if index==2:
            c,o=observed[-1]
            if not o['script_steps'] or not o['acceptance']['passed']:
                raise ValueError('first upgrade did not execute in subsequent operational task')
            rsi.state_event(exp,'prior_upgrade_executed_in_next_round',{'outcome_file':str(Path(o['attempt'])/'outcome.json'),'requests':o['run']['upstream_requests']})
    held=final_materials(exp,p)
    if sha(exp/'final-materials.json')!=rsi.read(exp/'final-lock.json')['sha256'] or sha(held['registry_file'])!=held['registry_sha256']:
        raise ValueError('final freeze changed')
    for c in held['tasks']:
        rsi.run_task(exp,c,p,Path(seed['registry_file']) if c['arm']=='F' else Path(held['registry_file']) if c['arm']=='R' else None)
        summarize(exp,p)
    rsi.state_event(exp,'complete',{'operational_pairs':10,'final_pairs':10,'new_operational_upgrades':2,'final_learning':False})
    return summarize(exp,p)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--parent',type=Path);parser.add_argument('--experiment',type=Path)
    parser.add_argument('--call-model',action='store_true');args=parser.parse_args()
    if not args.experiment:
        if not args.parent:parser.error('--parent required')
        prepare(args.parent.resolve());return
    exp=args.experiment.resolve();p=rsi.read(exp/'protocol.json')
    if not args.call_model:print(json.dumps({'experiment':str(exp),'paid':False,'batch_usd':300}));return
    lock=ROOT/'.local/file-management/active.lock'
    with lock.open('x') as f:f.write(exp.name)
    try:print(json.dumps(execute(exp,p)),flush=True)
    except BaseException as error:
        rsi.state_event(exp,'stopped_with_failure',{'type':type(error).__name__,'message':str(error),'failures_retained':True})
        summarize(exp,p);raise
    finally:lock.unlink()


if __name__=='__main__':main()
