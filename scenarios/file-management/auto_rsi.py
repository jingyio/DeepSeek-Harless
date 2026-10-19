"""Bounded autonomous detect -> ordinary exploration -> certify -> activate; frozen final evaluation."""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from uuid import uuid4
from common import ROOT, HERE, DATA, PREFIX, digest, sha, save, snapshot, source_code
sys.path.insert(0, str(ROOT))
import workflow_holdout as h
import script_adaptation_study as fixtures
from script_adaptation_learning import load_witness, RUNTIME_FILES
from script_reuse_study import arms
from experiment import accounting
from src.motif_core.offline.experience_registry import ExperienceRegistry, durable

EXTRA = ['src/adapters/dsh_experience.ts', 'src/motif_core/offline/experience_registry.py',
         'src/adapters/dsh_learned_script.ts', *RUNTIME_FILES]
CORE = ['src/motif_core/online_skill_runtime.mjs', 'src/motif_core/terminal_receipt_policy.ts']


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def state_event(exp, kind, detail):
    directory = exp / 'controller-events'
    directory.mkdir(exist_ok=True)
    files = sorted(directory.glob('*.json'))
    row = {'sequence': len(files) + 1, 'previous_sha256': sha(files[-1]) if files else None,
           'kind': kind, 'detail': detail}
    durable(directory / f'{len(files) + 1:06d}.json', row, exclusive=True)


def make(exp, role, business_case, layout, size, label, arm_order):
    # Business cases generate external rule changes. No execution/learning selector sees this label.
    t = fixtures.template(exp, role, business_case, layout, size, label)
    t.pop('profile_id', None)
    tasks = arms(exp, t, arm_order)
    for c in tasks:
        c.pop('profile_id', None)
    return t, tasks


def runtime_source(kind, protocol):
    names = set(CORE + ['src/adapters/dsh_learned_script.ts'] if kind == 'script_v1' else RUNTIME_FILES)
    if not kind.startswith('script_'):
        names = set(read(Path(protocol['library']) / 'library-lock.json')['groups']['workflow14']['dependencies'])
        names.update(['src/motif_core/collection_read_policy.ts', 'src/motif_core/collection_reentry_policy.ts',
                      'src/motif_core/authorized_plan_policy.ts', 'src/motif_core/online_skill_runtime.mjs'])
    return {n: sha(ROOT / n) for n in sorted(names)}


def seed_registry(exp, p):
    registry = ExperienceRegistry(exp / 'registry')
    seed = Path(p['seed_experiment'])
    entries = []
    for r in read(seed / 'candidate-lock.json')['scripts']:
        entries.append(registry.entry('script_v1', r['path'], runtime_source('script_v1', p), seed / 'certificate.json'))
    library = Path(p['library'])
    for kind, name in [('read_library', 'workflow14/edge-library.json'), ('collection', 'workflow14/collection-policy.json')]:
        entries.append(registry.entry(kind, library / 'libraries' / name, runtime_source(kind, p)))
    # The plan is preserved, with its outer service/job dependencies; no autonomous restore certificate.
    lock = read(library / 'library-lock.json')
    plan_source = {n: sha(ROOT / n) for n in lock['groups']['recovery15']['dependencies']}
    plan_source.update({n: sha(ROOT / n) for n in ['src/motif_core/authorized_plan_policy.ts', 'src/motif_core/online_skill_runtime.mjs']})
    entries.append(registry.entry('plan', library / 'libraries/recovery15/plan-policy.json', plan_source))
    file = registry.publish(entries, reason='same historical certified seed for frozen and RSI arms', expected=0)
    durable(exp / 'seed-lock.json', {'registry_file': str(file), 'registry_sha256': sha(file),
                                    'registry_digest': registry.load()['registry_digest'], 'generation': 1})
    return file


