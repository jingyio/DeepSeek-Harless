#!/usr/bin/env python3
"""Audit the frozen raw/compact × ordinary/Motif local-app runs without model calls."""
from __future__ import annotations

import hashlib
import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / '.local/benchmarks/local-app-compaction-v1/PLAN.json'
FIELDS = {
    'numbers': ['request_count', 'total_usd', 'most_expensive_request', 'total_matches', 'total_is_formula'],
    'keynote': ['slide_title', 'claim_usd', 'note_usd', 'consistent', 'source_code'],
    'finder': ['project', 'report_name', 'size_bytes', 'nonempty', 'has_manifest'],
}


def frozen_source(app: str, scope: dict) -> bool:
    path = Path(scope['path'])
    if app == 'finder':
        files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in path.iterdir() if p.is_file()}
        return files == scope['files']
    return hashlib.sha256(path.read_bytes()).hexdigest() == scope['sha256']


def parse_answer(raw: str) -> tuple[dict, bool]:
    text = raw.strip()
    fence = re.fullmatch(r'```(?:json)?\s*(.*?)\s*```', text, re.S)
    candidate = fence.group(1) if fence else text
    try:
        value = json.loads(candidate)
        return (value if isinstance(value, dict) else {}), isinstance(value, dict)
    except json.JSONDecodeError:
        blocks = re.findall(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.S)
        if len(blocks) == 1:
            try:
                value = json.loads(blocks[0])
                if isinstance(value, dict):
                    return value, False
            except json.JSONDecodeError:
                pass
        decoder = json.JSONDecoder()
        candidates = []
        for match in re.finditer(r'\{', text):
            try:
                value, end = decoder.raw_decode(text, match.start())
                if isinstance(value, dict):
                    candidates.append((end, value))
            except json.JSONDecodeError:
                continue
        if candidates:
            return max(candidates, key=lambda row: row[0])[1], False
        return {}, False


def projection_audit(log_path: Path) -> list[dict]:
    match = re.search(r'distil_home=\S+/homes/([0-9a-f]{32})', log_path.read_text())
    if not match:
        raise ValueError('missing private projection run id: ' + str(log_path))
    home = ROOT / '.local/distil-sss/projections' / match.group(1)
    records = []
    for audit_path in (home / 'audit').glob('*.json'):
        row = json.loads(audit_path.read_text())
        original = (home / 'originals' / (audit_path.stem + '.txt')).read_bytes()
        view = (home / 'views' / (audit_path.stem + '.txt')).read_bytes()
        if (hashlib.sha256(original).hexdigest() != row['original_sha256']
                or hashlib.sha256(view).hexdigest() != row['view_sha256']
                or len(original) != row['original_bytes'] or len(view) != row['view_bytes']
                or json.loads(original) != json.loads(view)):
            raise ValueError('compacted tool result changed values: ' + str(audit_path))
        records.append(row)
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, default=PLAN)
    parser.add_argument('--combine-raw-v1', action='store_true')
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    rows = []
    for trial in plan['trials']:
        app, case, arm, compression = (trial[key] for key in ('app', 'case', 'arm', 'compression'))
        run = Path(trial['output'])
        base = ROOT / f'.local/benchmarks/{app}-live-v1'
        scope = json.loads((base / case / 'scope.json').read_text())
        preview = json.loads((run / 'PREVIEW.json').read_text())
        if (not frozen_source(app, scope) or scope != preview['scope']
                or hashlib.sha256((base / case / 'prompt.txt').read_bytes()).hexdigest() != trial['prompt_sha256']
                or preview['reasoning_effort'] != 'off'
                or preview['tool_compaction'] != ('json_compact_v1' if compression == 'compact' else 'off')):
            raise ValueError('frozen input changed: ' + str(run))
        for name, digest in preview['code_sha256'].items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
                raise ValueError('trial code changed: ' + name)
        metrics = json.loads((run / 'metrics.json').read_text())
        if metrics['status'] != 'completed' or metrics['tool_compaction'] != preview['tool_compaction']:
            raise ValueError('incomplete or wrong compression mode: ' + str(run))
        answer, json_only = parse_answer((run / 'answer.txt').read_text())
        expected = json.loads((base / case / 'reference.json').read_text())
        checks = {field: (type(answer.get(field)) is type(expected[field]) and
                          (abs(answer[field] - expected[field]) <= 1e-8 if field == 'total_usd'
                           else answer[field] == expected[field])) for field in FIELDS[app]}
        ledger = [json.loads(line) for line in Path(metrics['budget_ledger']).read_text().splitlines()]
        if sum(entry.get('response_status') == 200 for entry in ledger) != metrics['model_requests']:
            raise ValueError('API request count mismatch: ' + str(run))
        cost = sum(entry.get('observed_peak_usd') or 0 for entry in ledger)
        if cost > plan['per_run_cap_usd'] + 1e-9:
            raise ValueError('trial exceeded its budget: ' + str(run))
        if compression == 'compact':
            audits = projection_audit(args.plan.parent / f'{app}-{case}-{arm}-{compression}.log')
            bytes_removed = sum(row['original_bytes'] - row['view_bytes'] for row in audits)
            if len(audits) != metrics['compacted_results'] or bytes_removed != metrics['tool_bytes_removed']:
                raise ValueError('projection audit mismatch: ' + str(run))
        else:
            audits, bytes_removed = [], 0
        rows.append({'app': app, 'case': case, 'arm': arm, 'compression': compression,
                     'data_pass': all(checks.values()), 'json_only': json_only,
                     'quality_pass': all(checks.values()) and json_only,
                     'checks': checks, 'model_requests': metrics['model_requests'],
                     'verified_skips': metrics['verified_skips'],
                     'compacted_results': len(audits), 'tool_bytes_removed': bytes_removed,
                     'inputTokens': metrics['inputTokens'], 'cacheReadTokens': metrics['cacheReadTokens'],
                     'outputTokens': metrics['outputTokens'], 'elapsed_seconds': metrics['elapsed_seconds'],
                     'cost_usd': cost,
                     'api_failed_attempts': sum(entry.get('response_status', 200) != 200 for entry in ledger)})
    if args.combine_raw_v1:
        prior = json.loads((PLAN.parent / 'EVALUATION.json').read_text())
        raw_rows = [row for row in prior['rows'] if row['compression'] == 'raw']
        if len(raw_rows) != 18 or len(rows) != 18:
            raise ValueError('combined comparison needs 18 audited raw and 18 compact runs')
        rows.extend(raw_rows)
    totals = {}
    for app in FIELDS:
        totals[app] = {}
        for arm in ('baseline', 'motif'):
            for compression in ('raw', 'compact'):
                subset = [row for row in rows if row['app'] == app and row['arm'] == arm
                          and row['compression'] == compression]
                totals[app][arm + '-' + compression] = {key: sum(row[key] for row in subset)
                    for key in ('data_pass', 'quality_pass', 'model_requests', 'verified_skips',
                                'compacted_results', 'tool_bytes_removed', 'inputTokens',
                                'cacheReadTokens', 'outputTokens', 'elapsed_seconds', 'cost_usd',
                                'api_failed_attempts')}
    result = {'date': '2026-09-30', 'task_set': 'nine previously seen local-app cases',
              'cost_kind': 'API-usage-priced estimate, not provider invoice',
              'quality_kind': 'exact answer fields plus JSON-only format',
              'rows': rows, 'totals': totals}
    out = args.plan.parent / 'EVALUATION.json'
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    out.chmod(0o600)
    print(json.dumps(totals, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
