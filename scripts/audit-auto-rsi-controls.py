"""Independent operational stream pairing, final quality and complete cost recomputation."""
import argparse
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT));sys.path.insert(0, str(ROOT / 'scenarios/file-management'))
import auto_rsi as rsi
from common import sha, digest, snapshot, save
from src.adapters.deepseek_cost_gate import observed_peak_cost


def audit(parent, controls):
    p = rsi.read(parent / 'protocol.json');cp = rsi.read(controls / 'protocol.json')
    rsi.check_frozen(parent, p);rsi.check_frozen(controls, cp)
    assert cp['learning_permitted'] is False and cp['parent_protocol_sha256'] == sha(parent / 'protocol.json')
    assert not list(controls.glob('upgrade-*')) and not list(controls.glob('*-materials.json'))
    ledger_cost = 0;requests = 0;rows = [];paired = {}
    original = [rsi.read(next(Path(c['task_dir']).glob('attempts/*/outcome.json'))) for c in p['tasks']]
    for c in cp['tasks']:
        out_file = next(Path(c['task_dir']).glob('attempts/*/outcome.json'))
        o = rsi.read(out_file);out = out_file.parent;spec = rsi.read(out / 'input.json')
        assert o['role'] == 'observe' and o['arm'] in 'HSF' and o['accounting_complete']
        assert o['input_sha256'] == digest(spec) and o['source_sha256'] == digest(cp['source_code'])
        assert rsi.read(out / 'source-code.json') == cp['source_code']
        base = rsi.read(Path(c['template_dir']) / 'input-template.json')
        assert {k: v for k, v in spec.items() if k != 'workspace'} == {k: v for k, v in base.items() if k != 'workspace'}
        group = paired.setdefault(c['pair_id'], {'input': digest(base), 'schema': digest(rsi.read(out / 'tool-schemas.json')), 'arms': {}})
        assert group['input'] == digest(base) and group['schema'] == digest(rsi.read(out / 'tool-schemas.json'))
        group['arms'][c['arm']] = o
        events, paid_cost, paid_requests = [], 0, 0
        if c['arm'] == 'S':
            events = [json.loads(l) for l in (out / 'mcp-calls.jsonl').read_text().splitlines()]
            assert o['run']['budget_accounted_usd'] == o['run']['upstream_requests'] == 0
        else:
            for run in o['runs']:
                directory = Path(run['output_dir'])
                assert sha(directory / 'agent-events.jsonl') == o['events_sha256']
                events.extend(json.loads(l) for l in (directory / 'agent-events.jsonl').read_text().splitlines())
                ledger = [json.loads(l) for l in (directory / 'cost-ledger.jsonl').read_text().splitlines()] if (directory / 'cost-ledger.jsonl').exists() else []
                paid = [r for r in ledger if r.get('kind') != 'budget_denied']
                assert len(paid) == run['upstream_requests']
                amount = 0
                for row in paid:
                    assert row.get('response_usage') and row.get('observed_peak_usd') is not None
                    cost = observed_peak_cost(row['model'], row['response_usage'])
                    assert abs(cost - row['observed_peak_usd']) < 1e-8
                    amount += cost
                assert abs(amount - run['budget_accounted_usd']) < 1e-8
                paid_requests += len(paid);paid_cost += amount
            assert paid_requests <= 96 and paid_cost <= 5 and o['acceptance_repairs'] <= 2
            repairing = False
            for e in events:
                if e.get('type') == 'user/message' and e['data'].get('source', {}).get('kind') == 'task-acceptance-repair':repairing = True
                if e.get('type') == 'tool/call' and (c['arm'] == 'H' or repairing):assert not e['data']['callId'].startswith('sss-')
            if c['arm'] == 'F':
                binding = rsi.read(out / 'experience-binding.json')
                assert binding['registry_sha256'] == rsi.read(parent / 'seed-lock.json')['registry_sha256']
        report = rsi.read(out / 'delivery/report.json') if (out / 'delivery/report.json').exists() else None
        review = rsi.h.verify_workflow(spec, report if o['receipt_verified'] else None, out / 'delivery', events)
        assert review['passed'] == o['acceptance']['passed'] and digest(snapshot(spec['workspace'])) == o['final_snapshot_sha256']
        assert abs(paid_cost - o['run']['budget_accounted_usd']) < 1e-8 and paid_requests == o['run']['upstream_requests']
        requests += paid_requests;ledger_cost += paid_cost;rows.append({'task_id': c['task_id'], 'passed': review['passed']})
    for c, outcome in zip(p['tasks'], original):
        g = paired[c['pair_id']];out = Path(outcome['attempt'])
        assert g['schema'] == digest(rsi.read(out / 'tool-schemas.json'))
        base = rsi.read(Path(c['template_dir']) / 'input-template.json')
        assert g['input'] == digest(base);g['arms']['R'] = outcome
    assert len(paired) == 5 and all(set(g['arms']) == set('HSFR') for g in paired.values())
    full = rsi.read(parent / 'complete-cost-comparison.json')
    initial = p['seed_setup_cost_usd'] + p['motif_setup_cost_usd']
    all_original = rsi.read(parent / 'summary.json')['outcomes']
    for arm in 'HSFR':
        normal = [g['arms'][arm] for g in paired.values()]
        final = [o for o in all_original if o['role'] == 'holdout' and o['arm'] == arm]
        extra = [o for o in all_original if o['role'] in ('explore', 'certify')] if arm == 'R' else []
        expected = sum(o['run']['budget_accounted_usd'] for o in normal + final + extra) + (initial if arm in 'FR' else 0)
        assert abs(full['arms'][arm]['full_api_cost_usd'] - expected) < 1e-8
    result = {'status': 'passed', 'paired_stream_conditions': len(paired), 'controls_runs': len(rows),
              'requests': requests, 'cost_usd': ledger_cost, 'full_cost_recomputed': True,
              'same_frozen_operational_tasks': True, 'final_holdout_not_learned': True, 'rows': rows}
    save(controls / 'independent-audit.json', result)
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser();parser.add_argument('--parent', type=Path, required=True);parser.add_argument('--controls', type=Path, required=True)
    args = parser.parse_args();audit(args.parent.resolve(), args.controls.resolve())