def prepare(continuation=None):
    parent = Path(read(ROOT / '.local/file-management/script-reuse-current.json')['experiment'])
    old = read(parent / 'protocol.json')
    exp = ROOT / '.local/file-management' / ('fm-auto-rsi-20261014-' + uuid4().hex[:8])
    exp.mkdir(mode=0o700)
    templates, observations, probes = [], [], []
    # A fixed external task stream. The controller must discover failures/benefits from actual outcomes.
    for role, business, layout, size, label in [
        ('probe', 'FM05:min', False, 0, 'free'), ('probe', 'FM17:all', False, 0, 'free'),
        ('observe', 'FM05:max', False, 0, 'stream-1a'), ('observe', 'FM05:max', True, 1, 'stream-1b'),
        ('observe', 'FM05:max', True, 1, 'stream-2-prior-library'),
        ('observe', 'FM17:filtered', False, 0, 'stream-2a'), ('observe', 'FM17:filtered', True, 1, 'stream-2b')]:
        t, tasks = make(exp, role, business, layout, size, label, ('R',))
        templates.append(t)
        (probes if role == 'probe' else observations).extend(tasks)
    patch = exp / 'control.patch.yml'
    patch.write_text(json.dumps([{'insert': [
        {'id': 'sss-workflow-experiment', 'name': (ROOT / 'src/adapters/dsh_workflow_experiment.ts').as_uri()},
        {'id': 'sss-experience', 'name': (ROOT / 'src/adapters/dsh_experience.ts').as_uri()}]}]))
    launcher = exp / 'launcher.py'
    launcher.write_text("import importlib.util\ns=importlib.util.spec_from_file_location('public_runner'," + repr(str(ROOT / 'scripts/run-file-scenario.py')) + ");m=importlib.util.module_from_spec(s);s.loader.exec_module(m)\noriginal=m.create_harness\ndef wrapped(**kwargs):\n kwargs['patches']=tuple(kwargs['patches'])+(" + repr(str(patch)) + ",)\n return original(**kwargs)\nm.create_harness=wrapped\nraise SystemExit(m.main())\n")
    paths = sorted(set(n for n in source_code() if not n.endswith('.md')) | set(h.EXTRA) | set(EXTRA))
    for name in paths:
        q = exp / 'frozen-source' / name
        q.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, q)
    p = {k: old[k] for k in ['library', 'library_lock_sha256', 'limits', 'max_steps', 'max_output', 'max_repairs',
                             'per_task_cap_usd', 'total_cap_usd', 'model', 'reasoning_effort', 'compression_enabled',
                             'original_pdfs', 'runtime', 'price_source']}
    imported = []
    if continuation:
        old_exp = Path(continuation).resolve()
        old_p = read(old_exp / 'protocol.json')
        if list(old_exp.glob('upgrade-*/certificate.json')) or (old_exp / 'final-materials.json').exists():
            raise ValueError('continuation imports only pre-certification operational/ordinary evidence')
        if sha(old_exp / 'protocol.json') != read(old_exp / 'protocol-lock.json')['sha256']:
            raise ValueError('original continuation protocol changed')
        for n in read(Path(old_p['library']) / 'library-lock.json')['groups']['workflow14']['dependencies']:
            if old_p['source_code'][n] != sha(ROOT / n):
                raise ValueError('incompatible original MCP evidence')
        for c in old_p['tasks'][:2]:
            outcome = next(Path(c['task_dir']).glob('attempts/*/outcome.json'))
            imported.append({'kind': 'observe', 'case': c, 'outcome_file': str(outcome), 'outcome_sha256': sha(outcome),
                             'experiment': str(old_exp), 'protocol_sha256': sha(old_exp / 'protocol.json')})
        observations[:2] = [r['case'] for r in imported]
        for c in read(old_exp / 'exploration-1-materials.json')['tasks']:
            outcome = next(Path(c['task_dir']).glob('attempts/*/outcome.json'))
            imported.append({'kind': 'explore', 'case': c, 'outcome_file': str(outcome), 'outcome_sha256': sha(outcome),
                             'experiment': str(old_exp), 'protocol_sha256': sha(old_exp / 'protocol.json')})
    p.update(experiment_id=exp.name, type='generated bounded autonomous RSI with two upgrades and four-arm final evaluation',
             source_code={n: sha(ROOT / n) for n in paths}, templates=templates, tasks=observations, probes=probes,
             seed_experiment=str(parent), seed_certificate_sha256=sha(parent / 'certificate.json'),
             seed_setup_cost_usd=read(parent / 'summary.json')['setup_cost_usd'],
             motif_setup_cost_usd=sum(r['estimated_usd'] for r in old['overhead_sources']),
             series_before=accounting(), batch_cap_usd=300, max_upgrade_rounds=2, max_discoveries=2,
             ordinary_explorations_per_opportunity=4, independent_certifications_per_candidate=2,
             imported_pre_certification_evidence=imported,
             final_holdout_learning_permitted=False, human_blind_review=False, actual_bill_verified=False,
             max_cold_restarts=0, default_sdk_web_enabled=False, push_enabled=False,
             auto_selection_uses_profile_id=False, exact_goal_guard_semantic_paraphrase='ordinary Harness fallback',
             before_any_model_calls=True, test_sources={q.name: sha(q) for q in [patch, launcher]})
    save(exp / 'protocol.json', p)
    save(exp / 'protocol-lock.json', {'sha256': sha(exp / 'protocol.json')})
    seed_registry(exp, p)
    save(ROOT / '.local/file-management/auto-rsi-current.json', {'experiment': str(exp)})
    state_event(exp, 'prepared', {'batch_cap_usd': 300, 'same_seed': True, 'final_holdout_exists': False})
    print(json.dumps({'experiment': str(exp), 'real_model': p['model'], 'series_before': p['series_before'],
                      'batch_cap_usd': 300, 'max_upgrades': 2, 'final_holdout_created': False, 'paid': False}), flush=True)
    return exp


