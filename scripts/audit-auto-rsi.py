"""Independent byte/provenance/roles/activation/HTTP audit of the autonomous experiment."""
from __future__ import annotations
import argparse
import json
import sys
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT));sys.path.insert(0, str(ROOT / 'scenarios/file-management'))
import auto_rsi as rsi
from common import sha, digest, snapshot, save, PREFIX
from script_adaptation_learning import load_witness
from src.adapters.file_cost_gate import observed_peak_cost


def audit(exp, partial=False):
    p = rsi.read(exp / 'protocol.json');rsi.check_frozen(exp, p)
    for name, expected in p['source_code'].items():
        assert sha(exp / 'frozen-source' / name) == expected, name
    for name, expected in p['test_sources'].items():
        assert sha(exp / name) == expected, name
    for name, expected in p['original_pdfs'].items():
        assert sha(ROOT / 'testpdf' / name) == expected
    cases = {c['task_id']: c for c in p['tasks']}
    for row in p.get('imported_pre_certification_evidence', []):
        cases[row['case']['task_id']] = row['case']
    for file in exp.glob('*-materials.json'):
        for c in rsi.read(file)['tasks']:
            cases[c['task_id']] = c
    views = []
    previous = None
    for file in sorted((exp / 'registry/versions').glob('*.json')):
        state = rsi.read(file)
        assert state['registry_digest'] == digest({k: v for k, v in state.items() if k != 'registry_digest'})
        assert state['parent_digest'] == previous
        assert state['automatic_selection_uses_profile_id'] is False
        for entry in state['entries']:
            assert sha(exp / 'registry' / entry['payload']) == entry['sha256']
        views.append(state);previous = state['registry_digest']
    assert views[0]['generation'] == 1
    pointer = rsi.read(exp / 'registry/current.json')
    assert sha(exp / 'registry' / pointer['file']) == pointer['sha256']
    seed = rsi.read(exp / 'seed-lock.json')
    assert sha(seed['registry_file']) == seed['registry_sha256']
    assertions = []
    for directory in sorted(exp.glob('upgrade-*')):
        if not (directory / 'candidate-lock.json').exists():
            continue
        lock = rsi.read(directory / 'candidate-lock.json')
        assert not lock['holdout_used'] and not lock['certification_used']
        for rec in lock['scripts']:
            assert sha(rec['path']) == rec['sha256']
            program = rsi.read(rec['path'])
            assert 'profile_id' not in program
            assert program['script_digest'] == digest({k: v for k, v in program.items() if k != 'script_digest'})
            guards = []
            for review in program['training']:
                case = cases[review['task_id']]
                assert case['role'] == 'explore' and case['arm'] == 'H'
                recovered, witness, guard = load_witness(case)
                recovered.pop('profile_id', None)
                assert witness == review
                assert recovered == {k: v for k, v in program.items() if k not in ('script_digest', 'training', 'guard_cases', 'runtime_source')}
                guards.append(guard)
            assert len({r['source_count'] for r in program['training']}) >= 2
            assert {digest(g) for g in guards} == {digest(g) for g in program['guard_cases']}
        if (directory / 'certificate.json').exists():
            cert = rsi.read(directory / 'certificate.json')
            assert cert['candidate_lock_sha256'] == sha(directory / 'candidate-lock.json')
            assert cert['holdout_used'] is False
            for review in cert['reviews']:
                assert review['role'] == 'certify' and sha(review['outcome_file']) == review['outcome_sha256']
                outcome = rsi.read(review['outcome_file'])
                assert outcome['arm'] == 'C' and outcome['role'] == 'certify'
                assert outcome['acceptance']['passed'] and outcome['run']['upstream_requests'] == 0
                assert outcome['script_steps'] > 0 and not outcome['experience_deferred'] and not outcome['acceptance_repairs']
                script = next(rsi.read(rec['path']) for rec in lock['scripts'] if rec['script_digest'] == review['script_digest'])
                assert review['task_fingerprint'] not in {t['task_fingerprint'] for t in script['training']}
        if (directory / 'activation.json').exists():
            activation = rsi.read(directory / 'activation.json')
            assert activation['automatic'] and not activation['holdout_used']
            assert cert['status'] == 'certified_v2' and activation['certificate_sha256'] == sha(directory / 'certificate.json')
            assert sha(activation['registry_file']) == activation['registry_sha256']
            assertions.append(activation)
    held = rsi.read(exp / 'final-materials.json') if (exp / 'final-materials.json').exists() else None
    if held:
        assert sha(exp / 'final-materials.json') == rsi.read(exp / 'final-lock.json')['sha256']
        assert held['learning_from_holdout_permitted'] is False and held['final_model_calls_when_frozen'] == 0
        assert sha(held['registry_file']) == held['registry_sha256']
    rows, paired, usage = [], {}, Counter()
    for c in cases.values():
        files = list(Path(c['task_dir']).glob('attempts/*/outcome.json'))
        if not files and partial:
            continue
        assert len(files) == 1, c['task_id']
        file = files[0];outcome = rsi.read(file);out = file.parent
        spec = rsi.read(out / 'input.json');base = rsi.read(Path(c['template_dir']) / 'input-template.json')
        assert outcome['role'] == c['role'] and outcome['arm'] == c['arm'] and outcome['accounting_complete']
        assert outcome['input_sha256'] == digest(spec) and not outcome['learning_performed']
        assert {k: v for k, v in spec.items() if k != 'workspace'} == {k: v for k, v in base.items() if k != 'workspace'}
        imported = next((r for r in p.get('imported_pre_certification_evidence', []) if r['case']['task_id'] == c['task_id']), None)
        source = rsi.read(Path(imported['experiment']) / 'protocol.json')['source_code'] if imported else p['source_code']
        assert rsi.read(out / 'source-code.json') == source and outcome['source_sha256'] == digest(source)
        events, requests, cost = [], 0, 0
        if c['arm'] == 'S':
            assert outcome['run']['upstream_requests'] == outcome['run']['budget_accounted_usd'] == 0
            events = [json.loads(l) for l in (out / 'mcp-calls.jsonl').read_text().splitlines()]
        else:
            for run in outcome['runs']:
                directory = Path(run['output_dir'])
                data = [json.loads(l) for l in (directory / 'agent-events.jsonl').read_text().splitlines()]
                assert sha(directory / 'agent-events.jsonl') == outcome['events_sha256']
                events.extend(data)
                ledger = [json.loads(l) for l in (directory / 'cost-ledger.jsonl').read_text().splitlines()] if (directory / 'cost-ledger.jsonl').exists() else []
                paid = [r for r in ledger if r.get('kind') != 'budget_denied']
                assert len(paid) == run['upstream_requests']
                observed = 0
                for row in paid:
                    tokens = row.get('response_usage')
                    assert tokens and row.get('observed_peak_usd') is not None, 'unknown costs must be reconciled'
                    actual = observed_peak_cost(row['model'], tokens)
                    assert abs(actual - row['observed_peak_usd']) < 1e-8
                    usage.update(tokens);observed += actual
                assert abs(observed - run['budget_accounted_usd']) < 1e-8
                requests += len(paid);cost += run['budget_accounted_usd']
            assert requests == outcome['run']['upstream_requests'] and abs(cost - outcome['run']['budget_accounted_usd']) < 1e-8
            assert requests <= 96 and cost <= 5
            automatic = [e for e in events if e.get('type') == 'tool/call' and e['data']['callId'].startswith('sss-')]
            if c['arm'] == 'H':
                assert not automatic
            repairing = False
            repairs = 0
            for e in events:
                if e.get('type') == 'user/message' and e['data'].get('source', {}).get('kind') == 'task-acceptance-repair':
                    repairing = True;repairs += 1
                if repairing and e.get('type') == 'tool/call':
                    assert not e['data']['callId'].startswith('sss-')
            assert repairs == outcome['acceptance_repairs'] and repairs <= 2
            if c['arm'] in ('F', 'R', 'C'):
                binding = rsi.read(out / 'experience-binding.json')
                assert not any(k in binding for k in ('profile_id', 'candidate_id', 'script_id', 'workflow_id', 'oracle'))
                assert binding['task_sha256'] == sha(out / 'input.json') and binding['registry_sha256'] == sha(binding['registry_file'])
                if c['role'] == 'holdout':
                    expected = held['seed']['registry_sha256'] if c['arm'] == 'F' else held['registry_sha256']
                    assert binding['registry_sha256'] == expected
        report = rsi.read(out / 'delivery/report.json') if (out / 'delivery/report.json').exists() else None
        review = rsi.h.verify_workflow(spec, report if outcome['receipt_verified'] else None, out / 'delivery', events)
        assert review['passed'] == outcome['acceptance']['passed']
        assert digest(snapshot(spec['workspace'])) == outcome['final_snapshot_sha256']
        for read_file in (out / 'delivery/reads').glob('*.json'):
            observation = rsi.read(read_file)
            assert observation['path'] in spec['workflow_contract']['allowed_reads']
            assert observation['sha256'] == spec['initial_snapshot'][observation['path']]
        if c['condition'] == 'V':
            assert outcome['control_marker'] and not review['passed']
            current = dict(spec['initial_snapshot'])
            for journal_file in (out / 'delivery/journals').glob('*.json'):
                journal = rsi.read(journal_file)
                assert c['workflow_id'] == 'FM17'
                ids = {'file:local:' + digest({'path': n, 'sha': h})[:24]: n for n, h in journal['before'].items()}
                for action in journal['completed']:
                    assert action['op'] == 'copy' and action['destination'].startswith('backup-set/')
                    current[action['destination']] = journal['before'][ids[action['file_ids'][0]]]
            marker = outcome['control_marker'];current[marker['target']] = marker['after_sha256']
            assert current == snapshot(spec['workspace']), 'unknown external bytes were overwritten'
        if c['role'] == 'holdout':
            g = paired.setdefault(c['pair_id'], {'input': digest(base), 'schema': digest(rsi.read(out / 'tool-schemas.json')), 'arms': set()})
            assert g['input'] == digest(base) and g['schema'] == digest(rsi.read(out / 'tool-schemas.json'))
            g['arms'].add(c['arm'])
        rows.append({'task_id': c['task_id'], 'requests': requests, 'cost_usd': cost, 'passed': review['passed']})
    events = sorted((exp / 'controller-events').glob('*.json'))
    prior = None
    for index, file in enumerate(events, 1):
        event = rsi.read(file)
        assert event['sequence'] == index and event['previous_sha256'] == prior
        prior = sha(file)
    if not partial:
        assert len(assertions) == 2 and held and len(paired) == 9
        assert all(g['arms'] == set('HSFR') for g in paired.values())
        prior_result = rsi.read(next(Path(p['tasks'][2]['task_dir']).glob('attempts/*/outcome.json')))
        assert prior_result['acceptance']['passed'] and prior_result['script_steps'] and prior_result['run']['upstream_requests'] == 0
        assert any(r['entry_id'] in assertions[0]['new_entries'] for r in prior_result['experience_selected'])
        final_event = next(i for i, f in enumerate(events) if rsi.read(f)['kind'] == 'final_holdout_frozen')
        assert not any(rsi.read(f)['kind'] in ('opportunity_observed', 'certified_version_activated', 'candidate_rejected') for f in events[final_event + 1:])
    result = {'status': 'passed', 'checks': len(rows), 'requests': sum(r['requests'] for r in rows),
              'cost_usd': round(sum(r['cost_usd'] for r in rows), 9), 'usage': dict(usage),
              'automatic_upgrades': len(assertions), 'profile_hint_absent': True, 'final_holdout_not_learned': True,
              'only_clean_ordinary_training': True, 'original_limits_unchanged': True, 'rows': rows}
    save(exp / ('partial-audit.json' if partial else 'independent-audit.json'), result)
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser();parser.add_argument('--experiment', type=Path, required=True);parser.add_argument('--partial', action='store_true')
    args = parser.parse_args();audit(args.experiment.resolve(), args.partial)
