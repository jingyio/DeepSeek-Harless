"""Collect an explicit review of the original Web delivery without model calls."""
from __future__ import annotations

import json
import math
import re
import subprocess
import sys
from pathlib import Path

from .documents import file_hash
from .feedback_learning import FeedbackStore
from .service import ROOT, private_path
from .trial import GROUPS, feedback_record, read_json, save_new


def collect_review(request: dict) -> dict:
    required = {'trial', 'trial_sha256', 'request_id', 'pptx_sha256',
                'quality', 'revision_minutes', 'learning_consent', 'feedback'}
    if not isinstance(request, dict) or set(request) != required:
        raise ValueError('Invalid review fields')
    if not isinstance(request['request_id'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,80}', request['request_id']):
        raise ValueError('Invalid review request ID')
    for key in ('trial_sha256', 'pptx_sha256'):
        if not isinstance(request[key], str) or not re.fullmatch(r'[0-9a-f]{64}', request[key]):
            raise ValueError('Invalid review version')
    quality = request['quality']
    if (not isinstance(quality, dict) or set(quality) !=
            {'scientific_facts', 'figures_and_citations', 'usable_presentation'}
            or any(type(value) is not bool for value in quality.values())):
        raise ValueError('The three review judgments must be explicit booleans')
    minutes = request['revision_minutes']
    if type(minutes) not in (int, float) or not math.isfinite(minutes) or not 0 <= minutes <= 10000:
        raise ValueError('Invalid revision time')
    if type(request['learning_consent']) is not bool:
        raise ValueError('Learning consent must be explicit')
    if not isinstance(request['feedback'], str) or len(request['feedback']) > 1000:
        raise ValueError('Invalid review text')

    path = private_path(Path(request['trial'])).resolve(strict=True)
    if path.name != 'trial.json' or file_hash(path) != request['trial_sha256']:
        raise ValueError('Trial version changed')
    data = read_json(path)
    comparison_path = path.parent / 'comparison.json'
    if comparison_path.exists() and read_json(comparison_path).get('trial_sha256') != request['trial_sha256']:
        raise ValueError('Comparison is not bound to this trial')
    result_path = path.parent / 'optimized-result.json'
    optimized = read_json(result_path)
    if not optimized.get('mechanical_delivery_verified') or optimized.get('strategy_adherence') is False:
        raise ValueError('The optimized deck did not pass delivery checks')
    pptx_files = [item for delivery in optimized.get('deliveries', [])
                  for item in delivery.get('files', []) if item.get('kind') == 'pptx']
    if not any(item.get('sha256') == request['pptx_sha256']
               and file_hash(private_path(Path(item['path'])).resolve(strict=True)) == request['pptx_sha256']
               for item in pptx_files):
        raise ValueError('The reviewed deck version changed')

    area = path.parent / 'rsi-reviews'
    area.mkdir(mode=0o700, exist_ok=True)
    review_path = area / (request['request_id'] + '.json')
    if review_path.exists():
        if read_json(review_path) != request:
            raise ValueError('Review request ID was reused with different content')
    else:
        save_new(review_path, request)
    review_sha = file_hash(review_path)
    receipt_path = area / (request['request_id'] + '-receipt.json')
    if receipt_path.exists():
        receipt = read_json(receipt_path)
        if receipt.get('review_sha256') != review_sha:
            raise ValueError('Review receipt changed')
        return receipt

    store = FeedbackStore(Path(data['feedback_store']))
    stored = {}
    for group in GROUPS:
        result_path = path.parent / (group + '-result.json')
        evidence = path.parent / (group + '-delivery-receipts.json')
        if group != 'optimized' and (not result_path.is_file() or not evidence.is_file()):
            continue
        result = read_json(result_path)
        proposed = feedback_record(data, group, result, evidence)
        previous = next((row for row in store._records() if row['run_id'] == proposed['run_id']), None)
        row = {key: value for key, value in previous.items()
               if key not in ('record_id', 'created_at', 'revision', 'supersedes', 'evidence_lock')} if previous else proposed
        row['consent'] = {'collect': True, 'learn': request['learning_consent']}
        row['review_evidence'] = {'path': str(review_path), 'sha256': review_sha}
        if request['learning_consent'] and row.get('run_dir'):
            frozen = subprocess.run(
                [sys.executable, str(ROOT / 'scripts/freeze-dsh-task-identity.py'),
                 '--task-dir', row['run_dir'], '--decision-id', row['task_identity'],
                 '--events', 'agent-events.jsonl'], cwd=ROOT, capture_output=True,
                text=True, timeout=30)
            row['identity_confirmed'] = frozen.returncode == 0
        if group == 'optimized':
            row['quality'] = {'delivery': 'passed',
                              'scientific': 'passed' if quality['scientific_facts'] and quality['figures_and_citations'] else 'failed',
                              'visual': 'passed' if quality['usable_presentation'] else 'failed',
                              'reviewer': 'user', 'revision_minutes': minutes}
            row['feedback'] = request['feedback']
        existing = next((item for item in store._records()
                         if item['run_id'] == row['run_id']
                         and item.get('review_evidence', {}).get('sha256') == review_sha), None)
        stored[group] = ({'record_id': existing['record_id'], 'revision': existing['revision']}
                         if existing else store.collect(row))

    receipt = {'review_sha256': review_sha, 'reviewed_pptx_sha256': request['pptx_sha256'],
               'learning_consent': request['learning_consent'], 'records': stored,
               'learning_started': False, 'candidate_activated': False}
    save_new(receipt_path, receipt)
    return receipt


def invalidate_revised_review(request: dict) -> dict:
    if not isinstance(request, dict) or set(request) != {
            'action', 'trial', 'review_request_id', 'result_path', 'result_sha256'} \
            or request['action'] != 'revision':
        raise ValueError('Invalid revision evidence fields')
    if (not isinstance(request['review_request_id'], str)
            or not re.fullmatch(r'[A-Za-z0-9_-]{8,80}', request['review_request_id'])
            or not isinstance(request['result_sha256'], str)
            or not re.fullmatch(r'[0-9a-f]{64}', request['result_sha256'])):
        raise ValueError('Invalid revision evidence ID or digest')
    trial = private_path(Path(request['trial'])).resolve(strict=True)
    if trial.name != 'trial.json':
        raise ValueError('Invalid trial path')
    review_path = trial.parent / 'rsi-reviews' / (request['review_request_id'] + '.json')
    if not review_path.is_file():
        return {'status': 'no_original_review'}
    review = read_json(review_path)
    if review.get('trial') != str(trial) or review.get('trial_sha256') != file_hash(trial):
        raise ValueError('Original review is not bound to this trial')
    result_path = private_path(Path(request['result_path'])).resolve(strict=True)
    if result_path.name != 'result.json' or file_hash(result_path) != request['result_sha256']:
        raise ValueError('Revision result changed')
    result = read_json(result_path)
    original = read_json(trial.parent / 'optimized-result.json')
    original_decks = {item.get('deck_id') for item in original.get('deliveries', [])}
    if result.get('status') != 'delivered' or result.get('parent_deck_id') not in original_decks:
        return {'status': 'no_delivered_revision'}
    changed = [item for delivery in result.get('deliveries', [])
               for item in delivery.get('files', []) if item.get('kind') == 'pptx'
               and item.get('sha256') != review.get('pptx_sha256')]
    if not changed or not any(file_hash(private_path(Path(item['path'])).resolve(strict=True)) == item['sha256']
                              for item in changed):
        return {'status': 'no_delivered_revision'}
    store = FeedbackStore(Path(read_json(trial)['feedback_store']))
    previous = next((row for row in store._records() if row['pair_id'] == trial.parent.name
                     and row['group'] == 'optimized'
                     and row.get('review_evidence', {}).get('sha256') == file_hash(review_path)), None)
    if previous is None:
        return {'status': 'no_original_feedback'}
    if previous.get('post_review_revision', {}).get('sha256') == request['result_sha256']:
        return {'status': 'already_invalidated'}
    if previous.get('post_review_revision'):
        return {'status': 'already_invalidated'}
    row = {key: value for key, value in previous.items()
           if key not in ('record_id', 'created_at', 'revision', 'supersedes', 'evidence_lock')}
    row['quality'] = {**row['quality'], 'revision_minutes': None}
    row['post_review_revision'] = {'path': str(result_path), 'sha256': request['result_sha256']}
    receipt = store.collect(row)
    return {'status': 'invalidated', 'record_id': receipt['record_id']}


def main() -> None:
    raw = sys.stdin.buffer.read(32769)
    if len(raw) > 32768:
        raise ValueError('Review request too large')
    request = json.loads(raw)
    result = invalidate_revised_review(request) if request.get('action') == 'revision' else collect_review(request)
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