def check_frozen(exp, p):
    if sha(exp / 'protocol.json') != read(exp / 'protocol-lock.json')['sha256']:
        raise ValueError('pre-frozen protocol/acceptance changed')
    for name, hsh in p['source_code'].items():
        if sha(ROOT / name) != hsh:
            raise ValueError('frozen execution/learning/acceptance source changed: ' + name)
    for row in p.get('imported_pre_certification_evidence', []):
        if sha(row['outcome_file']) != row['outcome_sha256'] or sha(Path(row['experiment']) / 'protocol.json') != row['protocol_sha256']:
            raise ValueError('original continuation evidence changed')
    if sha(Path(p['seed_experiment']) / 'certificate.json') != p['seed_certificate_sha256']:
        raise ValueError('historical seed changed')
    if sha(Path(p['library']) / 'library-lock.json') != p['library_lock_sha256']:
        raise ValueError('original Motif changed')
    groups = [p['templates']] + [read(file)['templates'] for file in exp.glob('*-materials.json')]
    for templates in groups:
        for t in templates:
            td = Path(t['task_dir'])
            for n, key in [('input-template.json', 'input_template_sha256'), ('oracle.json', 'oracle_sha256'),
                           ('prompt.md', 'prompt_sha256'), ('scenario.json', 'scenario_sha256')]:
                if sha(td / n) != t[key]:
                    raise ValueError('frozen new material changed')
            if digest(snapshot(t['pristine'])) != t['snapshot_sha256']:
                raise ValueError('new pristine copy changed')


def experience_binding(exp, c, p, out, spec, env, registry_file):
    # Profile/family/condition labels and acceptance oracle are never sent as selection hints.
    if c['arm'] not in ('R', 'F', 'C'):
        return
    root = exp / 'registry'
    b = {'role': 'certify' if c['arm'] == 'C' else c['role'], 'registry_root': str(root),
         'registry_file': str(registry_file), 'registry_sha256': sha(registry_file),
         'task_file': str(out / 'input.json'), 'task_sha256': sha(out / 'input.json'),
         'prompt_sha256': c['prompt_sha256'], 'runtime_sha256': sha(ROOT / 'src/adapters/dsh_experience.ts'),
         'audit_file': str(out / 'experience-audit.jsonl')}
    if c['workflow_id'] == 'FM38':
        b.update(plan_binding=str(out / 'binding.json'), plan_policy=str(Path(p['library']) / 'libraries/recovery15/plan-policy.json'))
    save(out / 'experience-binding.json', b)
    env['SSS_EXPERIENCE_BINDING'] = str(out / 'experience-binding.json')


