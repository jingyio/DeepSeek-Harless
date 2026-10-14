"""Bounded, no-model orchestration for user-reviewed read-only PPT motifs."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from itertools import combinations
import json
import os
from pathlib import Path
import time

from .feedback_learning import (DEFAULT_STORE, FeedbackStore, _compatibility,
                                _digest, _private)
from .service import ROOT


@contextmanager
def _tick_lock(store: FeedbackStore):
    store.path.mkdir(parents=True, exist_ok=True)
    path = store.path / '.auto-tick-lock'
    if os.name == 'posix':
        import fcntl
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
                return
            yield True
        finally:
            os.close(fd)
        return
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        yield False
        return
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump({'pid': os.getpid()}, stream)
        yield True
    finally:
        path.unlink(missing_ok=True)


def _auto_candidates(store: FeedbackStore) -> list[dict]:
    return [row for row in store.status()['candidates']
            if row['valid'] and row['learning_scope'] == 'auto_structural']


def _has_usable_active(store: FeedbackStore) -> bool:
    if store.status()['active_version'] is None:
        return False
    try:
        return store.active_manifest() is not None
    except (OSError, ValueError):
        return False


def _failed_candidate(store: FeedbackStore, version: str) -> bool:
    records = store._records()
    reviewed_pairs = []
    for row in records:
        if row.get('candidate_version') != version or row['group'] != 'optimized':
            continue
        if any(row['quality'][key] == 'failed' for key in ('delivery', 'scientific', 'visual')):
            return True
        if row['quality']['reviewer'] == 'user':
            baseline = next((base for base in records if base['pair_id'] == row['pair_id']
                             and base['group'] == 'baseline'), None)
            if (baseline is None or row['quality']['revision_minutes'] != 0
                    or any(row['cost'][key] is None or baseline['cost'][key] is None
                           or row['cost'][key] > baseline['cost'][key]
                           for key in ('requests', 'proxy_usd'))):
                return True
            try:
                store._candidate_execution(row, store._candidate(version))
            except (OSError, ValueError, KeyError, TypeError):
                return True
            reviewed_pairs.append((baseline, row))
    if len(reviewed_pairs) >= 2 and any(
            sum(opt['cost'][key] for _, opt in reviewed_pairs) >=
            sum(base['cost'][key] for base, _ in reviewed_pairs)
            for key in ('requests', 'proxy_usd')):
        return True
    trials = ROOT / '.local/research-ppt/trials'
    attempts = 0
    for path in trials.glob('trial-*/trial.json'):
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            if data.get('candidate_evaluation') is not True or not isinstance(data.get('active_learning'), dict):
                continue
            if data['active_learning'].get('version') != version or data.get('rsi_enabled') is not True:
                continue
            if not (path.parent / 'execution-started.json').is_file():
                continue
            attempts += 1
            result = path.parent / 'optimized-result.json'
            if result.is_file():
                delivered = json.loads(result.read_text(encoding='utf-8'))
                if delivered.get('mechanical_delivery_verified') is not True:
                    return True
        except (OSError, ValueError, AttributeError):
            continue
    return attempts >= 6 and len(reviewed_pairs) < 2


def _canary_progress(store: FeedbackStore, version: str) -> tuple[list[str], int]:
    reviewed = {row['pair_id']: row for row in store._records()
                if row['group'] == 'optimized' and row.get('candidate_version') == version
                and row['quality']['reviewer'] == 'user'}
    verified = []
    pending = 0
    for path in (ROOT / '.local/research-ppt/trials').glob('trial-*/trial.json'):
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            if (data.get('candidate_evaluation') is not True or data.get('rsi_enabled') is not True
                    or data.get('active_learning', {}).get('version') != version):
                continue
            if not (path.parent / 'execution-started.json').is_file():
                continue
            row = reviewed.get(data['trial_id'])
            if row is not None:
                metrics = json.loads((Path(row['run_dir']) / 'metrics.json').read_text(encoding='utf-8'))
                if metrics.get('model_requests_skipped_verified', 0) > 0:
                    verified.append(row['pair_id'])
            elif time.time() - path.stat().st_mtime < 86400:
                pending += 1
        except (OSError, ValueError, AttributeError, TypeError, KeyError):
            continue
    return verified, pending


def candidate_for_next_trial(store: FeedbackStore | None = None) -> str | None:
    store = store or FeedbackStore()
    if _has_usable_active(store):
        return None
    for row in reversed(_auto_candidates(store)):
        version = row['version']
        if _failed_candidate(store, version):
            continue
        try:
            store.candidate_manifest(version)
        except (OSError, ValueError):
            continue
        verified, pending = _canary_progress(store, version)
        if len(verified) + pending < 2:
            return version
    return None


def _learning_record_groups(store: FeedbackStore) -> list[list[dict]]:
    groups: dict[str, list[dict]] = {}
    for row in store._records():
        if not store._eligibility(row, auto_structural=True)[0]:
            continue
        try:
            store._auto_training_pair(row)
            key = _digest(_compatibility(row))
        except (OSError, ValueError, KeyError, TypeError):
            continue
        groups.setdefault(key, []).append(row)
    return [rows for rows in groups.values() if len(rows) >= 3]


def _learn_once(store: FeedbackStore) -> dict:
    if any(not _failed_candidate(store, row['version']) for row in _auto_candidates(store)) \
            or _has_usable_active(store):
        return {'stage': 'candidate_or_active_exists'}
    groups = _learning_record_groups(store)
    if not groups:
        return {'stage': 'waiting_for_three_independent_user_approved_tasks'}
    tried = set()
    for path in (store.path / 'plans').glob('*.json'):
        try:
            plan = json.loads(path.read_text(encoding='utf-8'))
            if plan.get('learning_scope') == 'auto_structural':
                tried.add(tuple(item['id'] for item in plan['records']))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    failures = []
    for rows in groups:
        for selected in combinations(reversed(rows[-8:]), 3):
            chosen = list(reversed(selected))
            if len({store._auto_task_key(row) for row in chosen}) != 3:
                continue
            ids = tuple(row['record_id'] for row in chosen)
            if ids in tried:
                continue
            try:
                schema = _private(ROOT / '.local/research-ppt/trials' / chosen[0]['pair_id'] / 'baseline-schema.json',
                                  exists=True)
                plan = store.preview(ids[:2], [ids[2]],
                                     contracts=ROOT / 'scenarios/research_ppt/contracts.json',
                                     version_fields=ROOT / 'scenarios/research_ppt/version-fields.json',
                                     tool_schema=schema, mining='witnessed_edges', auto_structural=True)
                candidate = store.learn(Path(plan['plan_path']), confirm=True)
                return {'stage': 'candidate_certified', 'version': candidate['version'],
                        'learning_cost': candidate['learning_cost']}
            except (OSError, ValueError) as exc:
                failures.append(type(exc).__name__)
    return {'stage': 'no_certified_candidate', 'attempted_splits': len(failures),
            'failure_types': sorted(set(failures))}


def _promote_once(store: FeedbackStore) -> dict:
    if _has_usable_active(store):
        return {'stage': 'active_exists'}
    for candidate in reversed(_auto_candidates(store)):
        version = candidate['version']
        if _failed_candidate(store, version):
            continue
        pairs, _ = _canary_progress(store, version)
        if len(pairs) < 2:
            continue
        for selected in combinations(pairs, 2):
            try:
                preview = store.activate_auto(version, list(selected), confirm=False)
                release = store.activate_auto(version, list(selected), confirm=True)
            except (OSError, ValueError):
                continue
            return {'stage': 'active', 'version': version,
                    'baseline_requests': preview['gate']['baseline_requests'],
                    'optimized_requests': preview['gate']['optimized_requests'],
                    'baseline_proxy_usd': preview['gate']['baseline_proxy_usd'],
                    'optimized_proxy_usd': preview['gate']['optimized_proxy_usd'],
                    'release_sequence': release['sequence']}
        return {'stage': 'candidate_not_promoted', 'reason': 'no_pair_passed_release_gate'}
    return {'stage': 'waiting_for_two_user_approved_canaries'}


def tick(store: FeedbackStore | None = None) -> dict:
    store = store or FeedbackStore(DEFAULT_STORE)
    with _tick_lock(store) as acquired:
        if not acquired:
            return {'stage': 'another_tick_running', 'model_requests': 0}
        promotion = _promote_once(store)
        if promotion['stage'] == 'active':
            return {**promotion, 'model_requests': 0}
        learning = _learn_once(store)
        return {'promotion': promotion, 'learning': learning, 'model_requests': 0}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store', type=Path, default=DEFAULT_STORE)
    args = parser.parse_args()
    print(json.dumps(tick(FeedbackStore(args.store)), ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
