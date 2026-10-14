"""Conservative original-event call classification; output stays private."""
import argparse
import json
from pathlib import Path
from uuid import uuid4
from pdf_tools import ROOT, digest, save_private

MECHANICAL = {'list_pdfs', 'read_update_plan', 'prepare_pdf', 'read_claim_repair_packet'}


def classify(blocks):
    names = [b.get('name', '').split('__')[-1] for b in blocks if b.get('type') == 'tool-call']
    if not names:
        return 'final_reporting_or_semantic_text', 'Cannot assume final text is removable.'
    if all(n in MECHANICAL for n in names):
        return 'mechanical_candidate', 'Still requires frozen-target/source provenance before execution.'
    if any(n in MECHANICAL for n in names):
        return 'mixed', 'Do not bypass a whole request from tool-name frequency.'
    return 'semantic_or_approved_plan_required', 'Includes window/query selection, scientific verdicts or final synthesis.'


def analyze(phase_one, output):
    audit = json.loads((phase_one / 'final-audit.json').read_text())
    progress = json.loads((phase_one / 'progress.json').read_text())
    labels = {r['job_id']: r['label'] for r in progress['records']}
    run_labels = {}
    for job_id, label in labels.items():
        job = json.loads((ROOT / '.local/literature-notes/agent-jobs' / job_id / 'job.json').read_text())
        for s in job['stages']:
            for r in s.get('summaries', []):
                if r.get('output_dir'): run_labels[r['output_dir']] = (label, s['stage'])
    rows = []
    for directory, meta in audit['native_runs'].items():
        path = Path(directory) / 'agent-events.jsonl'
        events = [json.loads(l) for l in path.read_text().splitlines()]
        for e in events:
            m = e.get('data', {}).get('message', {})
            if e.get('type') != 'assistant/message' or m.get('source', {}).get('kind') != 'model': continue
            blocks = m.get('content', []); category, reason = classify(blocks)
            calls = [b for b in blocks if b.get('type') == 'tool-call']
            runtime = any(b.get('id', '').startswith('sss-') for b in calls)
            rows.append({'run': str(Path(directory)), 'origin_seq': e['seq'], 'events_sha256': meta['events_sha256'],
                'workflow': run_labels.get(directory, ('independent_correction', 'correction')),
                'category': 'runtime_generated' if runtime else category, 'reason': reason,
                'tool_names': [b['name'] for b in calls], 'tool_argument_chars': sum(len(b.get('arguments', '')) for b in calls),
                'visible_text_chars': sum(len(b.get('text', '')) for b in blocks if b.get('type') == 'text'),
                'provider_usage': e['data'].get('usage'), 'rationale_inferred': False,
                'candidate_only': True, 'approved_for_bypass': False})
    counts = {k: sum(r['category'] == k for r in rows) for k in sorted({r['category'] for r in rows})}
    save_private(output / 'call-classification.json', {'original_events_only': True, 'rows': rows, 'counts': counts,
        'limitations': 'Conservative tool-role labels are not scientific entailment or executable policy.'})
    candidates = [
        {'id': 'entry-target-packets', 'state': 'selected', 'structure': 'frozen task target list -> read each claim packet -> semantic handoff',
         'new_vs_previous': 'task-entry dynamic target frontier; not pin/read or extract/verify/build'},
        {'id': 'inventory-prepare-all', 'state': 'deferred', 'structure': 'current selected inventory -> prepare every required paper',
         'reason': 'Needs explicit all-paper frontier and nested result-object bindings.'},
        {'id': 'synthesis-input-ready', 'state': 'deferred', 'structure': 'verified current table -> read synthesis packet before model',
         'reason': 'Aggregate-source result lacks per-target document version contract.'},
        {'id': 'pending-claim-dispatch', 'state': 'mixed_not_executable', 'structure': 'accepted/pending results -> remaining claim work',
         'reason': 'Pending often requires semantic correction; targets may already have been read.'},
        {'id': 'receipt-final-report', 'state': 'deferred', 'structure': 'actual successful final receipt -> bounded delivery message',
         'reason': 'Requires separate stop/output contract; cannot assume every final model message is mechanical.'}]
    save_private(output / 'candidates.json', candidates)
    return {'output': str(output), 'provider_messages': len(rows), 'categories': counts, 'candidate_count': len(candidates)}


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--phase-one', type=Path, required=True); p.add_argument('--output', type=Path)
    a = p.parse_args(); out = (a.output or ROOT / '.local/literature-notes' / ('multitask-motif-20261012-' + uuid4().hex[:8])).resolve()
    if not out.is_relative_to(ROOT / '.local') or out.exists(): raise ValueError('use a new private experiment directory')
    out.mkdir(mode=0o700, parents=True)
    print(json.dumps(analyze(a.phase_one.resolve(), out), ensure_ascii=False))