def run_task(exp, c, p, registry_file=None):
    existing = list(Path(c['task_dir']).glob('attempts/*/outcome.json'))
    if existing:
        if len(existing) != 1:
            raise ValueError('ambiguous completed attempt')
        return read(existing[0])
    check_frozen(exp, p)
    budget = accounting()
    spent = sum(read(f)['run']['budget_accounted_usd'] for f in exp.glob('tasks/*/attempts/*/outcome.json'))
    if budget['estimated_usd'] + 5 > 1000 or spent + 5 > p['batch_cap_usd']:
        raise ValueError('original series or controller batch budget exhausted')
    out, spec, env, policy = h.instantiate(exp, c, p)
    # Remove inherited experience routes before selecting this task's frozen version.
    for n in list(env):
        if n.startswith(('SSS_LEARNED_', 'SSS_SCRIPT_REPAIR_', 'SSS_EXPERIENCE_', 'SSS_ONLINE_MOTIF_',
                         'SSS_COLLECTION_', 'SSS_PLAN_', 'SSS_REENTRY_', 'SSS_ENTRY_', 'SSS_TERMINAL_')):
            env.pop(n, None)
    if registry_file:
        experience_binding(exp, c, p, out, spec, env, registry_file)
    start = time.monotonic()
    print(json.dumps({'starting': c['task_id'], 'role': c['role'], 'arm': c['arm'], 'original_cap_usd': 5,
                      'registry': str(registry_file) if registry_file else None}), flush=True)
    if c['arm'] == 'S':
        receipt, error = asyncio.run(fixtures.fixed_script(out, spec, c))
        runs = [{'status': 'done' if receipt else 'stopped', 'upstream_requests': 0, 'budget_accounted_usd': 0,
                 'elapsed_seconds': time.monotonic() - start}]
        events = [json.loads(l) for l in (out / 'mcp-calls.jsonl').read_text().splitlines()]
        h.mcp.accept(out, spec, receipt, 0)
    else:
        runs, events = h.launcher_run(exp, c, p, out, spec, env, policy)
        receipt = h.receipt_from(events)
        error = None
    report = read(out / 'delivery/report.json') if (out / 'delivery/report.json').exists() else None
    receipt_ok = bool(receipt and report and receipt['input_sha256'] == digest(spec) and receipt['artifact_sha256'] == digest(report))
    review = h.verify_workflow(spec, report if receipt_ok else None, out / 'delivery', events)
    audit = [json.loads(l) for l in (out / 'experience-audit.jsonl').read_text().splitlines()] if (out / 'experience-audit.jsonl').exists() else []
    combined = {**runs[-1], **{k: sum(r.get(k, 0) for r in runs) for k in
                ('upstream_requests', 'budget_accounted_usd', 'elapsed_seconds', 'inputTokens', 'cacheReadTokens', 'outputTokens')}, 'segments': len(runs)}
    marker = read(out / 'control-marker.json') if (out / 'control-marker.json').exists() else None
    repair = [e for e in events if e.get('type') == 'user/message' and e['data'].get('source', {}).get('kind') == 'task-acceptance-repair']
    o = {'task_id': c['task_id'], 'pair_id': c['pair_id'], 'role': c['role'], 'arm': c['arm'], 'workflow_id': c['workflow_id'], 'condition': c['condition'],
         'attempt': str(out), 'input_sha256': digest(spec), 'source_sha256': digest(p['source_code']), 'run': combined, 'runs': runs,
         'events_sha256': sha(Path(runs[-1]['output_dir']) / 'agent-events.jsonl') if c['arm'] != 'S' else sha(out / 'mcp-calls.jsonl'),
         'receipt_verified': receipt_ok, 'acceptance': review, 'accounting_complete': True, 'normal_harness_only': c['arm'] == 'H',
         'learning_performed': False, 'error': error, 'control_marker': marker, 'condition_passed': review['passed'] if c['expected_delivery'] else bool(not review['passed'] and marker),
         'final_snapshot_sha256': digest(snapshot(spec['workspace'])), 'end_to_end_seconds': time.monotonic() - start,
         'script_steps': sum(r['kind'] in ('learned_script_step_verified', 'script_v2_step_verified') for r in audit),
         'experience_selected': [r for r in audit if r['kind'] == 'experience_selected'],
         'experience_deferred': [r for r in audit if r['kind'] == 'experience_deferred'],
         'retrievals': [r for r in audit if r['kind'] == 'experience_retrieval'], 'retrieval_model_requests': 0,
         'acceptance_repairs': len(repair), 'tool_errors': sum(b.get('isError', False) for e in events if e.get('type') == 'tool/result' for b in e['data']['message'].get('content', []))}
    save(out / 'outcome.json', o)
    save(exp / 'progress.json', {'task_id': c['task_id'], 'state': 'completed', 'phase': c['role']})
    print(json.dumps({'finished': c['task_id'], 'passed': review['passed'], 'requests': combined['upstream_requests'],
                      'cost_usd': combined['budget_accounted_usd'], 'script_steps': o['script_steps'], 'repairs': len(repair),
                      'errors': review['errors']}), flush=True)
    return o


def opportunity(outcomes):
    """Only real non-holdout experience can trigger paid exploration."""
    if any(o['role'] == 'holdout' for o in outcomes):
        raise ValueError('final holdout cannot trigger learning')
    reasons = Counter(r['reason'] for o in outcomes for retrieval in o['retrievals'] for r in retrieval.get('rejected', []))
    failed = sum(not o['acceptance']['passed'] for o in outcomes)
    repeated = sum(o['run']['upstream_requests'] >= 4 for o in outcomes)
    return {'worth_learning': repeated >= 2 or failed >= 2, 'repeated_costly_tasks': repeated, 'failed_tasks': failed,
            'requests': sum(o['run']['upstream_requests'] for o in outcomes), 'mismatch_reasons': dict(reasons),
            'trigger': 'actual repeat costs, mismatches and failures; no template profile'}


