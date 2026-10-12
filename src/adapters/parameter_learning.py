"""Append-only learning rounds for native parameter probes, not product certification."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
from uuid import uuid4

from .native_motif_compiler import digest, root_events
from .parameter_motif_compiler import compile_parameter_runs


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path = Path(path)
    with path.open('x', encoding='utf-8') as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write('\n')
    path.chmod(0o600)


def trace_identity(run):
    run = Path(run).resolve()
    manifest = json.loads((run / 'manifest.json').read_text())
    metrics = json.loads((run / 'metrics.json').read_text())
    if manifest.get('mode') not in {'baseline', 'shadow'} or metrics.get('status') != 'completed':
        raise ValueError('learning requires completed native baseline/shadow, not execute')
    if metrics.get('verified_skips', 0) or metrics.get('unverified_bypasses', 0):
        raise ValueError('synthetic execution cannot certify itself')
    if any(event['type'] == 'tool/call' and str(event['data'].get('callId', '')).startswith('sss-')
           for event in root_events(run)):
        raise ValueError('synthetic tool provenance in training')
    names = ['manifest.json', 'metrics.json', 'session-events.jsonl']
    if (run / 'file-versions.jsonl').exists(): names.append('file-versions.jsonl')
    if (run / 'library-snapshot.json').exists(): names.append('library-snapshot.json')
    return {'path': str(run), 'session_id': manifest['session_id'],
            'input_sha256': manifest.get('input_sha256', manifest.get('input_source_sha256')), 'model': manifest.get('model'),
            'provider': manifest.get('provider'), 'mode': manifest['mode'],
            'files': {name: sha(run / name) for name in names}}


def checked_round(path):
    path = Path(path)
    record = json.loads((path / 'round.json').read_text())
    body = {k: v for k, v in record.items() if k != 'round_digest'}
    library = json.loads((path / 'library.json').read_text())
    unsigned = {k: v for k, v in library.items() if k != 'manifest_digest'}
    if (record.get('schema_version') != 1 or type(record.get('round_index')) is not int or record['round_index'] < 1
            or path.name != f"round-{record['round_index']:04d}"
            or library.get('certification_scope') != 'parameterized_continuation_probe'
            or digest(body) != record.get('round_digest') or digest(unsigned) != library.get('manifest_digest')
            or sha(path / 'library.json') != record.get('library_sha256')
            or library['manifest_digest'] != record['library_digest']):
        raise ValueError('learning round/library changed')
    return record, library


def latest_round(store):
    store = Path(store).resolve()
    pointer = json.loads((store / 'latest.json').read_text())
    name = pointer['round']
    if Path(name).name != name or not name.startswith('round-'):
        raise ValueError('invalid learning pointer')
    path = (store / name).resolve()
    if path.parent != store: raise ValueError('learning round escapes store')
    record, library = checked_round(path)
    if record['round_digest'] != pointer['round_digest']:
        raise ValueError('learning pointer is stale')
    # Verify every recorded parent; a current version cannot hide altered history.
    current = record
    while current.get('parent_round'):
        parent_name = current['parent_round']
        if Path(parent_name).name != parent_name or (store / parent_name).resolve().parent != store:
            raise ValueError('invalid parent path')
        parent, _ = checked_round(store / parent_name)
        if parent['round_digest'] != current['parent_round_digest'] or parent['round_index'] != current['round_index'] - 1:
            raise ValueError('learning parent chain changed')
        current = parent
    if current['round_index'] != 1: raise ValueError('learning chain lacks initial round')
    return path, record, library


@contextmanager
def locked(store):
    store = Path(store).resolve(); store.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (store / '.lock').open('a') as file:
        fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield store


def advance_round(store, new_training_runs, validation_runs=None):
    """Append evidence, compile, publish one immutable probe version under a lock."""
    if not new_training_runs: raise ValueError('new normal training trace required')
    with locked(store) as store:
        previous_path, previous, previous_library = latest_round(store) if (store / 'latest.json').exists() else (None, None, None)
        old = previous['training'] if previous else []
        reserved = previous.get('reserved_validation', previous['validation']) if previous else []
        for row in old:
            if trace_identity(row['path']) != row: raise ValueError('past training evidence changed')
        for row in reserved:
            if trace_identity(row['path']) != row: raise ValueError('past validation evidence changed')
        fresh = [trace_identity(run) for run in new_training_runs]
        validation = ([trace_identity(run) for run in validation_runs] if validation_runs is not None
                      else (previous['validation'] if previous else []))
        if any(row['session_id'] in {r['session_id'] for r in reserved} for row in fresh):
            raise ValueError('reserved validation cannot later become training')
        training = old + fresh
        all_rows = training + validation
        if len({row['path'] for row in all_rows}) != len(all_rows) or len({row['session_id'] for row in all_rows}) != len(all_rows):
            raise ValueError('duplicate or overlapping training/validation session')
        # Validation is not a selector: only training witnesses create a prototype.
        library = compile_parameter_runs([(Path(r['path']), 'training') for r in training]
                                         + [(Path(r['path']), 'heldout') for r in validation],
                                         source_experiment=store.name)
        for row in all_rows:
            if trace_identity(row['path']) != row: raise ValueError('evidence changed during compilation')
        index = previous['round_index'] + 1 if previous else 1
        name = f'round-{index:04d}'
        old_ids = {m['motif_id'] for m in previous_library['motifs']} if previous_library else set()
        new_ids = {m['motif_id'] for m in library['motifs']}
        pending = store / ('.pending-' + uuid4().hex); pending.mkdir(mode=0o700)
        try:
            save(pending / 'library.json', library)
            record = {'schema_version': 1, 'round_index': index,
                      'created_at': datetime.now(timezone.utc).isoformat(),
                      'parent_round': previous_path.name if previous_path else None,
                      'parent_round_digest': previous['round_digest'] if previous else None,
                      'parent_library_digest': previous['library_digest'] if previous else None,
                      'library_digest': library['manifest_digest'], 'library_sha256': sha(pending / 'library.json'),
                      'training': training, 'validation': validation,
                      'reserved_validation': list({r['path']: r for r in reserved + validation}.values()),
                      'new_training_sessions': [r['session_id'] for r in fresh],
                      'added_motifs': sorted(new_ids - old_ids), 'removed_motifs': sorted(old_ids - new_ids),
                      'compiler_sha256': sha(Path(__file__).with_name('parameter_motif_compiler.py')),
                      'learning_code_sha256': sha(__file__),
                      'scope': 'native_parameter_probe_sequential_learning',
                      'independent_task_certification': False, 'actual_model_requests_skipped': 0,
                      'production_activation': False}
            record['round_digest'] = digest(record)
            save(pending / 'round.json', record)
            target = store / name
            if target.exists(): raise ValueError('round already exists; preserve old evidence')
            pending.rename(target)
            pointer = store / ('.latest-' + uuid4().hex)
            save(pointer, {'round': name, 'round_digest': record['round_digest']})
            pointer.replace(store / 'latest.json')
            return target, record, library
        finally:
            if pending.exists(): shutil.rmtree(pending)