def fresh_material_from_observed_task(exp, origin, role, label, arm):
    """Independent fixture generator; preserves frozen criteria, never supplies a program to the learner.

    Clone only an observed authorized task, retain rule bytes/permissions, change real
    text source bytes consistently within each duplicate class. The isolated oracle
    translates its original byte identities; selectors/compilers never read it.
    """
    td = Path(origin['template_dir'])
    spec = read(td / 'input-template.json')
    work = DATA / exp.name / 'pristine' / label
    shutil.copytree(origin['pristine'], work)
    nonce = uuid4().hex
    for n in spec['workflow_contract']['source_paths']:
        file = work / n
        if file.suffix.lower() in ('.txt', '.md') and file.stat().st_size:
            file.write_bytes(file.read_bytes() + ('\nNEW INDEPENDENT MATERIAL ' + nonce).encode())
    initial = snapshot(work)
    translations = {}
    for n, hsh in spec['initial_snapshot'].items():
        if hsh in translations and translations[hsh] != initial[n]:
            raise ValueError('fixture mutation split an original duplicate class')
        translations[hsh] = initial[n]
    oracle = read(td / 'oracle.json')
    oracle['expected_snapshot'] = {n: translations[hsh] for n, hsh in oracle['expected_snapshot'].items()}
    target = exp / 'templates' / label
    save(target / 'oracle.json', oracle)
    spec.update(task_id=label, role=role, workspace=str(work), initial_snapshot=initial,
                workflow_oracle_file=str(target / 'oracle.json'), workflow_oracle_sha256=sha(target / 'oracle.json'))
    save(target / 'input-template.json', spec)
    shutil.copyfile(td / 'prompt.md', target / 'prompt.md')
    config = read(td / 'scenario.json');config['prompt'] = str(target / 'prompt.md');save(target / 'scenario.json', config)
    t = {**{k: v for k, v in origin.items() if k not in ('arm', 'template_dir', 'profile_id')},
         'task_id': label, 'pair_id': label, 'role': role, 'task_dir': str(target), 'pristine': str(work),
         'input_template_sha256': sha(target / 'input-template.json'), 'oracle_sha256': sha(target / 'oracle.json'),
         'snapshot_sha256': digest(initial), 'prompt_sha256': sha(target / 'prompt.md'), 'scenario_sha256': sha(target / 'scenario.json'),
         'control': {**origin['control'], 'before_sha256': translations[origin['control']['before_sha256']]}}
    return t, arms(exp, t, (arm,))


def material_set(exp, name, role, origins, arm):
    file = exp / (name + '-materials.json')
    if file.exists():
        return read(file)
    templates, tasks = [], []
    for i, origin in enumerate(origins):
        t, rr = fresh_material_from_observed_task(exp, origin, role, name + '-' + str(i), arm)
        templates.append(t)
        tasks.extend(rr)
    value = {'role': role, 'templates': templates, 'tasks': tasks, 'acceptance_source_sha256': sha(ROOT / 'scenarios/file-management/workflow_contract.py'),
             'materials_frozen_before_execution': True, 'holdout_used': False}
    durable(file, value, exclusive=True)
    return value


def learn_candidate(exp, p, round_id, exploration, attempt=1):
    destination = exp / f'upgrade-{round_id}'
    destination.mkdir(exist_ok=True)
    lock = destination / 'candidate-lock.json'
    if lock.exists():
        result = read(lock)
        for rec in result['scripts']:
            if sha(rec['path']) != rec['sha256']:
                raise ValueError('frozen candidate changed')
        return result
    prior_attempt = destination / f'learning-attempt-{attempt}.json'
    if prior_attempt.exists():
        return read(prior_attempt)  # Resume the same retained decision; never overwrite or repay.
    if (exp / (f'certification-{round_id}-materials.json')).exists():
        raise ValueError('cannot learn after independent certification exposure')
    groups, excluded = {}, []
    for case in exploration['tasks']:
        try:
            program, witness, guard = load_witness(case)
            program.pop('profile_id', None)
            groups.setdefault(digest(program), []).append((program, witness, guard))
        except (ValueError, IndexError) as error:
            excluded.append({'task_id': case['task_id'], 'reason': str(error)})
    scripts = []
    for key, values in groups.items():
        if len(values) < 2 or len({v[1]['source_count'] for v in values}) < 2:
            excluded.append({'program': key, 'reason': 'insufficient varied ordinary witnesses'})
            continue
        guards = {digest(v[2]): v[2] for v in values}
        script = {**values[0][0], 'guard_cases': list(guards.values()), 'training': [v[1] for v in values],
                  'runtime_source': {n: sha(ROOT / n) for n in RUNTIME_FILES}}
        script['script_digest'] = digest(script)
        f = destination / ('program-' + key[:16] + '.json')
        durable(f, script, exclusive=True)
        subprocess.run(['node', '--input-type=module', '-e', "import fs from 'node:fs';import {validateScript} from './src/adapters/dsh_learned_script_v2.ts';validateScript(JSON.parse(fs.readFileSync(process.argv[1],'utf8')));", str(f)], cwd=ROOT, check=True, capture_output=True)
        scripts.append({'script_digest': script['script_digest'], 'path': str(f), 'sha256': sha(f)})
    result = {'scripts': scripts, 'excluded': excluded, 'training_roles': ['explore'], 'holdout_used': False, 'certification_used': False,
              'induction': 'existing relational compiler; group actual inferred instructions, never profile_id',
              'compiler_source_sha256': sha(HERE / 'script_adaptation_learning.py')}
    durable(destination / f'learning-attempt-{attempt}.json', result, exclusive=True)
    if not scripts:
        return result
    durable(lock, result, exclusive=True)
    registry = ExperienceRegistry(exp / 'registry')
    entries = []
    for rec in scripts:
        file, raw_sha = registry.object(rec['path'])
        entries.append({'entry_id': rec['script_digest'], 'artifact_digest': rec['script_digest'], 'kind': 'script_v2',
                        'payload': file, 'sha256': raw_sha, 'runtime_source': runtime_source('script_v2', p), 'state': 'candidate', 'activated_generation': round_id + 1})
    manifest = {'schema_version': 1, 'format': 'sss-experience-registry-v1', 'generation': 0, 'parent_digest': None,
                'entries': entries, 'reason': 'isolated independent certification only', 'automatic_selection_uses_profile_id': False}
    manifest['registry_digest'] = digest(manifest)
    durable(destination / 'certification-registry.json', manifest, exclusive=True)
    return result


def certify_candidate(exp, p, round_id, lock, materials):
    directory = exp / f'upgrade-{round_id}'
    certificate = directory / 'certificate.json'
    if certificate.exists():
        return certificate
    manifest = directory / 'certification-registry.json'
    reviews, failures = [], []
    for c in materials['tasks']:
        o = run_task(exp, c, p, manifest)
        spec = read(Path(o['attempt']) / 'input.json')
        fp = digest({'objective': spec['objective'], 'initial_snapshot': spec['initial_snapshot'], 'contract': spec['workflow_contract']})
        chosen = o['experience_selected']
        rec = next((r for r in lock['scripts'] if chosen and r['script_digest'] == chosen[0]['entry_id']), None)
        if not rec or not o['acceptance']['passed'] or not o['receipt_verified'] or o['run']['upstream_requests'] or o['acceptance_repairs'] or not o['script_steps'] or o['experience_deferred']:
            failures.append({'task_id': c['task_id'], 'reason': 'candidate alone did not pass fixed independent acceptance', 'outcome_sha256': sha(Path(o['attempt']) / 'outcome.json')})
            continue
        script = read(rec['path'])
        if fp in {r['task_fingerprint'] for r in script['training']}:
            raise ValueError('independent material reused training decision')
        reviews.append({'role': 'certify', 'task_id': c['task_id'], 'script_digest': rec['script_digest'], 'task_fingerprint': fp,
                        'outcome_file': str(Path(o['attempt']) / 'outcome.json'), 'outcome_sha256': sha(Path(o['attempt']) / 'outcome.json')})
    value = {'status': 'certified_v2' if len(reviews) >= 2 and not failures and len(lock['scripts']) == 1 else 'rejected',
             'scripts': lock['scripts'], 'reviews': reviews, 'failures': failures, 'candidate_lock_sha256': sha(directory / 'candidate-lock.json'),
             'runtime_source': {n: sha(ROOT / n) for n in RUNTIME_FILES}, 'holdout_used': False, 'human_semantic_review': False,
             'acceptance_source_sha256': materials['acceptance_source_sha256']}
    durable(certificate, value, exclusive=True)
    return certificate


def disable_failed(exp, outcomes):
    registry = ExperienceRegistry(exp / 'registry')
    ids = set()
    for o in outcomes:
        ids.update(r['entry_id'] for r in o['experience_deferred'] if r.get('entry_id'))
        if not o['acceptance']['passed']:
            ids.update(r['entry_id'] for r in o['experience_selected'] if r['experience_kind'].startswith('script_'))
    active = {r['entry_id'] for r in registry.load()['entries'] if r['state'] == 'active'}
    ids.intersection_update(active)
    if ids:
        registry.publish(disable=ids, reason='actual candidate guard/delivery failure; ordinary fallback; old version retained')
        state_event(exp, 'experiences_disabled', {'entries': sorted(ids)})


def cycle(exp, p, number, cases):
    completed = exp / f'upgrade-{number}/activation.json'
    if completed.exists():
        return read(completed)
    registry = ExperienceRegistry(exp / 'registry')
    current = exp / 'registry' / read(exp / 'registry/current.json')['file']
    observations = [run_task(exp, c, p, current) for c in cases]
    disable_failed(exp, observations)
    trigger = opportunity(observations)
    state_event(exp, 'opportunity_observed', {'round': number, **trigger})
    if not trigger['worth_learning']:
        raise ValueError('actual stream did not justify exploration; never force an upgrade')
    imported = [r['case'] for r in p.get('imported_pre_certification_evidence', []) if r['kind'] == 'explore'] if number == 1 else []
    if imported:
        exploration = {'tasks': imported}
    else:
        exploration = material_set(exp, f'exploration-{number}', 'explore', cases, 'H')
    for c in exploration['tasks']:
        run_task(exp, c, p)
    lock = learn_candidate(exp, p, number, exploration)
    if not lock['scripts']:
        state_event(exp, 'candidate_rejected', {'round': number, 'reason': 'no supported clean ordinary program', 'excluded': lock['excluded']})
        supplemental = material_set(exp, f'supplemental-exploration-{number}', 'explore', cases, 'H')
        for c in supplemental['tasks']:
            run_task(exp, c, p)
        exploration = {'tasks': exploration['tasks'] + supplemental['tasks']}
        lock = learn_candidate(exp, p, number, exploration, attempt=2)
        if not lock['scripts']:
            state_event(exp, 'candidate_rejected', {'round': number, 'reason': 'bounded additional ordinary exploration still insufficient', 'excluded': lock['excluded']})
            raise ValueError('learning exhausted four new/materially independent tasks; failures retained')
    # New certification materials are generated only after immutable candidate freeze.
    certification = material_set(exp, f'certification-{number}', 'certify', cases, 'C')
    cert = certify_candidate(exp, p, number, lock, certification)
    if read(cert)['status'] != 'certified_v2':
        state_event(exp, 'candidate_rejected', {'round': number, 'certificate_sha256': sha(cert)})
        raise ValueError('failed independent certification; candidate stays inactive')
    entries = [registry.entry('script_v2', r['path'], runtime_source('script_v2', p), cert) for r in lock['scripts']]
    file = registry.publish(entries, reason='autonomous round ' + str(number) + '; frozen independent acceptance passed')
    result = {'round': number, 'registry_file': str(file), 'registry_sha256': sha(file), 'new_entries': [e['entry_id'] for e in entries],
              'trigger': trigger, 'certificate_sha256': sha(cert), 'automatic': True, 'holdout_used': False}
    durable(completed, result, exclusive=True)
    state_event(exp, 'certified_version_activated', result)
    return result


def freeze_holdout(exp, p):
    file = exp / 'final-materials.json'
    if file.exists():
        return read(file)
    if not all((exp / f'upgrade-{n}/activation.json').exists() for n in (1, 2)):
        raise ValueError('two automatic independently certified upgrades required first')
    templates, tasks = [], []
    conditions = [('FM05:min', False, 0, 'old-goal'), ('FM17:all', False, 0, 'old-goal'),
                  ('FM05:max', False, 0, 'new-rule-a'), ('FM05:max', True, 1, 'new-rule-b'),
                  ('FM17:filtered', False, 0, 'new-rule-a'), ('FM17:filtered', True, 1, 'new-rule-b'),
                  ('FM05:max', True, 1, 'new-goal-paraphrase'), ('FM05:max', False, 0, 'V'), ('FM17:filtered', True, 1, 'V')]
    for index, (business, layout, size, label) in enumerate(conditions):
        t, rr = make(exp, 'holdout', business, layout, size, label, ())
        if label == 'new-goal-paraphrase':
            td = Path(t['task_dir'])
            spec = read(td / 'input-template.json')
            spec['objective'] = 'Follow the actual merge rule and current source list to consolidate exact-byte groups into the permitted destination; retain originals and give a verified task result.'
            save(td / 'input-template.json', spec)
            with (td / 'prompt.md').open('a') as stream:
                stream.write('\n当前真实目标覆盖前述目标表述：' + spec['objective'])
            t.update(input_template_sha256=sha(td / 'input-template.json'), prompt_sha256=sha(td / 'prompt.md'))
        templates.append(t)
        order = ('H', 'S', 'F', 'R')
        offset = index % 4
        tasks.extend(arms(exp, t, order[offset:] + order[:offset]))
    current = exp / 'registry' / read(exp / 'registry/current.json')['file']
    value = {'templates': templates, 'tasks': tasks, 'registry_file': str(current), 'registry_sha256': sha(current),
             'seed': read(exp / 'seed-lock.json'), 'learning_from_holdout_permitted': False,
             'frozen_before_final_execution': True, 'final_model_calls_when_frozen': 0}
    durable(file, value, exclusive=True)
    durable(exp / 'final-lock.json', {'sha256': sha(file)}, exclusive=True)
    state_event(exp, 'final_holdout_frozen', {'paired_conditions': len(conditions), 'four_arm_runs': len(tasks), 'learning_disabled': True})
    return value


def summary(exp, p):
    rows = [read(f) for f in exp.glob('tasks/*/attempts/*/outcome.json')]
    rows += [read(r['outcome_file']) for r in p.get('imported_pre_certification_evidence', [])]
    evaluation = [o for o in rows if o['role'] == 'holdout']
    setup = [o for o in rows if o['role'] != 'holdout']
    groups = {}
    for o in evaluation:
        groups.setdefault(o['pair_id'], {})[o['arm']] = o
    common = [g for g in groups.values() if set(g) == set('HSFR') and all(o['acceptance']['passed'] for o in g.values())]
    arms_summary = {}
    initial = p['seed_setup_cost_usd'] + p['motif_setup_cost_usd']
    learning = sum(o['run']['budget_accounted_usd'] for o in setup)
    for arm in 'HSFR':
        rr = [o for o in evaluation if o['arm'] == arm]
        cost = sum(o['run']['budget_accounted_usd'] for o in rr)
        arms_summary[arm] = {'runs': len(rr), 'delivery_passed': sum(o['acceptance']['passed'] for o in rr),
                            'positive_passed': sum(o['acceptance']['passed'] for o in rr if o['condition'] != 'V'),
                            'positive_conditions': sum(o['condition'] != 'V' for o in rr),
                            'version_stops': sum(o['condition'] == 'V' and o['condition_passed'] for o in rr),
                            'requests': sum(o['run']['upstream_requests'] for o in rr), 'execution_cost_usd': cost,
                            'shared_seed_cost_usd': initial if arm in 'FR' else 0,
                            'incremental_improvement_cost_usd': learning if arm == 'R' else 0,
                            'full_api_cost_usd': cost + (initial if arm in 'FR' else 0) + (learning if arm == 'R' else 0),
                            'retrieval_model_requests': 0, 'script_selected_runs': sum(bool(o['script_steps']) for o in rr),
                            'repairs': sum(o['acceptance_repairs'] for o in rr), 'tool_errors': sum(o['tool_errors'] for o in rr)}
    result = {'experiment_id': exp.name, 'attempts': len(rows), 'setup_runs': len(setup), 'setup_cost_usd': learning,
              'all_requests': sum(o['run']['upstream_requests'] for o in rows), 'all_cost_usd': sum(o['run']['budget_accounted_usd'] for o in rows),
              'two_upgrades': [read(exp / f'upgrade-{n}/activation.json') for n in (1, 2) if (exp / f'upgrade-{n}/activation.json').exists()],
              'arms': arms_summary, 'jointly_qualified_pairs': len(common),
              'jointly_qualified_execution': {a: {'requests': sum(g[a]['run']['upstream_requests'] for g in common),
                                                    'cost_usd': sum(g[a]['run']['budget_accounted_usd'] for g in common)} for a in 'HSFR'},
              'source_frozen': True, 'final_holdout_used_for_learning': False, 'human_blind_review': False,
              'actual_bill_verified': False, 'series': accounting(), 'outcomes': rows}
    save(exp / 'summary.json', result)
    return result


def execute(exp, p):
    if not (exp / 'free-sdk-summary.json').exists() or read(exp / 'free-sdk-summary.json')['passed'] != 2:
        raise ValueError('actual free SDK/MCP selection preflight required before paid execution')
    check_frozen(exp, p)
    stream = p['tasks']
    cycle(exp, p, 1, stream[:2])
    registry = exp / 'registry' / read(exp / 'registry/current.json')['file']
    previous = run_task(exp, stream[2], p, registry)
    if not previous['script_steps'] or not previous['acceptance']['passed']:
        raise ValueError('round one experience must actually execute in the next round')
    state_event(exp, 'prior_upgrade_executed_in_next_round', {'outcome_file': str(Path(previous['attempt']) / 'outcome.json'), 'requests': previous['run']['upstream_requests']})
    cycle(exp, p, 2, stream[3:])
    held = freeze_holdout(exp, p)
    if sha(exp / 'final-materials.json') != read(exp / 'final-lock.json')['sha256'] or sha(held['registry_file']) != held['registry_sha256']:
        raise ValueError('frozen final set/library changed')
    # Evaluation never calls opportunity, learn, certify or publish. Both learned arms stay frozen here.
    for c in held['tasks']:
        file = held['seed']['registry_file'] if c['arm'] == 'F' else held['registry_file'] if c['arm'] == 'R' else None
        run_task(exp, c, p, file)
        summary(exp, p)
    state_event(exp, 'complete', {'four_arm_final_runs': len(held['tasks']), 'automatic_upgrades': 2, 'final_holdout_learning': False})
    return summary(exp, p)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--experiment', type=Path)
    parser.add_argument('--call-model', action='store_true')
    parser.add_argument('--summary', action='store_true')
    parser.add_argument('--continuation-from', type=Path)
    args = parser.parse_args()
    if not args.experiment:
        prepare(args.continuation_from)
        return
    exp = args.experiment.resolve()
    p = read(exp / 'protocol.json')
    if args.summary:
        print(json.dumps({k: v for k, v in summary(exp, p).items() if k != 'outcomes'}), flush=True)
        return
    if not args.call_model:
        print(json.dumps({'paid': False, 'batch_cap_usd': p['batch_cap_usd'], 'ordinary_repairs': 2, 'source_frozen': True}))
        return
    lock = ROOT / '.local/file-management/active.lock'
    with lock.open('x') as stream:
        stream.write(exp.name)
    try:
        result = execute(exp, p)
        print(json.dumps({k: v for k, v in result.items() if k != 'outcomes'}), flush=True)
    except BaseException as error:
        state_event(exp, 'stopped_with_failure', {'type': type(error).__name__, 'message': str(error), 'prior_failures_retained': True})
        summary(exp, p)
        raise
    finally:
        lock.unlink()


if __name__ == '__main__':
    main()
